# Financial-Snapshot

You will need to create a file called settings.py with the following contents.

```
# ── settings.py ───────────────────────────────────────────────────────────────
# Non-sensitive configuration for financial_snapshot.py.
# API keys do NOT go here — set those as environment variables:
#
#   export AGENTMAIL_API_KEY="..."
#   export AGENTMAIL_INBOX_ID="..."
#   export EIA_API_KEY="..."
#   export FRED_API_KEY="..."
#
# ── Test mode ─────────────────────────────────────────────────────────────────
# Set TEST_MODE = True while developing. Emails will only go to TEST_EMAIL.
# Flip to False when you're ready to send to the full list.

TEST_MODE  = True
TEST_EMAIL = "<add email address>"

# ── Recipients ────────────────────────────────────────────────────────────────
# Add or remove addresses here. TEST_MODE above overrides this list.

RECIPIENTS = [
    (a list of email addresses. this is temporary)
]

# ── Log file ──────────────────────────────────────────────────────────────────
# Overridden by the LOG_FILE environment variable if set.
# call it whatever you want 
LOG_FILE = "financial_snapshot.log" 
```
