"""HTML rendering for financial snapshot emails."""

import html as html_lib
from datetime import datetime

from render_utils import is_market_closed
from snapshot_schema import build_snapshot_sections


def build_html(data: dict, now: datetime, root_url: str, unsubscribe_url: str = "") -> str:
    date_str = now.strftime("%B %-d, %Y %-I:%M %p ET")
    market_closed = is_market_closed()
    sections = build_snapshot_sections(data, market_closed=market_closed)

    ai_analysis = data.get("ai_analysis")
    watch_item  = data.get("watch_item")

    ai_block = ""
    if ai_analysis or watch_item:
        parts = []
        if ai_analysis:
            parts.append(
                f"<p style='margin:0 0 10px;'>{html_lib.escape(ai_analysis)}</p>"
            )
        if watch_item:
            parts.append(
                f"<p style='margin:0; padding:8px 10px; background:#f5f5f5; "
                f"border-left:3px solid #111; font-size:13px; color:#333;'>"
                f"<strong>Watch today:</strong> {html_lib.escape(watch_item)}</p>"
            )
        ai_block = (
            "<div style='margin-bottom:24px;'>"
            "<div style='font-size:13px;font-weight:700;text-transform:uppercase;"
            "letter-spacing:.05em;padding:8px 12px 6px;color:#111;"
            "border-bottom:2px solid #111;margin-bottom:10px;'>AI Morning Briefing</div>"
            + "".join(parts)
            + "</div>"
        )

    def format_row(row: dict) -> str:
        change_str = html_lib.escape(row.get("change", ""))
        if change_str:
            is_up = change_str.startswith("(+")
            invert = row.get("invert", False)
            is_good = (is_up and not invert) or (not is_up and invert)
            color = "#1a7a1a" if is_good else "#cc0000"
            change_str = f"<span style='color:{color};'>{change_str}</span>"
        chg_html = f"<span class='chg'>{change_str}</span>" if change_str else ""
        sub_html = f"<span class='sub'>{html_lib.escape(row.get('sub', ''))}</span>" if row.get("sub") else ""
        return f"""
        <tr>
          <td class=\"label\">{html_lib.escape(row['label'])}</td>
          <td class=\"val\">{html_lib.escape(row['value'])} {chg_html}{sub_html}</td>
        </tr>"""

    def section_html(title: str, rows_html: str) -> str:
        return f"""
        <div class=\"section-title\">{title}</div>
        <table>
          <tbody>{rows_html}
          </tbody>
        </table>"""

    body_sections = "".join(section_html(section["title"], "".join(format_row(row) for row in section["rows"])) for section in sections)

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"UTF-8\">

<style>
  body      {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
               background: #ffffff; color: #111111; margin: 0; padding: 20px; font-size: 16px; }}
  .wrap     {{ max-width: 560px; margin: 0 auto; }}
  h1        {{ font-size: 20px; font-weight: 700; color: #000; margin: 0 0 4px; }}
  h2        {{ font-size: 16px; font-weight: 600; color: #333; margin: 0 0 16px; }}
  .gen      {{ font-size: 13px; color: #555; margin-bottom: 24px; }}
  .section-title {{ font-size: 13px; font-weight: 700; text-transform: uppercase;
               letter-spacing: .05em; padding: 8px 12px 6px;
               color: #111; border-bottom: 2px solid #111; margin: 0; }}
  table     {{ width: 100%; border-collapse: collapse; margin: 0 0 20px 0; }}
  tbody tr:last-child {{ border-bottom: none; }}
  td        {{ padding: 2px 12px; font-size: 14px; vertical-align: top; }}
  td.label  {{ color: #444; width: 50%; }}
  td.val    {{ color: #111; font-variant-numeric: tabular-nums; font-weight: 500; }}
  .chg      {{ font-size: 13px; margin-left: 6px; font-weight: 400; }}
  .sub      {{ display: block; color: #888; font-size: 12px; margin-top: 2px; font-weight: 400; }}
  .footer   {{ font-size: 12px; color: #999; text-align: center; margin-top: 24px;
               border-top: 1px solid #e5e5e5; padding-top: 12px; }}
</style>
</head>
<body>
<div class=\"wrap\">
  <h1>📊 Daily Market Pulse</h1>
  <div class=\"gen\">Generated {date_str}</div>
  {"<h2>Market Closed</h2>" if market_closed else "<h2>Market Open</h2>"}
  {ai_block}
  {body_sections}

  <div class=\"footer\">Data sourced from CoinGecko, Yahoo Finance, Alternative.me, EIA, FRED/BLS &nbsp;·&nbsp;
  Not financial advice &nbsp;·&nbsp;
  <a href=\"{root_url}\" target=\"_blank\">View in browser</a>
  {f'&nbsp;·&nbsp; <a href=\"{html_lib.escape(unsubscribe_url)}\" target=\"_blank\">Unsubscribe</a>' if unsubscribe_url else ''}
  </div>
</div>
</body>
</html>"""
