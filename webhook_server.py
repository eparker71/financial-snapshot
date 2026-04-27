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
import time
from datetime import datetime
from email.utils import parseaddr
from threading import Lock

import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify

from models import User, init_db
from yahoo_api import fetch_yahoo_data
from crypto_api import fetch_crypto, fetch_fear_greed

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
        "You're now subscribed to the Daily Market Pulse.\n"
        "You'll receive a market summary email each morning.\n\n"
        "To unsubscribe at any time, reply with 'unsubscribe' in the subject line.\n\n"
        "— Market Pulse"
    )
    html = f"""
    <p>Hi {first},</p>
    <p>You're now subscribed to the <strong>Daily Market Pulse</strong>.</p>
    <p>You'll receive a market summary email each morning.</p>
    <p>To unsubscribe at any time, reply with <em>unsubscribe</em> in the subject line.</p>
    <p>— Market Pulse</p>
    """
    send_reply(email, "Subscribed: Daily Market Pulse", html, plain)


def unsubscribe(email: str):
    """Deactivate a user and send a confirmation email."""
    updated = User.update(active=False).where(User.email == email).execute()
    if updated:
        log.info(f"Unsubscribed: {email}")
    else:
        log.info(f"Unsubscribe requested but email not found: {email}")

    plain = (
        "You've been unsubscribed from the Daily Market Pulse.\n"
        "You will no longer receive emails.\n\n"
        "To resubscribe, send an email with 'subscribe' in the subject line.\n\n"
        "— Market Pulse"
    )
    html = """
    <p>You've been unsubscribed from the <strong>Daily Market Pulse</strong>.</p>
    <p>You will no longer receive emails.</p>
    <p>To resubscribe, send an email with <em>subscribe</em> in the subject line.</p>
    <p>— Market Pulse</p>
    """
    send_reply(email, "Unsubscribed: Daily Market Pulse", html, plain)


# ── Webhook endpoint ──────────────────────────────────────────────────────────

# ── Live data API ─────────────────────────────────────────────────────────────

_live_cache: dict = {"data": None, "ts": 0.0}
_live_lock = Lock()
CACHE_TTL = 60  # seconds


def _fmt(val, decimals=2, prefix="$", suffix="", invert=False, chg_pct=None):
    """Return a dict {price, change, cls} ready for JSON."""
    if val is None:
        return {"price": "—", "change": "", "cls": "neu"}
    price_str = (f"{prefix}{val:,.{decimals}f}{suffix}"
                 if val >= 1000 else f"{prefix}{val:.{decimals}f}{suffix}")
    chg_str, cls = "", "neu"
    if chg_pct is not None:
        chg_str = f"{'+' if chg_pct >= 0 else ''}{chg_pct:.2f}%"
        is_up = chg_pct >= 0
        good  = (is_up and not invert) or (not is_up and invert)
        cls   = "up" if good else "dn"
    return {"price": price_str, "change": chg_str, "cls": cls}


