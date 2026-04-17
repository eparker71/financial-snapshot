"""Export helpers for financial snapshot data."""

import logging
from datetime import datetime

from models import Snapshot

log = logging.getLogger(__name__)


def flatten_data_for_csv(data: dict, timestamp: datetime) -> dict:
    """Flatten the nested data dict into a single-level dict suitable for CSV."""
    flat = {"timestamp": timestamp.isoformat()}

    # Crypto
    flat["btc_price"] = data.get("btc_price")
    flat["btc_change_pct"] = data.get("btc_change_pct")
    flat["eth_price"] = data.get("eth_price")
    flat["eth_change_pct"] = data.get("eth_change_pct")
    flat["sol_price"] = data.get("sol_price")
    flat["sol_change_pct"] = data.get("sol_change_pct")
    flat["xrp_price"] = data.get("xrp_price")
    flat["xrp_change_pct"] = data.get("xrp_change_pct")
    flat["ada_price"] = data.get("ada_price")
    flat["ada_change_pct"] = data.get("ada_change_pct")
    fg_val, fg_label = data.get("fear_greed", (None, None))
    flat["fear_greed_value"] = fg_val
    flat["fear_greed_label"] = fg_label

    # Energy
    gas_price, diesel_price, gas_period = data.get("gas", (None, None, None))
    flat["gas_price"] = gas_price
    flat["diesel_price"] = diesel_price
    flat["gas_period"] = gas_period
    oil_p, oil_c, oil_pct = data.get("oil", (None, None, None))
    flat["oil_price"] = oil_p
    flat["oil_change"] = oil_c
    flat["oil_change_pct"] = oil_pct

    # Metals
    gold_p, gold_c, gold_pct = data.get("gold", (None, None, None))
    flat["gold_price"] = gold_p
    flat["gold_change"] = gold_c
    flat["gold_change_pct"] = gold_pct
    silv_p, silv_c, silv_pct = data.get("silver", (None, None, None))
    flat["silver_price"] = silv_p
    flat["silver_change"] = silv_c
    flat["silver_change_pct"] = silv_pct

    # Currencies
    jpyusd_p, jpyusd_c, jpyusd_pct = data.get("usdjpy", (None, None, None))
    flat["usdjpy_price"] = jpyusd_p
    flat["usdjpy_change"] = jpyusd_c
    flat["usdjpy_change_pct"] = jpyusd_pct
    eurusd_p, eurusd_c, eurusd_pct = data.get("eurusd", (None, None, None))
    flat["eurusd_price"] = eurusd_p
    flat["eurusd_change"] = eurusd_c
    flat["eurusd_change_pct"] = eurusd_pct

    # Bonds & Interest Rates
    t2_p, t2_c, t2_pct = data.get("t2y", (None, None, None))
    flat["t2y_yield"] = t2_p
    flat["t2y_change"] = t2_c
    flat["t2y_change_pct"] = t2_pct
    t10_p, t10_c, t10_pct = data.get("t10y", (None, None, None))
    flat["t10y_yield"] = t10_p
    flat["t10y_change"] = t10_c
    flat["t10y_change_pct"] = t10_pct
    mort_val, mort_mom, _ = data.get("ev_mortgage", (None, None, None))
    flat["mortgage_rate"] = mort_val
    flat["mortgage_mom_change"] = mort_mom
    cc_val, cc_mom, _ = data.get("ev_credit_card", (None, None, None))
    flat["credit_card_apr"] = cc_val
    flat["credit_card_mom_change"] = cc_mom

    # Futures (market closed)
    dj_p, dj_c, dj_pct = data.get("dow", (None, None, None))
    flat["dow_futures_price"] = dj_p
    flat["dow_futures_change"] = dj_c
    flat["dow_futures_change_pct"] = dj_pct
    sp_p, sp_c, sp_pct = data.get("sp500", (None, None, None))
    flat["sp500_futures_price"] = sp_p
    flat["sp500_futures_change"] = sp_c
    flat["sp500_futures_change_pct"] = sp_pct
    nq_p, nq_c, nq_pct = data.get("nasdaq", (None, None, None))
    flat["nasdaq_futures_price"] = nq_p
    flat["nasdaq_futures_change"] = nq_c
    flat["nasdaq_futures_change_pct"] = nq_pct
    rty_p, rty_c, rty_pct = data.get("russell", (None, None, None))
    flat["russell_futures_price"] = rty_p
    flat["russell_futures_change"] = rty_c
    flat["russell_futures_change_pct"] = rty_pct

    # Live indices (market open)
    dji_p, dji_c, dji_pct = data.get("dji", (None, None, None))
    flat["dji_price"] = dji_p
    flat["dji_change"] = dji_c
    flat["dji_change_pct"] = dji_pct
    gspc_p, gspc_c, gspc_pct = data.get("gspc", (None, None, None))
    flat["gspc_price"] = gspc_p
    flat["gspc_change"] = gspc_c
    flat["gspc_change_pct"] = gspc_pct
    ndx_p, ndx_c, ndx_pct = data.get("ndx", (None, None, None))
    flat["ndx_price"] = ndx_p
    flat["ndx_change"] = ndx_c
    flat["ndx_change_pct"] = ndx_pct
    rut_p, rut_c, rut_pct = data.get("rut", (None, None, None))
    flat["rut_price"] = rut_p
    flat["rut_change"] = rut_c
    flat["rut_change_pct"] = rut_pct

    # Volatility
    vix_p, vix_c, vix_pct = data.get("vix", (None, None, None))
    flat["vix_price"] = vix_p
    flat["vix_change"] = vix_c
    flat["vix_change_pct"] = vix_pct

    # Magnificent 7
    for ticker in ("aapl", "msft", "amzn", "googl", "meta", "tsla", "nvda"):
        p, c, pct = data.get(ticker, (None, None, None))
        flat[f"{ticker}_price"] = p
        flat[f"{ticker}_change"] = c
        flat[f"{ticker}_change_pct"] = pct

    # Consumer Prices
    eggs_val, eggs_mom, eggs_date = data.get("ev_eggs", (None, None, None))
    flat["eggs_price"] = eggs_val
    flat["eggs_mom_change"] = eggs_mom
    flat["eggs_date"] = eggs_date
    milk_val, milk_mom, milk_date = data.get("ev_milk", (None, None, None))
    flat["milk_price"] = milk_val
    flat["milk_mom_change"] = milk_mom
    flat["milk_date"] = milk_date
    cpi_food_pct, cpi_food_date = data.get("ev_cpi_food", (None, None))
    flat["cpi_food_yoy"] = cpi_food_pct
    flat["cpi_food_date"] = cpi_food_date
    cpi_shelter_pct, cpi_shelter_date = data.get("ev_cpi_shelter", (None, None))
    flat["cpi_shelter_yoy"] = cpi_shelter_pct
    flat["cpi_shelter_date"] = cpi_shelter_date

    # Macro Economy
    cpi_all_pct, cpi_all_date = data.get("ev_cpi_all", (None, None))
    flat["cpi_all_yoy"] = cpi_all_pct
    flat["cpi_all_date"] = cpi_all_date
    unemp_val, unemp_mom, _ = data.get("ev_unemployment", (None, None, None))
    flat["unemployment_rate"] = unemp_val
    flat["unemployment_mom_change"] = unemp_mom
    debt_val, debt_prev, debt_change, debt_date = data.get("national_debt", (None, None, None, None))
    flat["national_debt"] = debt_val
    flat["national_debt_prev"] = debt_prev
    flat["national_debt_change"] = debt_change
    flat["national_debt_date"] = debt_date
    gdp_level, gdp_date, gdp_growth, gdp_growth_prev, gdp_growth_date = data.get("ev_gdp", (None, None, None, None, None))
    flat["gdp_level"] = gdp_level
    flat["gdp_date"] = gdp_date
    flat["gdp_growth_qoq"] = gdp_growth
    flat["gdp_growth_prev"] = gdp_growth_prev
    flat["gdp_growth_date"] = gdp_growth_date

    # AI Analysis
    flat["ai_analysis"]   = data.get("ai_analysis")
    flat["watch_item"]    = data.get("watch_item")
    flat["anomaly_alert"] = data.get("anomaly_alert")

    return flat


def save_to_db(data: dict, timestamp: datetime):
    """Save the flattened snapshot data to SQLite."""
    flat = flatten_data_for_csv(data, timestamp)
    flat["timestamp"] = timestamp  # use datetime object, not isoformat string
    try:
        Snapshot.create(**flat)
        log.info("Saved snapshot to database")
        print("✓ Saved snapshot to database")
    except Exception as e:
        log.error(f"Failed to save snapshot to database: {e}")
        print(f"✗ Failed to save snapshot to database: {e}")


