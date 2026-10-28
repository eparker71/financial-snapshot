# Market Pulse

A Python application that fetches live financial market data from multiple APIs, generates an AI-powered morning briefing, sends a daily HTML email snapshot, and publishes a static public dashboard to GitHub Pages.

## Features

- **AI Morning Briefing**: Generates a concise market overview and a "Watch today" callout using Claude Haiku (Anthropic). Displayed in the daily email and at the top of the dashboard. Also generates a dynamic email subject line reflecting the day's most notable move.
- **Anomaly Detection**: Automatically scans each snapshot for notable market moves (large index swings, VIX spikes, yield jumps, crypto volatility, Mag 7 movers, and extreme Fear & Greed readings). On anomaly days, Claude writes a brief contextual alert that appears as an amber banner in the email and dashboard. Costs nothing on quiet days.
- **Cryptocurrency Data**: Bitcoin, Ethereum, Solana, Ripple, and Cardano prices from CoinGecko, Fear & Greed Index from Alternative.me
- **Energy Prices**: US gas and diesel prices from EIA (Energy Information Administration)
- **Economic Indicators**: CPI, unemployment, GDP, mortgage rates, and credit card rates from FRED (Federal Reserve Economic Data)
- **Market Data**: Stocks, commodities, currencies, bonds, and indices from Yahoo Finance — including Magnificent 7 stocks
- **National Debt**: US national debt data from Treasury Fiscal Data API
- **Email Delivery**: Sends formatted HTML emails via AgentMail
- **Public Dashboard**: Auto-generated landing page with latest snapshot data, news headlines, firm insights, and a snapshot archive
- **AI Portfolio Advisor**: Generates a tabbed portfolio recommendations page (`html/portfolios.html`) with four strategies per brokerage (Fidelity, Vanguard, Schwab, E*TRADE, Generic). Uses Claude Sonnet to select brokerage-appropriate funds, then validates every ticker live via Yahoo Finance for expense ratios and AUM.
- **Firm Insights**: Curated articles from Fidelity, BlackRock, J.P. Morgan AM, MarketWatch, and the On Watch podcast
- **Snapshot Storage**: Saves each run's market data to a SQLite database for historical tracking and analytics
- **Test Mode**: Safe testing mode that only sends to test email addresses

## Project Structure

The application has been refactored into modular components for better maintainability:

```
financial_snapshot.py     # Main application orchestrator
├── csv_export.py         # CSV data export functionality
├── html_builder.py       # HTML email rendering
├── plain_text_builder.py # Plain-text email rendering
├── render_utils.py       # Shared formatting utilities
├── snapshot_schema.py    # Centralized snapshot data schema
├── crypto_api.py         # CoinGecko and Alternative.me APIs
├── energy_api.py         # EIA energy prices API
├── fred_api.py           # FRED economic data API
├── treasury_api.py       # US Treasury debt API
├── yahoo_api.py          # Yahoo Finance API
├── settings.py           # Configuration settings
├── models.py             # SQLite models: User and Snapshot (Peewee ORM)
├── generate_index.py     # Generates html/index.html — the public dashboard
├── generate_portfolios.py # Generates html/portfolios.html — AI portfolio advisor
├── .env                  # Secret API keys (never committed)
├── .env.example          # Template showing required keys
├── db.sqlite3            # SQLite database (never committed)
├── logs/                 # Application logs (auto-created)
└── html/                 # HTML output (auto-created)
```

## Setup

### 1. Clone and Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. API Keys

You need to obtain API keys for the following services:

