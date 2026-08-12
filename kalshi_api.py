"""
Kalshi API module.
Fetches Bitcoin prediction market odds from Kalshi's public market data
endpoints. No auth required for read-only data; KALSHI_API_KEY is reserved
for future use (trade history, account-scoped endpoints).

Kalshi recently migrated price fields to `*_dollars` and `*_fp` suffixes —
the legacy unsuffixed fields return None on active markets. Always read the
suffixed variants.
"""

import calendar
import logging
import os
import re
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
TIMEOUT = (10, 15)
ET = ZoneInfo("America/New_York")

KALSHI_API_KEY = os.environ.get("KALSHI_API_KEY", "")


def _today_et() -> datetime:
    return datetime.now(ET)


def _monthly_event_ticker() -> str:
    """Build the current-month BTC monthly-high event ticker.

    Pattern observed: KXBTCMAXMON-BTC-<YY><MMM><DD>, last day of month uppercased.
    Example for May 2026: KXBTCMAXMON-BTC-26MAY31
    """
    now = _today_et()
    last_day = calendar.monthrange(now.year, now.month)[1]
    yy = now.strftime("%y")
    mon = now.strftime("%b").upper()
    return f"KXBTCMAXMON-BTC-{yy}{mon}{last_day:02d}"


def _event_config() -> dict:
    """Event tickers we want to fetch. Map of human label -> Kalshi event_ticker.

    WARNING: annual_high and above_200k encode the year and stop resolving after
    Jan 2027 — update them annually (the run only logs a warning when they die).
    """
    return {
        "annual_high":   "KXBTCMAXY-26DEC31",       # Multi-outcome: highest strike BTC hits in 2026
        "eoy_level":     "KXBTCY-27JAN0100",        # Multi-outcome: BTC closing price at end of 2026
        "when_150k":     "KXBTCMAX150-25",          # Multi-outcome: by which date does BTC hit $150K
        "above_200k":    "KXBTC2026200-27JAN01",    # Single binary: BTC > $200K by Jan 1 2027
        "monthly_high":  _monthly_event_ticker(),    # Multi-outcome: highest BTC reaches this month
    }


def _f(val) -> float | None:
    """Coerce Kalshi numeric fields (often returned as strings) to float, or None."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _mid_price(market: dict) -> float | None:
    """Return mid market price in [0, 1].

    Prefer bid/ask midpoint; fall back to last trade; finally previous price.
    All Kalshi `_dollars` fields are already in dollars (0.45 = 45c = 45% implied).
    """
    bid = _f(market.get("yes_bid_dollars"))
    ask = _f(market.get("yes_ask_dollars"))
    if bid is not None and ask is not None and ask > 0:
        return (bid + ask) / 2
    last = _f(market.get("last_price_dollars"))
    if last is not None:
        return last
    prev = _f(market.get("previous_price_dollars"))
    return prev


def _prev_mid_price(market: dict) -> float | None:
    """Yesterday's mid, when Kalshi exposes one — used as delta fallback when our DB lacks history."""
    bid = _f(market.get("previous_yes_bid_dollars"))
    ask = _f(market.get("previous_yes_ask_dollars"))
    if bid is not None and ask is not None and ask > 0:
        return (bid + ask) / 2
    return _f(market.get("previous_price_dollars"))


def _fmt_dollar(s: str) -> str:
    val = float(s.replace(",", ""))
    if val >= 1000:
        return f"${int(round(val/1000))}K"
    return f"${int(round(val))}"


def _short_strike(market: dict) -> str:
    """Compact label for a Kalshi sub-market, derived from yes_sub_title or title.

    Handles three shapes:
      "Above $99,999.99"        -> "$100K"
      "80,000 to 84,999.99"     -> "$80K-$85K"
      "150,000 or above"        -> "$150K+"
    """
    sub = (market.get("yes_sub_title") or "").strip()
    # Date-bucketed events ("Before July 2026", "By Dec 2026") use month phrases
    # rather than strike values. Prefer that when it's the differentiating axis.
    if sub:
        m_date = re.match(
            r"^(?:before|by)\s+([A-Z][a-z]+(?:\s+\d{4})?)$", sub, re.IGNORECASE
        )
        if m_date:
            return sub  # e.g. "Before July 2026"
    candidates = [sub, market.get("title") or ""]
    for src in candidates:
        if not src:
            continue
        # Range: "X to Y"
        m = re.match(r"^([\d,]+(?:\.\d+)?)\s+to\s+([\d,]+(?:\.\d+)?)", src)
        if m:
            try:
                return f"{_fmt_dollar(m.group(1))}-{_fmt_dollar(m.group(2))}"
            except ValueError:
                pass
        # Open-ended high bucket: "X or above"
        m = re.match(r"^([\d,]+(?:\.\d+)?)\s+or\s+above", src, re.IGNORECASE)
        if m:
            try:
                return f"{_fmt_dollar(m.group(1))}+"
            except ValueError:
                pass
        # Standard "$X" anywhere in the string
        m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", src)
        if m:
            try:
                return _fmt_dollar(m.group(1))
            except ValueError:
                pass
    return (sub or market.get("title") or market.get("ticker", ""))[:40]


