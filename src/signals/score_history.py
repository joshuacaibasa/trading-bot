"""
Tracks each stock's conviction_score over time using a small JSON snapshot
file committed to git daily (data/score_history.json) — since each GitHub
Actions run starts from a fresh checkout, this is the only way today's run
can see yesterday's numbers.

score_trend compares two already-saved historical snapshots (the most recent
one vs. one roughly config.SCORE_TREND_LOOKBACK_DAYS before that) rather than
today's still-being-computed score, so there's no circular dependency on the
score this module is helping to produce. Today's final score is only saved
for future runs after scoring is complete (see save_snapshot in main.py).
"""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from .. import config

HISTORY_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "score_history.json"


def load_history() -> dict:
    if not HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(HISTORY_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def _closest_date_at_or_before(history: dict, target: date) -> str | None:
    candidates = [d for d in history if datetime.strptime(d, "%Y-%m-%d").date() <= target]
    return max(candidates) if candidates else None


def compute_score_trend(history: dict) -> dict:
    """Returns {ticker: recent_score - past_score} for tickers with both a
    recent and an older (~SCORE_TREND_LOOKBACK_DAYS earlier) saved snapshot.
    Tickers without enough history simply aren't included — callers should
    treat a missing key as "no trend data yet" (neutral)."""
    if not history:
        return {}

    most_recent_date = max(history)
    recent_scores = history[most_recent_date]

    target = datetime.strptime(most_recent_date, "%Y-%m-%d").date() - timedelta(days=config.SCORE_TREND_LOOKBACK_DAYS)
    past_date = _closest_date_at_or_before(history, target)
    if not past_date or past_date == most_recent_date:
        return {}
    past_scores = history[past_date]

    return {
        ticker: recent_scores[ticker] - past_scores[ticker]
        for ticker in recent_scores
        if ticker in past_scores
    }


def save_snapshot(scored_df: pd.DataFrame, as_of: date | None = None) -> None:
    """Append today's ticker -> conviction_score into history, prune entries
    older than SCORE_TREND_MAX_HISTORY_DAYS, and write back."""
    as_of = as_of or date.today()
    history = load_history()
    history[as_of.isoformat()] = dict(zip(scored_df["ticker"], scored_df["conviction_score"]))

    cutoff = as_of - timedelta(days=config.SCORE_TREND_MAX_HISTORY_DAYS)
    history = {
        d: v for d, v in history.items()
        if datetime.strptime(d, "%Y-%m-%d").date() >= cutoff
    }

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2))