def _fetch_live_data() -> dict:
    result: dict = {}

    try:
        yahoo = fetch_yahoo_data()
        sp_p,  sp_c,  sp_pct  = yahoo.get("gspc",    (None, None, None))
        if sp_p  is None: sp_p,  sp_c,  sp_pct  = yahoo.get("sp500",   (None, None, None))
        dj_p,  dj_c,  dj_pct  = yahoo.get("dji",     (None, None, None))
        if dj_p  is None: dj_p,  dj_c,  dj_pct  = yahoo.get("dow",     (None, None, None))
        nq_p,  nq_c,  nq_pct  = yahoo.get("ndx",     (None, None, None))
        if nq_p  is None: nq_p,  nq_c,  nq_pct  = yahoo.get("nasdaq",  (None, None, None))
        rut_p, rut_c, rut_pct = yahoo.get("rut",     (None, None, None))
        if rut_p is None: rut_p, rut_c, rut_pct = yahoo.get("russell", (None, None, None))

        vix_p,   vix_c,   vix_pct   = yahoo.get("vix",    (None, None, None))
        gold_p,  gold_c,  gold_pct  = yahoo.get("gold",   (None, None, None))
        silv_p,  silv_c,  silv_pct  = yahoo.get("silver", (None, None, None))
        oil_p,   oil_c,   oil_pct   = yahoo.get("oil",    (None, None, None))
        eur_p,   eur_c,   eur_pct   = yahoo.get("eurusd", (None, None, None))
        jpy_p,   jpy_c,   jpy_pct   = yahoo.get("usdjpy", (None, None, None))
        t2_p,    t2_c,    t2_pct    = yahoo.get("t2y",    (None, None, None))
        t10_p,   t10_c,   t10_pct   = yahoo.get("t10y",   (None, None, None))

        result["sp500"]   = _fmt(sp_p,  chg_pct=sp_pct)
        result["dow"]     = _fmt(dj_p,  chg_pct=dj_pct)
        result["nasdaq"]  = _fmt(nq_p,  chg_pct=nq_pct)
        result["russell"] = _fmt(rut_p, chg_pct=rut_pct)
        result["vix"]     = _fmt(vix_p,  decimals=2, prefix="",  chg_pct=vix_pct,  invert=True)
        result["gold"]    = _fmt(gold_p, chg_pct=gold_pct)
        result["silver"]  = _fmt(silv_p, chg_pct=silv_pct)
        result["oil"]     = _fmt(oil_p,  chg_pct=oil_pct)
        result["eurusd"]  = _fmt(eur_p,  decimals=4, prefix="",  chg_pct=eur_pct)
        result["usdjpy"]  = _fmt(jpy_p,  decimals=2, prefix="¥", chg_pct=jpy_pct)
        result["t2y"]     = _fmt(t2_p,   decimals=3, prefix="",  suffix="%", chg_pct=t2_pct,  invert=True)
        result["t10y"]    = _fmt(t10_p,  decimals=3, prefix="",  suffix="%", chg_pct=t10_pct, invert=True)
    except Exception as e:
        log.error(f"Live data — Yahoo fetch error: {e}")

    try:
        crypto = fetch_crypto()
        result["btc"] = _fmt(crypto.get("btc_price"), decimals=0, chg_pct=crypto.get("btc_change_pct"))
        result["eth"] = _fmt(crypto.get("eth_price"), chg_pct=crypto.get("eth_change_pct"))
        result["sol"] = _fmt(crypto.get("sol_price"), chg_pct=crypto.get("sol_change_pct"))
        result["xrp"] = _fmt(crypto.get("xrp_price"), decimals=4, chg_pct=crypto.get("xrp_change_pct"))
        result["ada"] = _fmt(crypto.get("ada_price"), decimals=4, chg_pct=crypto.get("ada_change_pct"))
    except Exception as e:
        log.error(f"Live data — crypto fetch error: {e}")

    try:
        fg_val, fg_lbl = fetch_fear_greed()
        if fg_val is not None:
            fg = int(fg_val)
            result["fear_greed"] = {
                "price":  str(fg),
                "change": fg_lbl or "",
                "cls":    "up" if fg >= 50 else "dn",
            }
    except Exception as e:
        log.error(f"Live data — fear/greed fetch error: {e}")

    result["updated_at"] = datetime.now().strftime("%-I:%M:%S %p")
    return result


@app.route("/api/live", methods=["GET"])
def api_live():
    now = time.time()
    with _live_lock:
        if _live_cache["data"] and (now - _live_cache["ts"]) < CACHE_TTL:
            return jsonify(_live_cache["data"])

    try:
        data = _fetch_live_data()
        with _live_lock:
            _live_cache["data"] = data
            _live_cache["ts"] = time.time()
        return jsonify(data)
    except Exception as e:
        log.error(f"api_live error: {e}")
        with _live_lock:
            if _live_cache["data"]:
                return jsonify(_live_cache["data"])
        return jsonify({"error": "data unavailable"}), 503


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
    """Show a confirmation page — actual unsubscribe requires a POST to prevent
    email security scanners from auto-clicking the link and deactivating users."""
    token = request.args.get("token", "")
    email = request.args.get("email", "").strip().lower()

    if WEBHOOK_SECRET and token != WEBHOOK_SECRET:
        return "<p>Invalid or missing token.</p>", 401
    if not email:
        return "<p>Missing email address.</p>", 400

    from html import escape
    safe_email = escape(email)
    safe_token = escape(token)
    return f"""
    <html><body style="font-family:sans-serif;max-width:480px;margin:60px auto;text-align:center;">
      <h2>Unsubscribe from Daily Market Pulse</h2>
      <p>Click the button below to stop receiving emails at <strong>{safe_email}</strong>.</p>
      <form method="POST" action="/unsubscribe">
        <input type="hidden" name="email" value="{safe_email}">
        <input type="hidden" name="token" value="{safe_token}">
        <button type="submit" style="background:#c0392b;color:#fff;border:none;padding:12px 28px;font-size:16px;border-radius:6px;cursor:pointer;">
          Confirm Unsubscribe
        </button>
      </form>
    </body></html>
    """, 200


@app.route("/unsubscribe", methods=["POST"])
def unsubscribe_confirm():
    """Process the confirmed unsubscribe."""
    data  = request.get_json(silent=True) or request.form
    token = data.get("token", "")
    email = (data.get("email") or "").strip().lower()

    if WEBHOOK_SECRET and token != WEBHOOK_SECRET:
        return "<p>Invalid or missing token.</p>", 401
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
      <p>You will no longer receive the Daily Market Pulse.</p>
      <p style="color:#888;font-size:13px;">To resubscribe, send an email with <em>subscribe</em> in the subject line.</p>
    </body></html>
    """, 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    log.info(f"Starting webhook server on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
