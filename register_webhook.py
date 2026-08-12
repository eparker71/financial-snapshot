"""
One-time script to register the webhook URL with AgentMail.

Usage:
    python register_webhook.py https://your-server-ip:5000/webhook

If you've set WEBHOOK_SECRET in .env, the secret will be appended
as a query parameter automatically:
    https://your-server-ip:5000/webhook?token=your_secret
"""

import os
import sys
from dotenv import load_dotenv
from agentmail import AgentMail

load_dotenv()

AGENTMAIL_API_KEY  = os.environ.get("AGENTMAIL_API_KEY", "")
AGENTMAIL_INBOX_ID = os.environ.get("AGENTMAIL_INBOX_ID", "")
WEBHOOK_SECRET     = os.environ.get("WEBHOOK_SECRET", "")

if not AGENTMAIL_API_KEY:
    print("Error: AGENTMAIL_API_KEY not set in .env")
    sys.exit(1)

if len(sys.argv) < 2:
    print("Usage: python register_webhook.py <webhook_url>")
    print("  e.g. python register_webhook.py http://123.45.67.89:5000/webhook")
    sys.exit(1)

url = sys.argv[1]
if WEBHOOK_SECRET and "token=" not in url:
    url = f"{url}?token={WEBHOOK_SECRET}"

client = AgentMail(api_key=AGENTMAIL_API_KEY)

webhook = client.webhooks.create(
    url=url,
    event_types=["message.received"],
    inbox_ids=[AGENTMAIL_INBOX_ID],
)

print("Webhook registered successfully.")
print(f"  ID:  {webhook.webhook_id}")
print(f"  URL: {url}")
