"""
Yahoo Finance API module
Handles data fetching from Yahoo Finance using yfinance library
"""

import logging
import yfinance as yf

log = logging.getLogger(__name__)

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

def fetch_yahoo_data():
    """Fetch all Yahoo Finance data points."""
    ticker_map = {
        "gold":    "GC=F",
        "silver":  "SI=F",
        "oil":     "CL=F",
        "usdjpy":  "JPY=X",
        "eurusd":  "EURUSD=X",
        "t2y":     "^IRX",
        "t10y":    "^TNX",
        # Futures (shown when market closed)
        "dow":     "YM=F",
        "sp500":   "ES=F",
        "nasdaq":  "NQ=F",
        "russell": "RTY=F",
        # Live indices (shown when market open)
        "dji":     "^DJI",
        "gspc":    "^GSPC",
        "ndx":     "^NDX",
        "rut":     "^RUT",
        "vix":     "^VIX",
        # Magnificent 7
        "aapl":  "AAPL",
        "msft":  "MSFT",
        "amzn":  "AMZN",
        "googl": "GOOGL",
        "meta":  "META",
        "tsla":  "TSLA",
        "nvda":  "NVDA",
        # Sector ETFs (SPDR)
        "xlc":  "XLC",
        "xlp":  "XLP",
        "xli":  "XLI",
        "xlb":  "XLB",
        "xlre": "XLRE",
        "xlu":  "XLU",
        "xle":  "XLE",
        # Industry ETFs (narrower than broad sectors)
        "smh":  "SMH",
        "xbi":  "XBI",
        "kre":  "KRE",
        "xhb":  "XHB",
    }

    data = {}
    for key, symbol in ticker_map.items():
        data[key] = yf_price(symbol)

    return data