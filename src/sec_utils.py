"""
Shared helpers for talking to SEC EDGAR (data.sec.gov / www.sec.gov).

SEC requires every automated requester to identify itself with a descriptive
User-Agent header containing real contact info, and asks that you stay under
10 requests/second. See: https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data

IMPORTANT: fill in config.SEC_USER_AGENT with your own name + email before
running anything in this file — SEC will block/rate-limit generic or missing
User-Agents. We don't hardcode an email here on purpose; put your own in
config.py.
"""
import json
import os
import time
from pathlib import Path

import requests

from . import config

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TICKER_CIK_CACHE = DATA_DIR / "ticker_cik_map.json"

_last_request_time = [0.0]
_MIN_INTERVAL = 0.11  # ~9 req/sec, a hair under SEC's 10/sec limit


def _headers() -> dict:
    # Environment variable wins (used by GitHub Actions via a repo secret, so
    # your contact info never has to be committed to the repo). Falls back to
    # config.py for local runs.
    ua = os.environ.get("SEC_USER_AGENT", "").strip() or getattr(config, "SEC_USER_AGENT", "").strip()
    if not ua or "you@example.com" in ua.lower() or "your name" in ua.lower():
        raise RuntimeError(
            "No SEC_USER_AGENT set. SEC requires a real contact string like "
            "'Josh Caibasa yourname@example.com'. Either edit config.SEC_USER_AGENT "
            "for local runs, or set the SEC_USER_AGENT repo secret for GitHub Actions."
        )
    return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}


def sec_get(url: str, **kwargs) -> requests.Response:
    """GET a SEC URL with the required headers and basic rate limiting."""
    elapsed = time.time() - _last_request_time[0]
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    resp = requests.get(url, headers=_headers(), timeout=15, **kwargs)
    _last_request_time[0] = time.time()
    resp.raise_for_status()
    return resp


def load_ticker_cik_map(refresh: bool = False) -> dict:
    """Return {TICKER: CIK-as-int}. Cached locally since this file only changes
    occasionally (SEC publishes it fresh regularly, but tickers are stable
    day-to-day)."""
    if not refresh and TICKER_CIK_CACHE.exists():
        return json.loads(TICKER_CIK_CACHE.read_text())

    resp = sec_get("https://www.sec.gov/files/company_tickers.json")
    raw = resp.json()  # {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    mapping = {entry["ticker"].upper(): entry["cik_str"] for entry in raw.values()}

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TICKER_CIK_CACHE.write_text(json.dumps(mapping))
    return mapping


def cik_to_padded(cik: int) -> str:
    return str(cik).zfill(10)
