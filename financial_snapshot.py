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
from datetime import datetime, time
from zoneinfo import ZoneInfo

import yfinance as yf
import zoneinfo

# ── Config ────────────────────────────────────────────────────────────────────
# API keys — set as environment variables, never hardcode
AGENTMAIL_API_KEY  = os.environ.get("AGENTMAIL_API_KEY", "YOUR_AGENTMAIL_API_KEY")
AGENTMAIL_INBOX_ID = os.environ.get("AGENTMAIL_INBOX_ID", "YOUR_INBOX_ID")
EIA_API_KEY        = os.environ.get("EIA_API_KEY", "")     # free at eia.gov/api
FRED_API_KEY       = os.environ.get("FRED_API_KEY", "")    # free at fred.stlouisfed.org

# Non-sensitive config — managed in settings.py
from settings import TEST_MODE, TEST_EMAIL, RECIPIENTS, LOG_FILE_PATH
#LOG_FILE = os.environ.get("LOG_FILE", LOG_FILE)  # env var still overrides if set
LOG_FILE = LOG_FILE_PATH


logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# Resolve recipient list — TEST_MODE sends only to TEST_EMAIL
EMAIL_TO = [TEST_EMAIL] if TEST_MODE else RECIPIENTS
if TEST_MODE:
    print(f"⚠️  TEST MODE — sending only to {TEST_EMAIL}")

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_market_closed() -> bool:
    now = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return True
    market_open  = time(9, 30)
    market_close = time(16, 0)
    if not (market_open <= now.time() <= market_close):
        return True
    return False

def fmt_price(val, decimals=2, prefix="$"):
    if val is None:
        return "N/A"
    return f"{prefix}{val:,.{decimals}f}"

def fmt_change(val, pct, decimals=2):
    if val is None or pct is None:
        return ""
    sign = "+" if val >= 0 else ""
    return f"({sign}{val:,.{decimals}f}, {sign}{pct:.2f}%)"

def fmt_pct_change(pct, suffix="% MoM", decimals=2):
    """Format a plain percentage change into the (+X.XX% ...) style used by row()."""
    if pct is None:
        return ""
    sign = "+" if pct >= 0 else ""
    return f"({sign}{pct:.{decimals}f}{suffix})"

def yf_price(symbol):
    """Return (last_price, change, change_pct) or (None, None, None)."""
    try:
        t  = yf.Ticker(symbol)
        fi = t.fast_info
        price = fi.last_price
        prev  = fi.previous_close
        if price is None or prev is None:
            return None, None, None
        change = price - prev
        pct    = (change / prev) * 100
        return price, change, pct
    except Exception as e:
        log.warning(f"yf_price error for {symbol}: {e}")
        return None, None, None

def yf_rate(symbol):
    return yf_price(symbol)

# ── Data fetchers ─────────────────────────────────────────────────────────────

def fetch_crypto():
    """BTC and ETH via CoinGecko /coins/markets (no key needed)."""
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": "bitcoin,ethereum",
        "order": "market_cap_desc",
        "per_page": 2,
        "page": 1,
        "sparkline": False,
        "price_change_percentage": "24h",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = {item["id"]: item for item in r.json()}
        btc  = data.get("bitcoin", {})
        eth  = data.get("ethereum", {})
        return {
            "btc_price":      btc.get("current_price"),
            "btc_change_pct": btc.get("price_change_percentage_24h"),
            "eth_price":      eth.get("current_price"),
            "eth_change_pct": eth.get("price_change_percentage_24h"),
        }
    except Exception as e:
        log.warning(f"CoinGecko error: {e}")
        return {}

def fetch_fear_greed():
    """Crypto Fear & Greed Index via alternative.me."""
    try:
        r     = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        r.raise_for_status()
        entry = r.json()["data"][0]
        return int(entry["value"]), entry["value_classification"]
    except Exception as e:
        log.warning(f"Fear & Greed error: {e}")
        return None, None

