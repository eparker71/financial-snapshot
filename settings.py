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
from models import User, init_db
import os

init_db()
userEmails = [u.email for u in User.select().where(User.active == True)]

# ── Create HTML output file ──────────────────────────────────────────----──────
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_OUTPUT_DIR = os.path.join(ROOT_DIR, "html")
print(f"HTML Output Directory: {HTML_OUTPUT_DIR}")
CREATE_HTML_OUTPUT_FILE = True  # Set to False to disable saving the HTML output to a file.
HTML_ROOT_URL   = "https://mktpulse.online" # Base URL where the HTML files will be hosted. Adjust if you host them elsewhere.

# ── Recipients ────────────────────────────────────────────────────────────────
# Add or remove addresses here. TEST_MODE above overrides this list.

EMAIL_TO = [TEST_EMAIL] if TEST_MODE else userEmails

# ── Log file ──────────────────────────────────────────────────────────────────
# Overridden by the LOG_FILE environment variable if set.

LOG_FILE_DIR = os.path.join(ROOT_DIR, "logs")
os.makedirs(LOG_FILE_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_FILE_DIR, "financial_snapshot_app.log")
print(f"App Log File: {LOG_FILE}")

