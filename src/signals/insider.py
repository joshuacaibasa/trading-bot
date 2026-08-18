"""
Insider trading signal (SEC Form 4), pulled straight from SEC EDGAR — free,
official, reliable. See src/sec_utils.py for the required SEC_USER_AGENT setup.

For each ticker: find its CIK, list recent Form 4 filings, download and parse
the handful of most recent ones, and summarize into a simple net-buying signal
over a trailing window.

This does 1 (submissions list) + up to config.INSIDER_MAX_FILINGS_PER_TICKER
extra HTTP requests PER TICKER, so at ~9 req/sec it's the slowest of the new
signals across a ~500-stock universe. See config.INSIDER_REFRESH behavior in
main.py for how caching mitigates this on daily runs.
"""
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from .. import config, sec_utils

# Transaction codes that represent genuine open-market activity (ignore
# grants/awards/gifts/option exercises, which aren't a "conviction" signal).
BUY_CODES = {"P"}   # open market purchase
SELL_CODES = {"S"}  # open market sale


def _parse_form4_xml(xml_bytes: bytes) -> list[dict]:
    """Extract non-derivative transactions from a Form 4 XML document."""
    transactions = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return transactions

    owner_name = None
    owner_el = root.find(".//reportingOwner/reportingOwnerId/rptOwnerName")
    if owner_el is not None:
        owner_name = owner_el.text

    for txn in root.findall(".//nonDerivativeTransaction"):
        try:
            code = txn.findtext("./transactionCoding/transactionCode")
            date = txn.findtext("./transactionDate/value")
            shares = txn.findtext("./transactionAmounts/transactionShares/value")
            price = txn.findtext("./transactionAmounts/transactionPricePerShare/value")
            acquired_disposed = txn.findtext("./transactionAmounts/transactionAcquiredDisposedCode/value")
            if not (code and date and shares):
                continue
            transactions.append({
                "owner": owner_name,
                "code": code,
                "date": date,
                "shares": float(shares),
                "price": float(price) if price else None,
                "acquired_disposed": acquired_disposed,
            })
        except (ValueError, TypeError):
            continue
    return transactions


def fetch_insider_transactions(ticker: str, cik: int, max_filings: int = None) -> list[dict]:
    """Fetch and parse the most recent Form 4 filings for a ticker."""
    max_filings = max_filings or config.INSIDER_MAX_FILINGS_PER_TICKER
    padded_cik = sec_utils.cik_to_padded(cik)

    try:
        resp = sec_utils.sec_get(f"https://data.sec.gov/submissions/CIK{padded_cik}.json")
    except Exception as e:
        print(f"[insider] Failed to fetch submissions for {ticker}: {e}")
        return []

    recent = resp.json().get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accession_numbers = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    form4_indices = [i for i, f in enumerate(forms) if f == "4"][:max_filings]

    all_transactions = []
    for i in form4_indices:
        accession_no_dashes = accession_numbers[i].replace("-", "")
        doc = primary_docs[i]
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_no_dashes}/{doc}"
        try:
            filing_resp = sec_utils.sec_get(url)
        except Exception as e:
            print(f"[insider] Failed to fetch Form 4 doc for {ticker}: {e}")
            continue
        all_transactions.extend(_parse_form4_xml(filing_resp.content))

    return all_transactions


def summarize_insider_signal(transactions: list[dict], window_days: int = None) -> dict:
    """Turn a list of raw transactions into a compact signal dict."""
    window_days = window_days or config.INSIDER_WINDOW_DAYS
    cutoff = datetime.now() - timedelta(days=window_days)

    buy_value = 0.0
    sell_value = 0.0
    buyers = set()
    sellers = set()

    for t in transactions:
        try:
            txn_date = datetime.strptime(t["date"], "%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        if txn_date < cutoff:
            continue

        value = t["shares"] * (t["price"] or 0)
        if t["code"] in BUY_CODES:
            buy_value += value
            buyers.add(t["owner"])
        elif t["code"] in SELL_CODES:
            sell_value += value
            sellers.add(t["owner"])

    return {
        "insider_buy_value": round(buy_value, 2),
        "insider_sell_value": round(sell_value, 2),
        "insider_net_value": round(buy_value - sell_value, 2),
        "insider_num_buyers": len(buyers),
        "insider_num_sellers": len(sellers),
    }


def get_insider_signal(ticker: str, cik: int | None) -> dict:
    """Full pipeline for one ticker. Returns a neutral/empty signal on any failure
    so a single bad ticker never crashes the overall run."""
    empty = {
        "insider_buy_value": 0.0, "insider_sell_value": 0.0, "insider_net_value": 0.0,
        "insider_num_buyers": 0, "insider_num_sellers": 0,
    }
    if not cik:
        return empty
    try:
        transactions = fetch_insider_transactions(ticker, cik)
        return summarize_insider_signal(transactions)
    except Exception as e:
        print(f"[insider] Unexpected failure for {ticker}: {e}")
        return empty