- **AGENTMAIL_API_KEY** - Get from [AgentMail](https://www.agentmail.to/)
- **AGENTMAIL_INBOX_ID** - Your AgentMail inbox ID
- **EIA_API_KEY** - Get from [EIA Open Data](https://www.eia.gov/opendata/register.php)
- **FRED_API_KEY** - Get from [FRED API](https://fred.stlouisfed.org/docs/api/api_key.html)
- **ANTHROPIC_API_KEY** *(optional)* - Get from [Anthropic Console](https://console.anthropic.com/). Powers the AI Morning Briefing. Uses Claude Haiku — cost is a fraction of a cent per run (under $1/month at daily cadence). If not set, the briefing section is silently skipped.

Copy the example env file and fill in your keys:

```bash
cp .env.example .env
chmod 600 .env  # restrict to your user only
```

```bash
# .env
AGENTMAIL_API_KEY=your_agentmail_key
AGENTMAIL_INBOX_ID=your_inbox_id
EIA_API_KEY=your_eia_key
FRED_API_KEY=your_fred_key
ANTHROPIC_API_KEY=your_anthropic_key   # optional — enables AI Morning Briefing
```

The app loads `.env` automatically at startup via `python-dotenv`. The `.env` file is excluded from git. If the keys are already set as environment variables (e.g. in CI or a cron environment), those take priority over `.env`.


### 3. Email Configuration

Edit `app_secrets.py` to configure test mode and recipients:

```python
# app_secrets.py - Sensitive configuration

TEST_MODE = True  # Set to False for production
TEST_EMAIL = "test@example.com"
```

**Note**: When `TEST_MODE = True`, emails are only sent to `TEST_EMAIL`. Always test with this enabled before switching to production.

### 4. Set Up the User Database

The recipient list is stored in a local SQLite database. On a fresh clone, initialise it and add your users:

```bash
# Create the database and table
python -c "from models import init_db; init_db()"

# Add a user
python -c "
from models import User, init_db
init_db()
User.create(first_name='Jane', last_name='Doe', email='jane@example.com', format_pref='HTML')
"
```


## Configuration

### settings.py

Contains non-sensitive configuration:

- `TEST_MODE` / `TEST_EMAIL`: Imported from `app_secrets.py`
- `EMAIL_TO`: Active users from SQLite when in production, `TEST_EMAIL` when in test mode
- `CREATE_HTML_OUTPUT_FILE`: Whether to save HTML output to file
- `HTML_ROOT_URL`: Base URL where archived HTML snapshots are hosted
- `LOG_FILE`: Path to log file (`logs/financial_snapshot_app.log`)

### Managing Users

Users are stored in `db.sqlite3`. Common operations:

```bash
source venv/bin/activate

# List all active users
python -c "from models import User, init_db; init_db(); [print(u.email) for u in User.select().where(User.active==True)]"

# Add a user
python -c "from models import User, init_db; init_db(); User.create(first_name='Jane', last_name='Doe', email='jane@example.com', format_pref='HTML')"

# Deactivate a user (keeps the record)
python -c "from models import User, init_db; init_db(); User.update(active=False).where(User.email=='jane@example.com').execute()"

# Delete a user
python -c "from models import User, init_db; init_db(); User.delete().where(User.email=='jane@example.com').execute()"
```

### Environment Variables

All API keys are read from environment variables (or `.env`). Environment variables always take priority over `.env`, making it safe to use either approach depending on your setup.

## Usage

### Running the Application

```bash
# Activate virtual environment
source venv/bin/activate

# Run the financial snapshot
python financial_snapshot.py
```

### Generating the Portfolio Advisor Page

```bash
# Generate html/portfolios.html (calls Claude + validates via Yahoo Finance)
python generate_portfolios.py

# Skip Yahoo Finance validation (faster, no live ER/AUM)
python generate_portfolios.py --skip-validation

# Write to a custom path
python generate_portfolios.py --out /path/to/out.html
```

This generates a tabbed page with four portfolio strategies per brokerage:

| Tab | Brokerage | Fund preference |
|-----|-----------|----------------|
| Fidelity | Fidelity Investments | Fidelity ZERO funds, iShares Core ETFs |
| Vanguard | Vanguard | Vanguard ETFs and Admiral shares |
| Schwab | Charles Schwab | Schwab ETFs |
| E*TRADE | E*TRADE (Morgan Stanley) | iShares Core ETFs, Vanguard ETFs |
| Generic | Any brokerage | Broadly available ETFs |

Each portfolio covers four strategies: Dividend Income, Aggressive Growth, Moderate Growth, and Capital Preservation. Expense ratios and AUM are validated live against Yahoo Finance. The page links back to the main dashboard and is linked from the dashboard's top navigation bar.

### Scheduled Execution & Publishing

`run_daily.sh` sends the email, regenerates the dashboard, and pushes `html/` to the `gh-pages` branch (GitHub Pages). Schedule it locally:

```bash
# crontab -e   (7 AM local time, weekdays; the script itself skips market holidays)
0 7 * * 1-5 /path/to/financial_snapshot/run_daily.sh >> /path/to/financial_snapshot/logs/cron.log 2>&1
```

The Mac must be awake at that time (e.g. `sudo pmset repeat wakeorpoweron MTWRF 06:55:00`). No need to export API keys — the app loads `.env` automatically.

**One-time GitHub Pages setup:** run `./publish_pages.sh` once to create the `gh-pages` branch, then in the repo's Settings → Pages choose "Deploy from branch → gh-pages / (root)" and set the custom domain `mktpulse.online` (the script writes the `CNAME` file). Point the domain's DNS at GitHub Pages.

Subscribers are managed directly in the `User` table of `db.sqlite3`; there is no web signup or unsubscribe link.

## APIs Used

| API | Purpose | Key Required |
|-----|---------|--------------|
| CoinGecko | Cryptocurrency prices | No |
| Alternative.me | Fear & Greed Index | No |
| EIA | Energy prices | Yes |
| FRED | Economic indicators | Yes |
| Yahoo Finance | Market data | No |
| Treasury Fiscal Data | National debt | No |
| AgentMail | Email delivery | Yes |
| Anthropic (Claude Haiku) | AI Morning Briefing | Optional |

## Data Sources

The email includes sections for:

- **AI Morning Briefing**: Claude-generated market overview, "Watch today" callout, and dynamic subject line
- **Anomaly Alert**: Amber warning banner (email + dashboard) when notable moves are detected — large index swings, VIX spikes, yield jumps, crypto volatility, extreme sentiment, or big Mag 7 moves
- **US Markets**: Live indices or futures (depending on market hours)
- **Magnificent 7**: AAPL, MSFT, AMZN, GOOGL, META, TSLA, NVDA
- **Volatility**: VIX index
- **Cryptocurrencies**: BTC, ETH, SOL, XRP, ADA, Fear & Greed Index
- **Energy**: Gas prices, crude oil
- **Metals**: Gold, silver
- **Currencies**: USD/JPY, EUR/USD
- **Bonds & Rates**: Treasury yields, mortgage rates, credit card APR
- **Consumer Prices**: Eggs, milk, grocery inflation
- **Macro Economy**: GDP, CPI, unemployment, national debt
- **Firm Insights**: Curated articles from Fidelity, BlackRock, J.P. Morgan AM, MarketWatch, and the On Watch podcast

## Logging

The application logs to `logs/financial_snapshot_app.log`. Check the logs for API errors or delivery status.

## Troubleshooting

### Common Issues

1. **Missing API Keys**: Ensure keys are set in `.env` or as environment variables
2. **Email Not Sending**: Check `AGENTMAIL_API_KEY` and `AGENTMAIL_INBOX_ID` in `.env`
3. **Import Errors**: Make sure you're running from the virtual environment
4. **Missing directories**: `logs/` and `html/` are created automatically on first run

### Test Mode

Always test with `TEST_MODE = True` first to avoid sending emails to production recipients.

## Development

The modular structure makes it easy to:

- Add new data sources by creating new API modules
- Modify existing APIs without affecting other components
- Test individual API modules independently
- Extend functionality while maintaining clean separation of concerns
- Add new output formats by creating new renderer modules (like `html_builder.py`)
- Update data presentation by modifying the shared `snapshot_schema.py`
- Customize formatting using shared utilities in `render_utils.py`

## License

This project is for educational and personal use. Please respect API terms of service and rate limits.
