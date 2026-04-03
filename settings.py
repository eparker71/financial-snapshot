# ── settings.py ───────────────────────────────────────────────────────────────
# Non-sensitive configuration for financial_snapshot.py.
# API keys do NOT go here — set those as environment variables:
#
#   export AGENTMAIL_API_KEY="..."
#   export AGENTMAIL_INBOX_ID="..."
#   export EIA_API_KEY="..."
#   export FRED_API_KEY="..."
#

from secrets import TEST_EMAIL_ADDRESS, RECIPIENT_LIST, TEST_MODE

# ── Test mode ─────────────────────────────────────────────────────────────────
# Set TEST_MODE = True while developing. Emails will only go to TEST_EMAIL.
# Flip to False when you're ready to send to the full list.

TEST_MODE  = TEST_MODE
TEST_EMAIL = TEST_EMAIL_ADDRESS

# ── Recipients ────────────────────────────────────────────────────────────────
# Add or remove addresses here. TEST_MODE above overrides this list.

RECIPIENTS = RECIPIENT_LIST

# ── Log file ──────────────────────────────────────────────────────────────────
# Overridden by the LOG_FILE environment variable if set.

LOG_FILE = "financial_snapshot.log"
