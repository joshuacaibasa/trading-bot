# Trading Research Bot — Pilot Report (2026-08-18_0634)

Universe scanned: 5 stocks passed quality filters (market cap, positive earnings, analyst coverage — see config.py).

This is a research aid, not financial advice. Conviction scores are relative rankings within this run's universe, not absolute predictions.

## Top conviction candidates

Stocks that score well across valuation vs. sector peers, analyst upside, and (contrarian) distance from their 52-week high, with a stabilization check so we're not just flagging stocks in freefall.

- **NKE** (Nike, Inc.) — Consumer Cyclical
  Conviction score: 71.0/100 | Price: $40.73 | Sector-relative valuation: 0.0% more expensive than sector median | Analyst upside: 24.4% | Off 52-week high: 49.2%
- **NVDA** (NVIDIA Corporation) — Technology
  Conviction score: 70.0/100 | Price: $225.01 | Sector-relative valuation: 0.0% more expensive than sector median | Analyst upside: 34.6% | Off 52-week high: 4.9%
- **UPS** (United Parcel Service, Inc.) — Industrials
  Conviction score: 55.0/100 | Price: $105.27 | Sector-relative valuation: 0.0% more expensive than sector median | Analyst upside: 8.5% | Off 52-week high: 14.0%
- **COST** (Costco Wholesale Corporation) — Consumer Defensive
  Conviction score: 54.0/100 | Price: $953.50 | Sector-relative valuation: 0.0% more expensive than sector median | Analyst upside: 13.0% | Off 52-week high: 13.0%
- **PYPL** (PayPal Holdings, Inc.) — Financial Services
  Conviction score: 50.0/100 | Price: $61.66 | Sector-relative valuation: 0.0% more expensive than sector median | Analyst upside: -4.1% | Off 52-week high: 22.2%

## Diamond-in-the-rough candidates

Stocks at least 25% off their 52-week high, still carrying at least 15% analyst upside, and priced at or below their sector's median valuation — i.e. potentially good businesses that got beaten down.

- **NKE** (Nike, Inc.) — Consumer Cyclical
  Conviction score: 71.0/100 | Price: $40.73 | Sector-relative valuation: 0.0% more expensive than sector median | Analyst upside: 24.4% | Off 52-week high: 49.2%

## Next steps (Phase 2, not yet built)

This pilot only uses price, valuation, and analyst data. It does not yet incorporate news sentiment, Reddit chatter, congressional trading disclosures, or an LLM-written thesis per stock — those come next, once we've confirmed this base layer produces sensible output. Sanity-check a few names above against what you already know before trusting the rankings.