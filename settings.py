# ── settings.py ───────────────────────────────────────────────────────────────
# Non-sensitive configuration for financial_snapshot.py.
# API keys do NOT go here — set those as environment variables:
#
#   export AGENTMAIL_API_KEY="..."
#   export AGENTMAIL_INBOX_ID="..."
#   export EIA_API_KEY="..."
#   export FRED_API_KEY="..."
#

from app_secrets import TEST_EMAIL_ADDRESS, RECIPIENT_LIST, TEST_MODE_SET

# ── Test mode ─────────────────────────────────────────────────────────────────
# Set TEST_MODE = True while developing. Emails will only go to TEST_EMAIL.
# Flip to False when you're ready to send to the full list.

TEST_MODE  = TEST_MODE_SET
TEST_EMAIL = TEST_EMAIL_ADDRESS

# ── Create HTML output file ──────────────────────────────────────────----──────

HTML_OUTPUT = True  # Set to False to disable saving the HTML output to a file.
HTML_PATH   = "html"  # Directory where HTML output files will be saved.

# ── Recipients ────────────────────────────────────────────────────────────────
# Add or remove addresses here. TEST_MODE above overrides this list.

RECIPIENTS = RECIPIENT_LIST

# ── Log file ──────────────────────────────────────────────────────────────────
# Overridden by the LOG_FILE environment variable if set.

LOG_FILE = "financial_snapshot.log"

