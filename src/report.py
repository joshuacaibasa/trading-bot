"""
Turns scored results into a CSV (for Excel/Numbers), a readable markdown
report, and a JSON file (data/site/latest.json) that the static dashboard
website reads directly.
"""
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
SITE_DATA_DIR = Path(__file__).resolve().parent.parent / "site" / "data"

DISPLAY_COLS = [
    "ticker", "shortName", "sector", "price", "conviction_score",
    "valuation_discount", "analyst_upside", "drawdown", "diamond_in_rough",
    "smart_money_aligned",
]

# Columns included in the JSON feed the website reads. Keep this in sync with
# what site/app.js expects to render.
JSON_COLS = [
    "ticker", "shortName", "sector", "price", "conviction_score",
    "valuation_discount", "analyst_upside", "drawdown", "momentum_score",
    "insider_intensity", "congress_net", "institutional_flow",
    "diamond_in_rough", "smart_money_aligned",
]


def _fmt_pct(x):
    return f"{x * 100:.1f}%" if pd.notna(x) else "n/a"


def _row_to_bullet(row: pd.Series) -> str:
    smart_money_tag = " 🔥 *smart money aligned*" if row.get("smart_money_aligned") else ""
    return (
        f"- **{row['ticker']}** ({row.get('shortName', '')}) — {row.get('sector', 'Unknown sector')}"
        f"{smart_money_tag}\n"
        f"  Conviction score: {row['conviction_score']}/100 | "
        f"Price: ${row['price']:.2f} | "
        f"Sector-relative valuation: {_fmt_pct(row['valuation_discount'])} "
        f"{'cheaper' if row['valuation_discount'] > 0 else 'more expensive'} than sector median | "
        f"Analyst upside: {_fmt_pct(row['analyst_upside'])} | "
        f"Off 52-week high: {_fmt_pct(row['drawdown'])}"
    )


def build_report(scored_df: pd.DataFrame) -> tuple[Path, Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")

    csv_path = REPORTS_DIR / f"report_{timestamp}.csv"
    scored_df.to_csv(csv_path, index=False)

    top_conviction = scored_df.head(config.TOP_N_CONVICTION)
    diamonds = (
        scored_df[scored_df["diamond_in_rough"]]
        .sort_values("drawdown", ascending=False)
        .head(config.TOP_N_DIAMONDS)
    )

    lines = [
        f"# Trading Research Bot — Pilot Report ({timestamp})",
        "",
        f"Universe scanned: {len(scored_df)} stocks passed quality filters "
        f"(market cap, positive earnings, analyst coverage, no persistent 18mo+ "
        f"downtrend — see config.py).",
        "",
        "This is a research aid, not financial advice. Conviction scores are relative "
        "rankings within this run's universe, not absolute predictions.",
        "",
        "## Top conviction candidates",
        "",
        "Stocks that score well across valuation vs. sector peers, analyst upside, "
        "and (contrarian) distance from their 52-week high, with a stabilization check "
        "so we're not just flagging stocks in freefall.",
        "",
    ]
    for _, row in top_conviction.iterrows():
        lines.append(_row_to_bullet(row))

    lines += [
        "",
        "## Diamond-in-the-rough candidates",
        "",
        f"Stocks at least {config.DIAMOND_MIN_DRAWDOWN*100:.0f}% off their 52-week high, "
        f"still carrying at least {config.DIAMOND_MIN_ANALYST_UPSIDE*100:.0f}% analyst upside, "
        "and priced at or below their sector's median valuation — i.e. potentially good "
        "businesses that got beaten down.",
        "",
    ]
    if diamonds.empty:
        lines.append("*None found in this run — try loosening thresholds in config.py.*")
    else:
        for _, row in diamonds.iterrows():
            lines.append(_row_to_bullet(row))

    n_smart_money = int(scored_df["smart_money_aligned"].sum()) if "smart_money_aligned" in scored_df else 0
    lines += [
        "",
        "## Notes",
        "",
        f"🔥 = \"smart money aligned\": {n_smart_money} of the diamond-in-the-rough candidates above "
        "also have insiders, institutions, or Congress members net *buying* recently — not just "
        "cheap on paper. See README for how each of those signals is sourced and their limitations "
        "(insider trading data is solid/official; institutional 13F data is approximate and "
        "quarterly; congressional trading data is experimental, Senate-only for now, and discounts "
        "purchases where the stock already ran up 30%+ between the trade date and disclosure as "
        "stale/late signals).",
        "",
        "Still not yet incorporated: news sentiment and Reddit chatter (Phase 3) and an LLM-written "
        "thesis per stock (Phase 3). Sanity-check a few names above against what you already know "
        "before trusting the rankings.",
    ]

    md_path = REPORTS_DIR / f"report_{timestamp}.md"
    md_path.write_text("\n".join(lines))

    latest_md = REPORTS_DIR / "latest_report.md"
    latest_csv = REPORTS_DIR / "latest_report.csv"
    latest_md.write_text("\n".join(lines))
    scored_df.to_csv(latest_csv, index=False)

    _write_site_json(scored_df, timestamp)

    return md_path, csv_path


def _write_site_json(scored_df: pd.DataFrame, timestamp: str) -> Path:
    """Write the JSON feed the static dashboard (site/) reads. Always overwrites
    site/data/latest.json; the website has no other way to get fresh data."""
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    cols = [c for c in JSON_COLS if c in scored_df.columns]
    records = json.loads(scored_df[cols].to_json(orient="records"))  # handles NaN -> None cleanly
    payload = {
        "generated_at": timestamp,
        "universe_size": len(scored_df),
        "stocks": records,
    }
    out_path = SITE_DATA_DIR / "latest.json"
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path
