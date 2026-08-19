"""
Tunable settings for the screener. Change these to reshape what the bot looks for.
"""

# Where to pull the ticker universe from. Wikipedia's S&P 500 table is free and
# updated regularly. If this ever breaks (Wikipedia changes their page layout),
# fall back to a static CSV you maintain yourself in data/universe_override.csv
# with a single column "Symbol".
SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# Politeness delay between Yahoo Finance requests (seconds). Lower = faster but
# more likely to get temporarily rate-limited.
REQUEST_DELAY_SECONDS = 0.3

# How many days before cached data is considered stale and re-fetched.
CACHE_MAX_AGE_DAYS = 1

# --- Scoring weights (must be non-negative; don't need to sum to 1, we normalize) ---
# The original 7 weights below are each scaled to 80% of their original value
# (same relative balance among themselves) to make room for 4 new signals
# without any single old signal silently losing more influence than another.
WEIGHTS = {
    "valuation_discount": 0.19,   # cheaper than sector peers = higher score
    "analyst_upside": 0.19,       # more upside to analyst target = higher score
    "drawdown": 0.11,             # further off 52-week high = higher score (contrarian tilt)
    "momentum_penalty": 0.08,     # penalize stocks in a severe, accelerating downtrend (falling knife guard)
    "insider_signal": 0.08,       # net insider open-market buying vs selling, trailing 90 days
    "congress_signal": 0.04,      # net Senate PTR buying vs selling, trailing window (experimental — see signals/congress.py)
    "institutional_signal": 0.08, # institutional (13F) accumulation vs distribution, quarter-over-quarter
    # --- New quality/growth/trend signals ---
    "fcf_yield": 0.08,     # free cash flow / market cap — a cheapness signal that's harder to accounting-massage than P/E
    "quality_roe": 0.06,   # return on equity — separates "actually a good business" from "just statistically cheap"
    "growth": 0.05,        # trailing year-over-year revenue growth
    "score_trend": 0.04,   # is this stock's conviction score rising or falling recently (see signals/score_history.py)
}

# --- SEC EDGAR access (required for insider + institutional signals) ---
# SEC requires a real contact string in every request's User-Agent. This repo
# is public, so the real value lives in the SEC_USER_AGENT env var (or the
# repo's Actions secret for CI) rather than here — see src/sec_utils.py, which
# reads the env var first and only falls back to this placeholder. For local
# runs, export SEC_USER_AGENT="Your Name you@example.com" before running.
SEC_USER_AGENT = ""

# --- Insider trading signal (src/signals/insider.py) ---
INSIDER_WINDOW_DAYS = 90            # trailing window for "recent" insider activity
INSIDER_MAX_FILINGS_PER_TICKER = 5  # cap Form 4 filings fetched per ticker (keeps daily runtime sane)

# --- Congressional trading signal (src/signals/congress.py) — experimental, Senate only ---
CONGRESS_LOOKBACK_DAYS = 45  # PTRs must be filed within 45 days of the transaction, so this covers "recent" trades

# A politician's trade isn't disclosed until well after it's placed (PTRs are
# filed up to 45 days after the transaction, per CONGRESS_LOOKBACK_DAYS above,
# and often later). If the stock has already rallied a lot between the actual
# trade date and disclosure, that "buy" signal is stale — the move it might
# have predicted has largely already happened by the time we see it. Purchases
# where the stock has already run up at least this much since the trade date
# aren't counted as a fresh buy signal.
CONGRESS_STALE_BUY_THRESHOLD = 0.30  # 30%+ run-up since the trade date = stale

# --- Score trend (src/signals/score_history.py) ---
# Each day's run appends its conviction scores to data/score_history.json
# (committed to git, since each GitHub Actions run starts from a fresh
# checkout). score_trend compares the two most recent already-saved
# snapshots roughly this many days apart — never today's in-progress score
# — so there's no circular dependency on the score being computed right now.
SCORE_TREND_LOOKBACK_DAYS = 7        # ~a week of trading, given weekday-only runs
SCORE_TREND_MAX_HISTORY_DAYS = 30    # bounds how much history the JSON file retains

# --- Quality filters: stocks failing these are excluded entirely, not just scored low ---
MIN_MARKET_CAP = 2_000_000_000     # $2B+ only, for the pilot (avoid illiquid microcaps)
REQUIRE_POSITIVE_EARNINGS = True   # exclude companies with negative trailing EPS
MIN_ANALYST_COVERAGE = 3           # need at least this many analysts covering it

# Exclude stocks in a persistent long-term downtrend — this is a chronic-decliner
# filter, distinct from the "drawdown" contrarian signal above (which rewards
# being off a 52-week high). Fit a linear trend to log(price) over the trailing
# window; a stock only gets excluded if the fit is both declining AND a good
# enough fit (LONG_TERM_DOWNTREND_MIN_R2) to call it a real trend rather than
# sideways noise. A ticker with less price history than the window (e.g. a
# recent IPO) is never excluded by this filter — there's no 18mo trend to judge.
LONG_TERM_DOWNTREND_LOOKBACK_MONTHS = 18   # ~1.5 years
LONG_TERM_DOWNTREND_MIN_R2 = 0.5  # tuned so a genuine V-shaped reversal isn't caught by this filter

# --- "Diamond in the rough" flag thresholds ---
DIAMOND_MIN_DRAWDOWN = 0.25        # at least 25% off 52-week high
DIAMOND_MIN_ANALYST_UPSIDE = 0.15  # at least 15% upside to analyst target
DIAMOND_MIN_VALUATION_DISCOUNT = 0.0  # at or below sector median P/E (0 = breakeven, positive = cheaper)

# How many rows to show in the human-readable report
TOP_N_CONVICTION = 20
TOP_N_DIAMONDS = 15
