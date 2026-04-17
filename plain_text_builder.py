"""Plain-text rendering for financial snapshot messages."""

from datetime import datetime

from render_utils import is_market_closed
from snapshot_schema import build_snapshot_sections


def build_plain(data: dict, now: datetime, unsubscribe_url: str = "") -> str:
    date_str = now.strftime("%B %-d, %Y %-I:%M %p ET")
    market_closed = is_market_closed()
    sections = build_snapshot_sections(data, market_closed=market_closed)

    def p(label: str, value: str, chg: str = "") -> str:
        return f"  {label}: {value} {chg}".rstrip() + "\n"

    lines = [f"Daily Market Pulse\nGenerated: {date_str}\n"]
    lines.append("Market Closed\n" if market_closed else "Market Open\n")

    if data.get("anomaly_alert"):
        lines.append(f"\n⚠ MARKET ALERT\n{data['anomaly_alert']}\n")

    if data.get("ai_analysis") or data.get("watch_item"):
        lines.append("\nAI MORNING BRIEFING\n")
        if data.get("ai_analysis"):
            lines.append(f"{data['ai_analysis']}\n")
        if data.get("watch_item"):
            lines.append(f"\nWatch today: {data['watch_item']}\n")

    for section in sections:
        lines.append(f"\n{section['title'].upper()}\n")
        for row in section["rows"]:
            lines.append(p(row["label"], row["value"], row.get("change", "")))
            if row.get("sub"):
                lines.append(f"    {row['sub']}\n")

    if unsubscribe_url:
        lines.append(f"\n---\nTo unsubscribe: {unsubscribe_url}\n")

    return "".join(lines)
