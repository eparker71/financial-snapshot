#!/usr/bin/env python3
"""
generate_index.py
-----------------
Generates the public-facing Financial Snapshot dashboard (html/index.html).
Reads the latest market data from db.sqlite3, fetches recent financial news
from RSS, and produces a modern HTML dashboard with subscribe form and archive.

Usage:
    python generate_index.py              # writes to ./html/index.html
    python generate_index.py /path/html   # writes to specified directory
"""

import html as html_lib
import re
import sys
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
OUTPUT_FILENAME = "index.html"
FILE_PATTERN    = re.compile(r"^output_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.html$")
APP_TITLE       = "Market Pulse"
NEWS_FEEDS = [
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("CNBC Markets",  "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("Investopedia",   "https://www.investopedia.com/markets-news-4427704"),
]
MAX_NEWS = 12
MAX_INSIGHTS_PER_SOURCE = 4
FIRM_INSIGHT_SOURCES = [
    {
        "name": "Fidelity Viewpoints",
        "type": "js_scrape",
        "url": "https://www.fidelity.com/learning-center/viewpoints",
        "base_url": "https://www.fidelity.com",
        "container_sel": "div.pvd-tile__tile.article",
        "heading_sel":   "h3",
    },
    {
        "name": "BlackRock",
        "type": "js_scrape",
        "url": "https://www.blackrock.com/us/individual/insights",
        "base_url": "https://www.blackrock.com",
    },
    {
        "name": "J.P. Morgan AM",
        "type": "scrape",
        "url": "https://am.jpmorgan.com/us/en/asset-management/adv/insights/market-insights/market-updates/",
        "base_url": "https://am.jpmorgan.com",
    },
    {
        "name": "MarketWatch",
        "type": "rss",
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
        "base_url": "",
    },
    {
        "name": "On Watch by MarketWatch",
        "type": "rss",
        "url": "https://feeds.megaphone.fm/WSJ6764429165",
        "base_url": "",
    },
]
# ───────────────────────────────────────────────────────────────────────────────


# ── Database ──────────────────────────────────────────────────────────────────

def get_latest_snapshot():
    try:
        root = Path(__file__).parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from models import Snapshot, init_db
        init_db()
        return Snapshot.select().order_by(Snapshot.timestamp.desc()).first()
    except Exception as e:
        print(f"Warning: could not read DB: {e}", file=sys.stderr)
        return None


# ── News ──────────────────────────────────────────────────────────────────────

def fetch_news(max_items=MAX_NEWS):
    per_source = max(1, max_items // len(NEWS_FEEDS))
    articles = []
    for source_name, url in NEWS_FEEDS:
        count = 0
        try:
            r = requests.get(url, timeout=8,
                             headers={"User-Agent": "Mozilla/5.0 FinancialSnapshot/1.0"})
            try:
                root_el = ET.fromstring(r.content)
                items = root_el.findall(".//item")
                for item in items:
                    title = item.findtext("title", "").strip()
                    link  = item.findtext("link",  "").strip()
                    if title and link:
                        articles.append({"title": title[:100], "link": link, "source": source_name})
                        count += 1
                    if count >= per_source:
                        break
            except ET.ParseError:
                # Fall back to BeautifulSoup for malformed feeds
                soup = BeautifulSoup(r.content, "html.parser")
                for item in soup.find_all("item"):
                    title = (item.find("title") or {}).get_text(strip=True)
                    link  = (item.find("link")  or {}).get_text(strip=True)
                    if title and link:
                        articles.append({"title": title[:100], "link": link, "source": source_name})
                        count += 1
                    if count >= per_source:
                        break
        except Exception as e:
            print(f"Warning: news fetch failed ({source_name}): {e}", file=sys.stderr)
    return articles[:max_items]


# ── Firm Insights ─────────────────────────────────────────────────────────────

def _scrape_articles(url, base_url, max_items):
    """Scrape article titles and links from a page using BeautifulSoup."""
    headers = {"User-Agent": "Mozilla/5.0 FinancialSnapshot/1.0"}
    r = requests.get(url, timeout=10, headers=headers)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "html.parser")
    articles = []
    # Find <a> tags that contain a heading child
    for a in soup.find_all("a", href=True):
        heading = a.find(["h2", "h3", "h4"])
        if not heading:
            continue
        title = heading.get_text(strip=True)
        if len(title) < 10:
            continue
        href = a["href"]
        if href.startswith("/"):
            href = base_url + href
        if not href.startswith("http"):
            continue
        articles.append({"title": title[:120], "link": href})
        if len(articles) >= max_items:
            break
    return articles


def _rss_articles(url, max_items):
    """Fetch articles from an RSS feed. Falls back to channel link for podcast feeds."""
    headers = {"User-Agent": "Mozilla/5.0 FinancialSnapshot/1.0"}
    r = requests.get(url, timeout=10, headers=headers)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    channel_link = (root.findtext(".//channel/link") or "").strip()
    articles = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link  = (item.findtext("link")  or "").strip()
        guid  = (item.findtext("guid")  or "").strip()
        # Use guid if it looks like a URL, otherwise fall back to channel link
        if not link:
            link = guid if guid.startswith("http") else channel_link
        if title and link:
            articles.append({"title": title[:120], "link": link})
        if len(articles) >= max_items:
            break
    return articles


def _js_scrape_articles(url, base_url, max_items, container_sel=None, heading_sel=None):
    """Scrape a JS-rendered page using Playwright headless Firefox."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0"
        )
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)
        html = page.content()
        browser.close()
    soup = BeautifulSoup(html, "html.parser")
    articles = []

    if container_sel:
        # Container-based: each tile has a heading + a sibling link
        h_tag = heading_sel or "h2, h3, h4"
        for container in soup.select(container_sel):
            heading = container.select_one(h_tag)
            if not heading:
                continue
            title = heading.get_text(strip=True)
            if len(title) < 10:
                continue
            link_tag = container.find("a", href=True)
            if not link_tag:
                continue
            href = link_tag["href"]
            if href.startswith("/"):
                href = base_url + href
            if not href.startswith("http"):
                continue
            articles.append({"title": title[:120], "link": href})
            if len(articles) >= max_items:
                break
    else:
        # Generic: find <a> tags that wrap a heading
        for a in soup.find_all("a", href=True):
            heading = a.find(["h2", "h3", "h4"])
            if not heading:
                continue
            title = heading.get_text(strip=True)
            if len(title) < 10:
                continue
            href = a["href"]
            if href.startswith("/"):
                href = base_url + href
            if not href.startswith("http"):
                continue
            articles.append({"title": title[:120], "link": href})
            if len(articles) >= max_items:
                break
    return articles


def fetch_firm_insights(max_per_source=MAX_INSIGHTS_PER_SOURCE):
    """Fetch articles from institutional insight sources. Returns list of (source_name, articles)."""
    results = []
    for source in FIRM_INSIGHT_SOURCES:
        name = source["name"]
        try:
            if source["type"] == "rss":
                articles = _rss_articles(source["url"], max_per_source)
            elif source["type"] == "js_scrape":
                articles = _js_scrape_articles(
                    source["url"], source.get("base_url", ""), max_per_source,
                    container_sel=source.get("container_sel"),
                    heading_sel=source.get("heading_sel"),
                )
            else:
                articles = _scrape_articles(source["url"], source.get("base_url", ""), max_per_source)
            if articles:
                results.append({"source": name, "articles": articles})
        except Exception as e:
            print(f"Warning: firm insights fetch failed ({name}): {e}", file=sys.stderr)
    return results


# ── Archive helpers ───────────────────────────────────────────────────────────

def parse_filename(filename):
    m = FILE_PATTERN.match(filename)
    if not m:
        return None
    y, mo, d, h, mi, s = (int(x) for x in m.groups())
    try:
        return datetime(y, mo, d, h, mi, s)
    except ValueError:
        return None


def build_entries(directory):
    entries = []
    for f in directory.iterdir():
        if f.is_file():
            dt = parse_filename(f.name)
            if dt:
                entries.append((dt, f.name))
    entries.sort(key=lambda x: x[0], reverse=True)
    return entries


# ── Formatting helpers ────────────────────────────────────────────────────────

def fv(val, decimals=2, prefix="$"):
    if val is None:
        return "—"
    if val >= 1000:
        return f"{prefix}{val:,.{decimals}f}"
    return f"{prefix}{val:.{decimals}f}"


def fc(val, suffix="%"):
    if val is None:
        return ""
    return f"{'+' if val >= 0 else ''}{val:.2f}{suffix}"


# ── Component builders ────────────────────────────────────────────────────────

def dr(label, val_str, chg="", sub="", invert=False, live_key=""):
    """Render a single data row inside a card."""
    price_live = f' data-live="{live_key}:price"' if live_key else ""
    price_h = f'<span{price_live}>{html_lib.escape(val_str)}</span>'

    if chg:
        is_up = chg.startswith("+")
        good  = (is_up and not invert) or (not is_up and invert)
        c     = "up" if good else "dn"
        chg_live = f' data-live="{live_key}:change"' if live_key else ""
        chg_h = f'<span class="dr-chg {c}"{chg_live}>{html_lib.escape(chg)}</span>'
    elif live_key:
        chg_h = f'<span class="dr-chg neu" data-live="{live_key}:change"></span>'
    else:
        chg_h = ""

    sub_h = f'<div class="dr-sub">{html_lib.escape(sub)}</div>' if sub else ""
    return (
        f'<div class="dr">'
        f'<span class="dr-lbl">{html_lib.escape(label)}</span>'
        f'<span class="dr-val">{price_h}{chg_h}{sub_h}</span>'
        f'</div>'
    )


def card(title, icon, *rows):
    body = "".join(r for r in rows if r)
    if not body:
        return ""
    return (
        f'<div class="data-card">'
        f'<div class="card-hd"><span class="card-icon">{icon}</span>{html_lib.escape(title)}</div>'
        f'{body}'
        f'</div>'
    )


# ── Main renderer ─────────────────────────────────────────────────────────────

def render_html(snap, news, entries, firm_insights=None):
    now_str   = datetime.now().strftime("%b %-d, %Y · %-I:%M %p")
    snap_time = (snap.timestamp.strftime("%b %-d, %Y")
                 if snap and snap.timestamp else "no data yet")
    total = len(entries)

    # ── Hero tiles ────────────────────────────────────────────────────────────
    def hero(label, val, chg_pct=None, prefix="$", decimals=2, invert=False, live_key=""):
        val_str = fv(val, decimals, prefix) if val is not None else "—"
        chg     = fc(chg_pct) if chg_pct is not None else ""
        if chg:
            is_up = chg.startswith("+")
            good  = (is_up and not invert) or (not is_up and invert)
            cls   = "up" if good else "dn"
        else:
            cls = "neu"
        price_live = f' data-live="{live_key}:price"' if live_key else ""
        chg_live   = f' data-live="{live_key}:change"' if live_key else ""
        return (
            f'<div class="hero-tile">'
            f'<div class="h-label">{html_lib.escape(label)}</div>'
            f'<div class="h-val"{price_live}>{html_lib.escape(val_str)}</div>'
            f'<div class="h-chg {cls}"{chg_live}>{html_lib.escape(chg)}</div>'
            f'</div>'
        )

    if snap:
        sp_p = snap.gspc_price      or snap.sp500_futures_price
        sp_c = snap.gspc_change_pct or snap.sp500_futures_change_pct
        dj_p = snap.dji_price       or snap.dow_futures_price
        dj_c = snap.dji_change_pct  or snap.dow_futures_change_pct

        heroes = [
            hero("S&P 500",   sp_p,           sp_c,                  live_key="sp500"),
            hero("Dow Jones", dj_p,           dj_c,                  live_key="dow"),
            hero("Bitcoin",   snap.btc_price,  snap.btc_change_pct,   "$", 0, live_key="btc"),
            hero("Gold",      snap.gold_price, snap.gold_change_pct,  live_key="gold"),
            hero("VIX",       snap.vix_price,  snap.vix_change_pct,   "", 2, invert=True, live_key="vix"),
        ]
        if snap.fear_greed_value is not None:
            fg     = int(snap.fear_greed_value)
            fg_lbl = snap.fear_greed_label or ""
            fg_cls = "up" if fg >= 50 else "dn"
            heroes.append(
                f'<div class="hero-tile">'
                f'<div class="h-label">Fear &amp; Greed</div>'
                f'<div class="h-val" data-live="fear_greed:price">{fg}</div>'
                f'<div class="h-chg {fg_cls}" data-live="fear_greed:change">{html_lib.escape(fg_lbl)}</div>'
                f'</div>'
            )
    else:
        heroes = [hero("No data", None)]

    heroes_html = "\n".join(heroes)

    # ── AI Analysis card ──────────────────────────────────────────────────────
    ai_analysis_html = ""
    if snap and (getattr(snap, "ai_analysis", None) or getattr(snap, "watch_item", None)):
        watch_html = ""
        if getattr(snap, "watch_item", None):
            watch_html = (
                f'<div class="ai-watch">'
                f'<strong>Watch today:</strong> {html_lib.escape(snap.watch_item)}'
                f'</div>'
            )
        ai_analysis_html = (
            f'<div class="ai-card">'
            f'<div class="ai-hd">AI Morning Briefing</div>'
            + (f'<div class="ai-body">{html_lib.escape(snap.ai_analysis)}</div>' if snap.ai_analysis else "")
            + watch_html
            + f'</div>'
        )

    # ── Data cards ────────────────────────────────────────────────────────────
    cards_html = ""
    if snap:
        sp_p  = snap.gspc_price      or snap.sp500_futures_price
        sp_c  = snap.gspc_change_pct or snap.sp500_futures_change_pct
        dj_p  = snap.dji_price       or snap.dow_futures_price
        dj_c  = snap.dji_change_pct  or snap.dow_futures_change_pct
        nq_p  = snap.ndx_price       or snap.nasdaq_futures_price
        nq_c  = snap.ndx_change_pct  or snap.nasdaq_futures_change_pct
        rut_p = snap.rut_price       or snap.russell_futures_price
        rut_c = snap.rut_change_pct  or snap.russell_futures_change_pct

        cards_html += card("US Markets", "📈",
            dr("S&P 500",      fv(sp_p),                  fc(sp_c),                live_key="sp500")    if sp_p           else "",
            dr("Dow Jones",    fv(dj_p),                  fc(dj_c),                live_key="dow")      if dj_p           else "",
            dr("Nasdaq 100",   fv(nq_p),                  fc(nq_c),                live_key="nasdaq")   if nq_p           else "",
            dr("Russell 2000", fv(rut_p),                 fc(rut_c),               live_key="russell")  if rut_p          else "",
            dr("VIX",          fv(snap.vix_price, 2, ""), fc(snap.vix_change_pct), invert=True, live_key="vix") if snap.vix_price else "",
        )

        cards_html += card("Magnificent 7", "💎",
            dr("Apple (AAPL)",    fv(snap.aapl_price),  fc(snap.aapl_change_pct))  if snap.aapl_price  else "",
            dr("Microsoft (MSFT)", fv(snap.msft_price), fc(snap.msft_change_pct))  if snap.msft_price  else "",
            dr("Amazon (AMZN)",   fv(snap.amzn_price),  fc(snap.amzn_change_pct))  if snap.amzn_price  else "",
            dr("Alphabet (GOOGL)", fv(snap.googl_price), fc(snap.googl_change_pct)) if snap.googl_price else "",
            dr("Meta (META)",     fv(snap.meta_price),  fc(snap.meta_change_pct))  if snap.meta_price  else "",
            dr("Tesla (TSLA)",    fv(snap.tsla_price),  fc(snap.tsla_change_pct))  if snap.tsla_price  else "",
            dr("Nvidia (NVDA)",   fv(snap.nvda_price),  fc(snap.nvda_change_pct))  if snap.nvda_price  else "",
        )

        fg_row = (dr("Fear & Greed", f"{int(snap.fear_greed_value)} – {snap.fear_greed_label or ''}", live_key="fear_greed")
                  if snap.fear_greed_value is not None else "")
        cards_html += card("Crypto", "🪙",
            dr("Bitcoin (BTC)",  fv(snap.btc_price, 0), fc(snap.btc_change_pct), live_key="btc") if snap.btc_price  else "",
            dr("Ethereum (ETH)", fv(snap.eth_price),    fc(snap.eth_change_pct), live_key="eth") if snap.eth_price  else "",
            dr("Solana (SOL)",   fv(snap.sol_price),    fc(snap.sol_change_pct), live_key="sol") if snap.sol_price  else "",
            dr("Ripple (XRP)",   fv(snap.xrp_price, 4), fc(snap.xrp_change_pct), live_key="xrp") if snap.xrp_price else "",
            dr("Cardano (ADA)",  fv(snap.ada_price, 4), fc(snap.ada_change_pct), live_key="ada") if snap.ada_price else "",
            fg_row,
        )

        cards_html += card("Energy & Metals", "⛽",
            dr("Crude Oil (WTI)",  fv(snap.oil_price),    fc(snap.oil_change_pct),    live_key="oil")    if snap.oil_price    else "",
            dr("US Gas (avg)",     f"${snap.gas_price:.3f}/gal")                                          if snap.gas_price    else "",
            dr("US Diesel (avg)",  f"${snap.diesel_price:.3f}/gal")                                       if snap.diesel_price else "",
            dr("Gold",             fv(snap.gold_price),   fc(snap.gold_change_pct),   live_key="gold")   if snap.gold_price   else "",
            dr("Silver",           fv(snap.silver_price), fc(snap.silver_change_pct), live_key="silver") if snap.silver_price else "",
        )

        cards_html += card("FX & Rates", "💱",
            dr("EUR/USD",         f"{snap.eurusd_price:.4f}" if snap.eurusd_price else "—",   fc(snap.eurusd_change_pct), live_key="eurusd") if snap.eurusd_price  else "",
            dr("USD/JPY",         f"¥{snap.usdjpy_price:.2f}" if snap.usdjpy_price else "—",  fc(snap.usdjpy_change_pct), live_key="usdjpy") if snap.usdjpy_price  else "",
            dr("10-Yr Treasury",  f"{snap.t10y_yield:.3f}%" if snap.t10y_yield else "—",      fc(snap.t10y_change_pct), invert=True, live_key="t10y") if snap.t10y_yield   else "",
            dr("2-Yr Treasury",   f"{snap.t2y_yield:.3f}%"  if snap.t2y_yield  else "—",      fc(snap.t2y_change_pct),  invert=True, live_key="t2y")  if snap.t2y_yield    else "",
            dr("30-Yr Mortgage",  f"{snap.mortgage_rate:.2f}%")                                                                                         if snap.mortgage_rate else "",
            dr("Credit Card APR", f"{snap.credit_card_apr:.2f}%")                                                                                       if snap.credit_card_apr else "",
        )

        macro_rows = "".join(filter(None, [
            dr("CPI (All Items)",  f"{snap.cpi_all_yoy:.1f}% YoY",          sub=snap.cpi_all_date or "",    invert=True) if snap.cpi_all_yoy       else "",
            dr("Unemployment",     f"{snap.unemployment_rate:.1f}%",                                         invert=True) if snap.unemployment_rate  else "",
            dr("GDP Growth",       f"{snap.gdp_growth_qoq:.1f}% QoQ ann.",  sub=snap.gdp_growth_date or "")              if snap.gdp_growth_qoq     else "",
            dr("National Debt",    f"${snap.national_debt/1e12:.2f}T",       sub=snap.national_debt_date or "", invert=True) if snap.national_debt   else "",
            dr("Eggs (Grade A)",   f"${snap.eggs_price:.2f}/doz",                                            invert=True) if snap.eggs_price         else "",
            dr("Milk (whole)",     f"${snap.milk_price:.2f}/gal",                                            invert=True) if snap.milk_price         else "",
        ]))
        if macro_rows:
            cards_html += card("Economy", "📉", macro_rows)
    else:
        cards_html = '<p class="empty-msg">No snapshot data yet — run financial_snapshot.py first.</p>'

    # ── News section ──────────────────────────────────────────────────────────
    if news:
        news_cards = "".join(
            f'<a class="news-card" href="{html_lib.escape(a["link"])}" target="_blank" rel="noopener noreferrer">'
            f'<div class="nc-source">{html_lib.escape(a["source"])}</div>'
            f'<div class="nc-title">{html_lib.escape(a["title"])}</div>'
            f'</a>'
            for a in news
        )
        news_section = (
            f'<section class="page-sec" id="news">'
            f'<h2 class="sec-hd">Market News</h2>'
            f'<div class="news-grid">{news_cards}</div>'
            f'</section>'
        )
    else:
        news_section = ""

    # ── Firm Insights ─────────────────────────────────────────────────────────
    if firm_insights:
        insight_cols = ""
        for group in firm_insights:
            rows = "".join(
                f'<a class="fi-row" href="{html_lib.escape(a["link"])}" target="_blank" rel="noopener noreferrer">'
                f'{html_lib.escape(a["title"])}'
                f'</a>'
                for a in group["articles"]
            )
            insight_cols += (
                f'<div class="fi-card">'
                f'<div class="fi-hd">{html_lib.escape(group["source"])}</div>'
                f'{rows}'
                f'</div>'
            )
        firm_insights_section = (
            f'<section class="page-sec" id="insights">'
            f'<h2 class="sec-hd">Firm Insights</h2>'
            f'<div class="fi-grid">{insight_cols}</div>'
            f'</section>'
        )
    else:
        firm_insights_section = ""

    # ── Archive ───────────────────────────────────────────────────────────────
    groups = defaultdict(list)
    for dt, name in entries:
        groups[(dt.year, dt.month)].append((dt, name))
    groups = dict(sorted(groups.items(), reverse=True))

    arc_months = ""
    for (year, month), month_entries in groups.items():
        mname = datetime(year, month, 1).strftime("%B %Y")
        rows  = "".join(
            f'<a class="arc-row" href="{name}">{dt.strftime("%a %b %-d · %H:%M")}</a>'
            for dt, name in month_entries
        )
        arc_months += (
            f'<div class="arc-month">'
            f'<div class="arc-mhd">{mname} <span class="arc-cnt">{len(month_entries)}</span></div>'
            f'<div class="arc-rows">{rows}</div>'
            f'</div>'
        )

    archive_section = (
        f'<section class="page-sec" id="archive">'
        f'<h2 class="sec-hd">Snapshot Archive</h2>'
        f'<div class="arc-grid">{arc_months if arc_months else "<p class=\"empty-msg\">No snapshots yet.</p>"}</div>'
        f'</section>'
    ) if entries else ""

    # ── Full page ─────────────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{APP_TITLE}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg:      #0d1117;
      --bg2:     #161b22;
      --bg3:     #21262d;
      --border:  rgba(240,246,252,0.10);
      --border2: rgba(240,246,252,0.18);
      --t1:      #e6edf3;
      --t2:      #8b949e;
      --t3:      #484f58;
      --accent:  #388bfd;
      --up:      #3fb950;
      --dn:      #f85149;
      --neu:     #8b949e;
      --r:       8px;
    }}
    html {{ scroll-behavior: smooth; }}
    body {{
      background: var(--bg);
      color: var(--t1);
      font-family: 'Inter', -apple-system, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      min-height: 100vh;
    }}
    a {{ color: inherit; text-decoration: none; }}

    /* ── Top bar ────────────────────────────────────── */
    .topbar {{
      position: sticky; top: 0; z-index: 100;
      background: rgba(13,17,23,0.92);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
      padding: 0 24px; height: 56px;
      display: flex; align-items: center; justify-content: space-between;
    }}
    .tb-left  {{ display: flex; align-items: center; gap: 12px; }}
    .tb-logo  {{ font-size: 16px; font-weight: 600; letter-spacing: -.3px; }}
    .tb-badge {{
      font-size: 10px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase;
      background: var(--bg3); color: var(--t2); border: 1px solid var(--border);
      padding: 2px 8px; border-radius: 20px;
    }}
    .tb-right {{ display: flex; align-items: center; gap: 16px; }}
    .tb-meta  {{ font-size: 12px; color: var(--t2); font-family: 'JetBrains Mono', monospace; }}
    .tb-meta span {{ color: var(--t1); }}
    .tb-cta {{
      font-size: 13px; font-weight: 500; color: var(--accent);
      padding: 6px 14px; border: 1px solid var(--accent);
      border-radius: 6px; transition: background .15s;
    }}
    .tb-cta:hover {{ background: rgba(56,139,253,.1); }}
    .live-badge {{
      display: flex; align-items: center; gap: 5px;
      font-size: 10px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
      color: var(--up);
    }}
    .live-dot {{
      width: 6px; height: 6px; border-radius: 50%; background: var(--up);
      animation: livepulse 2s ease-in-out infinite;
    }}
    @keyframes livepulse {{
      0%, 100% {{ opacity: 1; transform: scale(1); }}
      50%       {{ opacity: 0.35; transform: scale(0.85); }}
    }}
    .tb-updated {{ font-size: 11px; color: var(--t3); font-family: 'JetBrains Mono', monospace; }}

    /* ── Page wrapper ───────────────────────────────── */
    .page {{ max-width: 1100px; margin: 0 auto; padding: 32px 24px 80px; }}

    /* ── Hero strip ─────────────────────────────────── */
    .hero-strip {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(155px, 1fr));
      gap: 12px;
      margin-bottom: 40px;
    }}
    .hero-tile {{
      background: var(--bg2); border: 1px solid var(--border);
      border-radius: var(--r); padding: 16px;
      transition: border-color .15s;
    }}
    .hero-tile:hover {{ border-color: var(--border2); }}
    .h-label {{ font-size: 11px; color: var(--t2); text-transform: uppercase; letter-spacing: .07em; margin-bottom: 6px; }}
    .h-val   {{ font-family: 'JetBrains Mono', monospace; font-size: 20px; font-weight: 500; color: var(--t1); line-height: 1.1; margin-bottom: 4px; }}
    .h-chg   {{ font-family: 'JetBrains Mono', monospace; font-size: 12px; min-height: 16px; }}

    /* ── Section heading ────────────────────────────── */
    .sec-hd {{
      font-size: 11px; font-weight: 600; letter-spacing: .09em; text-transform: uppercase;
      color: var(--t2); margin-bottom: 14px; padding-bottom: 10px;
      border-bottom: 1px solid var(--border);
    }}
    .page-sec {{ margin-bottom: 48px; }}

    /* ── Data cards ─────────────────────────────────── */
    .cards-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
      gap: 12px;
    }}
    .data-card {{
      background: var(--bg2); border: 1px solid var(--border);
      border-radius: var(--r); overflow: hidden;
    }}
    .card-hd {{
      font-size: 11px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase;
      color: var(--t2); padding: 10px 14px; border-bottom: 1px solid var(--border);
      display: flex; align-items: center; gap: 6px;
    }}
    .card-icon {{ font-size: 13px; }}
    .dr {{
      display: flex; align-items: baseline; justify-content: space-between;
      padding: 7px 14px; border-bottom: 1px solid var(--border);
    }}
    .dr:last-child {{ border-bottom: none; }}
    .dr-lbl {{ color: var(--t2); font-size: 13px; }}
    .dr-val {{ font-family: 'JetBrains Mono', monospace; font-size: 13px; color: var(--t1); text-align: right; }}
    .dr-chg {{ font-size: 11px; margin-left: 5px; }}
    .dr-sub {{ font-size: 10px; color: var(--t3); display: block; margin-top: 1px; }}

    /* ── Colors ─────────────────────────────────────── */
    .up  {{ color: var(--up); }}
    .dn  {{ color: var(--dn); }}
    .neu {{ color: var(--neu); }}

    /* ── News ───────────────────────────────────────── */
    .news-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
      gap: 12px;
    }}
    .news-card {{
      background: var(--bg2); border: 1px solid var(--border);
      border-radius: var(--r); padding: 16px; display: block;
      transition: border-color .15s, background .15s;
    }}
    .news-card:hover {{ border-color: var(--border2); background: var(--bg3); }}
    .nc-source {{ font-size: 10px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--accent); margin-bottom: 6px; }}
    .nc-title  {{ font-size: 14px; color: var(--t1); line-height: 1.4; }}

    /* ── AI Analysis ───────────────────────────────── */
    .ai-card {{
      background: linear-gradient(135deg, rgba(56,139,253,0.08) 0%, rgba(56,139,253,0.03) 100%);
      border: 1px solid rgba(56,139,253,0.25);
      border-radius: var(--r); padding: 20px 24px;
      margin-bottom: 40px;
    }}
    .ai-hd {{
      font-size: 10px; font-weight: 600; letter-spacing: .1em; text-transform: uppercase;
      color: var(--accent); margin-bottom: 10px;
      display: flex; align-items: center; gap: 6px;
    }}
    .ai-hd::after {{
      content: ''; flex: 1; height: 1px;
      background: rgba(56,139,253,0.2);
    }}
    .ai-body {{
      font-size: 14px; color: var(--t1); line-height: 1.65;
    }}
    .ai-watch {{
      margin-top: 12px; padding: 8px 12px;
      background: rgba(56,139,253,0.07); border-left: 3px solid var(--accent);
      font-size: 13px; color: var(--t1); line-height: 1.55; border-radius: 0 4px 4px 0;
    }}

    /* ── Firm Insights ──────────────────────────────── */
    .fi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      gap: 12px;
    }}
    .fi-card {{
      background: var(--bg2); border: 1px solid var(--border);
      border-radius: var(--r); overflow: hidden;
    }}
    .fi-hd {{
      font-size: 11px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase;
      color: var(--accent); padding: 10px 14px; border-bottom: 1px solid var(--border);
    }}
    .fi-row {{
      display: block; padding: 9px 14px; font-size: 13px; color: var(--t2);
      border-bottom: 1px solid var(--border); line-height: 1.4;
      transition: color .12s, background .12s;
    }}
    .fi-row:last-child {{ border-bottom: none; }}
    .fi-row:hover {{ color: var(--t1); background: var(--bg3); }}

    /* ── Subscribe ──────────────────────────────────── */
    .sub-card {{
      background: var(--bg2); border: 1px solid var(--border);
      border-radius: var(--r); padding: 36px 40px;
      display: flex; align-items: center; gap: 48px;
    }}
    .sub-copy       {{ flex: 1; }}
    .sub-copy h2    {{ font-size: 20px; font-weight: 600; margin-bottom: 6px; }}
    .sub-copy p     {{ color: var(--t2); font-size: 14px; }}
    .sub-form       {{ flex: 1; display: flex; flex-direction: column; gap: 10px; }}
    .form-row       {{ display: flex; gap: 8px; }}
    .form-row input, .sub-form input[type="email"] {{
      flex: 1; background: var(--bg3); border: 1px solid var(--border);
      border-radius: 6px; padding: 9px 12px; color: var(--t1);
      font-size: 13px; font-family: inherit; outline: none;
      transition: border-color .15s;
    }}
    .form-row input:focus, .sub-form input[type="email"]:focus {{ border-color: var(--accent); }}
    .sub-form button {{
      background: var(--accent); color: #fff; border: none; border-radius: 6px;
      padding: 10px; font-size: 14px; font-weight: 500; cursor: pointer;
      font-family: inherit; transition: opacity .15s;
    }}
    .sub-form button:hover {{ opacity: .85; }}
    .sub-msg      {{ font-size: 13px; min-height: 18px; }}
    .sub-msg.ok   {{ color: var(--up); }}
    .sub-msg.err  {{ color: var(--dn); }}

    /* ── Archive ────────────────────────────────────── */
    .arc-grid   {{ display: flex; flex-direction: column; gap: 20px; }}
    .arc-mhd    {{
      font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
      color: var(--t2); margin-bottom: 8px; display: flex; align-items: center; gap: 8px;
    }}
    .arc-cnt    {{
      font-size: 10px; background: var(--bg3); border: 1px solid var(--border);
      padding: 1px 6px; border-radius: 10px; color: var(--t3); font-weight: 400;
    }}
    .arc-rows   {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .arc-row    {{
      font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--t2);
      background: var(--bg2); border: 1px solid var(--border); border-radius: 4px;
      padding: 4px 10px; transition: color .12s, border-color .12s;
    }}
    .arc-row:hover {{ color: var(--t1); border-color: var(--border2); }}

    /* ── Footer ─────────────────────────────────────── */
    .footer {{
      border-top: 1px solid var(--border); padding-top: 24px; margin-top: 8px;
      display: flex; justify-content: space-between; align-items: center;
      flex-wrap: wrap; gap: 8px;
    }}
    .footer-l, .footer-r {{ font-size: 11px; color: var(--t3); }}

    /* ── Misc ───────────────────────────────────────── */
    .empty-msg {{ color: var(--t3); font-size: 13px; padding: 8px 0; }}

    /* ── Responsive ─────────────────────────────────── */
    @media (max-width: 640px) {{
      .topbar {{ padding: 0 16px; }}
      .page {{ padding: 20px 16px 60px; }}
      .hero-strip {{ grid-template-columns: repeat(2, 1fr); }}
      .tb-meta {{ display: none; }}
      .sub-card {{ flex-direction: column; gap: 24px; padding: 24px; }}
      .form-row {{ flex-direction: column; }}
    }}
  </style>
</head>
<body>

<header class="topbar">
  <div class="tb-left">
    <span class="tb-logo">📊 {APP_TITLE}</span>
    <span class="tb-badge">Last snapshot: {snap_time}</span>
  </div>
  <div class="tb-right">
    <div class="live-badge"><div class="live-dot"></div>Live</div>
    <span class="tb-updated" id="live-ts">updating…</span>
    <a href="#subscribe" class="tb-cta">Subscribe</a>
  </div>
</header>

<div class="page">

  {ai_analysis_html}

  <div class="hero-strip">
    {heroes_html}
  </div>

  <section class="page-sec" id="data">
    <h2 class="sec-hd">Market Data</h2>
    <div class="cards-grid">
      {cards_html}
    </div>
  </section>

  {news_section}

  {firm_insights_section}

  <section class="page-sec" id="subscribe">
    <h2 class="sec-hd">Daily Email</h2>
    <div class="sub-card">
      <div class="sub-copy">
        <h2>Get the Daily Snapshot</h2>
        <p>Markets, crypto, energy, rates, and macro&nbsp;&mdash; delivered to your inbox each morning.</p>
      </div>
      <form class="sub-form" id="sub-form">
        <div class="form-row">
          <input type="text" name="first_name" placeholder="First name">
          <input type="email" name="email" placeholder="Email address" required>
        </div>
        <button type="submit">Subscribe &rarr;</button>
        <div class="sub-msg" id="sub-msg"></div>
      </form>
    </div>
  </section>

  {archive_section}

  <footer class="footer">
    <div class="footer-l">Data: CoinGecko &middot; Yahoo Finance &middot; EIA &middot; FRED/BLS &middot; US Treasury &middot; Not financial advice</div>
    <div class="footer-r">{total} snapshot{"s" if total != 1 else ""} archived</div>
  </footer>

</div>

<script>
// ── Live data polling ────────────────────────────────────────────────────────
const POLL_INTERVAL = 60000; // ms

function applyLiveData(data) {{
  document.querySelectorAll('[data-live]').forEach(el => {{
    const [key, type] = el.getAttribute('data-live').split(':');
    const item = data[key];
    if (!item) return;
    if (type === 'price') {{
      el.textContent = item.price;
    }} else if (type === 'change') {{
      el.textContent = item.change;
      if (item.cls) {{
        el.className = el.className.replace(/\b(up|dn|neu)\b/g, '').trim() + ' ' + item.cls;
      }}
    }}
  }});
  const ts = document.getElementById('live-ts');
  if (ts && data.updated_at) ts.textContent = data.updated_at;
}}

async function pollLive() {{
  try {{
    const r = await fetch('/api/live');
    if (r.ok) applyLiveData(await r.json());
  }} catch (e) {{
    console.warn('Live data fetch failed:', e);
  }}
}}

pollLive();
setInterval(pollLive, POLL_INTERVAL);

// ── Subscribe form ───────────────────────────────────────────────────────────
document.getElementById('sub-form').addEventListener('submit', async function(e) {{
  e.preventDefault();
  const msg = document.getElementById('sub-msg');
  msg.className = 'sub-msg';
  msg.textContent = 'Subscribing\u2026';
  const data = {{
    first_name: (this.first_name.value || '').trim(),
    email:      this.email.value.trim(),
  }};
  try {{
    const r = await fetch('/subscribe', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(data),
    }});
    if (r.ok) {{
      msg.className = 'sub-msg ok';
      msg.textContent = "You\u2019re subscribed! Check your inbox for a confirmation.";
      this.reset();
    }} else {{
      const j = await r.json().catch(() => ({{}}));
      msg.className = 'sub-msg err';
      msg.textContent = j.error || 'Something went wrong. Please try again.';
    }}
  }} catch {{
    msg.className = 'sub-msg err';
    msg.textContent = 'Could not connect. Please try again.';
  }}
}});
</script>

</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────

def generate(target_dir=None):
    """Generate the dashboard. Can be called programmatically."""
    if target_dir is None:
        target_dir = Path(__file__).parent / "html"
    target_dir = Path(target_dir)
    target_dir.mkdir(exist_ok=True)

    snap           = get_latest_snapshot()
    news           = fetch_news()
    firm_insights  = fetch_firm_insights()
    entries        = build_entries(target_dir)
    page           = render_html(snap, news, entries, firm_insights)

    out = target_dir / OUTPUT_FILENAME
    out.write_text(page, encoding="utf-8")

    insight_count = sum(len(g["articles"]) for g in firm_insights)
    print(f"✓  Dashboard generated: {out}")
    print(f"   Snapshot: {'yes' if snap else 'none'} · News: {len(news)} articles · Insights: {insight_count} ({len(firm_insights)} sources) · Archive: {len(entries)} files")


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print(__doc__)
        sys.exit(0)
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    generate(target)


if __name__ == "__main__":
    main()
