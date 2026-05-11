# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate virtual environment (required before any Python command)
source venv/bin/activate

# Run the daily snapshot (fetches data, sends email, regenerates dashboard)
python financial_snapshot.py

# Start the webhook server locally (live API, web signup, inbound email webhooks)
python webhook_server.py

# Regenerate the public dashboard only
python generate_index.py

# Generate the AI portfolio advisor page
python generate_portfolios.py
python generate_portfolios.py --skip-validation   # skip Yahoo Finance ticker validation
python generate_portfolios.py --out /path/out.html

# Initialize or migrate the SQLite database
python -c "from models import init_db; init_db()"

# Check webhook server health
curl http://localhost:5000/health
curl http://localhost:5000/api/live
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
| `app_secrets.py` | `TEST_MODE`, `TEST_EMAIL` (sensitive runtime flags) |
| `settings.py` | Everything else — imports from the above two |

`settings.py` is imported by `financial_snapshot.py` at startup. It calls `init_db()` as a side effect, so it should not be imported in contexts where a database connection is undesirable.

### Database

`models.py` uses Peewee ORM with SQLite (`db.sqlite3`). Two tables:
- `User` — subscribers (email, name, `active` flag, `format_pref`)
- `Snapshot` — one row per application run with all fetched market values

`init_db()` is idempotent and calls `_migrate_add_columns()` to add any new columns without recreating the table.

### Webhook server

`webhook_server.py` is a Flask app run via Gunicorn in production (see `financial-snapshot-webhook.service`). It serves:
- `GET /api/live` — real-time market data with 60-second in-memory cache
- `POST /subscribe` — web form signup
- `GET /unsubscribe` — confirmation page (intentionally two-step to prevent email security scanners from silently deactivating users)
- `POST /unsubscribe` — processes the confirmed unsubscribe
- `POST /webhook` — AgentMail inbound email events (subscribe/unsubscribe via email)
- `GET /health` — liveness check

The webhook is authenticated via a `?token=WEBHOOK_SECRET` query parameter.

### Market calendar

`financial_snapshot.py` implements its own NYSE holiday calendar (`_nyse_holidays`) and `is_market_open()` check. The main script exits early with code 0 on non-trading days. The live `/api/live` endpoint does not check this — it always fetches data.

### AI features

Two separate AI calls, both using the Anthropic SDK:
1. **Daily briefing** (`generate_market_analysis`) — called in every run, uses `claude-haiku-4-5`, returns JSON with `briefing`, `subject`, and `watch` fields.
2. **Anomaly alert** (`generate_anomaly_alert`) — only called when `detect_anomalies()` finds flagged moves; uses `claude-haiku-4-5`, returns 1–2 sentences.
3. **Portfolio advisor** (`generate_portfolios.py`) — one-off generation using `claude-sonnet-4-6`.

All AI calls are skipped gracefully when `ANTHROPIC_API_KEY` is not set.

### Dashboard generation

`generate_index.py` reads the latest `Snapshot` from SQLite, scrapes financial news RSS feeds and firm insight pages (Fidelity, BlackRock, J.P. Morgan AM, MarketWatch), and writes `html/index.html`. It is called automatically at the end of each `financial_snapshot.py` run. The `html/` directory also stores timestamped snapshot archives (`output_YYYYMMDD_HHMMSS.html`) that are linked from the dashboard.

## Key conventions

- The `invert` field on a `RowData` row means "color this red when the value goes up" — used for yields, VIX, inflation, debt, etc.
- Market-open vs. market-closed state determines which Yahoo Finance tickers are fetched: live indices (`^DJI`, `^GSPC`, etc.) during market hours, futures (`YM=F`, `ES=F`, etc.) otherwise. `render_utils.is_market_closed()` drives this branch in `snapshot_schema.py`.
- The `data` dict accepts both legacy key names (e.g. `"sp500"`, `"dow"`) and canonical names (`"gspc"`, `"dji"`). Anomaly detection and AI analysis code checks both with `or` fallbacks.
