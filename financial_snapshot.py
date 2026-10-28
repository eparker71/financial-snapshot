#!/usr/bin/env python3
"""
Daily Financial Snapshot Emailer
Fetches live market data and sends a formatted email via AgentMail.
Run via cron: 0 7 * * * /path/to/venv/bin/python /path/to/financial_snapshot.py
"""

import os
import sys
import logging
import requests
from datetime import date, datetime, timedelta
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
from polymarket_api import fetch_polymarket
from kalshi_api import fetch_kalshi

# ── Config ────────────────────────────────────────────────────────────────────
# API keys — set as environment variables, never hardcode
AGENTMAIL_API_KEY  = os.environ.get("AGENTMAIL_API_KEY", "")
AGENTMAIL_INBOX_ID = os.environ.get("AGENTMAIL_INBOX_ID", "")

# Non-sensitive config — managed in settings.py
from settings import TEST_MODE, EMAIL_TO, LOG_FILE, HTML_OUTPUT_DIR, CREATE_HTML_OUTPUT_FILE, HTML_ROOT_URL

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── Anomaly Detection ────────────────────────────────────────────────────────

def detect_anomalies(data: dict) -> list[str]:
    """Check market data against thresholds. Returns a list of plain-English flag strings."""
    flags = []

    def _c(key, idx=2):
        """Safely pull a value from a (price, change, pct) tuple stored under key."""
        return (data.get(key) or (None, None, None))[idx]

    def _first(*vals):
        """First value that is not None — unlike `or`, a legitimate 0.0 wins."""
        return next((v for v in vals if v is not None), None)

    # Equity indices — flag ≥ ±2% (S&P/Dow) or ≥ ±2.5% (Nasdaq)
    sp_c  = _first(_c("gspc"), _c("sp500"))
    dj_c  = _first(_c("dji"),  _c("dow"))
    nq_c  = _first(_c("ndx"),  _c("nasdaq"))
    rut_c = _first(_c("rut"),  _c("russell"))
    for name, val, thresh in [
        ("S&P 500",      sp_c,  2.0),
        ("Dow Jones",    dj_c,  2.0),
        ("Nasdaq 100",   nq_c,  2.5),
        ("Russell 2000", rut_c, 2.5),
    ]:
        if val is not None and abs(val) >= thresh:
            flags.append(f"{name} {'up' if val > 0 else 'down'} {abs(val):.1f}% today")

    # VIX — elevated ≥ 25, extreme ≥ 30
    vix_p = _c("vix", 0)
    if vix_p is not None:
        if vix_p >= 30:
            flags.append(f"VIX at {vix_p:.1f} (extreme fear territory)")
        elif vix_p >= 25:
            flags.append(f"VIX at {vix_p:.1f} (elevated volatility)")

    # Fear & Greed — extreme fear ≤ 15, extreme greed ≥ 85
    fg_val = (data.get("fear_greed") or (None, None))[0]
    if fg_val is not None:
        if fg_val <= 15:
            flags.append(f"Fear & Greed Index at {int(fg_val)} — extreme fear")
        elif fg_val >= 85:
            flags.append(f"Fear & Greed Index at {int(fg_val)} — extreme greed")

    # Bitcoin — flag ≥ ±8% in 24h
    btc_c = data.get("btc_change_pct")
    if btc_c is not None and abs(btc_c) >= 8.0:
        flags.append(f"Bitcoin {'up' if btc_c > 0 else 'down'} {abs(btc_c):.1f}% in 24 hours")

    # 10-yr Treasury yield — flag ≥ 8 bps daily move (change is in pct-points, e.g. 0.08 = 8bps)
    t10y_chg = _c("t10y", 1)
    if t10y_chg is not None and abs(t10y_chg) >= 0.08:
        bps = int(round(abs(t10y_chg) * 100))
        flags.append(
            f"10-yr Treasury yield moved {'+' if t10y_chg > 0 else '-'}{bps}bps today "
            f"({'higher' if t10y_chg > 0 else 'lower'} yields)"
        )

    # Oil — flag ≥ ±3%
    oil_c = _c("oil")
    if oil_c is not None and abs(oil_c) >= 3.0:
        flags.append(f"Crude oil {'up' if oil_c > 0 else 'down'} {abs(oil_c):.1f}% today")

    # Gold — flag ≥ ±2%
    gold_c = _c("gold")
    if gold_c is not None and abs(gold_c) >= 2.0:
        flags.append(f"Gold {'up' if gold_c > 0 else 'down'} {abs(gold_c):.1f}% today")

    # Magnificent 7 — flag any individual stock ≥ ±5%
    mag7 = [
        ("aapl",  "Apple (AAPL)"),
        ("msft",  "Microsoft (MSFT)"),
        ("amzn",  "Amazon (AMZN)"),
        ("googl", "Alphabet (GOOGL)"),
        ("meta",  "Meta (META)"),
        ("tsla",  "Tesla (TSLA)"),
        ("nvda",  "Nvidia (NVDA)"),
    ]
    for key, label in mag7:
        c = _c(key)
        if c is not None and abs(c) >= 5.0:
            flags.append(f"{label} {'up' if c > 0 else 'down'} {abs(c):.1f}% today")

    return flags


