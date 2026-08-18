"""
Not a real unit test framework — a quick manual verification script.
Builds a synthetic dataset (no network needed) shaped like what data_fetch.py
would produce, then runs it through scoring + report to sanity-check the logic
end-to-end without hitting Yahoo Finance.

Run with: python3 -m tests.test_pipeline_synthetic   (from the trading-bot/ root)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src import report, scoring

# Hand-built synthetic universe covering a few scenarios:
# - AAA: expensive, no drawdown, low upside -> should score low
# - CHEAP1: cheap vs sector, big drawdown, still positive analyst upside,
#           NOT sitting at its low (recovering) -> should be a top diamond
# - FALLINGKNIFE: big drawdown but sitting right at 52wk low -> momentum penalty should hurt it
# - SOLID: not cheap, not expensive, strong analyst upside, no drawdown -> decent conviction, not a diamond
# - BROKEN: negative earnings -> should be filtered out entirely
# - THIN: only 1 analyst -> should be filtered out (coverage requirement)
rows = [
    dict(ticker="AAA", shortName="Aaa Corp", sector="Tech", marketCap=50e9,
         trailingPE=45, forwardPE=40, trailingEps=2.0, currentPrice=200,
         regularMarketPrice=200, fiftyTwoWeekHigh=205, fiftyTwoWeekLow=150,
         targetMeanPrice=205, numberOfAnalystOpinions=10, recommendationMean=2.5),
    dict(ticker="CHEAP1", shortName="Cheap One Inc", sector="Tech", marketCap=20e9,
         trailingPE=12, forwardPE=11, trailingEps=5.0, currentPrice=60,
         regularMarketPrice=60, fiftyTwoWeekHigh=100, fiftyTwoWeekLow=50,
         targetMeanPrice=85, numberOfAnalystOpinions=15, recommendationMean=2.0),
    dict(ticker="FALLINGKNIFE", shortName="Falling Knife Co", sector="Tech", marketCap=15e9,
         trailingPE=13, forwardPE=12, trailingEps=3.0, currentPrice=51,
         regularMarketPrice=51, fiftyTwoWeekHigh=100, fiftyTwoWeekLow=50,
         targetMeanPrice=80, numberOfAnalystOpinions=8, recommendationMean=2.8),
    dict(ticker="SOLID", shortName="Solid Industries", sector="Industrials", marketCap=30e9,
         trailingPE=22, forwardPE=20, trailingEps=4.0, currentPrice=88,
         regularMarketPrice=88, fiftyTwoWeekHigh=95, fiftyTwoWeekLow=70,
         targetMeanPrice=110, numberOfAnalystOpinions=12, recommendationMean=1.8),
    dict(ticker="BROKEN", shortName="Broken Ltd", sector="Energy", marketCap=5e9,
         trailingPE=None, forwardPE=None, trailingEps=-1.5, currentPrice=10,
         regularMarketPrice=10, fiftyTwoWeekHigh=25, fiftyTwoWeekLow=8,
         targetMeanPrice=15, numberOfAnalystOpinions=5, recommendationMean=3.0),
    dict(ticker="THIN", shortName="Thin Coverage Co", sector="Industrials", marketCap=10e9,
         trailingPE=15, forwardPE=14, trailingEps=2.0, currentPrice=40,
         regularMarketPrice=40, fiftyTwoWeekHigh=60, fiftyTwoWeekLow=35,
         targetMeanPrice=55, numberOfAnalystOpinions=1, recommendationMean=2.0),
]
df = pd.DataFrame(rows)

print("=== Input rows ===")
print(df[["ticker", "trailingPE", "currentPrice", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "numberOfAnalystOpinions"]])
print()

scored = scoring.score_universe(df)

print("\n=== Scored output ===")
print(scored[["ticker", "conviction_score", "valuation_discount", "analyst_upside",
              "drawdown", "momentum_score", "diamond_in_rough"]].to_string(index=False))

assert "BROKEN" not in scored["ticker"].values, "FAIL: BROKEN (negative earnings) should have been filtered out"
assert "THIN" not in scored["ticker"].values, "FAIL: THIN (low analyst coverage) should have been filtered out"
assert scored.loc[scored["ticker"] == "CHEAP1", "diamond_in_rough"].iloc[0] == True, \
    "FAIL: CHEAP1 should be flagged as a diamond in the rough"
assert scored.loc[scored["ticker"] == "AAA", "conviction_score"].iloc[0] < \
       scored.loc[scored["ticker"] == "CHEAP1", "conviction_score"].iloc[0], \
    "FAIL: AAA (expensive, no upside) should score lower than CHEAP1"
cheap1_score = scored.loc[scored["ticker"] == "CHEAP1", "conviction_score"].iloc[0]
knife_score = scored.loc[scored["ticker"] == "FALLINGKNIFE", "conviction_score"].iloc[0]
assert cheap1_score > knife_score, (
    f"FAIL: CHEAP1 ({cheap1_score}) should outscore FALLINGKNIFE ({knife_score}) "
    f"since it has stabilized off its low and the knife hasn't"
)

print("\nAll assertions passed.")

md_path, csv_path = report.build_report(scored)
print(f"\nSynthetic report written to: {md_path}")
print("\n--- Report contents ---\n")
print(md_path.read_text())
