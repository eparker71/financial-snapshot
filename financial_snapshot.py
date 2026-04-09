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
from settings import TEST_MODE, TEST_EMAIL, RECIPIENTS, LOG_FILE, HTML_OUTPUT, HTML_PATH, HTML_ROOT_URL
#LOG_FILE = os.environ.get("LOG_FILE", LOG_FILE)  # env var still overrides if set
LOG_FILE = LOG_FILE


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
    oil_p, oil_c, oil_pct = data.get("oil", (None, None, None))

    energy_rows = (
        row("US Avg Gas (regular)",
            f"${gas_price:.3f}/gal" if gas_price else "N/A",
            sub=f"EIA week ending {gas_period}" if gas_period else "EIA (add EIA_API_KEY for live data)")
        + row("US Avg Diesel",
            f"${diesel_price:.3f}/gal" if diesel_price else "N/A",
            sub=f"EIA week ending {gas_period}" if gas_period else "")
        + row("Crude Oil (WTI)", fmt_price(oil_p, 2), fmt_change(oil_c, oil_pct))
    )

    # ── Metals ────────────────────────────────────────────────────────────────
    gold_p, gold_c, gold_pct = data.get("gold",   (None, None, None))
    silv_p, silv_c, silv_pct = data.get("silver", (None, None, None))

    metals_rows = (
        row("Gold (GC=F)",     fmt_price(gold_p, 2), fmt_change(gold_c, gold_pct))
        + row("Silver (SI=F)", fmt_price(silv_p, 2), fmt_change(silv_c, silv_pct))
    )

    # ── Currencies ────────────────────────────────────────────────────────────
    jpyusd_p, jpyusd_c, jpyusd_pct = data.get("usdjpy", (None, None, None))
    eurusd_p, eurusd_c, eurusd_pct = data.get("eurusd", (None, None, None))

    fx_rows = (
        row("USD/JPY", fmt_price(jpyusd_p, 2, prefix="¥"), fmt_change(jpyusd_c, jpyusd_pct))
        + row("EUR/USD", fmt_price(eurusd_p, 4, prefix=""),  fmt_change(eurusd_c, eurusd_pct))
    )

    # ── Bonds & Interest Rates ────────────────────────────────────────────────
    t2_p,  t2_c,  t2_pct  = data.get("t2y",  (None, None, None))
    t10_p, t10_c, t10_pct = data.get("t10y", (None, None, None))
    mort_val, mort_mom, _  = data.get("ev_mortgage",    (None, None, None))
    cc_val,   cc_mom,   _  = data.get("ev_credit_card", (None, None, None))

    bond_rows = (
        row("US 2-Year Treasury",  f"{t2_p:.3f}%"  if t2_p  else "N/A", fmt_change(t2_c,  t2_pct,  3), invert=True)
        + row("US 10-Year Treasury", f"{t10_p:.3f}%" if t10_p else "N/A", fmt_change(t10_c, t10_pct, 3), invert=True)
    )
    if mort_val is not None:
        bond_rows += row("30-Year Mortgage Rate", f"{mort_val:.2f}%",
            fmt_pct_change(mort_mom, suffix="pp MoM"),
            sub="Freddie Mac weekly average", invert=True)
    if cc_val is not None:
        bond_rows += row("Credit Card APR", f"{cc_val:.2f}%",
            fmt_pct_change(cc_mom, suffix="pp MoM"),
            sub="Fed avg interest rate on revolving balances", invert=True)

    # ── Futures (market closed) ───────────────────────────────────────────────
    dj_p,  dj_c,  dj_pct  = data.get("dow",     (None, None, None))
    sp_p,  sp_c,  sp_pct  = data.get("sp500",   (None, None, None))
    nq_p,  nq_c,  nq_pct  = data.get("nasdaq",  (None, None, None))
    rty_p, rty_c, rty_pct = data.get("russell", (None, None, None))

    futures_rows = (
        row("Dow Jones (YM=F)",      fmt_price(dj_p,  2), fmt_change(dj_c,  dj_pct))
        + row("S&amp;P 500 (ES=F)",  fmt_price(sp_p,  2), fmt_change(sp_c,  sp_pct))
        + row("Nasdaq 100 (NQ=F)",   fmt_price(nq_p,  2), fmt_change(nq_c,  nq_pct))
        + row("Russell 2000 (RTY=F)",fmt_price(rty_p, 2), fmt_change(rty_c, rty_pct))
    )

    # ── Live indices (market open) ────────────────────────────────────────────
    dji_p,  dji_c,  dji_pct  = data.get("dji",  (None, None, None))
    gspc_p, gspc_c, gspc_pct = data.get("gspc", (None, None, None))
    ndx_p,  ndx_c,  ndx_pct  = data.get("ndx",  (None, None, None))
    rut_p,  rut_c,  rut_pct  = data.get("rut",  (None, None, None))

    index_rows = (
        row("Dow Jones (^DJI)",      fmt_price(dji_p,  2), fmt_change(dji_c,  dji_pct))
        + row("S&amp;P 500 (^GSPC)", fmt_price(gspc_p, 2), fmt_change(gspc_c, gspc_pct))
        + row("Nasdaq 100 (^NDX)",   fmt_price(ndx_p,  2), fmt_change(ndx_c,  ndx_pct))
        + row("Russell 2000 (^RUT)", fmt_price(rut_p,  2), fmt_change(rut_c,  rut_pct))
    )

    # ── VIX ───────────────────────────────────────────────────────────────────
    vix_p, vix_c, vix_pct = data.get("vix", (None, None, None))
    vol_rows = row("VIX", fmt_price(vix_p, 2, prefix=""), fmt_change(vix_c, vix_pct), invert=True)

    # ── Consumer Prices (FRED/BLS) ────────────────────────────────────────────
    eggs_val, eggs_mom, eggs_date     = data.get("ev_eggs",        (None, None, None))
    milk_val, milk_mom, milk_date     = data.get("ev_milk",        (None, None, None))
    cpi_food_pct,    cpi_food_date    = data.get("ev_cpi_food",    (None, None))
    cpi_shelter_pct, cpi_shelter_date = data.get("ev_cpi_shelter", (None, None))

    consumer_rows = ""
    if eggs_val is not None:
        consumer_rows += row("Eggs, Grade A Large", f"${eggs_val:.2f}/doz",
            fmt_pct_change(eggs_mom, suffix="% MoM"),
            sub=f"BLS monthly · latest: {eggs_date}", invert=True)
    if milk_val is not None:
        consumer_rows += row("Milk, whole", f"${milk_val:.2f}/gal",
            fmt_pct_change(milk_mom, suffix="% MoM"),
            sub=f"BLS monthly · latest: {milk_date}", invert=True)
    if cpi_food_pct is not None:
        consumer_rows += row("CPI – Food at Home", fmt_pct_change(cpi_food_pct, suffix="% YoY"),
            sub=f"Grocery inflation · {cpi_food_date}", invert=True)
    if cpi_shelter_pct is not None:
        consumer_rows += row("CPI – Shelter", fmt_pct_change(cpi_shelter_pct, suffix="% YoY"),
            sub=f"Rent &amp; housing costs · {cpi_shelter_date}", invert=True)
    consumer_section = section("🛒 Consumer Prices", consumer_rows) if consumer_rows else ""

    # ── Macro Economy ─────────────────────────────────────────────────────────
    cpi_all_pct, cpi_all_date                              = data.get("ev_cpi_all",     (None, None))
    unemp_val, unemp_mom, _                                = data.get("ev_unemployment",(None, None, None))
    debt_val, debt_prev, debt_change, debt_date            = data.get("national_debt",  (None, None, None, None))
    gdp_level, gdp_date, gdp_growth, gdp_growth_prev, gdp_growth_date = data.get("ev_gdp", (None, None, None, None, None))

    macro_rows = ""
    if gdp_growth is not None:
        gdp_level_str = f"${gdp_level/1000:.2f}T" if gdp_level is not None else ""
        macro_rows += row("Real GDP Growth",
            fmt_pct_change(gdp_growth, suffix="% QoQ ann."),
            sub=f"BEA quarterly · {gdp_growth_date}" + (f" · level: {gdp_level_str}" if gdp_level_str else ""))
    if cpi_all_pct is not None:
        macro_rows += row("CPI – All Items", fmt_pct_change(cpi_all_pct, suffix="% YoY"),
            sub=f"Headline inflation · {cpi_all_date}", invert=True)
    if unemp_val is not None:
        macro_rows += row("Unemployment Rate", f"{unemp_val:.1f}%",
            fmt_pct_change(unemp_mom, suffix="pp MoM"), invert=True)
    if debt_val is not None:
        debt_trillions  = debt_val / 1e12
        change_billions = debt_change / 1e9 if debt_change is not None else None
        chg_str = f"({'+' if (change_billions or 0) >= 0 else ''}{change_billions:,.1f}B DoD)" if change_billions is not None else ""
        macro_rows += row("US National Debt", f"${debt_trillions:,.2f}T", chg_str,
            sub=f"US Treasury · as of {debt_date}", invert=True)
    macro_section = section("📉 Macro Economy", macro_rows) if macro_rows else ""
    t2_p,  t2_c,  t2_pct  = data.get("t2y",  (None, None, None))
    t10_p, t10_c, t10_pct = data.get("t10y", (None, None, None))
    mort_val, mort_mom, _  = data.get("ev_mortgage",    (None, None, None))
    cc_val,   cc_mom,   _  = data.get("ev_credit_card", (None, None, None))

    bond_rows = (
        row("US 2-Year Treasury",  f"{t2_p:.3f}%"  if t2_p  else "N/A", fmt_change(t2_c,  t2_pct,  3), invert=True)
        + row("US 10-Year Treasury", f"{t10_p:.3f}%" if t10_p else "N/A", fmt_change(t10_c, t10_pct, 3), invert=True)
    )
    if mort_val is not None:
        bond_rows += row("30-Year Mortgage Rate", f"{mort_val:.2f}%",
            fmt_pct_change(mort_mom, suffix="pp MoM"),
            sub="Freddie Mac weekly average", invert=True)
    if cc_val is not None:
        bond_rows += row("Credit Card APR", f"{cc_val:.2f}%",
            fmt_pct_change(cc_mom, suffix="pp MoM"),
            sub="Fed avg interest rate on revolving balances", invert=True)

    # ── Consumer Prices (FRED/BLS) ────────────────────────────────────────────
    eggs_val, eggs_mom, eggs_date     = data.get("ev_eggs",        (None, None, None))
    milk_val, milk_mom, milk_date     = data.get("ev_milk",        (None, None, None))
    cpi_food_pct,    cpi_food_date    = data.get("ev_cpi_food",    (None, None))
    cpi_shelter_pct, cpi_shelter_date = data.get("ev_cpi_shelter", (None, None))

    consumer_rows = ""
    if eggs_val is not None:
        consumer_rows += row("Eggs, Grade A Large", f"${eggs_val:.2f}/doz",
            fmt_pct_change(eggs_mom, suffix="% MoM"),
            sub=f"BLS monthly · latest: {eggs_date}", invert=True)
    if milk_val is not None:
        consumer_rows += row("Milk, whole", f"${milk_val:.2f}/gal",
            fmt_pct_change(milk_mom, suffix="% MoM"),
            sub=f"BLS monthly · latest: {milk_date}", invert=True)
    if cpi_food_pct is not None:
        consumer_rows += row("CPI – Food at Home", fmt_pct_change(cpi_food_pct, suffix="% YoY"),
            sub=f"Grocery inflation · {cpi_food_date}", invert=True)
    if cpi_shelter_pct is not None:
        consumer_rows += row("CPI – Shelter", fmt_pct_change(cpi_shelter_pct, suffix="% YoY"),
            sub=f"Rent &amp; housing costs · {cpi_shelter_date}", invert=True)
    consumer_section = section("🛒 Consumer Prices", consumer_rows) if consumer_rows else ""

    # ── Macro Economy ─────────────────────────────────────────────────────────
    cpi_all_pct, cpi_all_date                         = data.get("ev_cpi_all",     (None, None))
    unemp_val, unemp_mom, _                            = data.get("ev_unemployment",(None, None, None))
    debt_val, debt_prev, debt_change, debt_date        = data.get("national_debt",  (None, None, None, None))
    gdp_level, gdp_date, gdp_growth, gdp_growth_prev, gdp_growth_date = data.get("ev_gdp", (None, None, None, None, None))

    macro_rows = ""
    if gdp_growth is not None:
        gdp_chg = f"({'+' if gdp_growth >= 0 else ''}{gdp_growth:.1f}% QoQ ann.)"
        gdp_prev_str = f"prior quarter: {gdp_growth_prev:+.1f}%" if gdp_growth_prev is not None else ""
        gdp_level_str = f"${gdp_level/1000:.2f}T" if gdp_level is not None else ""
        macro_rows += row("Real GDP Growth", gdp_chg,
            sub=f"BEA quarterly · {gdp_growth_date}" + (f" · level: {gdp_level_str}" if gdp_level_str else ""))
    if cpi_all_pct is not None:
        macro_rows += row("CPI – All Items", fmt_pct_change(cpi_all_pct, suffix="% YoY"),
            sub=f"Headline inflation · {cpi_all_date}", invert=True)
    if unemp_val is not None:
        macro_rows += row("Unemployment Rate", f"{unemp_val:.1f}%",
            fmt_pct_change(unemp_mom, suffix="pp MoM"), invert=True)
    if debt_val is not None:
        debt_trillions  = debt_val / 1e12
        change_billions = debt_change / 1e9 if debt_change is not None else None
        chg_str = f"({'+' if (change_billions or 0) >= 0 else ''}{change_billions:,.1f}B DoD)" if change_billions is not None else ""
        macro_rows += row("US National Debt", f"${debt_trillions:,.2f}T", chg_str,
            sub=f"US Treasury · as of {debt_date}", invert=True)
    macro_section = section("📉 Macro Economy", macro_rows) if macro_rows else ""

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
  {section("📈 US Market Futures", futures_rows) if market_closed else section("📈 US Markets", index_rows)}
  {section("⚡ Volatility", vol_rows) if market_open else ''}
  {section("🪙 Cryptocurrencies", crypto_rows)}
  {section("⛽ Energy", energy_rows)}
  {section("🥇 Metals", metals_rows)}
  {section("💱 Currencies", fx_rows)}
  {section("🏦 Bonds &amp; Interest Rates", bond_rows)}
  {consumer_section}
  {macro_section}

  <div class="footer">Data sourced from CoinGecko, Yahoo Finance, Alternative.me, EIA, FRED/BLS &nbsp;·&nbsp;
  Not financial advice
  <a href="{HTML_ROOT_URL}" target="_blank">View in previous days browser</a>
  </div>
