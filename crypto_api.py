"""
Cryptocurrency API module
Handles data fetching from CoinGecko and Alternative.me APIs
"""

import logging
import requests

log = logging.getLogger(__name__)

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