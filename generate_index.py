#!/usr/bin/env python3
"""
generate_index.py
-----------------
Scans the current directory (or a specified directory) for HTML files matching
the pattern  output_YYYYMMDD_HHMMSS.html  and generates a polished index.html
that links to every snapshot, organised by month.

Usage:
    python generate_index.py                     # scans current directory
    python generate_index.py /path/to/snapshots  # scans specified directory
    python generate_index.py --help
"""

import os
import re
import sys
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────
OUTPUT_FILENAME = "index.html"
FILE_PATTERN    = re.compile(
    r"^output_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.html$"
)
APP_TITLE = "Financial Snapshots"
APP_SUBTITLE = "Portfolio · Performance · History"
# ─────────────────────────────────────────────────────────────────────────────


def parse_filename(filename: str):
    """Return a datetime object if filename matches the convention, else None."""
    m = FILE_PATTERN.match(filename)
    if not m:
        return None
    year, month, day, hour, minute, second = (int(x) for x in m.groups())
    try:
        return datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def build_entries(directory: Path) -> list[tuple[datetime, str]]:
    """Return list of (datetime, filename) sorted newest-first."""
    entries = []
    for f in directory.iterdir():
        if f.is_file():
            dt = parse_filename(f.name)
            if dt:
                entries.append((dt, f.name))
    entries.sort(key=lambda x: x[0], reverse=True)
    return entries


def group_by_month(entries):
    """Return OrderedDict {(year, month): [(dt, filename), ...]} newest-first."""
    groups = defaultdict(list)
    for dt, name in entries:
        groups[(dt.year, dt.month)].append((dt, name))
    # sort months newest-first
    return dict(sorted(groups.items(), reverse=True))


def ordinal(n: int) -> str:
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10 if n % 100 not in (11, 12, 13) else 0, "th")
    return f"{n}{suffix}"


def render_html(groups: dict, total: int) -> str:
    now_str = datetime.now().strftime("%d %b %Y · %H:%M")

    # Build month sections
    month_nav_items  = []
    month_sections   = []

    for (year, month), entries in groups.items():
        month_dt   = datetime(year, month, 1)
        month_id   = f"m-{year}-{month:02d}"
        month_name = month_dt.strftime("%B %Y")
        count      = len(entries)

        month_nav_items.append(
            f'<a href="#{month_id}" class="nav-month">'
            f'<span class="nav-month-name">{month_name}</span>'
            f'<span class="nav-month-count">{count}</span>'
            f'</a>'
        )

        # Card rows for each snapshot
        cards_html = []
        for i, (dt, filename) in enumerate(entries):
            weekday   = dt.strftime("%a")
            day_ord   = ordinal(dt.day)
            time_str  = dt.strftime("%H:%M:%S")
            date_full = dt.strftime(f"%A, {day_ord} %B %Y")
            cards_html.append(f"""
            <a href="{filename}" class="snap-card" style="animation-delay:{i * 0.04:.2f}s">
              <div class="snap-left">
                <span class="snap-weekday">{weekday}</span>
                <span class="snap-day">{dt.day:02d}</span>
              </div>
              <div class="snap-center">
                <span class="snap-date-full">{date_full}</span>
                <span class="snap-filename">{filename}</span>
              </div>
              <div class="snap-right">
                <span class="snap-time">{time_str}</span>
                <span class="snap-arrow">↗</span>
              </div>
            </a>""")

        month_sections.append(f"""
        <section class="month-section" id="{month_id}">
          <div class="month-header">
            <h2 class="month-title">{month_name}</h2>
            <span class="month-pill">{count} snapshot{"s" if count != 1 else ""}</span>
          </div>
          <div class="snap-list">
            {''.join(cards_html)}
          </div>
        </section>""")

    nav_html      = "\n".join(month_nav_items)
    sections_html = "\n".join(month_sections)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{APP_TITLE}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet" />
  <style>
    /* ── Reset & Tokens ───────────────────────────────────────────── */
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

