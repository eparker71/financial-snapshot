# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate virtual environment (required before any Python command)
source venv/bin/activate

# Run the daily snapshot (fetches data, sends email, regenerates dashboard)
python financial_snapshot.py

# Daily entry point for cron: send snapshot, then publish html/ to GitHub Pages
./run_daily.sh

# Publish html/ to the gh-pages branch only
./publish_pages.sh

# Regenerate the public dashboard only
python generate_index.py

# Generate the AI portfolio advisor page
python generate_portfolios.py
python generate_portfolios.py --skip-validation   # skip Yahoo Finance ticker validation
python generate_portfolios.py --out /path/out.html

# Initialize or migrate the SQLite database
python -c "from models import init_db; init_db()"
```

## Architecture

### Data flow

`financial_snapshot.py` is the orchestrator. It calls each API module, merges the results into a single `data` dict, then passes that dict to `html_builder.py` and `plain_text_builder.py` to render the email.

Most market values in `data` are stored as `(price, change, pct_change)` tuples keyed by ticker symbol (e.g. `data["gspc"] = (5300.0, -12.5, -0.23)`). Crypto is an exception — `btc_price` and `btc_change_pct` are flat keys.

### Shared schema layer

`snapshot_schema.py` is the single source of truth for how market data is presented. It converts the raw `data` dict into a list of `SectionData` objects (each with a title and list of `RowData` rows). Both `html_builder.py` and `plain_text_builder.py` consume these sections. When adding a new data field or display row, `snapshot_schema.py` is almost always the right place to edit.

`render_utils.py` holds formatting helpers (`fmt_change`, `fmt_price`, `fmt_pct_change`) used by the schema and both renderers.

### Configuration layers (three-tier)

| File | Contains |
|------|----------|
| `.env` | API keys (never committed) |
| `app_secrets.py` | `TEST_MODE`, `TEST_EMAIL` (sensitive runtime flags). `TEST_MODE` is derived from the `ENV` env var: `PROD` sends to all active users, anything else (default `DEV`) sends only to `TEST_EMAIL`. `run_daily.sh` exports `ENV=PROD` |
| `settings.py` | Everything else — imports from the above two |

`settings.py` is imported by `financial_snapshot.py` at startup. It calls `init_db()` as a side effect, so it should not be imported in contexts where a database connection is undesirable.

### Database

`models.py` uses Peewee ORM with SQLite (`db.sqlite3`). Two tables:
- `User` — subscribers (email, name, `active` flag, `format_pref`)
- `Snapshot` — one row per application run with all fetched market values

`init_db()` is idempotent and calls `_migrate_add_columns()` to add any new columns without recreating the table.

### Hosting

Everything runs locally. `run_daily.sh` (cron/launchd) runs `financial_snapshot.py` then `publish_pages.sh`, which copies `html/` into a `gh-pages` git worktree (`.pages/`) and pushes it; GitHub Pages serves it. The custom domain is opt-in: `publish_pages.sh` writes `CNAME` only when `PAGES_CNAME` is set; `run_daily.sh` exports `PAGES_CNAME=mktpulse.online` by default (the Hostinger DNS records must point at GitHub Pages), and `publish_pages.sh` also pushes any unpushed local `gh-pages` commits. If a push is rejected, someone (e.g. the GitHub Pages settings UI) has committed to `gh-pages`; rebase `.pages/` onto `origin/gh-pages` rather than forcing. The dashboard is fully static: there is no live-data API, web signup, or unsubscribe endpoint. Subscribers are managed directly in the SQLite `User` table.

### Market calendar

`financial_snapshot.py` implements its own NYSE holiday calendar (`_nyse_holidays`) and `is_market_open()` check. The main script exits early with code 0 on non-trading days.

### AI features

Three separate AI calls, all using the Anthropic SDK:
1. **Daily briefing** (`generate_market_analysis`) — called in every run, uses `claude-haiku-4-5`, returns JSON with `briefing`, `subject`, and `watch` fields.
2. **Anomaly alert** (`generate_anomaly_alert`) — only called when `detect_anomalies()` finds flagged moves; uses `claude-haiku-4-5`, returns 1–2 sentences.
3. **Portfolio advisor** (`generate_portfolios.py`) — one-off generation using `claude-sonnet-4-6`.

All AI calls are skipped gracefully when `ANTHROPIC_API_KEY` is not set.

### Dashboard generation

`generate_index.py` reads the latest `Snapshot` from SQLite, scrapes financial news RSS feeds and firm insight pages (Fidelity, BlackRock, J.P. Morgan AM, MarketWatch), and writes `html/index.html`. It is called automatically at the end of each `financial_snapshot.py` run. The `html/` directory also stores timestamped snapshot archives (`output_YYYYMMDD_HHMMSS.html`) that are linked from the dashboard.

## Gotchas

- There is no test suite or linter. Verify changes by running `python generate_index.py` (writes `html/index.html`, needs network for the news scrape) or `financial_snapshot.py` with `TEST_MODE` on.
- The repo lives in OneDrive. If git fails with `mmap failed: Operation timed out`, OneDrive has evicted `.git/objects` files to cloud-only placeholders; keep the folder set to "Always Keep on This Device".
- `html/` and `.pages/` are gitignored. `html/` is published only via `publish_pages.sh` (the `gh-pages` branch), never committed to `main`.
- The email recipient list (`EMAIL_TO`) is read from the `User` table when `settings.py` is imported; subscribers are edited directly in SQLite since there is no signup or unsubscribe flow.

## Key conventions

- The `invert` field on a `RowData` row means "color this red when the value goes up" — used for yields, VIX, inflation, debt, etc.
- Market-open vs. market-closed state determines which Yahoo Finance tickers are fetched: live indices (`^DJI`, `^GSPC`, etc.) during market hours, futures (`YM=F`, `ES=F`, etc.) otherwise. `render_utils.is_market_closed()` drives this branch in `snapshot_schema.py`.
- The `data` dict accepts both legacy key names (e.g. `"sp500"`, `"dow"`) and canonical names (`"gspc"`, `"dji"`). Anomaly detection and AI analysis code checks both with `or` fallbacks.
