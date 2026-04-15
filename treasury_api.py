"""
Treasury API module
Handles data fetching from US Treasury Fiscal Data API
"""

import logging
import requests

log = logging.getLogger(__name__)

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
        if len(records) < 2:
            log.warning("National debt API returned fewer than 2 records")
            return None, None, None, None
        latest  = float(records[0]["tot_pub_debt_out_amt"])
        prev    = float(records[1]["tot_pub_debt_out_amt"])
        date    = records[0]["record_date"]
        change  = latest - prev
        return latest, prev, change, date
    except Exception as e:
        log.warning(f"National debt fetch error: {e}")
        return None, None, None, None