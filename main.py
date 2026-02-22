from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from poker_analyzer import aggregate_stats, biggest_hands, load_sessions, replay_state

HAND_HISTORY_DIR = Path("hand_history")


class PokerAnalyzerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Poker Hand Analyzer")
        self.geometry("1280x800")

        self.sessions = []
        self.current_file_hands = []
        self.current_replay_hand = None
        self.replay_step = 0

        self._build_ui()
        self.refresh_files()

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill=tk.X)

        ttk.Label(top, text="Session file:").pack(side=tk.LEFT)
        self.file_var = tk.StringVar()
        self.file_combo = ttk.Combobox(top, textvariable=self.file_var, state="readonly", width=45)
        self.file_combo.pack(side=tk.LEFT, padx=8)
        self.file_combo.bind("<<ComboboxSelected>>", lambda _: self.on_file_selected())

        ttk.Button(top, text="Refresh", command=self.refresh_files).pack(side=tk.LEFT)

        self.stats_var = tk.StringVar(value="No hands loaded.")
        ttk.Label(self, textvariable=self.stats_var, padding=(10, 5)).pack(fill=tk.X)

        body = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left = ttk.Frame(body)
        body.add(left, weight=1)
        right = ttk.Frame(body)
        body.add(right, weight=2)

        ttk.Label(left, text="Top 5 biggest hands").pack(anchor=tk.W)
        self.hand_list = tk.Listbox(left, height=20)
        self.hand_list.pack(fill=tk.BOTH, expand=True)
        self.hand_list.bind("<<ListboxSelect>>", lambda _: self.on_hand_selected())

        replay_controls = ttk.Frame(left)
        replay_controls.pack(fill=tk.X, pady=8)
        ttk.Button(replay_controls, text="◀ Prev", command=self.prev_step).pack(side=tk.LEFT)
        ttk.Button(replay_controls, text="Next ▶", command=self.next_step).pack(side=tk.LEFT, padx=6)

        self.step_var = tk.StringVar(value="Step: 0")
        ttk.Label(left, textvariable=self.step_var).pack(anchor=tk.W)

        self.action_text = tk.Text(left, height=12, wrap="word")
        self.action_text.pack(fill=tk.BOTH, expand=True)

        self.fig = Figure(figsize=(8, 6), dpi=100)
        self.ax1 = self.fig.add_subplot(211)
        self.ax2 = self.fig.add_subplot(212)
        self.fig.tight_layout(pad=3)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def refresh_files(self) -> None:
        HAND_HISTORY_DIR.mkdir(exist_ok=True)
        self.sessions = load_sessions(HAND_HISTORY_DIR)
        names = [s.path.name for s in self.sessions]
        self.file_combo["values"] = names
        if names:
            if self.file_var.get() not in names:
                self.file_var.set(names[0])
            self.on_file_selected()
        else:
            self.file_var.set("")
            self.stats_var.set("No .txt files found in hand_history.")

    def on_file_selected(self) -> None:
        fname = self.file_var.get()
        selected = next((s for s in self.sessions if s.path.name == fname), None)
        if not selected:
            return

        hands = selected.hands
        self.current_file_hands = hands
        stats = aggregate_stats(hands)
        vpip = (100 * stats.vpip_hands / stats.total_hands) if stats.total_hands else 0
        pfr = (100 * stats.pfr_hands / stats.total_hands) if stats.total_hands else 0
        win_rate = (100 * stats.win_hands / stats.total_hands) if stats.total_hands else 0

        self.stats_var.set(
            f"Hands: {stats.total_hands} | VPIP: {vpip:.1f}% | PFR: {pfr:.1f}% | "
            f"Win hands: {win_rate:.1f}% | Net: ${stats.total_net:.2f} | Avg pot: ${stats.avg_pot:.2f}"
        )

        top_hands = biggest_hands(hands, 5)
        self.hand_list.delete(0, tk.END)
        for h in top_hands:
            self.hand_list.insert(tk.END, f"#{h.hand_id} | Pot ${h.total_pot:.2f} | {h.timestamp}")

        self._draw_summary_charts(stats)
        self.canvas.draw()

    def _draw_summary_charts(self, stats) -> None:
        self.ax1.clear()
        self.ax2.clear()

        labels = ["VPIP", "PFR", "Win"]
        values = [stats.vpip_hands, stats.pfr_hands, stats.win_hands]
        self.ax1.bar(labels, values, color=["#4e79a7", "#f28e2b", "#59a14f"])
        self.ax1.set_title("Hero action stats (count)")

        street_labels = ["Preflop only", "To Flop", "To Turn", "To River"]
        street_values = [
            stats.street_counter.get(0, 0),
            stats.street_counter.get(1, 0),
            stats.street_counter.get(2, 0),
            stats.street_counter.get(3, 0),
        ]
        self.ax2.pie(street_values, labels=street_labels, autopct="%1.1f%%")
        self.ax2.set_title("Street depth distribution")

    def on_hand_selected(self) -> None:
        idxs = self.hand_list.curselection()
        if not idxs:
            return

        top_hands = biggest_hands(self.current_file_hands, 5)
        self.current_replay_hand = top_hands[idxs[0]]
        self.replay_step = 0
        self.render_replay()

    def render_replay(self) -> None:
        hand = self.current_replay_hand
        if hand is None:
            return

        self.step_var.set(f"Step: {self.replay_step}/{len(hand.actions)}")
        shown = hand.actions[: self.replay_step]
        lines = [
            f"Hand #{hand.hand_id}",
            f"Hero cards: {hand.hero_cards or 'Unknown'}",
            f"Total pot: ${hand.total_pot:.2f}",
            "\nBoard:",
        ]
        for street, board_line in hand.board_by_street.items():
            lines.append(f"- {street}: {board_line}")
        lines.append("\nActions:")
        lines.extend(f"{i+1}. {a.line}" for i, a in enumerate(shown))

        self.action_text.delete("1.0", tk.END)
        self.action_text.insert(tk.END, "\n".join(lines))

        pot_state = replay_state(hand, self.replay_step)
        self.ax2.clear()
        if pot_state:
            players = list(pot_state.keys())
            amounts = [pot_state[p] for p in players]
            self.ax2.barh(players, amounts, color="#9c755f")
            self.ax2.set_title("Pot contribution by player at current step")
            self.ax2.set_xlabel("$ contributed")
        else:
            self.ax2.text(0.5, 0.5, "No actions yet", ha="center", va="center")
            self.ax2.set_title("Replay")
        self.canvas.draw()

    def prev_step(self) -> None:
        if self.current_replay_hand is None:
            return
        self.replay_step = max(0, self.replay_step - 1)
        self.render_replay()

    def next_step(self) -> None:
        if self.current_replay_hand is None:
            return
        self.replay_step = min(len(self.current_replay_hand.actions), self.replay_step + 1)
        self.render_replay()


if __name__ == "__main__":
    app = PokerAnalyzerApp()
    app.mainloop()
