"""
Refresh the institutional (13F) holdings flow cache. Only meaningful to run
after a new quarterly 13F data set is published by SEC (~mid-Feb, mid-May,
mid-Aug, mid-Nov) — running it more often just re-downloads the same data.
See .github/workflows/quarterly-institutional-refresh.yml.

Usage: python3 -m scripts.refresh_institutional_data
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import data_fetch
from src.signals import institutional


def main():
    print("[refresh_institutional_data] Loading current ticker universe...")
    tickers = data_fetch.get_sp500_universe()

    # Use whatever we already have cached from the daily price/fundamentals run
    # (avoids re-fetching ~500 yfinance calls just to get company names).
    raw_df = data_fetch.fetch_universe_data(tickers, refresh=False)
    universe_names = dict(zip(raw_df["ticker"], raw_df["shortName"].fillna(raw_df["ticker"])))

    institutional.build_institutional_flow_table(universe_names)


if __name__ == "__main__":
    main()
