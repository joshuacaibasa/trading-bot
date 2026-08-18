"""
Entry point: fetch -> score -> report.

Usage:
    python3 -m src.main                  # use cache where fresh
    python3 -m src.main --refresh        # force re-fetch everything (yfinance + insider signals)
    python3 -m src.main --skip-insider   # skip the slow SEC insider-trading step (e.g. for quick iteration)

Before running with insider/institutional signals enabled, set config.SEC_USER_AGENT
to your own name + email (see src/sec_utils.py for why).
"""
import argparse
import sys

import pandas as pd

from . import data_fetch, report, scoring
from .signals import institutional as institutional_signals


def main():
    parser = argparse.ArgumentParser(description="Run the trading research bot pilot screen.")
    parser.add_argument("--refresh", action="store_true", help="Ignore cache, re-fetch all data.")
    parser.add_argument("--skip-insider", action="store_true",
                         help="Skip the SEC insider-trading fetch (fastest way to iterate on scoring/report logic).")
    args = parser.parse_args()

    print("[main] Fetching S&P 500 universe...")
    tickers = data_fetch.get_sp500_universe()
    print(f"[main] {len(tickers)} tickers in universe.")

    print("[main] Fetching per-ticker price/fundamentals data (this can take a few minutes on first run)...")
    raw_df = data_fetch.fetch_universe_data(tickers, refresh=args.refresh)
    print(f"[main] Got data for {len(raw_df)} tickers.")

    if raw_df.empty:
        print("[main] No data fetched — check your internet connection and try again.")
        sys.exit(1)

    if not args.skip_insider:
        print("[main] Fetching insider trading signals (this is the slowest step — "
              "SEC rate-limits to ~9 req/sec)...")
        insider_df = data_fetch.fetch_insider_signals(raw_df["ticker"].tolist(), refresh=args.refresh)
        raw_df = raw_df.merge(insider_df, on="ticker", how="left")
    else:
        print("[main] Skipping insider signals (--skip-insider).")

    print("[main] Loading congressional trading signals (run scripts/refresh_congress_trades.py "
          "to update this)...")
    congress_df = data_fetch.load_congress_signals()
    if not congress_df.empty:
        raw_df = raw_df.merge(congress_df, on="ticker", how="left")

    print("[main] Loading institutional (13F) flow signals (run scripts/refresh_institutional_data.py "
          "to update this — it's quarterly, not daily)...")
    institutional_table = institutional_signals.load_institutional_flow_table()
    if institutional_table:
        inst_df = pd.DataFrame([
            {"ticker": t, "institutional_flow_pct": v["institutional_flow_pct"]}
            for t, v in institutional_table.items()
        ])
        raw_df = raw_df.merge(inst_df, on="ticker", how="left")

    print("[main] Scoring...")
    scored_df = scoring.score_universe(raw_df)

    print("[main] Building report...")
    md_path, csv_path = report.build_report(scored_df)
    print(f"[main] Done. Report: {md_path}")
    print(f"[main] Full data: {csv_path}")


if __name__ == "__main__":
    main()
