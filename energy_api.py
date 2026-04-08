"""
Energy API module
Handles data fetching from EIA (Energy Information Administration) API
"""

import logging
import os
import requests

log = logging.getLogger(__name__)

EIA_API_KEY = os.environ.get("EIA_API_KEY", "")

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