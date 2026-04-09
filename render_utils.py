"""Shared formatting and market-time helpers for financial snapshot rendering."""

from datetime import datetime, time
from zoneinfo import ZoneInfo


def is_market_closed() -> bool:
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return True
    market_open = time(9, 30)
    market_close = time(16, 0)
    return not (market_open <= now.time() <= market_close)


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
    if pct is None:
        return ""
    sign = "+" if pct >= 0 else ""
    return f"({sign}{pct:.{decimals}f}{suffix})"
