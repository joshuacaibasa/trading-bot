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
