"""HTML rendering for financial snapshot emails."""

from datetime import datetime

from render_utils import is_market_closed
from snapshot_schema import build_snapshot_sections


def build_html(data: dict, now: datetime, root_url: str) -> str:
    date_str = now.strftime("%B %-d, %Y %-I:%M %p ET")
    market_closed = is_market_closed()
    sections = build_snapshot_sections(data, market_closed=market_closed)

    def format_row(row: dict) -> str:
        change_str = row.get("change", "")
        if change_str:
            is_up = change_str.startswith("(+")
            invert = row.get("invert", False)
            is_good = (is_up and not invert) or (not is_up and invert)
            color = "#1a7a1a" if is_good else "#cc0000"
            change_str = f"<span style='color:{color};'>{change_str}</span>"
        chg_html = f"<span class='chg'>{change_str}</span>" if change_str else ""
        sub_html = f"<span class='sub'>{row.get('sub', '')}</span>" if row.get("sub") else ""
        return f"""
        <tr>
          <td class=\"label\">{row['label']}</td>
          <td class=\"val\">{row['value']} {chg_html}{sub_html}</td>
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
  <h1>📊 Daily Financial Snapshot</h1>
  <div class=\"gen\">Generated {date_str}</div>
  {"<h2>Market Closed</h2>" if market_closed else "<h2>Market Open</h2>"}
  {body_sections}

  <div class=\"footer\">Data sourced from CoinGecko, Yahoo Finance, Alternative.me, EIA, FRED/BLS &nbsp;·&nbsp;
  Not financial advice
  <a href=\"{root_url}\" target=\"_blank\">View in previous days browser</a>
  </div>
</div>
</body>
</html>"""
