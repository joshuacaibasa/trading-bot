"""
The scoring "brain." Deliberately simple and explainable (percentile ranks +
weighted sum) rather than a black-box model, so every score can be traced back
to a reason. Tune weights/thresholds in config.py, not here.
"""
import numpy as np
import pandas as pd

from . import config


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["price"] = df["currentPrice"].fillna(df["regularMarketPrice"])
    return df


def apply_quality_filters(df: pd.DataFrame) -> pd.DataFrame:
    df = _clean(df)
    mask = (
        (df["marketCap"].fillna(0) >= config.MIN_MARKET_CAP)
        & df["trailingPE"].notna()
        & (df["trailingPE"] > 0)
        & df["targetMeanPrice"].notna()
        & df["fiftyTwoWeekHigh"].notna()
        & df["fiftyTwoWeekLow"].notna()
        & df["price"].notna()
        & (df["numberOfAnalystOpinions"].fillna(0) >= config.MIN_ANALYST_COVERAGE)
    )
    if config.REQUIRE_POSITIVE_EARNINGS:
        mask &= df["trailingEps"].fillna(-1) > 0
    if "long_term_downtrend" in df.columns:
        # None ("not enough price history to judge") is not treated as a
        # downtrend — only a confirmed persistent decline excludes a stock.
        mask &= df["long_term_downtrend"].fillna(False) != True  # noqa: E712
    excluded = len(df) - mask.sum()
    print(f"[scoring] Quality filters excluded {excluded}/{len(df)} tickers "
          f"({mask.sum()} remain).")
    return df[mask].reset_index(drop=True)


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Sector-relative valuation: compare each stock's trailing P/E to the
    # median P/E of its own sector within this universe.
    sector_median_pe = df.groupby("sector")["trailingPE"].transform("median")
    df["sector_median_pe"] = sector_median_pe
    df["valuation_discount"] = (sector_median_pe - df["trailingPE"]) / sector_median_pe

    # Analyst upside: gap between current price and average analyst target.
    df["analyst_upside"] = (df["targetMeanPrice"] - df["price"]) / df["price"]

    # Drawdown from 52-week high (contrarian signal — bigger is "more interesting").
    df["drawdown"] = (df["fiftyTwoWeekHigh"] - df["price"]) / df["fiftyTwoWeekHigh"]

    # Position within the 52-week range: 0 = sitting at the low, 1 = sitting at the high.
    range_span = (df["fiftyTwoWeekHigh"] - df["fiftyTwoWeekLow"]).replace(0, np.nan)
    df["position_in_range"] = (df["price"] - df["fiftyTwoWeekLow"]) / range_span
    # "momentum_score": reward stocks that have stabilized off their lows, penalize
    # ones sitting right at a fresh 52-week low (possible falling knife).
    df["momentum_score"] = df["position_in_range"]

    # --- "Smart money" signals (Phase 2). Missing/unmatched data defaults to a
    # neutral 0 rather than being dropped, since "no recent activity found" is
    # usually a legitimate, common state (not missing data). ---

    # Insider signal: net insider open-market buying, sized relative to the
    # company's market cap so mega-caps and small-caps are comparable (a $2M
    # insider purchase means very different things at a $5B vs $500B company).
    if "insider_net_value" in df.columns:
        df["insider_intensity"] = (df["insider_net_value"].fillna(0) / df["marketCap"]).fillna(0)
    else:
        df["insider_intensity"] = 0.0

    # Congressional signal: net number of distinct members buying vs. selling.
    # Experimental — see signals/congress.py. Absence of data (module not run,
    # or genuinely no recent trades) both collapse to 0 ("no signal either way").
    if "congress_buyers" in df.columns:
        df["congress_net"] = (df["congress_buyers"].fillna(0) - df["congress_sellers"].fillna(0))
    else:
        df["congress_net"] = 0.0

    # Institutional (13F) signal: quarter-over-quarter % change in aggregate
    # institutional dollar value held, from the free name-matched dataset.
    if "institutional_flow_pct" in df.columns:
        df["institutional_flow"] = df["institutional_flow_pct"].fillna(0)
    else:
        df["institutional_flow"] = 0.0

    # --- Quality/growth/trend signals ---

    # Free cash flow yield: cash generation relative to market cap. A
    # cheapness signal that's harder to accounting-massage than trailing P/E
    # (marketCap is guaranteed positive here — apply_quality_filters runs
    # before compute_features and enforces MIN_MARKET_CAP).
    if "freeCashflow" in df.columns:
        df["fcf_yield"] = (df["freeCashflow"].fillna(0) / df["marketCap"]).fillna(0)
    else:
        df["fcf_yield"] = 0.0

    # Return on equity: separates "actually a good business, temporarily
    # cheap" from "cheap because it's mediocre." No clipping of extreme
    # values (e.g. heavy-buyback companies with unusually high ROE) — since
    # everything downstream uses percentile rank, only relative order
    # matters, not magnitude.
    if "returnOnEquity" in df.columns:
        df["roe"] = df["returnOnEquity"].fillna(0)
    else:
        df["roe"] = 0.0

    # Growth: trailing year-over-year revenue growth. Revenue growth is used
    # over earnings growth since it's less prone to one-off accounting noise
    # (buybacks, tax changes, write-offs).
    if "revenueGrowth" in df.columns:
        df["growth"] = df["revenueGrowth"].fillna(0)
    else:
        df["growth"] = 0.0

    # Score trend: is this stock's conviction score rising or falling
    # recently (see signals/score_history.py). Absent for tickers without
    # enough saved history yet (including every ticker on the very first
    # run) — that collapses to a neutral 0, same as the other signals above.
    if "score_trend" in df.columns:
        df["score_trend"] = df["score_trend"].fillna(0)
    else:
        df["score_trend"] = 0.0

    return df