def _eia_fetch_price(product_code: str) -> tuple:
    """Fetch a single EIA weekly fuel price by product code. Returns (price, period) or (None, None)."""
    if not EIA_API_KEY:
        return None, None
    url = (
        f"https://api.eia.gov/v2/petroleum/pri/gnd/data/"
        f"?api_key={EIA_API_KEY}"
        f"&frequency=weekly"
        f"&data[0]=value"
        f"&facets[product][]={product_code}"
        f"&facets[duoarea][]=NUS"
        f"&sort[0][column]=period"
        f"&sort[0][direction]=desc"
        f"&length=1"
    )
    for attempt in range(2):
        try:
            r = requests.get(url, timeout=45)
            r.raise_for_status()
            row = r.json()["response"]["data"][0]
            return float(row["value"]), row["period"]
        except requests.Timeout:
            log.warning(f"EIA timeout attempt {attempt + 1} for {product_code}")
            continue
        except Exception as e:
            log.warning(f"EIA price error for {product_code}: {e}")
            return None, None
    log.warning(f"EIA price failed after 2 attempts for {product_code}")
    return None, None

def fetch_gas():
    """US avg regular gas and diesel prices via EIA. Returns (gas_price, diesel_price, period)."""
    gas_price,    gas_period    = _eia_fetch_price("EPMR")   # Regular unleaded
    diesel_price, diesel_period = _eia_fetch_price("EPD2D")  # No. 2 on-highway diesel
    period = gas_period or diesel_period
    return gas_price, diesel_price, period

