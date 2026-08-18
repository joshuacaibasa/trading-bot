# Handoff: continue this project in Claude Code

This file exists so a fresh Claude Code session (running locally, with real
internet access) can pick up exactly where a Claude Cowork cloud session left
off, without Josh having to re-explain everything. If you're Claude Code
reading this: read this whole file first, then `README.md` for full technical
detail — this file is the "what happened and what's next," README.md is the
"how everything works" reference.

**Read this file, then just ask Josh which step to start on (probably Step 2
below) rather than re-planning from scratch.**

## The vision (why this project exists)

Josh wants a stock research/trading tool that independently researches
companies from multiple sources (financial data, news, Reddit, politician
trades, institutional filings) and surfaces **medium-to-long-term,
high-conviction ideas** — specifically:
1. "Diamonds in the rough" — companies with real tailwinds not yet reflected
   in their share price.
2. Good companies that have dropped a lot for reasons that may not reflect
   their long-term fundamentals (a buying opportunity, not a broken company).

**Explicit non-goal (for now):** this does NOT place trades automatically.
It's a research/decision-support tool Josh reviews and acts on manually.
Auto-execution was deliberately deferred — see "Decisions already made" below.

## Decisions already made (don't re-litigate these without checking with Josh)

- **Research/alerts only, no auto-trading.** Chosen explicitly early on —
  automation of the *research*, not the *execution*.
- **Free data sources over paid APIs.** Josh chose the fully-free route
  (SEC EDGAR + Senate eFD scraping) over paying for QuiverQuant's API
  (~$30-75/mo), knowing it's more fragile/approximate. If the free
  congressional-trades scraper (see Step 3 below) proves too unreliable,
  QuiverQuant's Hobbyist tier is the documented fallback — see README's
  "Known rough edges" section.
- **GitHub Actions + GitHub Pages for automation/hosting**, chosen over
  running locally via cron or paying for a VPS — free, no laptop dependency.
- **Public GitHub repo**, chosen knowingly — Josh is aware this means his
  source code AND the committed daily report (actual stock picks/scores)
  are visible to anyone with the repo link. He explicitly chose this over a
  private repo (which would require GitHub Pro, ~$4/mo) or a private-repo +
  free-external-host setup (e.g. Netlify/Vercel). If Josh's risk tolerance on
  this changes, that tradeoff is documented in the chat history, not in this
  repo — ask him rather than assuming.
- **Simple static read-only dashboard to start**, not an interactive app with
  a backend — deliberately scoped small; an interactive version (adjustable
  weights, saved watchlists) was deferred to a later phase.

## What's built and its confidence level

- **Core scoring pipeline (v0.1)** — `src/data_fetch.py`, `src/scoring.py`,
  `src/report.py`, `src/main.py`. **Confirmed working**: Josh ran this for
  real against the full S&P 500 (467 stocks passed filters) before Phase 2
  work started. This is solid.
- **Phase 2 signals** — `src/signals/insider.py` (SEC Form 4),
  `src/signals/institutional.py` (SEC 13F bulk data),
  `src/signals/congress.py` (Senate eFD scrape). Written and unit-tested with
  synthetic data (see `tests/`) to confirm the scoring/merging logic is
  correct, but **never run against live data** — the cloud sandbox this was
  built in turned out to have no general internet access from its shell
  (only Yahoo Finance calls made it through indirectly via the earlier local
  run Josh did himself). Confidence level, highest to lowest:
  - `insider.py` — high confidence. SEC's Form 4 API/XML format is
    well-documented and stable.
  - `institutional.py` — medium confidence. The bulk-data URLs and INFOTABLE
    format are documented, but this hasn't been run live, and the
    name-based ticker matching is inherently approximate by design.
  - `congress.py` — **lowest confidence, flagged explicitly as
    experimental** in its own docstring. Reverse-engineered from documented
    patterns for how efdsearch.senate.gov's search works (CSRF token,
    agreement cookie, DataTables JSON endpoint, per-filing HTML table), but
    literally never connected to the live site. This is the most likely
    thing to need real debugging.
