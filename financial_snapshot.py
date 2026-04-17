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

from dotenv import load_dotenv
load_dotenv()  # loads .env into os.environ if present; existing env vars take priority

from csv_export import save_to_db
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
AGENTMAIL_API_KEY  = os.environ.get("AGENTMAIL_API_KEY", "")
AGENTMAIL_INBOX_ID = os.environ.get("AGENTMAIL_INBOX_ID", "")
WEBHOOK_SECRET     = os.environ.get("WEBHOOK_SECRET", "")

# Non-sensitive config — managed in settings.py
from settings import TEST_MODE, EMAIL_TO, LOG_FILE, HTML_OUTPUT_DIR, CREATE_HTML_OUTPUT_FILE, HTML_ROOT_URL, WEBHOOK_BASE_URL

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── AI Market Analysis ────────────────────────────────────────────────────────

def generate_market_analysis(data: dict) -> dict:
    """Generate AI market content (briefing, email subject, watch item) using Claude Haiku.

    Returns a dict with keys: analysis, subject, watch.
    All values are None on failure or if the API key is not set.
    """
    fallback = {"analysis": None, "subject": None, "watch": None}
    if not ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY not set — skipping AI analysis")
        return fallback
    raw = ""
    try:
        import anthropic
        import json

        # Build a compact market summary to pass as context
        def _v(val, fmt=".2f"):
            return f"{val:{fmt}}" if val is not None else "N/A"

        sp_p  = data.get("gspc", (None,))[0] or data.get("sp500", (None,))[0]
        sp_c  = (data.get("gspc") or (None, None, None))[2] or (data.get("sp500") or (None, None, None))[2]
        dj_p  = data.get("dji",  (None,))[0] or data.get("dow",  (None,))[0]
        dj_c  = (data.get("dji")  or (None, None, None))[2] or (data.get("dow")  or (None, None, None))[2]
        nq_p  = data.get("ndx",  (None,))[0] or data.get("nasdaq", (None,))[0]
        nq_c  = (data.get("ndx")  or (None, None, None))[2] or (data.get("nasdaq") or (None, None, None))[2]

        fg_val, fg_lbl = data.get("fear_greed", (None, None))
        btc_p,  btc_c  = data.get("btc_price"), data.get("btc_change_pct")
        oil_p  = (data.get("oil")    or (None, None, None))[0]
        oil_c  = (data.get("oil")    or (None, None, None))[2]
        gold_p = (data.get("gold")   or (None, None, None))[0]
        t10y_p = (data.get("t10y")   or (None, None, None))[0]
        vix_p  = (data.get("vix")    or (None, None, None))[0]
        cpi    = (data.get("ev_cpi_all") or (None, None))
        unemp  = (data.get("ev_unemployment") or (None, None, None))[0]

        market_summary = f"""
S&P 500: {_v(sp_p, ",.0f")} ({_v(sp_c, "+.2f")}%)
Dow Jones: {_v(dj_p, ",.0f")} ({_v(dj_c, "+.2f")}%)
Nasdaq 100: {_v(nq_p, ",.0f")} ({_v(nq_c, "+.2f")}%)
VIX: {_v(vix_p)}
Fear & Greed Index: {_v(fg_val, ".0f")} ({fg_lbl or "N/A"})
Bitcoin: ${_v(btc_p, ",.0f")} ({_v(btc_c, "+.2f")}%)
Crude Oil (WTI): ${_v(oil_p)} ({_v(oil_c, "+.2f")}%)
Gold: ${_v(gold_p, ",.0f")}
10-Yr Treasury Yield: {_v(t10y_p)}%
CPI (YoY): {_v(cpi[0] if cpi else None)}%
Unemployment: {_v(unemp)}%
""".strip()

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=500,
            system=[
                {
                    "type": "text",
                    "text": (
                        "You are a concise financial market analyst. Given today's market data, return a JSON "
                        "object with exactly three fields:\n"
                        "- \"briefing\": A 3–4 sentence market overview in flowing prose. Highlight the most "
                        "notable moves, trends, or tensions. Be factual and neutral. No bullets, no disclaimers.\n"
                        "- \"subject\": An email subject line under 60 characters capturing the single most "
                        "notable move. Examples: \"S&P +1.2%, VIX spiking — Tech leads\" or "
                        "\"Yields surge, equities slip — CPI in focus\"\n"
                        "- \"watch\": One specific, actionable thing to monitor today — 1–2 sentences explaining "
                        "what to watch and why it matters right now.\n\n"
                        "Return only valid JSON with those three keys. No markdown fences, no other text."
                    ),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": f"Here is today's market data:\n\n{market_summary}\n\nReturn the JSON.",
                }
            ],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code fences if the model wraps the JSON anyway
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]  # drop the opening ```json line
            raw = raw.rsplit("```", 1)[0].strip()
        parsed = json.loads(raw)
        result = {
            "analysis": (parsed.get("briefing") or "").strip() or None,
            "subject":  (parsed.get("subject")  or "").strip() or None,
            "watch":    (parsed.get("watch")    or "").strip() or None,
        }
        log.info("AI content generated successfully")
        print(f"✓ AI content generated — subject: {result['subject']!r}")
        return result
    except (ValueError, KeyError) as e:
        log.warning(f"AI content JSON parse failed: {e} — raw: {raw[:200]}")
        print(f"⚠  AI content parse failed: {e} — raw: {raw[:200]}")
        return fallback
    except Exception as e:
        log.warning(f"AI content failed: {e}")
        print(f"⚠  AI content skipped: {e}")
        return fallback

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
    print(f"Crypto data: {crypto}") if TEST_MODE else None

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

    # AI market content (Claude Haiku — low cost)
    ai = generate_market_analysis(data)
    data["ai_analysis"] = ai["analysis"]
    data["watch_item"]  = ai["watch"]

    # Build content — use AI subject when available, fall back to static
    ai_subject = ai["subject"] or f"Market Pulse — {now.strftime('%b %-d, %Y')}"
    subject = f"{'[TEST] ' if TEST_MODE else ''}📊 {ai_subject}"
    print(f"  Subject: {subject}")

    def unsubscribe_url(addr: str) -> str:
        if WEBHOOK_BASE_URL and WEBHOOK_SECRET:
            from urllib.parse import urlencode
            return f"{WEBHOOK_BASE_URL}/unsubscribe?{urlencode({'email': addr, 'token': WEBHOOK_SECRET})}"
        return ""

    # Send
    for addr in EMAIL_TO:
        try:
            unsub_url = unsubscribe_url(addr)
            html  = build_html(data, now, HTML_ROOT_URL, unsub_url)
            plain = build_plain(data, now, unsub_url)
            result = send_email(subject, html, plain, addr)
            log.info(f"Sent to {addr} — message_id: {result.get('id')}")
            print(f"✓ Sent to {addr}")
        except requests.RequestException as e:
            status = e.response.status_code if getattr(e, "response", None) is not None else "N/A"
            log.error(f"Failed to send to {addr}: {status} {e}")
    
    if CREATE_HTML_OUTPUT_FILE and HTML_OUTPUT_DIR:
        try:
            os.makedirs(HTML_OUTPUT_DIR, exist_ok=True)
            filename = f"{HTML_OUTPUT_DIR}/output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(html)
                log.info(f"Saved HTML output to {filename}")
                print(f"✓ Saved HTML output to {filename}")
        except OSError as e:
            log.error(f"Failed to write HTML file: {e}")
            print(f"✗ Failed to save HTML output: {e}")
    
    # Save snapshot to database
    save_to_db(data, now)

    # Regenerate public dashboard
    try:
        from generate_index import generate
        generate()
    except Exception as e:
        log.warning(f"Dashboard generation failed: {e}")

if __name__ == "__main__":
    main()