def fetch_national_debt():
    """
    US national debt (to the penny) from the Treasury Fiscal Data API.
    No API key required. Updated each business day.
    Returns (debt_usd, date_str) or (None, None).
    """
    url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
    params = {
        "fields":     "record_date,tot_pub_debt_out_amt",
        "sort":       "-record_date",
        "page[size]": 2,  # latest + previous for day-over-day change
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        records = r.json()["data"]
        latest  = float(records[0]["tot_pub_debt_out_amt"])
        prev    = float(records[1]["tot_pub_debt_out_amt"])
        date    = records[0]["record_date"]
        change  = latest - prev
        return latest, prev, change, date
    except Exception as e:
        log.warning(f"National debt fetch error: {e}")
        return None, None, None, None


# ── FRED / Everyday Economy ───────────────────────────────────────────────────
#
#  All series IDs reference BLS data published through FRED.
#  Prices (eggs, milk) are monthly and typically lag 2-4 weeks.
#  Gas is already covered by EIA above — not duplicated here.
#
#  Series reference:
#    APU0000708111  Eggs, Grade A Large, per dozen
#    APU0000709112  Milk, whole, per gallon
#    CPIAUCSL       CPI All Items (used for YoY headline inflation)
#    CUUR0000SAF11  CPI Food at Home (grocery inflation)
#    CUUR0000SEHA   CPI Shelter
#    MORTGAGE30US   30-Year Fixed Mortgage Rate (weekly)
#    TERMCBCCALLNS  Credit Card Interest Rate (quarterly)
#    UNRATE         Unemployment Rate

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

def _fred_fetch(series_id: str, limit: int = 14) -> list[dict]:
    """Return up to `limit` most-recent valid observations for a FRED series."""
    if not FRED_API_KEY:
        return []
    try:
        r = requests.get(FRED_BASE, params={
            "series_id":  series_id,
            "api_key":    FRED_API_KEY,
            "file_type":  "json",
            "sort_order": "desc",
            "limit":      limit,
        }, timeout=10)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        # Filter out FRED placeholder "." values for missing data
        return [o for o in obs if o.get("value") not in (".", "", None)]
    except Exception as e:
        log.warning(f"FRED fetch error ({series_id}): {e}")
        return []

def _fred_mom(series_id: str):
    """Latest value + month-over-month % change. Returns (value, mom_pct, date) or Nones."""
    obs = _fred_fetch(series_id, limit=3)
    if len(obs) < 2:
        return None, None, None
    latest = float(obs[0]["value"])
    prev   = float(obs[1]["value"])
    mom    = ((latest - prev) / prev) * 100 if prev else None
    return latest, mom, obs[0]["date"]

def _fred_yoy(series_id: str):
    """Latest value + year-over-year % change. Returns (value, yoy_pct, date) or Nones."""
    obs = _fred_fetch(series_id, limit=14)
    if len(obs) < 13:
        return None, None, None
    latest   = float(obs[0]["value"])
    year_ago = float(obs[12]["value"])
    yoy      = ((latest - year_ago) / year_ago) * 100 if year_ago else None
    return latest, yoy, obs[0]["date"]

def fetch_everyday_economy() -> dict:
    """
    Fetch all FRED-sourced everyday economy indicators.
    Returns a flat dict that gets merged into the main data dict.
    Keys prefixed with 'ev_' to avoid collisions.
    """
    if not FRED_API_KEY:
        log.info("FRED_API_KEY not set — skipping everyday economy section.")
        return {}

    result = {}

    # ── Grocery prices (monthly BLS data via FRED) ────────────────────────────
    for key, series_id in [("ev_eggs", "APU0000708111"), ("ev_milk", "APU0000709112")]:
        val, mom_pct, date = _fred_mom(series_id)
        result[key] = (val, mom_pct, date)

    # ── Inflation indexes (YoY %) ─────────────────────────────────────────────
    for key, series_id in [
        ("ev_cpi_all",     "CPIAUCSL"),
        ("ev_cpi_food",    "CUUR0000SAF11"),
        ("ev_cpi_shelter", "CUUR0000SEHA"),
    ]:
        _, yoy_pct, date = _fred_yoy(series_id)
        result[key] = (yoy_pct, date)

    # ── Interest rates (MoM change in percentage points) ─────────────────────
    for key, series_id in [
        ("ev_mortgage",    "MORTGAGE30US"),
        ("ev_credit_card", "TERMCBCCALLNS"),
    ]:
        val, mom_pct, date = _fred_mom(series_id)
        result[key] = (val, mom_pct, date)

    # ── Unemployment ──────────────────────────────────────────────────────────
    val, mom_pct, date = _fred_mom("UNRATE")
    result["ev_unemployment"] = (val, mom_pct, date)

    return result

# ── HTML builder ──────────────────────────────────────────────────────────────

def build_html(data: dict, now: datetime) -> str:
    date_str = now.strftime("%B %-d, %Y %-I:%M %p ET")

    def row(label, value, change_str="", sub="", invert=False):
        """
        invert=False (default): up = green, down = red  (stocks, crypto, metals)
        invert=True:            up = red,  down = green  (VIX, rates, inflation, unemployment)
        """
        if change_str:
            is_up = change_str.startswith("(+")
            is_good = (is_up and not invert) or (not is_up and invert)
            color = "#1a7a1a" if is_good else "#cc0000"
            change_str = f"<span style='color:{color};'>{change_str}</span>"
        chg_html = f"<span class='chg'>{change_str}</span>" if change_str else ""
        sub_html = f"<span class='sub'>{sub}</span>" if sub else ""
        return f"""
        <tr>
          <td class="label">{label}</td>
          <td class="val">{value} {chg_html}{sub_html}</td>
        </tr>"""

    def section(title, rows_html):
        return f"""
        <div class="section-title">{title}</div>
        <table>
          <tbody>{rows_html}
          </tbody>
        </table>"""

    market_closed = is_market_closed()
    market_open   = not market_closed

    # ── Crypto ────────────────────────────────────────────────────────────────
    btc_pct = data.get("btc_change_pct")
    eth_pct = data.get("eth_change_pct")
    fg_val, fg_label = data.get("fear_greed", (None, None))

    crypto_rows = (
        row("Bitcoin (BTC)",
            fmt_price(data.get("btc_price")),
            f"({'+' if (btc_pct or 0) >= 0 else ''}{btc_pct:.2f}% 24h)" if btc_pct else "")
        + row("Ethereum (ETH)",
            fmt_price(data.get("eth_price")),
            f"({'+' if (eth_pct or 0) >= 0 else ''}{eth_pct:.2f}% 24h)" if eth_pct else "")
        + row("Fear &amp; Greed",
            f"{fg_val} – {fg_label}" if fg_val is not None else "N/A")
    )

    # ── Energy ────────────────────────────────────────────────────────────────
    gas_price, diesel_price, gas_period = data.get("gas", (None, None, None))
    energy_rows = (
        row("US Avg Gas (regular)",
            f"${gas_price:.3f}/gal" if gas_price else "N/A",
            sub=f"EIA week ending {gas_period}" if gas_period else "EIA (add EIA_API_KEY for live data)")
        + row("US Avg Diesel",
            f"${diesel_price:.3f}/gal" if diesel_price else "N/A",
            sub=f"EIA week ending {gas_period}" if gas_period else "")
    )

    # ── Metals & Commodities ──────────────────────────────────────────────────
    gold_p, gold_c, gold_pct   = data.get("gold",   (None, None, None))
    silv_p, silv_c, silv_pct   = data.get("silver",  (None, None, None))
    oil_p,  oil_c,  oil_pct    = data.get("oil",     (None, None, None))

    metals_rows = (
        row("Gold (GC=F)",       fmt_price(gold_p, 2), fmt_change(gold_c, gold_pct))
        + row("Silver (SI=F)",   fmt_price(silv_p, 2), fmt_change(silv_c, silv_pct))
        + row("Crude Oil (WTI)", fmt_price(oil_p, 2),  fmt_change(oil_c,  oil_pct))
    )

    # ── Currencies ────────────────────────────────────────────────────────────
    jpyusd_p, jpyusd_c, jpyusd_pct = data.get("usdjpy",  (None, None, None))
    eurusd_p, eurusd_c, eurusd_pct = data.get("eurusd",  (None, None, None))

    fx_rows = (
        row("USD/JPY", fmt_price(jpyusd_p, 2, prefix="¥"), fmt_change(jpyusd_c, jpyusd_pct))
        + row("EUR/USD", fmt_price(eurusd_p, 4, prefix=""),  fmt_change(eurusd_c, eurusd_pct))
    )

    # ── Bonds ─────────────────────────────────────────────────────────────────
    t2_p,  t2_c,  t2_pct  = data.get("t2y",  (None, None, None))
    t10_p, t10_c, t10_pct = data.get("t10y", (None, None, None))

    bond_rows = (
        row("US 2-Year Treasury",  f"{t2_p:.3f}%"  if t2_p  else "N/A", fmt_change(t2_c,  t2_pct,  3), invert=True)
        + row("US 10-Year Treasury", f"{t10_p:.3f}%" if t10_p else "N/A", fmt_change(t10_c, t10_pct, 3), invert=True)
    )

    # ── Futures ───────────────────────────────────────────────────────────────
    dj_p,  dj_c,  dj_pct   = data.get("dow",     (None, None, None))
    sp_p,  sp_c,  sp_pct   = data.get("sp500",   (None, None, None))
    nq_p,  nq_c,  nq_pct   = data.get("nasdaq",  (None, None, None))
    rty_p, rty_c, rty_pct  = data.get("russell", (None, None, None))

    futures_rows = (
        row("Dow Jones (YM=F)",      fmt_price(dj_p,  2), fmt_change(dj_c,  dj_pct))
        + row("S&amp;P 500 (ES=F)",  fmt_price(sp_p,  2), fmt_change(sp_c,  sp_pct))
        + row("Nasdaq 100 (NQ=F)",   fmt_price(nq_p,  2), fmt_change(nq_c,  nq_pct))
        + row("Russell 2000 (RTY=F)",fmt_price(rty_p, 2), fmt_change(rty_c, rty_pct))
    )

    # ── VIX ───────────────────────────────────────────────────────────────────
    vix_p, vix_c, vix_pct = data.get("vix", (None, None, None))
    vol_rows = row("VIX", fmt_price(vix_p, 2, prefix=""), fmt_change(vix_c, vix_pct), invert=True)

    # ── Everyday Economy (FRED) ───────────────────────────────────────────────
    # National debt
    debt_val, debt_prev, debt_change, debt_date = data.get("national_debt", (None, None, None, None))

    # Grocery prices
    eggs_val, eggs_mom, eggs_date = data.get("ev_eggs",        (None, None, None))
    milk_val, milk_mom, milk_date = data.get("ev_milk",        (None, None, None))

    # Inflation (YoY %)
    cpi_all_pct,     cpi_all_date     = data.get("ev_cpi_all",     (None, None))
    cpi_food_pct,    cpi_food_date    = data.get("ev_cpi_food",    (None, None))
    cpi_shelter_pct, cpi_shelter_date = data.get("ev_cpi_shelter", (None, None))

    # Rates
    mort_val, mort_mom, _     = data.get("ev_mortgage",    (None, None, None))
    cc_val,   cc_mom,   _     = data.get("ev_credit_card", (None, None, None))

    # Unemployment
    unemp_val, unemp_mom, _  = data.get("ev_unemployment", (None, None, None))

    everyday_rows = ""

    # National debt
    if debt_val is not None:
        debt_trillions = debt_val / 1e12
        change_billions = debt_change / 1e9 if debt_change is not None else None
        change_str = f"({'+' if (change_billions or 0) >= 0 else ''}{change_billions:,.1f}B DoD)" if change_billions is not None else ""
        everyday_rows += row(
            "US National Debt",
            f"${debt_trillions:,.2f}T",
            change_str,
            sub=f"US Treasury · as of {debt_date}",
            invert=True
        )

    # Grocery prices — note data lag so readers aren't confused
    if eggs_val is not None:
        everyday_rows += row(
            "Eggs, Grade A Large",
            f"${eggs_val:.2f}/doz",
            fmt_pct_change(eggs_mom, suffix="% MoM"),
            sub=f"BLS monthly · latest: {eggs_date}",
            invert=True
        )
    if milk_val is not None:
        everyday_rows += row(
            "Milk, whole",
            f"${milk_val:.2f}/gal",
            fmt_pct_change(milk_mom, suffix="% MoM"),
            sub=f"BLS monthly · latest: {milk_date}",
            invert=True
        )

    # Inflation
    if cpi_all_pct is not None:
        everyday_rows += row(
            "CPI – All Items",
            fmt_pct_change(cpi_all_pct, suffix="% YoY"),
            sub=f"Headline inflation · {cpi_all_date}",
            invert=True
        )
    if cpi_food_pct is not None:
        everyday_rows += row(
            "CPI – Food at Home",
            fmt_pct_change(cpi_food_pct, suffix="% YoY"),
            sub=f"Grocery inflation · {cpi_food_date}",
            invert=True
        )
    if cpi_shelter_pct is not None:
        everyday_rows += row(
            "CPI – Shelter",
            fmt_pct_change(cpi_shelter_pct, suffix="% YoY"),
            sub=f"Rent &amp; housing costs · {cpi_shelter_date}",
            invert=True
        )

    # Rates
    if mort_val is not None:
        everyday_rows += row(
            "30-Year Mortgage Rate",
            f"{mort_val:.2f}%",
            fmt_pct_change(mort_mom, suffix="pp MoM"),
            sub="Freddie Mac weekly average",
            invert=True
        )
    if cc_val is not None:
        everyday_rows += row(
            "Credit Card APR",
            f"{cc_val:.2f}%",
            fmt_pct_change(cc_mom, suffix="pp MoM"),
            sub="Fed avg interest rate on revolving balances",
            invert=True
        )

    # Unemployment
    if unemp_val is not None:
        everyday_rows += row(
            "Unemployment Rate",
            f"{unemp_val:.1f}%",
            fmt_pct_change(unemp_mom, suffix="pp MoM"),
            invert=True
        )

    # Only render the section if FRED returned data
    everyday_section = section("🛒 Everyday Economy", everyday_rows) if everyday_rows else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">

<style>
  body      {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
               background: #ffffff; color: #111111; margin: 0; padding: 20px; font-size: 16px; }}
  .wrap     {{ max-width: 560px; margin: 0 auto; }}
  h1        {{ font-size: 20px; font-weight: 700; color: #000; margin: 0 0 4px; }}
  h2        {{ font-size: 16px; font-weight: 600; color: #333; margin: 0 0 16px; }}
  .gen      {{ font-size: 13px; color: #555; margin-bottom: 24px; }}
  .section-title {{ font-size: 13px; font-weight: 700; text-transform: uppercase;
               letter-spacing: .05em; padding: 8px 12px 6px;
               color: #111; border-bottom: 2px solid #111; margin: 0; }}
  table     {{ width: 100%; border-collapse: collapse; margin: 0 0 20px 0; }}
  /*tbody tr  {{ border-bottom: 1px solid #e5e5e5; }}*/
  tbody tr:last-child {{ border-bottom: none; }}
  td        {{ padding: 2px 12px; font-size: 14px; vertical-align: top; }}
  td.label  {{ color: #444; width: 50%; }}
  td.val    {{ color: #111; font-variant-numeric: tabular-nums; font-weight: 500; }}
  .chg      {{ font-size: 13px; margin-left: 6px; font-weight: 400; }}
  .sub      {{ display: block; color: #888; font-size: 12px; margin-top: 2px; font-weight: 400; }}
  .footer   {{ font-size: 12px; color: #999; text-align: center; margin-top: 24px;
               border-top: 1px solid #e5e5e5; padding-top: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>📊 Daily Financial Snapshot</h1>
  <div class="gen">Generated {date_str}</div>
  {"<h2>Market Closed</h2>" if market_closed else "<h2>Market Open</h2>"}
  {section("📈 US Market Futures", futures_rows) if market_closed else ''}
  {section("⚡ Volatility", vol_rows) if market_open else ''}
  {section("🪙 Cryptocurrencies", crypto_rows)}
  {section("⛽ Energy", energy_rows)}
  {section("🥇 Metals &amp; Commodities", metals_rows)}
  {section("💱 Currencies", fx_rows)}
  {section("🏦 Bonds / Interest Rates", bond_rows)}
  {everyday_section}

  <div class="footer">Data sourced from CoinGecko, Yahoo Finance, Alternative.me, EIA, FRED/BLS &nbsp;·&nbsp;
  Not financial advice</div>
</div>
</body>
</html>"""

# ── Plain-text builder ────────────────────────────────────────────────────────

def build_plain(data: dict, now: datetime) -> str:
    date_str = now.strftime("%B %-d, %Y %-I:%M %p ET")

    def p(label, val, chg=""):
        return f"  {label}: {val} {chg}".rstrip() + "\n"

    btc_pct = data.get("btc_change_pct")
    eth_pct = data.get("eth_change_pct")
    fg_val, fg_label = data.get("fear_greed", (None, None))
    gas_price, diesel_price, gas_period = data.get("gas", (None, None, None))

    gold_p, gold_c, gold_pct   = data.get("gold",    (None, None, None))
    silv_p, silv_c, silv_pct   = data.get("silver",  (None, None, None))
    oil_p,  oil_c,  oil_pct    = data.get("oil",     (None, None, None))
    jpyusd_p, jpyusd_c, jpyusd_pct = data.get("usdjpy",  (None, None, None))
    eurusd_p, eurusd_c, eurusd_pct = data.get("eurusd",  (None, None, None))
    t2_p,  t2_c,  t2_pct   = data.get("t2y",   (None, None, None))
    t10_p, t10_c, t10_pct  = data.get("t10y",  (None, None, None))
    dj_p,  dj_c,  dj_pct   = data.get("dow",   (None, None, None))
    sp_p,  sp_c,  sp_pct   = data.get("sp500", (None, None, None))
    nq_p,  nq_c,  nq_pct   = data.get("nasdaq",(None, None, None))
    rty_p, rty_c, rty_pct  = data.get("russell",(None,None, None))
    vix_p, vix_c, vix_pct  = data.get("vix",   (None, None, None))

    # Everyday economy
    eggs_val,  eggs_mom,  _ = data.get("ev_eggs",        (None, None, None))
    milk_val,  milk_mom,  _ = data.get("ev_milk",        (None, None, None))
    cpi_all_pct,     _      = data.get("ev_cpi_all",     (None, None))
    cpi_food_pct,    _      = data.get("ev_cpi_food",    (None, None))
    cpi_shelter_pct, _      = data.get("ev_cpi_shelter", (None, None))
    mort_val, mort_mom, _   = data.get("ev_mortgage",    (None, None, None))
    cc_val,   cc_mom,   _   = data.get("ev_credit_card", (None, None, None))
    unemp_val, unemp_mom, _ = data.get("ev_unemployment",(None, None, None))

    lines = [f"Daily Financial Snapshot\nGenerated: {date_str}\n"]

    lines.append("CRYPTOCURRENCIES\n")
    lines.append(p("Bitcoin (BTC)", fmt_price(data.get("btc_price")),
                   f"({'+' if (btc_pct or 0)>=0 else ''}{btc_pct:.2f}% 24h)" if btc_pct else ""))
    lines.append(p("Ethereum (ETH)", fmt_price(data.get("eth_price")),
                   f"({'+' if (eth_pct or 0)>=0 else ''}{eth_pct:.2f}% 24h)" if eth_pct else ""))
    lines.append(p("Fear & Greed", f"{fg_val} ({fg_label})" if fg_val else "N/A"))

    lines.append("\nENERGY\n")
    lines.append(p("US Avg Gas (regular)", f"${gas_price:.3f}/gal" if gas_price else "N/A"))
    lines.append(p("US Avg Diesel",        f"${diesel_price:.3f}/gal" if diesel_price else "N/A"))

    lines.append("\nMETALS & COMMODITIES\n")
    lines.append(p("Gold",        fmt_price(gold_p), fmt_change(gold_c, gold_pct)))
    lines.append(p("Silver",      fmt_price(silv_p), fmt_change(silv_c, silv_pct)))
    lines.append(p("Crude (WTI)", fmt_price(oil_p),  fmt_change(oil_c,  oil_pct)))

    lines.append("\nCURRENCIES\n")
    lines.append(p("USD/JPY", fmt_price(jpyusd_p, 2, ""), fmt_change(jpyusd_c, jpyusd_pct)))
    lines.append(p("EUR/USD", fmt_price(eurusd_p, 4, ""), fmt_change(eurusd_c, eurusd_pct)))

    lines.append("\nBONDS / INTEREST RATES\n")
    lines.append(p("US 2Y Treasury",  f"{t2_p:.3f}%"  if t2_p  else "N/A", fmt_change(t2_c,  t2_pct,  3)))
    lines.append(p("US 10Y Treasury", f"{t10_p:.3f}%" if t10_p else "N/A", fmt_change(t10_c, t10_pct, 3)))

    lines.append("\nMARKET FUTURES\n")
    lines.append(p("Dow Jones (YM=F)",    fmt_price(dj_p),  fmt_change(dj_c,  dj_pct)))
    lines.append(p("S&P 500 (ES=F)",      fmt_price(sp_p),  fmt_change(sp_c,  sp_pct)))
    lines.append(p("Nasdaq 100 (NQ=F)",   fmt_price(nq_p),  fmt_change(nq_c,  nq_pct)))
    lines.append(p("Russell 2000 (RTY=F)",fmt_price(rty_p), fmt_change(rty_c, rty_pct)))

    lines.append("\nVOLATILITY\n")
    lines.append(p("VIX", fmt_price(vix_p, 2, ""), fmt_change(vix_c, vix_pct)))

    # Only include section if FRED data came back
    debt_val, debt_prev, debt_change, debt_date = data.get("national_debt", (None, None, None, None))

    if any(v is not None for v in [debt_val, eggs_val, milk_val, cpi_all_pct, mort_val, unemp_val]):
        lines.append("\nEVERYDAY ECONOMY  (FRED/BLS · prices are monthly, may lag 2-4 wks)\n")

        if debt_val is not None:
            debt_trillions   = debt_val / 1e12
            change_billions  = debt_change / 1e9 if debt_change is not None else None
            chg_str = f"({'+' if (change_billions or 0) >= 0 else ''}{change_billions:,.1f}B DoD)" if change_billions is not None else ""
            lines.append(p("US National Debt", f"${debt_trillions:,.2f}T", chg_str))

        if eggs_val is not None:
            lines.append(p("Eggs, Grade A Large (doz)", f"${eggs_val:.2f}",
                           fmt_pct_change(eggs_mom, suffix="% MoM")))
        if milk_val is not None:
            lines.append(p("Milk, whole (gal)", f"${milk_val:.2f}",
                           fmt_pct_change(milk_mom, suffix="% MoM")))

        lines.append("")
        if cpi_all_pct is not None:
            lines.append(p("CPI – All Items (YoY)", fmt_pct_change(cpi_all_pct, suffix="% YoY")))
        if cpi_food_pct is not None:
            lines.append(p("CPI – Food at Home (YoY)", fmt_pct_change(cpi_food_pct, suffix="% YoY")))
        if cpi_shelter_pct is not None:
            lines.append(p("CPI – Shelter (YoY)", fmt_pct_change(cpi_shelter_pct, suffix="% YoY")))

        lines.append("")
        if mort_val is not None:
            lines.append(p("30-Year Mortgage Rate", f"{mort_val:.2f}%",
                           fmt_pct_change(mort_mom, suffix="pp MoM")))
        if cc_val is not None:
            lines.append(p("Credit Card APR", f"{cc_val:.2f}%",
                           fmt_pct_change(cc_mom, suffix="pp MoM")))
        if unemp_val is not None:
            lines.append(p("Unemployment Rate", f"{unemp_val:.1f}%",
                           fmt_pct_change(unemp_mom, suffix="pp MoM")))

    return "".join(lines)

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

    # yfinance tickers
    ticker_map = {
        "gold":    "GC=F",
        "silver":  "SI=F",
        "oil":     "CL=F",
        "usdjpy":  "JPY=X",
        "eurusd":  "EURUSD=X",
        "t2y":     "^IRX",
        "t10y":    "^TNX",
        "dow":     "YM=F",
        "sp500":   "ES=F",
        "nasdaq":  "NQ=F",
        "russell": "RTY=F",
        "vix":     "^VIX",
    }

    for key, symbol in ticker_map.items():
        data[key] = yf_price(symbol)

    # Build content
    subject = f"{'[TEST] ' if TEST_MODE else ''}📊 Financial Snapshot — {now.strftime('%b %-d, %Y')}"
    html  = build_html(data, now)
    plain = build_plain(data, now)

    # Send
    for addr in EMAIL_TO:
        try:
            result = send_email(subject, html, plain, addr)
            log.info(f"Sent to {addr} — message_id: {result.get('id')}")
            print(f"✓ Sent to {addr}")
        except requests.HTTPError as e:
            log.error(f"Failed to send to {addr}: {e.response.status_code} {e.response.text}")


if __name__ == "__main__":
    main()