def compute_conviction_scores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    feature_to_weight_key = {
        "valuation_discount": "valuation_discount",
        "analyst_upside": "analyst_upside",
        "drawdown": "drawdown",
        "momentum_score": "momentum_penalty",  # see config comment: higher momentum_score = less penalty
        "insider_intensity": "insider_signal",
        "congress_net": "congress_signal",
        "institutional_flow": "institutional_signal",
        "fcf_yield": "fcf_yield",
        "roe": "quality_roe",
        "growth": "growth",
        "score_trend": "score_trend",
    }

    total_weight = sum(config.WEIGHTS.values())
    score = pd.Series(0.0, index=df.index)
    for feature, weight_key in feature_to_weight_key.items():
        pct_rank = df[feature].rank(pct=True)  # 0-1 percentile within this universe
        weight = config.WEIGHTS[weight_key] / total_weight
        score += pct_rank * weight
        df[f"{feature}_percentile"] = (pct_rank * 100).round(1)

    df["conviction_score"] = (score * 100).round(1)
    return df


def flag_diamonds(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["diamond_in_rough"] = (
        (df["drawdown"] >= config.DIAMOND_MIN_DRAWDOWN)
        & (df["analyst_upside"] >= config.DIAMOND_MIN_ANALYST_UPSIDE)
        & (df["valuation_discount"] >= config.DIAMOND_MIN_VALUATION_DISCOUNT)
    )
    # "Smart money confirmation": among diamond candidates, flag the ones where
    # insiders, institutions, or Congress are *also* net buying — i.e. it's not
    # just cheap on paper, someone with real information is putting money in too.
    df["smart_money_aligned"] = (
        df["diamond_in_rough"]
        & ((df["insider_intensity"] > 0) | (df["institutional_flow"] > 0) | (df["congress_net"] > 0))
    )
    return df


def score_universe(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Full pipeline: filter -> feature engineering -> score -> flag."""
    df = apply_quality_filters(raw_df)
    if df.empty:
        raise ValueError("No tickers survived the quality filters — check data_fetch output "
                          "or loosen thresholds in config.py.")
    df = compute_features(df)
    df = compute_conviction_scores(df)
    df = flag_diamonds(df)
    return df.sort_values("conviction_score", ascending=False).reset_index(drop=True)
