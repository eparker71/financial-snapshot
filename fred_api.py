"""
FRED API module
Handles data fetching from Federal Reserve Economic Data (FRED) API
"""

import logging
import os
import requests

log = logging.getLogger(__name__)

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
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

    # ── GDP ───────────────────────────────────────────────────────────────────
    # Real GDP growth rate (QoQ annualized %) — the headline number people cite
    gdp_level, _, gdp_date   = _fred_mom("GDP")                  # level in $B
    _, gdp_growth, _          = _fred_yoy("A191RL1Q225SBEA")     # real growth rate %
    # For growth we want the latest value, not YoY — reuse _fred_mom
    gdp_obs = _fred_fetch("A191RL1Q225SBEA", limit=2)
    gdp_growth_latest = float(gdp_obs[0]["value"]) if gdp_obs else None
    gdp_growth_prev   = float(gdp_obs[1]["value"]) if len(gdp_obs) > 1 else None
    gdp_growth_date   = gdp_obs[0]["date"] if gdp_obs else None
    result["ev_gdp"] = (gdp_level, gdp_date, gdp_growth_latest, gdp_growth_prev, gdp_growth_date)

    return result