def generate_anomaly_alert(flags: list[str]) -> str | None:
    """Use Claude to write a brief contextual alert for the detected anomalies."""
    if not ANTHROPIC_API_KEY or not flags:
        return None
    try:
        import anthropic
        flags_text = "\n".join(f"- {f}" for f in flags)
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=150,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "You are a financial analyst writing a brief market alert for email subscribers. "
                        "Based on these notable market moves detected today, write 1–2 sentences explaining "
                        "what's happening and why it's worth paying attention to. Be specific and factual. "
                        "No bullets, no disclaimers, no greeting.\n\n"
                        f"Flagged moves:\n{flags_text}"
                    ),
                }
            ],
        )
        alert = response.content[0].text.strip()
        log.info(f"Anomaly alert generated ({len(flags)} flags)")
        print(f"⚠  {len(flags)} anomaly flag(s) — alert generated")
        return alert
    except Exception as e:
        log.warning(f"Anomaly alert generation failed: {e}")
        return None


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

        def _t(key, idx):
            return (data.get(key) or (None, None, None))[idx]

        def _first(*vals):
            return next((v for v in vals if v is not None), None)

        sp_p  = _first(_t("gspc", 0), _t("sp500", 0))
        sp_c  = _first(_t("gspc", 2), _t("sp500", 2))
        dj_p  = _first(_t("dji", 0),  _t("dow", 0))
        dj_c  = _first(_t("dji", 2),  _t("dow", 2))
        nq_p  = _first(_t("ndx", 0),  _t("nasdaq", 0))
        nq_c  = _first(_t("ndx", 2),  _t("nasdaq", 2))

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

# ── Market calendar ───────────────────────────────────────────────────────────

def _easter(year: int) -> date:
    """Return the date of Easter Sunday for the given year (Anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(114 + h + l - 7 * m, 31)
    return date(year, month, day + 1)


def _nyse_holidays(year: int) -> set[date]:
    """Return the set of NYSE market holidays for a given year."""

    def _observed(d: date) -> date:
        """Shift a holiday to the nearest weekday if it falls on a weekend."""
        if d.weekday() == 5:   # Saturday → Friday
            return d - timedelta(days=1)
        if d.weekday() == 6:   # Sunday → Monday
            return d + timedelta(days=1)
        return d

    def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
        """Return the nth occurrence (1-based) of weekday (Mon=0) in the given month."""
        first = date(year, month, 1)
        delta = (weekday - first.weekday()) % 7
        return first + timedelta(days=delta + (n - 1) * 7)

    def _last_weekday(year: int, month: int, weekday: int) -> date:
        """Return the last occurrence of weekday in the given month."""
        # Start from the last day of the month and go backwards
        if month == 12:
            last = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last = date(year, month + 1, 1) - timedelta(days=1)
        delta = (last.weekday() - weekday) % 7
        return last - timedelta(days=delta)

    holidays = {
        _observed(date(year, 1, 1)),                       # New Year's Day
        _nth_weekday(year, 1, 0, 3),                       # MLK Day (3rd Mon Jan)
        _nth_weekday(year, 2, 0, 3),                       # Presidents' Day (3rd Mon Feb)
        _easter(year) - timedelta(days=2),                 # Good Friday
        _last_weekday(year, 5, 0),                         # Memorial Day (last Mon May)
        _observed(date(year, 6, 19)),                      # Juneteenth
        _observed(date(year, 7, 4)),                       # Independence Day
        _nth_weekday(year, 9, 0, 1),                       # Labor Day (1st Mon Sep)
        _nth_weekday(year, 11, 3, 4),                      # Thanksgiving (4th Thu Nov)
        _observed(date(year, 12, 25)),                     # Christmas Day
    }
    return holidays


def is_market_open(today: date | None = None) -> bool:
    """Return True if the US stock market (NYSE) is open on *today* (ET date)."""
    if today is None:
        today = datetime.now(ET).date()
    if today.weekday() >= 5:          # Saturday=5, Sunday=6
        return False
    return today not in _nyse_holidays(today.year)

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

    if not is_market_open(now.date()):
        log.info(f"Market closed today ({now.date()}) — skipping run.")
        print(f"Market closed today ({now.date()}) — skipping run.")
        sys.exit(0)

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

    # Prediction markets (Polymarket + Kalshi — public read-only endpoints)
    data["prediction_markets"] = {
        "polymarket": fetch_polymarket(),
        "kalshi":     fetch_kalshi(),
    }

    # Anomaly detection (pure Python — always free)
    flags = detect_anomalies(data)
    if flags:
        data["anomaly_alert"] = generate_anomaly_alert(flags)
    else:
        data["anomaly_alert"] = None
        print("  No anomalies detected")

    # AI market content (Claude Haiku — low cost)
    ai = generate_market_analysis(data)
    data["ai_analysis"] = ai["analysis"]
    data["watch_item"]  = ai["watch"]

    # Build content — use AI subject when available, fall back to static
    ai_subject = ai["subject"] or f"Market Pulse — {now.strftime('%b %-d, %Y')}"
    subject = f"{'[TEST] ' if TEST_MODE else ''}📊 {ai_subject}"
    print(f"  Subject: {subject}")

    # Send
    for addr in EMAIL_TO:
        try:
            html  = build_html(data, now, HTML_ROOT_URL)
            plain = build_plain(data, now)
            result = send_email(subject, html, plain, addr)
            log.info(f"Sent to {addr} — message_id: {result.get('id')}")
            print(f"✓ Sent to {addr}")
        except requests.RequestException as e:
            status = e.response.status_code if getattr(e, "response", None) is not None else "N/A"
            log.error(f"Failed to send to {addr}: {status} {e}")
        except Exception as e:
            log.error(f"Failed to send to {addr}: {e}")

    if CREATE_HTML_OUTPUT_FILE and HTML_OUTPUT_DIR:
        try:
            archive_html = build_html(data, now, HTML_ROOT_URL)
            os.makedirs(HTML_OUTPUT_DIR, exist_ok=True)
            filename = f"{HTML_OUTPUT_DIR}/output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(archive_html)
                log.info(f"Saved HTML output to {filename}")
                print(f"✓ Saved HTML output to {filename}")
        except Exception as e:
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
