# Financial-Snapshot

This app uses AGENTMAIL to send email. You will need the following API keys

* AGENTMAIL_API_KEY - https://www.agentmail.to/
* EIA_API_KEY - https://www.eia.gov/opendata/register.php
* FRED_API_KEY - https://fred.stlouisfed.org/docs/api/api_key.html

```
# ── In settings.py you will find ───────────────────────────────────────────────────────────────
# Non-sensitive configuration for financial_snapshot.py.
# API keys do NOT go here — set those as environment variables or in app_secrets.py
# the app expects env vars. if you choose to use app_secrets you will need to mofidify the app. 
# 
#.  set env vars:
#   export AGENTMAIL_API_KEY="..."
#   export AGENTMAIL_INBOX_ID="..."
#   export EIA_API_KEY="..."
#   export FRED_API_KEY="..."
#
```


You will need to create a file called app_secrets.py with the following contents.

```
# ── Secrets and Configurations ───────────────────────────────────────────────
# This file contains sensitive information and should not be shared publicly.
# It is used to store email credentials and recipient lists for the application.    
# if TEST_MODE_SET is TRUE the app will only send email to the TEST_EMAIL_ADDRESS address
# otherwise it will send to the RECIPIENT_LIST

TEST_MODE_SET = True
TEST_EMAIL_ADDRESS = "address for testing"

# ── Recipients ────────────────────────────────────────────────────────────────
# Add or remove addresses here. TEST_MODE above overrides this list.
# If TEST_MODE is True, only TEST_EMAIL_ADDRESS will receive emails.

RECIPIENT_LIST = [
    email1@somewhere.com,
    email2@someplace.org,
    ...
]
```
