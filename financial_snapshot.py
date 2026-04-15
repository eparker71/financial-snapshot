#!/usr/bin/env python3
"""
Daily Financial Snapshot Emailer
Fetches live market data and sends a formatted email via AgentMail.
Run via cron: 0 7 * * * /path/to/venv/bin/python /path/to/financial_snapshot.py
"""

import os
import logging
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from csv_export import save_to_csv
from html_builder import build_html
from plain_text_builder import build_plain

# Import API modules
from crypto_api import fetch_crypto, fetch_fear_greed
from energy_api import fetch_gas
from treasury_api import fetch_national_debt
from fred_api import fetch_everyday_economy
from yahoo_api import fetch_yahoo_data

# ── Config ────────────────────────────────────────────────────────────────────
# API keys — set as environment variables, never hardcode
AGENTMAIL_API_KEY  = os.environ.get("AGENTMAIL_API_KEY", "YOUR_AGENTMAIL_API_KEY")
AGENTMAIL_INBOX_ID = os.environ.get("AGENTMAIL_INBOX_ID", "YOUR_INBOX_ID")

# Non-sensitive config — managed in settings.py
from settings import TEST_MODE, EMAIL_TO, LOG_FILE, HTML_OUTPUT_DIR, CREATE_HTML_OUTPUT_FILE, HTML_ROOT_URL
#LOG_FILE = os.environ.get("LOG_FILE", LOG_FILE)  # env var still overrides if set

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

if TEST_MODE:
    print(f"⚠️  TEST MODE — sending only to {EMAIL_TO[0] if EMAIL_TO else None}")

# ── Send via AgentMail ────────────────────────────────────────────────────────

def send_email(subject: str, html: str, plain: str, to: str):
    url = f"https://api.agentmail.to/v0/inboxes/{AGENTMAIL_INBOX_ID}/messages/send"
    headers = {
        "Authorization": f"Bearer {AGENTMAIL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "to":      to,
        "subject": subject,
        "html":    html,
        "text":    plain,
    }
    r = requests.post(url, json=payload, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    now = datetime.now(ET)
    log.info(f"Starting snapshot run at {now.isoformat()}")

    data = {}

    # Crypto
    crypto = fetch_crypto()
    data.update(crypto)

    # Fear & Greed
    fg_val, fg_label = fetch_fear_greed()
    data["fear_greed"] = (fg_val, fg_label)

    # Gas (EIA)
    data["gas"] = fetch_gas()

    # National debt (US Treasury)
    data["national_debt"] = fetch_national_debt()

    # Everyday economy (FRED) — gracefully skipped if FRED_API_KEY not set
    everyday = fetch_everyday_economy()
    data.update(everyday)

    # Yahoo Finance data
    yahoo_data = fetch_yahoo_data()
    data.update(yahoo_data)

    # Build content
    subject = f"{'[TEST] ' if TEST_MODE else ''}📊 Financial Snapshot — {now.strftime('%b %-d, %Y')}"
    html  = build_html(data, now, HTML_ROOT_URL)
    plain = build_plain(data, now)

    # Send
    for addr in EMAIL_TO:
        try:
            result = send_email(subject, html, plain, addr)
            log.info(f"Sent to {addr} — message_id: {result.get('id')}")
            print(f"✓ Sent to {addr}")
        except requests.HTTPError as e:
            log.error(f"Failed to send to {addr}: {e.response.status_code} {e.response.text}")
    
    if CREATE_HTML_OUTPUT_FILE and HTML_OUTPUT_DIR:
        try:
            filename = f"{HTML_OUTPUT_DIR}/output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(html)
                log.info(f"Saved HTML output to {filename}")
                print(f"✓ Saved HTML output to {filename}")
        except OSError as e:
            log.error(f"Failed to write HTML file: {e}")
            print(f"✗ Failed to save HTML output: {e}")
    
    # Save data to CSV
    save_to_csv(data, now)

if __name__ == "__main__":
    main()
