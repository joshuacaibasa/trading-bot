"""
Pulls the S&P 500 universe and per-ticker fundamentals/analyst data via yfinance,
with a simple on-disk cache so repeated runs don't hammer Yahoo Finance.
"""
import json
import time
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

from . import config, sec_utils
from .signals import insider as insider_signals

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_FILE = DATA_DIR / "ticker_cache.json"
INSIDER_CACHE_FILE = DATA_DIR / "insider_cache.json"
CONGRESS_SIGNAL_FILE = DATA_DIR / "congress_signal.json"


def get_sp500_universe() -> list[str]:
    """Return the current list of S&P 500 tickers, scraped from Wikipedia.

    Falls back to data/universe_override.csv (a single "Symbol" column) if the
    Wikipedia scrape fails for any reason.
    """
    try:
        # pandas' read_html makes a bare urllib request with no User-Agent,
        # which Wikipedia now 403s (especially from GitHub Actions IPs). Fetch
        # the HTML ourselves with a browser-like UA, then hand the text to
        # read_html instead of the URL.
        resp = requests.get(
            config.SP500_WIKI_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; trading-bot research script)"},
            timeout=15,
        )
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text))
        df = tables[0]
        tickers = df["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()
        if len(tickers) < 400:
            raise ValueError(f"Only found {len(tickers)} tickers, expected ~500 — page format may have changed.")
        return sorted(set(tickers))
    except Exception as e:
        override = DATA_DIR / "universe_override.csv"
        if override.exists():
            print(f"[data_fetch] Wikipedia scrape failed ({e}); using {override}")
            return sorted(set(pd.read_csv(override)["Symbol"].astype(str).tolist()))
        raise RuntimeError(
            f"Could not fetch S&P 500 universe from Wikipedia ({e}) and no "
            f"data/universe_override.csv fallback exists. Create one manually with a "
            f"'Symbol' column of tickers to work around this."
        ) from e


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2, default=str))


def _is_fresh(entry: dict) -> bool:
    fetched_at = entry.get("_fetched_at")
    if not fetched_at:
        return False
    age = datetime.now() - datetime.fromisoformat(fetched_at)
    return age < timedelta(days=config.CACHE_MAX_AGE_DAYS)


FIELDS = [
    "sector", "marketCap", "trailingPE", "forwardPE", "trailingEps",
    "currentPrice", "regularMarketPrice", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
    "targetMeanPrice", "numberOfAnalystOpinions", "recommendationMean",
    "shortName", "industry",
]


def fetch_ticker_data(ticker: str) -> dict | None:
    """Fetch the fields we care about for one ticker. Returns None on failure."""
    try:
        info = yf.Ticker(ticker).info
        if not info or "regularMarketPrice" not in info and "currentPrice" not in info:
            return None
        row = {f: info.get(f) for f in FIELDS}
        row["ticker"] = ticker
        return row
    except Exception as e:
        print(f"[data_fetch] Failed to fetch {ticker}: {e}")
        return None


def fetch_universe_data(tickers: list[str], refresh: bool = False) -> pd.DataFrame:
    """Fetch data for every ticker, using the cache where possible."""
    cache = _load_cache()
    rows = []
    total = len(tickers)
    for i, ticker in enumerate(tickers, 1):
        entry = cache.get(ticker)
        if not refresh and entry and _is_fresh(entry):
            rows.append(entry["data"])
            continue

        row = fetch_ticker_data(ticker)
        time.sleep(config.REQUEST_DELAY_SECONDS)
        if row is None:
            continue
        cache[ticker] = {"_fetched_at": datetime.now().isoformat(), "data": row}
        rows.append(row)

        if i % 25 == 0 or i == total:
            print(f"[data_fetch] {i}/{total} tickers processed...")
            _save_cache(cache)  # save incrementally in case of interruption

    _save_cache(cache)
    return pd.DataFrame(rows)


def fetch_insider_signals(tickers: list[str], refresh: bool = False) -> pd.DataFrame:
    """Fetch the insider-trading signal for each ticker (see signals/insider.py),
    using its own daily cache. Requires config.SEC_USER_AGENT to be set.

    Returns a DataFrame with columns: ticker, insider_buy_value, insider_sell_value,
    insider_net_value, insider_num_buyers, insider_num_sellers.
    """
    cik_map = sec_utils.load_ticker_cik_map()

    cache = {}
    if INSIDER_CACHE_FILE.exists():
        try:
            cache = json.loads(INSIDER_CACHE_FILE.read_text())
        except json.JSONDecodeError:
            cache = {}

    rows = []
    total = len(tickers)
    for i, ticker in enumerate(tickers, 1):
        entry = cache.get(ticker)
        if not refresh and entry and _is_fresh(entry):
            rows.append({"ticker": ticker, **entry["data"]})
            continue

        cik = cik_map.get(ticker.upper())
        signal = insider_signals.get_insider_signal(ticker, cik)
        cache[ticker] = {"_fetched_at": datetime.now().isoformat(), "data": signal}
        rows.append({"ticker": ticker, **signal})

        if i % 25 == 0 or i == total:
            print(f"[data_fetch] insider signals: {i}/{total} tickers processed...")
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            INSIDER_CACHE_FILE.write_text(json.dumps(cache, indent=2, default=str))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INSIDER_CACHE_FILE.write_text(json.dumps(cache, indent=2, default=str))
    return pd.DataFrame(rows)


def load_congress_signals() -> pd.DataFrame:
    """Load the precomputed congress-trading signal table (built by
    scripts/refresh_congress_trades.py). Returns an empty-but-correctly-shaped
    DataFrame if it hasn't been built yet, so downstream merges don't break."""
    empty = pd.DataFrame(columns=["ticker", "congress_buys", "congress_sells",
                                   "congress_buyers", "congress_sellers"])
    if not CONGRESS_SIGNAL_FILE.exists():
        print(f"[data_fetch] {CONGRESS_SIGNAL_FILE} not found — run "
              f"scripts/refresh_congress_trades.py first. Continuing without this signal.")
        return empty

    table = json.loads(CONGRESS_SIGNAL_FILE.read_text())
    rows = []
    for ticker, entry in table.items():
        rows.append({
            "ticker": ticker,
            "congress_buys": entry.get("buys", 0),
            "congress_sells": entry.get("sells", 0),
            "congress_buyers": len(entry.get("buyers", [])),
            "congress_sellers": len(entry.get("sellers", [])),
        })
    return pd.DataFrame(rows) if rows else empty
