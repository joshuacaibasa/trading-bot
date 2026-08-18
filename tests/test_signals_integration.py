"""
Manual verification (no network) that the Phase 2 signals (insider,
congress, institutional) merge into scoring correctly — including the case
where a signal is completely missing from the input (simulating "haven't run
that refresh script yet"), which should degrade to neutral, not crash.

Run with: python3 -m tests.test_signals_integration
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src import scoring

rows = [
    # BASE: identical fundamentals to CHEAP1 in the other synthetic test, but
    # with NO smart-money activity at all -> should be a diamond, but NOT smart-money-aligned.
    dict(ticker="BASE", shortName="Base Case Inc", sector="Tech", marketCap=20e9,
         trailingPE=12, forwardPE=11, trailingEps=5.0, currentPrice=60,
         regularMarketPrice=60, fiftyTwoWeekHigh=100, fiftyTwoWeekLow=50,
         targetMeanPrice=85, numberOfAnalystOpinions=15, recommendationMean=2.0,
         insider_net_value=0.0, congress_buyers=0, congress_sellers=0,
         institutional_flow_pct=0.0),
    # CONFIRMED: same setup, but insiders AND institutions are net buying ->
    # should be a diamond AND smart-money-aligned.
    dict(ticker="CONFIRMED", shortName="Confirmed Inc", sector="Tech", marketCap=20e9,
         trailingPE=12, forwardPE=11, trailingEps=5.0, currentPrice=60,
         regularMarketPrice=60, fiftyTwoWeekHigh=100, fiftyTwoWeekLow=50,
         targetMeanPrice=85, numberOfAnalystOpinions=15, recommendationMean=2.0,
         insider_net_value=5_000_000.0, congress_buyers=2, congress_sellers=0,
         institutional_flow_pct=0.08),
    # DISTRIBUTED: not a diamond (too close to highs), but insiders are dumping —
    # should score lower on the insider dimension than BASE/CONFIRMED.
    dict(ticker="DISTRIBUTED", shortName="Distributed Inc", sector="Tech", marketCap=20e9,
         trailingPE=25, forwardPE=24, trailingEps=3.0, currentPrice=95,
         regularMarketPrice=95, fiftyTwoWeekHigh=100, fiftyTwoWeekLow=60,
         targetMeanPrice=100, numberOfAnalystOpinions=10, recommendationMean=2.5,
         insider_net_value=-8_000_000.0, congress_buyers=0, congress_sellers=1,
         institutional_flow_pct=-0.05),
]
df_with_signals = pd.DataFrame(rows)

print("=== With Phase 2 signals present ===")
scored = scoring.score_universe(df_with_signals)
print(scored[["ticker", "conviction_score", "diamond_in_rough", "smart_money_aligned",
              "insider_intensity", "congress_net", "institutional_flow"]].to_string(index=False))

assert scored.loc[scored["ticker"] == "BASE", "diamond_in_rough"].iloc[0] == True
assert scored.loc[scored["ticker"] == "BASE", "smart_money_aligned"].iloc[0] == False, \
    "FAIL: BASE has zero smart-money activity, should NOT be smart_money_aligned"
assert scored.loc[scored["ticker"] == "CONFIRMED", "smart_money_aligned"].iloc[0] == True, \
    "FAIL: CONFIRMED has insider+institutional buying, should be smart_money_aligned"
confirmed_score = scored.loc[scored["ticker"] == "CONFIRMED", "conviction_score"].iloc[0]
base_score = scored.loc[scored["ticker"] == "BASE", "conviction_score"].iloc[0]
assert confirmed_score > base_score, \
    f"FAIL: CONFIRMED ({confirmed_score}) should outscore BASE ({base_score}) due to smart-money signals"
print("\nAssertions passed for signals-present case.\n")

print("=== Without Phase 2 signal columns at all (simulates scripts not yet run) ===")
df_without_signals = pd.DataFrame(rows)[[
    "ticker", "shortName", "sector", "marketCap", "trailingPE", "forwardPE", "trailingEps",
    "currentPrice", "regularMarketPrice", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
    "targetMeanPrice", "numberOfAnalystOpinions", "recommendationMean",
]]
scored_no_signals = scoring.score_universe(df_without_signals)
print(scored_no_signals[["ticker", "conviction_score", "diamond_in_rough", "smart_money_aligned"]].to_string(index=False))
assert not scored_no_signals["smart_money_aligned"].any(), \
    "FAIL: with no signal data at all, nothing should be flagged smart_money_aligned"
print("\nAssertions passed for signals-absent case (graceful degradation confirmed).")
