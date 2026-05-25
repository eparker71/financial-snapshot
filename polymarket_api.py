"""
Polymarket API module.
Fetches Bitcoin prediction market odds from Polymarket's public Gamma API.
No auth required for read-only market data.
"""

import json
import logging
import re
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"
TIMEOUT = (10, 15)  # (connect, read)

ET = ZoneInfo("America/New_York")


def _today_et() -> datetime:
    return datetime.now(ET)


def _slug_config() -> dict:
    """Build the slug/event identifiers we want to fetch.

    Polymarket slugs encode the year / month, so derive them at runtime.
    The 150K-binary slug is the highest-volume single binary at the time of
    writing; update annually when a new dated binary supersedes it.
    """
    now = _today_et()
    year = now.year
    next_year = year + 1
    month = now.strftime("%B").lower()  # e.g. "may"

    return {
        "events": {
            # Multi-outcome year forecast (~30 strike buckets, each a YES/NO child market)
            "year_forecast": f"what-price-will-bitcoin-hit-before-{next_year}",
            # Multi-outcome monthly high (~20 strikes for the current month)
            "monthly_high":  f"what-price-will-bitcoin-hit-in-{month}-{year}",
            # Date-bucketed "when will BTC hit 150K" event
            "when_150k":     "when-will-bitcoin-hit-150k",
        },
        "markets": {
            # Single-binary 150K market (top Polymarket BTC volume as of 2026)
            "150k_binary": "will-bitcoin-hit-150k-by-june-30-2026",
        },
    }


def _parse_prices(raw: str | list | None) -> list[float]:
    """outcomePrices ships as a JSON-encoded string. Defensively handle both forms."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [float(x) for x in raw]
    try:
        return [float(x) for x in json.loads(raw)]
    except Exception:
        return []


def _parse_outcomes(raw: str | list | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        return [str(x) for x in json.loads(raw)]
    except Exception:
        return []


def _short_strike(question: str) -> str:
    """Extract a compact strike label from a child market question.

    e.g. "Will Bitcoin reach $200,000 by December 31, 2026?" -> "$200K"
         "Will Bitcoin hit $150k by June 30, 2026?"          -> "$150K"
         falls back to the first 40 chars of the question.
    """
    m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)\s*k?", question, re.IGNORECASE)
    if not m:
        return question[:40]
    num_str = m.group(1).replace(",", "")
    try:
        val = float(num_str)
    except ValueError:
        return question[:40]
    # If question contained "k" suffix, treat as thousands as-is. Otherwise
    # detect scale by magnitude.
    if "k" in m.group(0).lower():
        return f"${int(val)}K"
    if val >= 1000:
        return f"${int(val/1000)}K"
    return f"${int(val)}"


def _normalize_event(event: dict, market_id: str) -> dict | None:
    """Reduce a Polymarket event (with N child binary markets) into one normalized market."""
    if not event:
        return None
    markets = event.get("markets") or []
    outcomes = []
    for m in markets:
        if m.get("closed") or m.get("archived"):
            continue
        prices = _parse_prices(m.get("outcomePrices"))
        if not prices:
            continue
        yes_price = prices[0]  # YES is first by Polymarket convention
        outcomes.append({
            "label":       _short_strike(m.get("question", "")),
            "price":       yes_price,
            "implied_pct": round(yes_price * 100, 1),
        })
    if not outcomes:
        return None
    # Headline outcome = highest implied probability — usually the most-likely strike bucket.
    outcomes.sort(key=lambda o: o["implied_pct"], reverse=True)
    return {
        "id":         market_id,
        "platform":   "polymarket",
        "title":      event.get("title") or "",
        "outcomes":   outcomes,
        "volume_usd": float(event.get("volume24hr") or 0),
        "end_date":   (event.get("endDate") or "")[:10],
    }


def _normalize_binary_market(market: dict, market_id: str) -> dict | None:
    """Reduce a single Polymarket binary market into the normalized shape."""
    if not market:
        return None
    prices = _parse_prices(market.get("outcomePrices"))
    labels = _parse_outcomes(market.get("outcomes")) or ["Yes", "No"]
    if not prices:
        return None
    outcomes = [
        {"label": labels[i] if i < len(labels) else f"Outcome {i+1}",
         "price": p,
         "implied_pct": round(p * 100, 1)}
        for i, p in enumerate(prices)
    ]
    return {
        "id":         market_id,
        "platform":   "polymarket",
        "title":      market.get("question") or market.get("title") or "",
        "outcomes":   outcomes,
        "volume_usd": float(market.get("volume24hr") or 0),
        "end_date":   (market.get("endDate") or "")[:10],
    }


def _fetch_event(slug: str) -> dict | None:
    try:
        r = requests.get(f"{GAMMA_BASE}/events", params={"slug": slug}, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
    except Exception as e:
        log.warning(f"Polymarket event fetch failed for slug={slug}: {e}")
    return None


def _fetch_market(slug: str) -> dict | None:
    try:
        r = requests.get(f"{GAMMA_BASE}/markets", params={"slug": slug}, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
    except Exception as e:
        log.warning(f"Polymarket market fetch failed for slug={slug}: {e}")
    return None


def fetch_polymarket() -> dict:
    """Fetch all configured Polymarket BTC markets.

    Returns:
        {
            "markets": [ normalized_market, ... ],
            "error": str | None,   # set when ALL fetches failed
        }
    """
    cfg = _slug_config()
    normalized: list[dict] = []
    failures = 0
    attempts = 0

    for key, slug in cfg["events"].items():
        attempts += 1
        ev = _fetch_event(slug)
        nm = _normalize_event(ev, market_id=f"poly:{slug}")
        if nm:
            normalized.append(nm)
        else:
            failures += 1
            log.warning(f"Polymarket event {key} ({slug}) returned no usable data")

    for key, slug in cfg["markets"].items():
        attempts += 1
        m = _fetch_market(slug)
        nm = _normalize_binary_market(m, market_id=f"poly:{slug}")
        if nm:
            normalized.append(nm)
        else:
            failures += 1
            log.warning(f"Polymarket market {key} ({slug}) returned no usable data")

    error = None
    if normalized:
        log.info(f"Polymarket: fetched {len(normalized)}/{attempts} markets")
    else:
        error = "Polymarket data unavailable"
        log.warning(f"Polymarket: all {attempts} fetches failed")

    return {"markets": normalized, "error": error}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    result = fetch_polymarket()
    print(json.dumps(result, indent=2))
