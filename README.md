# Poker Hand Analyzer

Minimal Python GUI to analyze Ignition hand-history `.txt` files stored in `hand_history/`.

## Features
- Auto-loads all `.txt` files in `hand_history` (use **Refresh** when new files are added).
- Session-level stats and charts (hands, VPIP, PFR, win%, net result, average pot, street depth).
- Top 5 biggest hands in selected file by total pot.
- Step-by-step hand replay with action log, board streets, and a live contribution chart.

## Run
```bash
python main.py
```

## Notes
- Keep adding new `.txt` files to `hand_history/`; no code change needed.
- Parser is tailored for Ignition-style hand history text.