:root {{
  --bg:          #f9f8f5;
  --bg2:         #ffffff;
  --bg3:         #f2f0eb;
  --border:      rgba(0,0,0,0.08);
  --border-h:    rgba(160,120,40,0.35);

  --gold:        #a07828;
  --gold-dim:    rgba(160,120,40,0.1);
  --gold-glow:   rgba(160,120,40,0.05);

  --text-1:      #1a1a14;
  --text-2:      #6b6b58;
  --text-3:      #b0ae9e;

  --nav-w:       240px;
  --radius:      10px;
  --transition:  0.22s cubic-bezier(0.4,0,0.2,1);
}}

    html {{ scroll-behavior: smooth; }}

    body {{
      background: var(--bg);
      color: var(--text-1);
      font-family: 'DM Sans', sans-serif;
      font-weight: 300;
      min-height: 100vh;
      overflow-x: hidden;
    }}

    /* ── Grain overlay ───────────────────────────────────────────── */
    body::before {{
      content: '';
      position: fixed;
      inset: 0;
      background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E");
      background-repeat: repeat;
      background-size: 200px 200px;
      pointer-events: none;
      z-index: 0;
      opacity: 0.5;
    }}

    /* ── Layout ─────────────────────────────────────────────────── */
    .layout {{
      display: grid;
      grid-template-columns: var(--nav-w) 1fr;
      grid-template-rows: auto 1fr;
      min-height: 100vh;
      position: relative;
      z-index: 1;
    }}

    /* ── Top bar ─────────────────────────────────────────────────── */
    .topbar {{
      grid-column: 1 / -1;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 20px 36px;
      border-bottom: 1px solid var(--border);
      background: rgba(12,14,17,0.9);
      backdrop-filter: blur(12px);
      position: sticky;
      top: 0;
      z-index: 100;
    }}

    .topbar-brand {{ display: flex; align-items: baseline; gap: 14px; }}

    .topbar-title {{
      font-family: 'DM Serif Display', serif;
      font-size: 1.45rem;
      letter-spacing: -0.01em;
      color: var(--text-1);
    }}

    .topbar-subtitle {{
      font-family: 'DM Mono', monospace;
      font-size: 0.65rem;
      color: var(--gold);
      letter-spacing: 0.18em;
      text-transform: uppercase;
    }}

    .topbar-meta {{
      display: flex;
      align-items: center;
      gap: 24px;
    }}

    .meta-chip {{
      font-family: 'DM Mono', monospace;
      font-size: 0.7rem;
      color: var(--text-2);
      letter-spacing: 0.06em;
    }}

    .meta-chip b {{ color: var(--gold); font-weight: 500; }}

    .meta-updated {{
      font-family: 'DM Mono', monospace;
      font-size: 0.65rem;
      color: var(--text-3);
      letter-spacing: 0.05em;
    }}

    /* ── Sidebar nav ─────────────────────────────────────────────── */
    .sidebar {{
      padding: 32px 0;
      border-right: 1px solid var(--border);
      position: sticky;
      top: 65px;
      height: calc(100vh - 65px);
      overflow-y: auto;
      scrollbar-width: thin;
      scrollbar-color: var(--border) transparent;
    }}

    .sidebar-label {{
      font-family: 'DM Mono', monospace;
      font-size: 0.6rem;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: var(--text-3);
      padding: 0 24px 12px;
    }}

    .nav-month {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 9px 24px;
      text-decoration: none;
      color: var(--text-2);
      font-size: 0.82rem;
      font-weight: 400;
      transition: var(--transition);
      border-left: 2px solid transparent;
    }}

    .nav-month:hover {{
      color: var(--text-1);
      background: var(--gold-glow);
      border-left-color: var(--gold);
    }}

    .nav-month-name {{ font-family: 'DM Sans', sans-serif; }}

    .nav-month-count {{
      font-family: 'DM Mono', monospace;
      font-size: 0.65rem;
      color: var(--text-3);
      background: var(--bg3);
      padding: 2px 7px;
      border-radius: 20px;
    }}

    /* ── Main content ────────────────────────────────────────────── */
    .main {{
      padding: 40px 48px;
      max-width: 900px;
    }}

    /* ── Month sections ──────────────────────────────────────────── */
    .month-section {{ margin-bottom: 52px; }}

    .month-header {{
      display: flex;
      align-items: baseline;
      gap: 14px;
      margin-bottom: 20px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--border);
    }}

    .month-title {{
      font-family: 'DM Serif Display', serif;
      font-size: 1.55rem;
      font-weight: 400;
      color: var(--text-1);
      letter-spacing: -0.02em;
    }}

    .month-pill {{
      font-family: 'DM Mono', monospace;
      font-size: 0.65rem;
      letter-spacing: 0.1em;
      color: var(--gold);
      background: var(--gold-dim);
      border: 1px solid rgba(212,175,95,0.25);
      padding: 3px 10px;
      border-radius: 20px;
    }}

    /* ── Snapshot cards ──────────────────────────────────────────── */
    .snap-list {{ display: flex; flex-direction: column; gap: 6px; }}

    .snap-card {{
      display: grid;
      grid-template-columns: 54px 1fr auto;
      align-items: center;
      gap: 18px;
      padding: 14px 20px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--bg2);
      text-decoration: none;
      color: inherit;
      transition: var(--transition);
      opacity: 0;
      animation: fadeUp 0.4s forwards;
      position: relative;
      overflow: hidden;
    }}

    .snap-card::before {{
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(90deg, var(--gold-glow) 0%, transparent 60%);
      opacity: 0;
      transition: var(--transition);
    }}

    .snap-card:hover {{
      border-color: var(--border-h);
      background: var(--bg3);
      transform: translateX(3px);
    }}

    .snap-card:hover::before {{ opacity: 1; }}

    .snap-left {{
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 4px 0;
      border-right: 1px solid var(--border);
    }}

    .snap-weekday {{
      font-family: 'DM Mono', monospace;
      font-size: 0.6rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--text-3);
    }}

    .snap-day {{
      font-family: 'DM Serif Display', serif;
      font-size: 1.4rem;
      color: var(--gold);
      line-height: 1;
    }}

    .snap-center {{
      display: flex;
      flex-direction: column;
      gap: 3px;
    }}

    .snap-date-full {{
      font-size: 0.85rem;
      color: var(--text-1);
      font-weight: 400;
    }}

    .snap-filename {{
      font-family: 'DM Mono', monospace;
      font-size: 0.65rem;
      color: var(--text-3);
      letter-spacing: 0.04em;
    }}

    .snap-right {{
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 4px;
    }}

    .snap-time {{
      font-family: 'DM Mono', monospace;
      font-size: 0.75rem;
      color: var(--text-2);
      letter-spacing: 0.05em;
    }}

    .snap-arrow {{
      font-size: 0.9rem;
      color: var(--text-3);
      transition: var(--transition);
    }}

    .snap-card:hover .snap-arrow {{ color: var(--gold); transform: translate(2px,-2px); }}

    /* ── Animation ───────────────────────────────────────────────── */
    @keyframes fadeUp {{
      from {{ opacity: 0; transform: translateY(10px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}

    /* ── Empty state ─────────────────────────────────────────────── */
    .empty {{
      text-align: center;
      padding: 100px 40px;
      color: var(--text-3);
      font-family: 'DM Mono', monospace;
      font-size: 0.8rem;
      letter-spacing: 0.1em;
    }}

    /* ── Scrollbar ───────────────────────────────────────────────── */
    ::-webkit-scrollbar {{ width: 5px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 4px; }}

    /* ── Responsive ──────────────────────────────────────────────── */
    @media (max-width: 720px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .sidebar {{ display: none; }}
      .topbar {{ padding: 16px 20px; }}
      .main {{ padding: 24px 20px; }}
    }}
  </style>
</head>
<body>
<div class="layout">

  <!-- Top bar -->
  <header class="topbar">
    <div class="topbar-brand">
      <span class="topbar-title">{APP_TITLE}</span>
      <span class="topbar-subtitle">{APP_SUBTITLE}</span>
    </div>
    <div class="topbar-meta">
      <span class="meta-chip"><b>{total}</b> total snapshots</span>
      <span class="meta-updated">Updated {now_str}</span>
    </div>
  </header>

  <!-- Sidebar -->
  <nav class="sidebar">
    <div class="sidebar-label">Browse by month</div>
    {nav_html}
  </nav>

  <!-- Main -->
  <main class="main">
    {"".join(month_sections) if groups else '<div class="empty">NO SNAPSHOTS FOUND</div>'}
  </main>

</div>
</body>
</html>"""


def main():
    # Determine target directory
    if len(sys.argv) > 1 and sys.argv[1] not in ("--help", "-h"):
        target = Path(sys.argv[1]).resolve()
    elif len(sys.argv) > 1:
        print(__doc__)
        sys.exit(0)
    else:
        target = Path.cwd()

    if not target.is_dir():
        print(f"Error: '{target}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    entries = build_entries(target)
    groups  = group_by_month(entries)
    html    = render_html(groups, len(entries))

    out_path = target / OUTPUT_FILENAME
    out_path.write_text(html, encoding="utf-8")

    print(f"✓  Index generated: {out_path}")
    print(f"   {len(entries)} snapshot(s) across {len(groups)} month(s).")


if __name__ == "__main__":
    main()
