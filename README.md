# Financial Snapshot Emailer

A Python application that fetches live financial market data from multiple APIs and sends a formatted HTML email snapshot using AgentMail.

## Features

- **Cryptocurrency Data**: Bitcoin, Ethereum, Solana, Ripple, and Cardano prices from CoinGecko, Fear & Greed Index from Alternative.me
- **Energy Prices**: US gas and diesel prices from EIA (Energy Information Administration)
- **Economic Indicators**: CPI, unemployment, GDP, mortgage rates, and credit card rates from FRED (Federal Reserve Economic Data)
- **Market Data**: Stocks, commodities, currencies, bonds, and indices from Yahoo Finance
- **National Debt**: US national debt data from Treasury Fiscal Data API
- **Email Delivery**: Sends formatted HTML emails via AgentMail
- **CSV Export**: Saves a row of snapshot data to `financial_data.csv` for later charting
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
├── app_secrets.py        # Sensitive email configuration
└── html/                 # HTML output directory
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

Set these as environment variables:

```bash
export AGENTMAIL_API_KEY="your_agentmail_key"
export AGENTMAIL_INBOX_ID="your_inbox_id"
export EIA_API_KEY="your_eia_key"
export FRED_API_KEY="your_fred_key"
```

### 3. Email Configuration

Create `app_secrets.py` with your email settings:

```python
# app_secrets.py - Sensitive configuration

# Test mode settings
TEST_MODE_SET = True  # Set to True for testing, False for production

# Email addresses
TEST_EMAIL_ADDRESS = "test@example.com"  # Email for test mode
RECIPIENT_LIST = ["recipient1@example.com", "recipient2@example.com"]  # Production recipients
```

**Note**: If `TEST_MODE_SET = True`, emails will only be sent to `TEST_EMAIL_ADDRESS`. Set to `False` for production use.

## Configuration

### settings.py

Contains non-sensitive configuration:

- `TEST_MODE`: Whether to use test mode (overrides `app_secrets.py`)
- `TEST_EMAIL`: Test email address
- `RECIPIENTS`: Production email recipients
- `LOG_FILE`: Path to log file
- `HTML_OUTPUT`: Whether to save HTML output to file
- `HTML_PATH`: Directory for HTML output files

### Environment Variables

The app prioritizes environment variables over `app_secrets.py` settings:

```bash
export LOG_FILE="/path/to/custom/logfile.log"
```

## Usage

### Running the Application

```bash
# Activate virtual environment
source venv/bin/activate

# Run the financial snapshot
python financial_snapshot.py
```

### Scheduled Execution

Set up a cron job to run daily (example for 7 AM ET):

```bash
# Add to crontab (crontab -e)
0 7 * * * /path/to/venv/bin/python /path/to/financial_snapshot.py
```

### HTML Output

When `HTML_OUTPUT = True` in settings.py, the application saves the generated HTML to the `html/` directory with timestamps.

### CSV Export

Each run now also appends a flattened data row to `data/data.csv`. This file contains timestamped snapshot values for later charting and analytics.

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

## Data Sources

The email includes sections for:

- **US Markets**: Live indices or futures (depending on market hours)
- **Volatility**: VIX index
- **Cryptocurrencies**: BTC, ETH, SOL, XRP, ADA, Fear & Greed Index
- **Energy**: Gas prices, crude oil
- **Metals**: Gold, silver
- **Currencies**: USD/JPY, EUR/USD
- **Bonds & Rates**: Treasury yields, mortgage rates, credit card APR
- **Consumer Prices**: Eggs, milk, grocery inflation
- **Macro Economy**: GDP, CPI, unemployment, national debt

## Logging

The application logs to `logs/financial_snapshot_app.log`. Check the logs for API errors or delivery status.

## Troubleshooting

### Common Issues

1. **Missing API Keys**: Ensure all required API keys are set as environment variables
2. **Email Not Sending**: Check AgentMail API key and inbox ID
3. **Import Errors**: Make sure you're running from the virtual environment
4. **Permission Errors**: Ensure write permissions for log files and HTML output directory

### Test Mode

Always test with `TEST_MODE_SET = True` first to avoid sending emails to production recipients.

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
