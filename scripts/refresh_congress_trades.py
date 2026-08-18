"""
Refresh the congressional trading signal cache. Meant to run daily (new PTR
filings trickle in continuously, unlike 13F which is quarterly) — GitHub
Actions runs this before src/main.py each day (see .github/workflows/daily-screen.yml).

Usage: python3 -m scripts.refresh_congress_trades
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.signals import congress

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "congress_signal.json"


def main():
    table = congress.build_congress_signal_table()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(table, indent=2))
    print(f"[refresh_congress_trades] Wrote signals for {len(table)} tickers to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