</div>
</body>
</html>"""

# ── Plain-text builder ────────────────────────────────────────────────────────

def build_plain(data: dict, now: datetime) -> str:
    date_str = now.strftime("%B %-d, %Y %-I:%M %p ET")

    def p(label, val, chg=""):
        return f"  {label}: {val} {chg}".rstrip() + "\n"

    market_closed = is_market_closed()

    btc_pct = data.get("btc_change_pct")
    eth_pct = data.get("eth_change_pct")
    fg_val, fg_label                    = data.get("fear_greed",    (None, None))
    gas_price, diesel_price, gas_period = data.get("gas",           (None, None, None))
    gold_p,  gold_c,  gold_pct          = data.get("gold",          (None, None, None))
    silv_p,  silv_c,  silv_pct          = data.get("silver",        (None, None, None))
    oil_p,   oil_c,   oil_pct           = data.get("oil",           (None, None, None))
    jpyusd_p, jpyusd_c, jpyusd_pct      = data.get("usdjpy",        (None, None, None))
    eurusd_p, eurusd_c, eurusd_pct      = data.get("eurusd",        (None, None, None))
    t2_p,  t2_c,  t2_pct               = data.get("t2y",           (None, None, None))
    t10_p, t10_c, t10_pct              = data.get("t10y",          (None, None, None))
    vix_p, vix_c, vix_pct              = data.get("vix",           (None, None, None))
    # Futures
    dj_p,  dj_c,  dj_pct              = data.get("dow",            (None, None, None))
    sp_p,  sp_c,  sp_pct              = data.get("sp500",          (None, None, None))
    nq_p,  nq_c,  nq_pct              = data.get("nasdaq",         (None, None, None))
    rty_p, rty_c, rty_pct             = data.get("russell",        (None, None, None))
    # Live indices
    dji_p,  dji_c,  dji_pct           = data.get("dji",            (None, None, None))
    gspc_p, gspc_c, gspc_pct          = data.get("gspc",           (None, None, None))
    ndx_p,  ndx_c,  ndx_pct           = data.get("ndx",            (None, None, None))
    rut_p,  rut_c,  rut_pct           = data.get("rut",            (None, None, None))
    # FRED
    eggs_val,  eggs_mom,  _            = data.get("ev_eggs",        (None, None, None))
    milk_val,  milk_mom,  _            = data.get("ev_milk",        (None, None, None))
    cpi_all_pct,      _                = data.get("ev_cpi_all",     (None, None))
    cpi_food_pct,     _                = data.get("ev_cpi_food",    (None, None))
    cpi_shelter_pct,  _                = data.get("ev_cpi_shelter", (None, None))
    mort_val,  mort_mom,  _            = data.get("ev_mortgage",    (None, None, None))
    cc_val,    cc_mom,    _            = data.get("ev_credit_card", (None, None, None))
    unemp_val, unemp_mom, _            = data.get("ev_unemployment",(None, None, None))
    gdp_level, gdp_date, gdp_growth, gdp_growth_prev, gdp_growth_date = data.get("ev_gdp", (None, None, None, None, None))
    debt_val, debt_prev, debt_change, debt_date = data.get("national_debt", (None, None, None, None))

    lines = [f"Daily Financial Snapshot\nGenerated: {date_str}\n"]
    lines.append("Market Open\n" if not market_closed else "Market Closed\n")

    if market_closed:
        lines.append("\nMARKET FUTURES\n")
        lines.append(p("Dow Jones (YM=F)",     fmt_price(dj_p),  fmt_change(dj_c,  dj_pct)))
        lines.append(p("S&P 500 (ES=F)",       fmt_price(sp_p),  fmt_change(sp_c,  sp_pct)))
        lines.append(p("Nasdaq 100 (NQ=F)",    fmt_price(nq_p),  fmt_change(nq_c,  nq_pct)))
        lines.append(p("Russell 2000 (RTY=F)", fmt_price(rty_p), fmt_change(rty_c, rty_pct)))
    else:
        lines.append("\nUS MARKETS\n")
        lines.append(p("Dow Jones (^DJI)",     fmt_price(dji_p),  fmt_change(dji_c,  dji_pct)))
        lines.append(p("S&P 500 (^GSPC)",      fmt_price(gspc_p), fmt_change(gspc_c, gspc_pct)))
        lines.append(p("Nasdaq 100 (^NDX)",    fmt_price(ndx_p),  fmt_change(ndx_c,  ndx_pct)))
        lines.append(p("Russell 2000 (^RUT)",  fmt_price(rut_p),  fmt_change(rut_c,  rut_pct)))
        lines.append("\nVOLATILITY\n")
        lines.append(p("VIX", fmt_price(vix_p, 2, ""), fmt_change(vix_c, vix_pct)))

    lines.append("\nCRYPTOCURRENCIES\n")
    lines.append(p("Bitcoin (BTC)", fmt_price(data.get("btc_price")),
                   f"({'+' if (btc_pct or 0)>=0 else ''}{btc_pct:.2f}% 24h)" if btc_pct else ""))
    lines.append(p("Ethereum (ETH)", fmt_price(data.get("eth_price")),
                   f"({'+' if (eth_pct or 0)>=0 else ''}{eth_pct:.2f}% 24h)" if eth_pct else ""))
    lines.append(p("Fear & Greed", f"{fg_val} ({fg_label})" if fg_val else "N/A"))

    lines.append("\nENERGY\n")
    lines.append(p("US Avg Gas (regular)", f"${gas_price:.3f}/gal"    if gas_price    else "N/A"))
    lines.append(p("US Avg Diesel",        f"${diesel_price:.3f}/gal" if diesel_price else "N/A"))
    lines.append(p("Crude Oil (WTI)",      fmt_price(oil_p), fmt_change(oil_c, oil_pct)))

    lines.append("\nMETALS\n")
    lines.append(p("Gold",   fmt_price(gold_p), fmt_change(gold_c, gold_pct)))
    lines.append(p("Silver", fmt_price(silv_p), fmt_change(silv_c, silv_pct)))

    lines.append("\nCURRENCIES\n")
    lines.append(p("USD/JPY", fmt_price(jpyusd_p, 2, ""), fmt_change(jpyusd_c, jpyusd_pct)))
    lines.append(p("EUR/USD", fmt_price(eurusd_p, 4, ""), fmt_change(eurusd_c, eurusd_pct)))

    lines.append("\nBONDS & INTEREST RATES\n")
    lines.append(p("US 2Y Treasury",  f"{t2_p:.3f}%"  if t2_p  else "N/A", fmt_change(t2_c,  t2_pct,  3)))
    lines.append(p("US 10Y Treasury", f"{t10_p:.3f}%" if t10_p else "N/A", fmt_change(t10_c, t10_pct, 3)))
    if mort_val is not None:
        lines.append(p("30-Year Mortgage Rate", f"{mort_val:.2f}%", fmt_pct_change(mort_mom, suffix="pp MoM")))
    if cc_val is not None:
        lines.append(p("Credit Card APR",       f"{cc_val:.2f}%",   fmt_pct_change(cc_mom,   suffix="pp MoM")))

    if any(v is not None for v in [eggs_val, milk_val, cpi_food_pct, cpi_shelter_pct]):
        lines.append("\nCONSUMER PRICES  (BLS monthly · may lag 2-4 wks)\n")
        if eggs_val is not None:
            lines.append(p("Eggs, Grade A Large (doz)", f"${eggs_val:.2f}", fmt_pct_change(eggs_mom, suffix="% MoM")))
        if milk_val is not None:
            lines.append(p("Milk, whole (gal)",         f"${milk_val:.2f}", fmt_pct_change(milk_mom, suffix="% MoM")))
        if cpi_food_pct is not None:
            lines.append(p("CPI – Food at Home (YoY)",  fmt_pct_change(cpi_food_pct,    suffix="% YoY")))
        if cpi_shelter_pct is not None:
            lines.append(p("CPI – Shelter (YoY)",       fmt_pct_change(cpi_shelter_pct, suffix="% YoY")))

    if any(v is not None for v in [gdp_growth, cpi_all_pct, unemp_val, debt_val]):
        lines.append("\nMACRO ECONOMY\n")
        if gdp_growth is not None:
            gdp_level_str = f"  (level: ${gdp_level/1000:.2f}T)" if gdp_level is not None else ""
            lines.append(p("Real GDP Growth", fmt_pct_change(gdp_growth, suffix="% QoQ ann."),
                           f"· {gdp_growth_date}{gdp_level_str}"))
        if cpi_all_pct is not None:
            lines.append(p("CPI – All Items (YoY)", fmt_pct_change(cpi_all_pct, suffix="% YoY")))
        if unemp_val is not None:
            lines.append(p("Unemployment Rate",     f"{unemp_val:.1f}%", fmt_pct_change(unemp_mom, suffix="pp MoM")))
        if debt_val is not None:
            debt_trillions  = debt_val / 1e12
            change_billions = debt_change / 1e9 if debt_change is not None else None
            chg_str = f"({'+' if (change_billions or 0) >= 0 else ''}{change_billions:,.1f}B DoD)" if change_billions is not None else ""
            lines.append(p("US National Debt", f"${debt_trillions:,.2f}T", chg_str))

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

    # Yahoo Finance data
    yahoo_data = fetch_yahoo_data()
    data.update(yahoo_data)

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
    
    if HTML_OUTPUT:
        try:
            filename = f"{HTML_PATH}/output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(html)
                log.info(f"Saved HTML output to {filename}")
                print(f"✓ Saved HTML output to {filename}")
        except OSError as e:
            log.error(f"Failed to write HTML file: {e}")
            print(f"✗ Failed to save HTML output: {e}")

if __name__ == "__main__":
    main()