- **Dashboard** (`site/`) — plain HTML/CSS/JS, no build step. Tested with a
  headless browser (Playwright) against synthetic data and confirmed
  rendering correctly (scatter chart, sortable table, tooltips, filters all
  worked). Never tested against real generated data yet.
- **GitHub Actions workflows** (`.github/workflows/`) — written but never
  run, since there's no GitHub repo yet (see Step 2).

## Immediate next steps, in order

1. ✅ **Done** — `src/config.py`'s `SEC_USER_AGENT` is set to Josh's real
   name/email (required by SEC for automated requests).
2. **Push this project to a public GitHub repo.** Not yet done — check first
   with `git status` / `git remote -v` in the project root. Last checked:
   git is installed, but no commits exist yet, no remote is configured, and
   global `git config user.name` / `user.email` are unset (will need to be
   set before the first commit succeeds). Neither GitHub CLI (`gh`) nor
   Homebrew were installed on Josh's Mac as of this handoff — either install
   `gh` (recommend `brew install gh` if he's open to installing Homebrew, or
   the standalone installer from cli.github.com) for the smoothest
   `gh repo create` experience, or use VS Code's built-in "Publish to
   GitHub" button in the Source Control panel, which handles browser-based
   auth without needing a CLI tool or manual personal access token. Confirm
   with Josh which he'd prefer before picking one.
3. **Add the `SEC_USER_AGENT` repo secret** (Settings → Secrets and
   variables → Actions) so the scheduled workflow can authenticate to SEC
   without committing Josh's contact info to the (public) repo.
4. **Set GitHub Pages source to "GitHub Actions"** (Settings → Pages) — NOT
   "Deploy from a branch." The workflow uses
   `actions/upload-pages-artifact` + `actions/deploy-pages`, which requires
   this setting.
5. **Manually trigger the `daily-screen` workflow** (Actions tab → "Daily
   research screen" → "Run workflow") rather than waiting for the schedule,
   and watch it run. Expect the congressional-trades step to possibly fail
   or misbehave (it has `continue-on-error: true` so it won't block the rest
   of the pipeline if so) — that's the known risk area, not a sign something
   else is broken.
6. **Debug `src/signals/congress.py` against the real site.** Open browser
   dev tools on https://efdsearch.senate.gov/search/, perform a real search,
   watch the Network tab, and compare the actual request/response shape
   (endpoint URLs, form field names, JSON structure, per-filing report page
   markup) to what's coded in `fetch_recent_ptr_filings()` and
   `parse_ptr_transactions()`. Fix whatever's drifted. This is exactly the
   kind of live-iteration task Claude Code is well-suited for that the cloud
   session couldn't do.
7. **Validate `insider.py` and `institutional.py` against real data** — run
   `python3 -m src.main` end-to-end (not `--skip-insider`) and
   `python3 -m scripts.refresh_institutional_data` once, and sanity-check a
   few resulting `insider_intensity` / `institutional_flow` values against
   what you can independently verify (e.g. check a known recent insider
   purchase shows up correctly).
8. Once the automation is confirmed working end-to-end and the dashboard is
   live at `https://<username>.github.io/<repo>/`, **Phase 3** is next:
   news sentiment, Reddit chatter, and an LLM-written thesis per stock. Not
   started yet — worth a planning conversation with Josh (possibly back in
   the Cowork session, which has web research tools) before implementation.

## Where to find things

- `README.md` — full technical reference: project layout, setup, how scoring
  works, all "known rough edges."
- `src/config.py` — every tunable weight/threshold, plus `SEC_USER_AGENT`.
- `tests/` — synthetic-data tests proving the scoring/merging logic is
  correct in isolation; useful as a regression check after changing
  `scoring.py`.
- Chat history with the Cowork session has the full reasoning behind each
  decision above, if you need more context than this file captures.
