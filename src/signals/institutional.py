"""
Institutional holdings signal (Form 13F), from SEC's quarterly bulk structured
data sets. This is inherently a batch/quarterly job, not a daily one — 13F
filings themselves only update quarterly (filed within 45 days of quarter
end), so there's nothing new to gain from checking daily. Run
scripts/refresh_institutional_data.py after each new quarter's data set is
published (roughly mid-Feb, mid-May, mid-Aug, mid-Nov), then main.py's daily
runs just read the cached result.

Because 13F data is keyed by CUSIP (a security identifier), not ticker, and
matching CUSIP -> ticker reliably needs a paid reference dataset, this module
matches on normalized *company name* instead — approximate by nature. Treat
`institutional_flow_pct` as a directional signal ("net accumulation" vs "net
distribution"), not a precise share count.
"""
import io
import json
import re
import zipfile
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .. import sec_utils

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
INSTITUTIONAL_CACHE = DATA_DIR / "institutional_flows.json"
LISTING_URL = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"


def _normalize_name(name) -> str:
    """Strip corporate suffixes/punctuation so 'Apple Inc' and 'APPLE INC.'
    both normalize to 'apple'."""
    if not isinstance(name, str):
        return ""  # a handful of SEC INFOTABLE rows have a genuinely missing issuer name
    name = name.lower()
    name = re.sub(r"[.,]", "", name)
    for suffix in [" inc", " corp", " corporation", " co", " ltd", " plc",
                   " llc", " lp", " holdings", " holding", " the "]:
        name = name.replace(suffix, "")
    return name.strip()


def find_recent_dataset_urls(n: int = 2) -> list[str]:
    """Scrape the SEC 13F data sets listing page for the N most recent ZIP URLs.
    Discovering these from the page (rather than computing filenames from
    today's date) is more robust to the exact quarterly boundary dates SEC uses."""
    resp = sec_utils.sec_get(LISTING_URL)
    soup = BeautifulSoup(resp.text, "html.parser")
    urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "form13f" in href.lower() and href.lower().endswith(".zip"):
            full_url = href if href.startswith("http") else f"https://www.sec.gov{href}"
            urls.append(full_url)
    # Filenames sort naturally-ish by date prefix; de-dupe while preserving order.
    seen = set()
    ordered = [u for u in urls if not (u in seen or seen.add(u))]
    return ordered[:n]


def _download_and_extract_infotable(zip_url: str) -> pd.DataFrame:
    resp = sec_utils.sec_get(zip_url)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        info_files = [n for n in zf.namelist() if "infotable" in n.lower()]
        if not info_files:
            raise RuntimeError(f"No INFOTABLE file found in {zip_url} — SEC may have changed the format.")
        with zf.open(info_files[0]) as f:
            df = pd.read_csv(f, sep="\t", low_memory=False)
    df.columns = [c.upper() for c in df.columns]
    return df


def _aggregate_by_issuer(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["NORM_NAME"] = df["NAMEOFISSUER"].astype(str).apply(_normalize_name)
    agg = df.groupby("NORM_NAME").agg(
        total_value=("VALUE", "sum"),
        total_shares=("SSHPRNAMT", "sum"),
        num_filers=("NAMEOFISSUER", "count"),
    ).reset_index()
    return agg


def build_institutional_flow_table(universe_names: dict[str, str]) -> dict:
    """universe_names: {ticker: company_name} for the stocks we care about
    (pass your fetched universe's shortName column so we only do the expensive
    matching work for tickers we'll actually score).

    Returns {ticker: {"institutional_flow_pct": float, "current_value": float,
    "prior_value": float}}.
    """
    urls = find_recent_dataset_urls(n=2)
    if len(urls) < 2:
        print("[institutional] Could not find two recent 13F data sets to compare — aborting.")
        return {}

    print(f"[institutional] Downloading current quarter: {urls[0]}")
    current_df = _aggregate_by_issuer(_download_and_extract_infotable(urls[0]))
    print(f"[institutional] Downloading prior quarter: {urls[1]}")
    prior_df = _aggregate_by_issuer(_download_and_extract_infotable(urls[1]))

    name_to_norm = {name: _normalize_name(name) for name in universe_names.values()}
    current_lookup = current_df.set_index("NORM_NAME")["total_value"].to_dict()
    prior_lookup = prior_df.set_index("NORM_NAME")["total_value"].to_dict()

    result = {}
    for ticker, company_name in universe_names.items():
        norm = name_to_norm[ticker] if ticker in name_to_norm else _normalize_name(company_name)
        current_value = current_lookup.get(norm)
        prior_value = prior_lookup.get(norm)
        if current_value is None or prior_value in (None, 0):
            continue
        result[ticker] = {
            "institutional_flow_pct": round((current_value - prior_value) / prior_value, 4),
            "current_value": current_value,
            "prior_value": prior_value,
        }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INSTITUTIONAL_CACHE.write_text(json.dumps(result, indent=2))
    print(f"[institutional] Matched {len(result)}/{len(universe_names)} tickers by name. "
          f"Saved to {INSTITUTIONAL_CACHE}")
    return result


def load_institutional_flow_table() -> dict:
    """Read the cached quarterly result (built by scripts/refresh_institutional_data.py).
    Returns {} if it hasn't been built yet."""
    if INSTITUTIONAL_CACHE.exists():
        return json.loads(INSTITUTIONAL_CACHE.read_text())
    return {}
