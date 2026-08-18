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
WEIGHTS = {
    "valuation_discount": 0.25,   # cheaper than sector peers = higher score
    "analyst_upside": 0.25,       # more upside to analyst target = higher score
    "drawdown": 0.15,             # further off 52-week high = higher score (contrarian tilt)
    "momentum_penalty": 0.10,     # penalize stocks in a severe, accelerating downtrend (falling knife guard)
    "insider_signal": 0.10,       # net insider open-market buying vs selling, trailing 90 days
    "congress_signal": 0.05,      # net Senate PTR buying vs selling, trailing window (experimental — see signals/congress.py)
    "institutional_signal": 0.10, # institutional (13F) accumulation vs distribution, quarter-over-quarter
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

# --- Quality filters: stocks failing these are excluded entirely, not just scored low ---
MIN_MARKET_CAP = 2_000_000_000     # $2B+ only, for the pilot (avoid illiquid microcaps)
REQUIRE_POSITIVE_EARNINGS = True   # exclude companies with negative trailing EPS
MIN_ANALYST_COVERAGE = 3           # need at least this many analysts covering it

# --- "Diamond in the rough" flag thresholds ---
DIAMOND_MIN_DRAWDOWN = 0.25        # at least 25% off 52-week high
DIAMOND_MIN_ANALYST_UPSIDE = 0.15  # at least 15% upside to analyst target
DIAMOND_MIN_VALUATION_DISCOUNT = 0.0  # at or below sector median P/E (0 = breakeven, positive = cheaper)

# How many rows to show in the human-readable report
TOP_N_CONVICTION = 20
TOP_N_DIAMONDS = 15
