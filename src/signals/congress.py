"""
Congressional trading signal — scraped from the U.S. Senate's official
Periodic Transaction Report (PTR) search system at efdsearch.senate.gov.

*** THIS MODULE IS THE MOST LIKELY TO NEED LIVE DEBUGGING. ***
There is no official API for this data (that's the whole reason paid
aggregators like QuiverQuant/Capitol Trades exist and charge for it — they've
already done and maintained this exact scraping work). efdsearch.senate.gov
is a Django app that:
  1. Requires accepting a "prohibition on insider trading" agreement (sets a
     cookie) before search results are served.
  2. Serves search results as a DataTables JSON endpoint.
  3. Renders each individual Periodic Transaction Report at a per-filing URL;
     reports filed electronically (the vast majority since ~2012) have an
     HTML table of transactions; older/paper filings are scanned PDFs we
     don't attempt to parse here.

This was written from documented patterns used by open-source Senate-trading
scrapers, but efdsearch.senate.gov's exact markup/endpoints can change without
notice and this was NOT tested against a live connection (this code was
written in a network-restricted sandbox). If it breaks: open browser dev
tools on https://efdsearch.senate.gov/search/, watch the Network tab while
performing a search, and compare the actual request/response shape to what's
below — then fix accordingly (this is a great task to hand to your local
Claude Code, which has live internet access to iterate against the real site).

Only covers the Senate for now — the House uses a separate, PDF-heavy system
(disclosures-clerk.house.gov) that's an even bigger lift to parse reliably.
If this whole approach proves too fragile, QuiverQuant's Hobbyist tier
($30/mo) gives you clean House + Senate data with none of this maintenance.
"""
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from .. import config

BASE = "https://efdsearch.senate.gov"
SEARCH_HOME = f"{BASE}/search/home/"
SEARCH_DATA = f"{BASE}/search/report/data/"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; trading-research-bot/0.1)",
    "Referer": SEARCH_HOME,
}


def _get_session_with_agreement() -> requests.Session:
    """Accept the site's agreement to unlock search access, returning a
    session with the resulting cookies."""
    session = requests.Session()
    session.headers.update(_HEADERS)

    home_resp = session.get(SEARCH_HOME, timeout=15)
    home_resp.raise_for_status()
    soup = BeautifulSoup(home_resp.text, "html.parser")
    csrf_input = soup.find("input", {"name": "csrfmiddlewaretoken"})
    if not csrf_input:
        raise RuntimeError("Could not find CSRF token on efdsearch.senate.gov — page layout may have changed.")
    csrf_token = csrf_input["value"]

    agree_resp = session.post(
        SEARCH_HOME,
        data={"csrfmiddlewaretoken": csrf_token, "prohibition_agreement": "1"},
        headers={**_HEADERS, "X-CSRFToken": csrf_token},
        timeout=15,
    )
    agree_resp.raise_for_status()
    return session


def fetch_recent_ptr_filings(days_back: int = None) -> list[dict]:
    """Return a list of {name, date, report_url} for recent Periodic Transaction
    Reports across all senators. Best-effort — returns [] on any failure."""
    days_back = days_back or config.CONGRESS_LOOKBACK_DAYS
    start_date = (datetime.now() - timedelta(days=days_back)).strftime("%m/%d/%Y")
    end_date = datetime.now().strftime("%m/%d/%Y")

    try:
        session = _get_session_with_agreement()
        csrf_token = session.cookies.get("csrftoken")

        payload = {
            "start": "0",
            "length": "100",
            "report_types": "[11]",   # 11 = Periodic Transaction Report (per common convention)
            "filer_types": "[]",
            "submitted_start_date": start_date,
            "submitted_end_date": end_date,
            "candidate_state": "",
            "senator_state": "",
            "office_id": "",
            "first_name": "",
            "last_name": "",
            "csrfmiddlewaretoken": csrf_token,
        }
        resp = session.post(SEARCH_DATA, data=payload, headers={"X-CSRFToken": csrf_token}, timeout=20)
        resp.raise_for_status()
        rows = resp.json().get("data", [])
    except Exception as e:
        print(f"[congress] Failed to fetch PTR filing list: {e}")
        return []

    filings = []
    for row in rows:
        try:
            # Row shape is a list of HTML-fragment strings (DataTables convention):
            # [first_name, last_name, office, report_type_link_html, date_str]
            name = f"{BeautifulSoup(row[0], 'html.parser').get_text().strip()} " \
                   f"{BeautifulSoup(row[1], 'html.parser').get_text().strip()}"
            link_soup = BeautifulSoup(row[3], "html.parser")
            a_tag = link_soup.find("a")
            if not a_tag or not a_tag.get("href"):
                continue
            report_url = BASE + a_tag["href"]
            date_str = BeautifulSoup(row[4], "html.parser").get_text().strip()
            filings.append({"name": name, "date": date_str, "report_url": report_url})
        except Exception:
            continue  # one malformed row shouldn't kill the whole batch

    return filings


def parse_ptr_transactions(report_url: str) -> list[dict]:
    """Parse an individual PTR's transaction table. Returns [] for PDF-format
    (non-HTML) reports or on any parse failure."""
    try:
        resp = requests.get(report_url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"[congress] Failed to fetch report {report_url}: {e}")
        return []

    if "application/pdf" in resp.headers.get("Content-Type", ""):
        return []  # scanned/paper filing — not handled in v1

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        return []

    transactions = []
    rows = table.find_all("tr")[1:]  # skip header row
    for tr in rows:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) < 5:
            continue
        # Typical PTR table columns: Transaction Date, Owner, Ticker, Asset Name,
        # Asset Type, Transaction Type, Amount Range, Comment — exact column
        # order varies; this is a best-effort heuristic extraction.
        row_text = " | ".join(cells)
        ticker = None
        for cell in cells:
            if cell.isupper() and 1 <= len(cell) <= 5 and cell.isalpha():
                ticker = cell
                break
        txn_type = "Purchase" if "purchase" in row_text.lower() else (
            "Sale" if "sale" in row_text.lower() else None)
        if ticker and txn_type:
            transactions.append({"ticker": ticker, "type": txn_type, "raw_row": cells})

    return transactions


def build_congress_signal_table() -> dict:
    """Full batch: fetch recent filings, parse each, aggregate into
    {TICKER: {"buys": n, "sells": n, "buyers": {names}, "sellers": {names}}}.
    Meant to be run periodically (e.g. daily) via scripts/refresh_congress_trades.py,
    not inline per-ticker (parsing every filing once per run is far cheaper than
    once per ticker)."""
    filings = fetch_recent_ptr_filings()
    print(f"[congress] Found {len(filings)} recent PTR filings.")

    signal_table: dict[str, dict] = {}
    for filing in filings:
        transactions = parse_ptr_transactions(filing["report_url"])
        for t in transactions:
            entry = signal_table.setdefault(t["ticker"], {
                "buys": 0, "sells": 0, "buyers": set(), "sellers": set(),
            })
            if t["type"] == "Purchase":
                entry["buys"] += 1
                entry["buyers"].add(filing["name"])
            elif t["type"] == "Sale":
                entry["sells"] += 1
                entry["sellers"].add(filing["name"])

    # sets aren't JSON-serializable — convert before returning/saving
    for ticker, entry in signal_table.items():
        entry["buyers"] = sorted(entry["buyers"])
        entry["sellers"] = sorted(entry["sellers"])

    return signal_table