def _fetch_event(event_ticker: str) -> dict | None:
    """Return the event metadata for a given event_ticker, or None on failure."""
    try:
        r = requests.get(f"{API_BASE}/events/{event_ticker}", timeout=TIMEOUT)
        r.raise_for_status()
        return r.json().get("event")
    except Exception as e:
        log.warning(f"Kalshi event fetch failed for {event_ticker}: {e}")
        return None


def _fetch_markets(event_ticker: str) -> list[dict]:
    """Return all child markets for an event_ticker. Paginates if needed."""
    out: list[dict] = []
    cursor = None
    try:
        for _ in range(5):  # safety cap; events have ~30 markets max
            params = {"event_ticker": event_ticker, "limit": 200, "status": "open"}
            if cursor:
                params["cursor"] = cursor
            r = requests.get(f"{API_BASE}/markets", params=params, timeout=TIMEOUT)
            r.raise_for_status()
            body = r.json()
            out.extend(body.get("markets") or [])
            cursor = body.get("cursor")
            if not cursor:
                break
    except Exception as e:
        log.warning(f"Kalshi markets fetch failed for {event_ticker}: {e}")
    return out


def _normalize_event(event_ticker: str, label: str) -> dict | None:
    """Fetch + normalize one Kalshi event into the shared shape."""
    event = _fetch_event(event_ticker)
    markets = _fetch_markets(event_ticker)
    if not markets:
        return None

    outcomes = []
    volume = 0.0
    for m in markets:
        price = _mid_price(m)
        if price is None:
            continue
        prev = _prev_mid_price(m)
        vol = _f(m.get("volume_24h_fp")) or 0.0
        volume += vol
        outcomes.append({
            "label":          _short_strike(m),
            "price":          round(price, 4),
            "implied_pct":    round(price * 100, 1),
            "prev_price":     round(prev, 4) if prev is not None else None,
        })

    if not outcomes:
        return None
    outcomes.sort(key=lambda o: o["implied_pct"], reverse=True)

    title = (event or {}).get("title") or markets[0].get("title", "")
    # When the event's title is generic ("How high will Bitcoin get this month?"),
    # most users want to see what month. Strip Kalshi's date suffix when present.
    title = title.strip()

    end_date = None
    if event and event.get("strike_date"):
        end_date = event["strike_date"][:10]
    elif markets[0].get("expiration_time"):
        end_date = markets[0]["expiration_time"][:10]

    return {
        "id":         f"kalshi:{event_ticker}",
        "platform":   "kalshi",
        "title":      title,
        "label":      label,
        "outcomes":   outcomes,
        "volume_usd": round(volume, 2),
        "end_date":   end_date,
    }


def fetch_kalshi() -> dict:
    """Fetch all configured Kalshi BTC markets.

    Returns:
        {
            "markets": [ normalized_market, ... ],
            "error": str | None,
        }
    """
    cfg = _event_config()
    normalized: list[dict] = []
    failures = 0

    for label, ticker in cfg.items():
        nm = _normalize_event(ticker, label=label)
        if nm:
            # The 'label' field is only useful internally; drop before returning to
            # keep the shape uniform with Polymarket.
            nm.pop("label", None)
            normalized.append(nm)
        else:
            failures += 1
            log.warning(f"Kalshi event {label} ({ticker}) returned no usable data")

    error = None
    if normalized:
        log.info(f"Kalshi: fetched {len(normalized)}/{len(cfg)} events")
    else:
        error = "Kalshi data unavailable"
        log.warning(f"Kalshi: all {len(cfg)} fetches failed")

    return {"markets": normalized, "error": error}


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    print(json.dumps(fetch_kalshi(), indent=2, default=str))
