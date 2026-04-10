# ── settings.py ───────────────────────────────────────────────────────────────
# Non-sensitive configuration for financial_snapshot.py.
# API keys do NOT go here — set those as environment variables:
#
#   export AGENTMAIL_API_KEY="..."
#   export AGENTMAIL_INBOX_ID="..."
#   export EIA_API_KEY="..."
#   export FRED_API_KEY="..."
#

from app_secrets import TEST_EMAIL, TEST_MODE
from csvdb import CsvDB

db = CsvDB("users.csv")
userEmails = db.column("Email")

# ── Create HTML output file ──────────────────────────────────────────----──────

HTML_OUTPUT = True  # Set to False to disable saving the HTML output to a file.
HTML_ROOT_URL   = "https://eparker71.github.io/Financial-Snapshot/html/index.html" # Base URL where the HTML files will be hosted. Adjust if you host them elsewhere.
HTML_PATH   = "html"  # Directory where HTML output files will be saved.

# ── Recipients ────────────────────────────────────────────────────────────────
# Add or remove addresses here. TEST_MODE above overrides this list.

EMAIL_TO = [TEST_EMAIL] if TEST_MODE else userEmails

# ── Log file ──────────────────────────────────────────────────────────────────
# Overridden by the LOG_FILE environment variable if set.

LOG_FILE = "financial_snapshot.log"

