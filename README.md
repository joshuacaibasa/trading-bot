# Trading Research Bot — v0.2

A research/screening tool that scans a stock universe (starting with the S&P 500),
scores each company on an explainable rubric, and surfaces two kinds of ideas:

1. **High-conviction candidates** — reasonably valued, positive analyst sentiment, real fundamentals.
2. **"Diamond in the rough" candidates** — good businesses that have dropped a lot in price
   for reasons that may not reflect their long-term fundamentals (the "great stock, bad price" case),
   now cross-checked against whether insiders, institutions, or Congress members are *also* buying.

This tool does **not** place trades. It produces a ranked report — and now a dashboard website —
for you to review manually. Nothing here is financial advice; sanity-check it yourself.

## What's new in v0.2

- **Insider trading signal** (`src/signals/insider.py`) — pulled directly from SEC EDGAR's Form 4
  filings. Solid, official, free.
- **Institutional (13F) holdings signal** (`src/signals/institutional.py`) — quarter-over-quarter
  change in aggregate institutional ownership, from SEC's free bulk 13F data sets. Approximate
  (matched by company name, not the security-level CUSIP a paid data vendor would use) and
  inherently quarterly — see the module docstring.
- **Congressional trading signal** (`src/signals/congress.py`) — Senate-only, **experimental**.
  There's no official API for this data, so this scrapes efdsearch.senate.gov directly. It was
  written from documented patterns but not tested against a live connection (see "Known rough
  edges" below) — budget some time to debug it with your local Claude Code, which has real
  internet access to iterate against the actual site.
- **`smart_money_aligned` flag** — among diamond-in-the-rough candidates, marks the ones where
  insiders/institutions/Congress are also net buying, not just cheap on paper.
- **Daily automation** via GitHub Actions — runs the whole pipeline on a schedule, no laptop needed.
- **Dashboard website** (`site/`) — a free static site (via GitHub Pages) that reads the daily
  output and gives you a sortable/filterable table plus a conviction-vs-drawdown chart.

## Project layout

```
trading-bot/
├── requirements.txt
├── .github/workflows/
│   ├── daily-screen.yml                    # runs the pipeline + publishes the dashboard, daily
│   └── quarterly-institutional-refresh.yml # refreshes 13F data, quarterly
├── src/
│   ├── config.py          # tunable settings: weights, thresholds, SEC contact info
│   ├── sec_utils.py        # shared SEC EDGAR request helper (rate limiting, headers)
│   ├── data_fetch.py       # pulls price/fundamentals (yfinance) + orchestrates signal fetching
│   ├── scoring.py          # the explainable scoring rubric — this is the "brain"
│   ├── report.py           # turns scored results into CSV + markdown + the dashboard's JSON feed
│   ├── main.py             # orchestrates: fetch -> score -> report (run this daily)
│   └── signals/
│       ├── insider.py       # SEC Form 4 (insider trading)
│       ├── institutional.py # SEC 13F (institutional holdings) — batch/quarterly
│       └── congress.py      # Senate eFD (congressional trades) — experimental
├── scripts/
│   ├── refresh_congress_trades.py      # run daily (via GitHub Actions), or manually anytime
│   └── refresh_institutional_data.py   # run quarterly (via GitHub Actions), or manually anytime
├── site/                    # the dashboard — plain HTML/CSS/JS, no build step, no dependencies
│   ├── index.html, style.css, app.js
│   └── data/latest.json     # written by report.py each run; this is what app.js fetches
├── data/                    # local caches (gitignored except institutional_flows.json)
└── reports/                 # generated reports land here
```

## Setup (on your Mac)

1. `pip install -r requirements.txt` inside your venv (same as before — one new dependency,
   `beautifulsoup4`, got added for the congress/institutional scrapers).
2. **Set your SEC contact info** — SEC requires every automated requester to identify themselves.
   Open `src/config.py` and change `SEC_USER_AGENT = "Your Name you@example.com"` to your own
   name and email. (This only goes to SEC in an HTTP header — it's never committed to a public
   repo if you use the GitHub Actions secret approach below instead.)
3. Run it:
   ```
   python3 -m src.main                # full run: price/fundamentals + insider signals
   python3 -m src.main --skip-insider  # faster iteration, skips the slow SEC insider step
   python3 -m scripts.refresh_congress_trades       # separately, to populate congressional signal
   python3 -m scripts.refresh_institutional_data    # separately, quarterly — this one's slow (downloads ~all US 13F filings)
   ```
4. Preview the dashboard locally: `cd site && python3 -m http.server 8000`, then open
   `http://localhost:8000`. (Opening `index.html` directly by double-clicking won't work —
   browsers block `fetch()` on `file://` paths, so it needs to be served.)

## Setting up daily automation (GitHub Actions + Pages)

1. Create a new GitHub repo and push this project to it (ask your local Claude Code for help
   with `git init` / `git remote add` / `git push` if you haven't done this before).
2. In the repo's **Settings → Secrets and variables → Actions**, add a repository secret named
   `SEC_USER_AGENT` with your name + email (same value as step 2 above) — this is how the
   scheduled workflow authenticates to SEC without your info sitting in the repo itself.
3. In **Settings → Pages**, set **Source** to **GitHub Actions** (not "Deploy from a branch").
4. That's it — `.github/workflows/daily-screen.yml` will run automatically on weekdays and
   publish the dashboard to `https://<your-username>.github.io/<repo-name>/`. You can also
   trigger it manually anytime from the **Actions** tab (**Run workflow** button) instead of
   waiting for the schedule.
5. Separately, `.github/workflows/quarterly-institutional-refresh.yml` runs a few times a year
   to refresh the 13F data (also triggerable manually).

## How the scoring works

For each stock we compute a handful of features, percentile-rank each one within the current
run's universe, and combine them into a weighted `conviction_score` (0-100) — see `config.WEIGHTS`
to change the balance:

- **Valuation discount** — P/E vs. the median P/E of its own sector within the universe.
- **Analyst upside** — gap between current price and the average analyst 12-month target.
- **Drawdown** — how far off its 52-week high (contrarian tilt — bigger is more interesting).
- **Momentum** — position within the 52-week range, so we're not just flagging stocks in freefall.
- **Insider signal** — net insider open-market buying (trailing 90 days), sized relative to market cap.
- **Congressional signal** — net Senate members buying vs. selling recently (experimental).
- **Institutional signal** — quarter-over-quarter change in aggregate institutional ownership.

A **quality filter** excludes companies with negative earnings, thin analyst coverage, or under
$2B market cap before any of this — see `config.py` to change the thresholds.

`diamond_in_rough` flags stocks with a big drawdown + real analyst upside + a sector-relative
discount. `smart_money_aligned` additionally requires insiders, institutions, or Congress to be
net buying too — the highest-conviction subset of the diamond list.

## Known rough edges (be aware before trusting this blindly)

- **Congressional trading data is experimental.** Unlike insider (Form 4) and institutional
  (13F) data, there's no clean government API for this — `signals/congress.py` reverse-engineers
  the Senate's search system, and it may need live debugging (see the big comment at the top of
  that file). It's also Senate-only; the House uses a PDF-heavy system not handled here. If this
  proves too unreliable, QuiverQuant's API (Hobbyist tier, ~$30/mo) gives you clean House +
  Senate data with none of the maintenance — worth revisiting if you outgrow the free approach.
- **Institutional matching is approximate.** It matches by normalized company name, not CUSIP, so
  some tickers won't match and a few could mismatch. Treat `institutional_flow` as directional,
  not precise.
- **This is v0.2.** Still not incorporated: news sentiment, Reddit chatter, and an LLM-written
  thesis per stock — that's next (Phase 3), once you've lived with this version for a bit.
