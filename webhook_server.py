"""
Webhook server for AgentMail inbound email signups.

Listens for inbound emails to the AgentMail inbox and:
  - Subscribes the sender if the subject contains "subscribe"
  - Unsubscribes the sender if the subject contains "unsubscribe"
  - Sends a confirmation reply either way

Run directly:   python webhook_server.py
Run via systemd: see financial-snapshot-webhook.service
"""

import logging
import os
import re
from email.utils import parseaddr

import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify

from models import User, init_db

load_dotenv()

AGENTMAIL_API_KEY  = os.environ.get("AGENTMAIL_API_KEY", "")
AGENTMAIL_INBOX_ID = os.environ.get("AGENTMAIL_INBOX_ID", "")
WEBHOOK_SECRET     = os.environ.get("WEBHOOK_SECRET", "")
PORT               = int(os.environ.get("WEBHOOK_PORT", 5000))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)
init_db()


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_sender(from_str: str) -> tuple[str, str, str]:
    """
    Parse a 'from' header into (first_name, last_name, email).
    Handles 'John Doe <john@example.com>' and 'john@example.com'.
    """
    display_name, email = parseaddr(from_str)
    email = email.strip().lower()

    if display_name:
        parts = display_name.strip().split(None, 1)
        first = parts[0]
        last  = parts[1] if len(parts) > 1 else ""
    else:
        first = email.split("@")[0]
        last  = ""

    return first, last, email


def send_reply(to: str, subject: str, html: str, plain: str):
    """Send a reply via AgentMail."""
    url = f"https://api.agentmail.to/v0/inboxes/{AGENTMAIL_INBOX_ID}/messages/send"
    headers = {
        "Authorization": f"Bearer {AGENTMAIL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"to": to, "subject": subject, "html": html, "text": plain}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        log.info(f"Reply sent to {to}")
    except requests.RequestException as e:
        log.error(f"Failed to send reply to {to}: {e}")


def subscribe(first: str, last: str, email: str):
    """Add or reactivate a user and send a confirmation email."""
    user, created = User.get_or_create(
        email=email,
        defaults={"first_name": first, "last_name": last, "format_pref": "HTML", "active": True},
    )
    if not created and not user.active:
        User.update(active=True).where(User.email == email).execute()
        log.info(f"Reactivated subscriber: {email}")
    elif created:
        log.info(f"New subscriber: {email}")
    else:
        log.info(f"Already subscribed: {email}")

    plain = (
        f"Hi {first},\n\n"
        "You're now subscribed to the Daily Financial Snapshot.\n"
        "You'll receive a market summary email each morning.\n\n"
        "To unsubscribe at any time, reply with 'unsubscribe' in the subject line.\n\n"
        "— Financial Snapshot"
    )
    html = f"""
    <p>Hi {first},</p>
    <p>You're now subscribed to the <strong>Daily Financial Snapshot</strong>.</p>
    <p>You'll receive a market summary email each morning.</p>
    <p>To unsubscribe at any time, reply with <em>unsubscribe</em> in the subject line.</p>
    <p>— Financial Snapshot</p>
    """
    send_reply(email, "Subscribed: Daily Financial Snapshot", html, plain)


def unsubscribe(email: str):
    """Deactivate a user and send a confirmation email."""
    updated = User.update(active=False).where(User.email == email).execute()
    if updated:
        log.info(f"Unsubscribed: {email}")
    else:
        log.info(f"Unsubscribe requested but email not found: {email}")

    plain = (
        "You've been unsubscribed from the Daily Financial Snapshot.\n"
        "You will no longer receive emails.\n\n"
        "To resubscribe, send an email with 'subscribe' in the subject line.\n\n"
        "— Financial Snapshot"
    )
    html = """
    <p>You've been unsubscribed from the <strong>Daily Financial Snapshot</strong>.</p>
    <p>You will no longer receive emails.</p>
    <p>To resubscribe, send an email with <em>subscribe</em> in the subject line.</p>
    <p>— Financial Snapshot</p>
    """
    send_reply(email, "Unsubscribed: Daily Financial Snapshot", html, plain)


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@app.route("/subscribe", methods=["POST"])
def subscribe_form():
    """Web form subscription from the dashboard page."""
    data  = request.get_json(silent=True) or request.form
    email = (data.get("email") or "").strip().lower()
    first = (data.get("first_name") or "").strip()

    if not email:
        return jsonify({"error": "email is required"}), 400

    subscribe(first or email.split("@")[0], "", email)
    return jsonify({"status": "subscribed"}), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    # Verify secret token if configured
    if WEBHOOK_SECRET and request.args.get("token") != WEBHOOK_SECRET:
        log.warning("Webhook request rejected: invalid or missing token")
        return jsonify({"error": "unauthorized"}), 401

    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "invalid payload"}), 400

    event_type = payload.get("event_type")
    if event_type != "message.received":
        return jsonify({"status": "ignored", "event_type": event_type}), 200

    message  = payload.get("message", {})
    from_str = message.get("from", "")
    subject  = (message.get("subject") or "").strip().lower()

    first, last, email = parse_sender(from_str)
    if not email:
        log.warning("Received webhook with no parseable sender email")
        return jsonify({"error": "no sender email"}), 400

    log.info(f"Inbound email from {email} — subject: '{subject}'")

    if "unsubscribe" in subject:
        unsubscribe(email)
        return jsonify({"status": "unsubscribed", "email": email}), 200

    # Treat any other email (blank subject, "subscribe", etc.) as a signup
    subscribe(first, last, email)
    return jsonify({"status": "subscribed", "email": email}), 200


@app.route("/unsubscribe", methods=["GET"])
def unsubscribe_link():
    """One-click unsubscribe from the link in the daily email."""
    if WEBHOOK_SECRET and request.args.get("token") != WEBHOOK_SECRET:
        return "<p>Invalid or missing token.</p>", 401

    email = request.args.get("email", "").strip().lower()
    if not email:
        return "<p>Missing email address.</p>", 400

    updated = User.update(active=False).where(User.email == email).execute()
    if updated:
        log.info(f"Unsubscribed via link: {email}")
    else:
        log.info(f"Unsubscribe link used but email not found: {email}")

    return """
    <html><body style="font-family:sans-serif;max-width:480px;margin:60px auto;text-align:center;">
      <h2>You've been unsubscribed</h2>
      <p>You will no longer receive the Daily Financial Snapshot.</p>
      <p style="color:#888;font-size:13px;">To resubscribe, send an email with <em>subscribe</em> in the subject line.</p>
    </body></html>
    """, 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    log.info(f"Starting webhook server on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
