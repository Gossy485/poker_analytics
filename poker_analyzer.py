from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from collections import Counter, defaultdict
from typing import Dict, List

HAND_START_RE = re.compile(r"^Ignition Hand #(\d+)")
TOTAL_POT_RE = re.compile(r"Total Pot\(\$(\d+(?:\.\d+)?)\)")
MONEY_RE = re.compile(r"\$(\d+(?:\.\d+)?)")
SEAT_LINE_RE = re.compile(r"^Seat\s+\d+\s*:\s*(.+?)\s*\(")


@dataclass
class Action:
    line: str
    actor: str
    action_type: str
    amount: float = 0.0


@dataclass
class Hand:
    hand_id: str
    timestamp: str
    players: List[str] = field(default_factory=list)
    hero_name: str | None = None
    hero_cards: str | None = None
    board_by_street: Dict[str, str] = field(default_factory=dict)
    actions: List[Action] = field(default_factory=list)
    total_pot: float = 0.0
    hero_result: float = 0.0

    @property
    def street_count(self) -> int:
        return sum(1 for street in ("FLOP", "TURN", "RIVER") if street in self.board_by_street)


@dataclass
class SessionFile:
    path: Path
    hands: List[Hand]


@dataclass
class AggregateStats:
    total_hands: int
    vpip_hands: int
    pfr_hands: int
    win_hands: int
    total_net: float
    avg_pot: float
    street_counter: Counter


def _safe_amount(line: str) -> float:
    m = MONEY_RE.search(line)
    return float(m.group(1)) if m else 0.0


def _parse_action(line: str) -> Action | None:
    if " : " not in line:
        return None
    actor, rest = line.split(" : ", 1)
    actor = actor.strip()
    lower = rest.lower()

    for keyword in ("fold", "check", "call", "bet", "raise", "all-in", "small blind", "big blind", "return uncalled", "hand result"):
        if keyword in lower:
            action_type = keyword
            break
    else:
        action_type = "other"

    amount = _safe_amount(rest)
    return Action(line=line, actor=actor, action_type=action_type, amount=amount)


def parse_hand_text(block: str) -> Hand | None:
    lines = [ln.rstrip() for ln in block.strip().splitlines() if ln.strip()]
    if not lines:
        return None

    start = HAND_START_RE.match(lines[0])
    if not start:
        return None

    hand_id = start.group(1)
    timestamp = lines[0].split(" - ")[-1].strip() if " - " in lines[0] else ""
    hand = Hand(hand_id=hand_id, timestamp=timestamp)

    in_action_region = False
    for line in lines:
        seat_match = SEAT_LINE_RE.match(line)
        if seat_match:
            name = seat_match.group(1).strip()
            hand.players.append(name)
            if "[ME]" in name:
                hand.hero_name = name.replace("[ME]", "").strip()

        if "[ME]" in line and "Card dealt to a spot" in line:
            cards = re.search(r"\[(.+?)\]", line)
            hand.hero_cards = cards.group(1) if cards else None
            if " : " in line:
                hero = line.split(" : ", 1)[0].replace("[ME]", "").strip()
                hand.hero_name = hero

        if line.startswith("*** FLOP ***"):
            hand.board_by_street["FLOP"] = line
            in_action_region = True
        elif line.startswith("*** TURN ***"):
            hand.board_by_street["TURN"] = line
            in_action_region = True
        elif line.startswith("*** RIVER ***"):
            hand.board_by_street["RIVER"] = line
            in_action_region = True
        elif line.startswith("*** SUMMARY ***"):
            in_action_region = False

        pot_match = TOTAL_POT_RE.search(line)
        if pot_match:
            hand.total_pot = float(pot_match.group(1))

        if in_action_region or "*** HOLE CARDS ***" in line:
            action = _parse_action(line)
            if action:
                hand.actions.append(action)

        if "[ME]" in line and "Hand result" in line:
            hand.hero_result = _safe_amount(line)

    return hand


def load_sessions(folder: str | Path) -> List[SessionFile]:
    folder_path = Path(folder)
    if not folder_path.exists():
        return []

    sessions: List[SessionFile] = []
    for path in sorted(folder_path.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        chunks = re.split(r"\n(?=Ignition Hand #)", text)
        hands: List[Hand] = []
        for chunk in chunks:
            hand = parse_hand_text(chunk)
            if hand:
                hands.append(hand)
        sessions.append(SessionFile(path=path, hands=hands))
    return sessions


def _hero_vpip(hand: Hand) -> bool:
    if not hand.hero_name:
        return False
    for a in hand.actions:
        if a.actor.startswith(hand.hero_name) and a.action_type in {"call", "raise", "bet", "all-in"}:
            return True
    return False


def _hero_pfr(hand: Hand) -> bool:
    if not hand.hero_name:
        return False
    for a in hand.actions:
        if a.actor.startswith(hand.hero_name) and a.action_type == "raise":
            return True
    return False


def aggregate_stats(hands: List[Hand]) -> AggregateStats:
    if not hands:
        return AggregateStats(0, 0, 0, 0, 0.0, 0.0, Counter())

    vpip = sum(1 for h in hands if _hero_vpip(h))
    pfr = sum(1 for h in hands if _hero_pfr(h))
    win = sum(1 for h in hands if h.hero_result > 0)
    net = sum(h.hero_result for h in hands)
    avg_pot = sum(h.total_pot for h in hands) / len(hands)
    street_counter = Counter(h.street_count for h in hands)
    return AggregateStats(len(hands), vpip, pfr, win, net, avg_pot, street_counter)


def biggest_hands(hands: List[Hand], top_n: int = 5) -> List[Hand]:
    return sorted(hands, key=lambda h: h.total_pot, reverse=True)[:top_n]


def replay_state(hand: Hand, step: int) -> Dict[str, float]:
    pot_by_player = defaultdict(float)
    for action in hand.actions[: max(0, min(step, len(hand.actions)))]:
        actor = action.actor
        if action.action_type in {"call", "bet", "raise", "all-in", "small blind", "big blind"}:
            pot_by_player[actor] += action.amount
        elif action.action_type == "return uncalled":
            pot_by_player[actor] -= action.amount
        elif action.action_type == "hand result":
            pot_by_player[actor] -= action.amount
    return dict(pot_by_player)
