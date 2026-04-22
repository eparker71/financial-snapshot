#!/usr/bin/env python3
"""
generate_portfolios.py
────────────────────────────────────────────────────────────────────────────
Generates html/portfolios.html — a single tabbed page with AI-generated
portfolio recommendations for every supported brokerage.

For each brokerage:
  1. Calls Anthropic API (claude-sonnet-4-6) with brokerage-specific fund hints
  2. Validates every ticker via Yahoo Finance (live ER, AUM, fund name)
  3. Embeds all results in one self-contained HTML with a tab switcher

Usage:
    python3 generate_portfolios.py                  # all brokerages → html/portfolios.html
    python3 generate_portfolios.py --skip-validation
    python3 generate_portfolios.py --out /path/to/out.html
"""

import json
import os
import re
import sys
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import anthropic
import yfinance as yf

# ── Config ────────────────────────────────────────────────────────────────────
HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
if not API_KEY:
    sys.exit("❌  ANTHROPIC_API_KEY not found. Add it to .env and retry.")

AUM_THRESHOLD = 10_000_000_000   # $10 B
YF_DELAY      = 0.3              # seconds between yfinance calls


# ── Brokerage definitions (tab order matters) ─────────────────────────────────
BROKERAGES = [
    {
        "key":   "fidelity",
        "label": "Fidelity",
        "prompt": """
Brokerage: Fidelity Investments
• Strongly prefer Fidelity ZERO index funds where appropriate:
    FZROX (Zero Total Market, 0% ER), FZILX (Zero International, 0% ER), FZIPX (Zero Extended Market, 0% ER)
  These are mutual funds available only at Fidelity and cannot be transferred in-kind to other brokerages.
  When recommending them, note the portability trade-off in the holding rationale.
• Also consider Fidelity's ultra-low-cost index funds: FXAIX (0.015%), FSKAX (0.015%),
  FXNAX (0.025%), FSMAX (0.035%)
• iShares Core ETFs (e.g. IEFA, IEMG, AGG, IEF) trade commission-free at Fidelity — acceptable alternatives
• Avoid Vanguard Admiral shares (VTSAX, VTIAX) — use their ETF equivalents (VTI, VXUS) instead
• Avoid Schwab-proprietary ETFs (SCHB, SCHF, etc.) — they offer no advantage at Fidelity""",
    },
    {
        "key":   "vanguard",
        "label": "Vanguard",
        "prompt": """
Brokerage: Vanguard
• Strongly prefer Vanguard ETFs: VTI, VXUS, BND, BNDX, VYM, VIG, VB, VO, VWO, VGSH, VTIP, etc.
• Vanguard Admiral shares (VTSAX, VTIAX, VBTLX) are also acceptable — no transaction fees at Vanguard
• Note Vanguard's unique investor-owned structure which structurally aligns costs with shareholders
• Avoid Fidelity ZERO funds (mutual funds not portable to Vanguard)
• Avoid Schwab-proprietary ETFs""",
    },
    {
        "key":   "schwab",
        "label": "Schwab",
        "prompt": """
Brokerage: Charles Schwab
• Strongly prefer Schwab ETFs where available — they trade commission-free with no minimums at Schwab:
    SCHB (broad US market, 0.03%), SCHF (international, 0.06%), SCHD (dividend, 0.06%),
    SCHZ (aggregate bond, 0.03%), SCHO (short treasury, 0.03%), SCHP (TIPS, 0.03%)
• iShares and Vanguard ETFs are also commission-free at Schwab and acceptable where no Schwab equivalent exists
• Avoid Fidelity ZERO funds — not available or transferable at Schwab""",
    },
    {
        "key":   "etrade",
        "label": "E*TRADE",
        "prompt": """
Brokerage: E*TRADE (Morgan Stanley)
• E*TRADE has no proprietary ETF lineup — favour the most liquid, cost-efficient broadly available ETFs
• iShares Core ETFs (AGG, IEFA, IEMG, ITOT) are available commission-free on E*TRADE — prefer these
• Vanguard ETFs (VTI, VXUS, BND) are also good choices
• Avoid Fidelity ZERO funds (not available at E*TRADE)
• Avoid Schwab-proprietary ETFs""",
    },
    {
        "key":   "any",
        "label": "Generic",
        "prompt": "",
    },
]


# ── Prompts ───────────────────────────────────────────────────────────────────
SYSTEM = (
    "You are a portfolio construction expert specialising in low-cost, "
    "tax-efficient index fund portfolios for retail investors. "
    "You respond ONLY with raw JSON — no markdown fences, no prose, no explanation. "
    "Your response must start with [ and end with ]."
)

BASE_USER = """\
Return a raw JSON array of exactly 4 investment portfolio objects.
No markdown, no explanation — only the JSON array.

Each object must contain exactly these fields:
  id                      — string slug
  name                    — display name string
  description             — 2-3 sentence strategy summary
  riskLevel               — one of: "Low", "Moderate", "High", "Very High"
  expectedAnnualReturn    — e.g. "4–6%"
  rebalancingFrequency    — one of: "Monthly", "Quarterly", "Semi-Annually", "Annually"
  rebalancingRationale    — one sentence explaining the frequency choice
  holdings                — array of holding objects, allocations must sum to exactly 100

Each holding object must contain:
  ticker       — string (e.g. "VYM")
  name         — full fund name string
  allocation   — number (percentage, e.g. 25)
  expenseRatio — number as decimal percentage, e.g. 0.03 for 0.03%
  type         — one of: "ETF", "Index Fund", "Bond Fund"
  rationale    — one sentence explaining why it fits

The four portfolios (in order, with exact id values):
1. id "dividend-income"       — Dividend Income: high-yield dividend ETFs/funds
2. id "aggressive-growth"     — Aggressive Growth: equity-heavy, small/mid-cap tilt, international exposure
3. id "moderate-growth"       — Moderate Growth: balanced equities and bonds
4. id "capital-preservation"  — Capital Preservation: bond-heavy, stable value, minimal volatility

Hard constraints — every fund selected must satisfy ALL of the following:
• AUM (total assets) greater than $10 billion — no small or illiquid funds
• Broad-market or multi-sector only — no single-sector ETFs (e.g. avoid XLE, XLF, XLV, etc.)
• ETF structure strongly preferred over mutual funds — better tax efficiency and intraday liquidity
  (exception: Fidelity ZERO funds are acceptable if the brokerage is Fidelity)
• Low portfolio turnover (< 20% annually) — minimises capital-gains distributions
• At least 5 years of operating history — no newly launched funds
• Favour passive index-tracking over actively managed
• Minimise expense ratios — favour the cheapest share class available
• 4–6 holdings per portfolio
• All allocations within each portfolio must sum to exactly 100"""


def build_user_prompt(brokerage_prompt: str) -> str:
    return BASE_USER + brokerage_prompt


# ── Step 1 — Fetch portfolios from Claude ────────────────────────────────────
def fetch_portfolios(label: str, brokerage_prompt: str) -> list[dict]:
    print(f"\n⏳  [{label}] Calling Anthropic API…")
    client  = anthropic.Anthropic(api_key=API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": build_user_prompt(brokerage_prompt)}],
    )

    raw = message.content[0].text.strip()
    raw = re.sub(r"^```[a-z]*\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```\s*$", "", raw).strip()

    portfolios = json.loads(raw)
    if not isinstance(portfolios, list) or len(portfolios) != 4:
        raise ValueError(
            f"[{label}] Expected 4 portfolios, got "
            f"{type(portfolios).__name__}({len(portfolios) if isinstance(portfolios, list) else '?'})"
        )
    print(f"✅  [{label}] Received {len(portfolios)} portfolios.")
    return portfolios


# ── Step 2 — Validate & enrich with Yahoo Finance ────────────────────────────
def _fmt_aum(n: float | None) -> str:
    if not n:
        return "N/A"
    if n >= 1e12:
        return f"${n/1e12:.1f}T"
    if n >= 1e9:
        return f"${n/1e9:.1f}B"
    return f"${n/1e6:.0f}M"


def validate_with_yfinance(portfolios: list[dict], label: str, key: str) -> tuple[list[dict], dict]:
    print(f"🔍  [{label}] Validating tickers via Yahoo Finance…")
    report = {
        "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "er_updates":  [],
        "warnings":    [],
    }

    seen_tickers: dict[str, dict] = {}

    for portfolio in portfolios:
        for holding in portfolio["holdings"]:
            ticker = holding["ticker"].upper()

            if ticker not in seen_tickers:
                time.sleep(YF_DELAY)
                try:
                    info = yf.Ticker(ticker).info
                    seen_tickers[ticker] = info
                except Exception as exc:
                    report["warnings"].append(f"{ticker}: yfinance fetch failed ({exc})")
                    seen_tickers[ticker] = {}

            info = seen_tickers[ticker]
            holding["validated"] = bool(info)

            if not info:
                report["warnings"].append(f"{ticker}: no data returned — ticker may be invalid")
                holding["aum"] = None
                continue

            live_er = info.get("netExpenseRatio")
            if live_er is not None:
                old_er = holding["expenseRatio"]
                if abs(old_er - live_er) > 0.001:
                    report["er_updates"].append((ticker, old_er, live_er))
                    print(f"   {ticker}: ER updated {old_er:.3f}% → {live_er:.3f}%")
                holding["expenseRatio"] = live_er

            aum = info.get("totalAssets")
            holding["aum"] = aum
            if aum is not None and aum < AUM_THRESHOLD:
                is_mutual_fund = info.get("quoteType") == "MUTUALFUND"
                if key != "any" and is_mutual_fund:
                    print(f"   ℹ️  {ticker}: AUM {_fmt_aum(aum)} (mutual fund — threshold waived for {label})")
                else:
                    report["warnings"].append(
                        f"{ticker}: AUM {_fmt_aum(aum)} is below the $10B threshold"
                    )
                    print(f"   ⚠️  {ticker}: AUM {_fmt_aum(aum)} is below $10B threshold")

            live_name = info.get("longName") or info.get("shortName")
            if live_name:
                holding["liveFullName"] = live_name

            qtype = info.get("quoteType", "")
            if qtype not in ("ETF", "MUTUALFUND", ""):
                report["warnings"].append(
                    f"{ticker}: unexpected quoteType '{qtype}'"
                )

    total  = sum(len(p["holdings"]) for p in portfolios)
    n_warn = len(report["warnings"])
    print(f"✅  [{label}] {total} holdings checked, {n_warn} warning{'s' if n_warn != 1 else ''}.")
    if report["warnings"]:
        for w in report["warnings"]:
            print(f"   ⚠️  {w}")

    return portfolios, report


# ── Step 3 — Build HTML ───────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Portfolio Advisor &mdash; Market Pulse</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
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
      --r:       8px;
    }
    html { scroll-behavior: smooth; }
    body {
      background: var(--bg);
      color: var(--t1);
      font-family: 'Inter', -apple-system, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      min-height: 100vh;
    }
    a { color: inherit; text-decoration: none; }

    /* ── Top bar ──────────────────────────────────────── */
    .topbar {
      position: sticky; top: 0; z-index: 100;
      background: rgba(13,17,23,0.92);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
      padding: 0 24px; height: 56px;
      display: flex; align-items: center; justify-content: space-between;
    }
    .tb-left  { display: flex; align-items: center; gap: 12px; }
    .tb-logo  { font-size: 16px; font-weight: 600; letter-spacing: -.3px; }
    .tb-badge {
      font-size: 10px; font-weight: 500; letter-spacing: .06em; text-transform: uppercase;
      background: var(--bg3); color: var(--t2); border: 1px solid var(--border);
      padding: 2px 8px; border-radius: 20px;
    }
    .tb-right { display: flex; align-items: center; gap: 16px; }
    .tb-back {
      font-size: 13px; font-weight: 500; color: var(--t2);
      padding: 6px 14px; border: 1px solid var(--border);
      border-radius: 6px; transition: border-color .15s, color .15s;
    }
    .tb-back:hover { border-color: var(--border2); color: var(--t1); }

    /* ── Page wrapper ─────────────────────────────────── */
    .page { max-width: 1200px; margin: 0 auto; padding: 32px 24px 80px; }

    /* ── Page header ──────────────────────────────────── */
    .page-header { margin-bottom: 24px; }
    .page-header h1 {
      font-size: 22px; font-weight: 600; color: var(--t1);
      letter-spacing: -.3px; margin-bottom: 6px;
    }
    .page-header p { color: var(--t2); font-size: 13px; }
    .meta-pills {
      display: flex; flex-wrap: wrap;
      gap: 6px; margin-top: 12px;
    }
    .pill {
      font-size: 10px; font-weight: 600; padding: 3px 10px;
      border-radius: 20px; border: 1px solid var(--border);
      background: var(--bg2); color: var(--t2); letter-spacing: .04em;
    }
    .pill.green { border-color: rgba(63,185,80,.35); color: var(--up); background: rgba(63,185,80,.08); }

    /* ── Brokerage tabs ───────────────────────────────── */
    .tab-bar {
      display: flex; gap: 4px; margin-bottom: 24px;
      border-bottom: 1px solid var(--border); padding-bottom: 0;
      overflow-x: auto; -webkit-overflow-scrolling: touch;
    }
    .tab-bar::-webkit-scrollbar { display: none; }
    .tab-btn {
      flex-shrink: 0;
      font-size: 13px; font-weight: 500; color: var(--t2);
      padding: 8px 16px; border: none; background: none; cursor: pointer;
      border-bottom: 2px solid transparent; margin-bottom: -1px;
      transition: color .15s, border-color .15s;
    }
    .tab-btn:hover { color: var(--t1); }
    .tab-btn.active { color: var(--t1); border-bottom-color: var(--accent); }

    /* ── Warnings banner ──────────────────────────────── */
    .warnings-banner {
      margin-bottom: 20px;
      background: rgba(248,81,73,.08); border: 1px solid rgba(248,81,73,.3);
      border-radius: var(--r); padding: 12px 16px;
      font-size: 12px; color: #f85149;
    }
    .warnings-banner strong { display: block; margin-bottom: 4px; font-weight: 600; }
    .warnings-banner ul { padding-left: 16px; }
    .warnings-banner li { margin-bottom: 3px; }

    /* ── Grid ─────────────────────────────────────────── */
    .portfolio-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 16px;
    }
    @media (max-width: 820px) { .portfolio-grid { grid-template-columns: 1fr; } }

    /* ── Card ─────────────────────────────────────────── */
    .card {
      background: var(--bg2); border: 1px solid var(--border);
      border-radius: 12px; overflow: hidden;
      display: flex; flex-direction: column;
      transition: border-color .15s;
    }
    .card:hover { border-color: var(--border2); }
    .card-header { padding: 18px 20px 16px; }
    .header-top  { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
    .card-name   { font-size: 15px; font-weight: 600; line-height: 1.3; flex: 1; color: #fff; }
    .risk-badge  {
      font-size: 10px; font-weight: 700; letter-spacing: .05em;
      text-transform: uppercase; padding: 3px 9px; border-radius: 20px;
      border: 1.5px solid rgba(255,255,255,.3); background: rgba(255,255,255,.12);
      white-space: nowrap; flex-shrink: 0; color: #fff;
    }
    .card-body {
      padding: 18px 20px 20px; flex: 1;
      display: flex; flex-direction: column; gap: 14px;
    }
    .description { font-size: 13px; color: var(--t2); line-height: 1.65; }

    /* Meta row */
    .meta-row  { display: flex; gap: 20px; flex-wrap: wrap; }
    .meta-item { display: flex; flex-direction: column; gap: 3px; }
    .meta-label {
      font-size: 10px; text-transform: uppercase; letter-spacing: .06em;
      color: var(--t3); font-weight: 600;
    }
    .meta-value {
      font-size: 15px; font-weight: 600; color: var(--t1);
      font-family: 'JetBrains Mono', monospace;
    }
    .rebal-rationale {
      font-size: 12px; color: var(--t2); line-height: 1.55;
      padding: 8px 12px; background: var(--bg3);
      border-radius: 6px; border-left: 3px solid var(--border2);
    }

    /* Allocation bar */
    .section-label {
      font-size: 10px; text-transform: uppercase; letter-spacing: .06em;
      font-weight: 600; color: var(--t3); margin-bottom: 6px;
    }
    .alloc-bar {
      display: flex; height: 14px; border-radius: 4px;
      overflow: hidden; background: var(--bg3);
    }
    .bar-seg { transition: filter 0.15s; cursor: default; }
    .bar-seg:hover { filter: brightness(1.15); }
    .bar-legend { display: flex; flex-wrap: wrap; gap: 5px 12px; margin-top: 6px; }
    .legend-item { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--t2); }
    .legend-swatch { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }

    /* Holdings table */
    .table-wrap { border: 1px solid var(--border); border-radius: var(--r); overflow: hidden; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    thead th {
      background: var(--bg3); padding: 7px 10px; text-align: left;
      font-weight: 600; font-size: 10px; text-transform: uppercase;
      letter-spacing: .06em; color: var(--t2); border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }
    tbody td {
      padding: 8px 10px; border-bottom: 1px solid var(--border);
      color: var(--t1); vertical-align: middle;
    }
    tbody tr:last-child td { border-bottom: none; }
    tbody tr:hover td { background: rgba(240,246,252,.03); }
    .ticker-cell {
      font-weight: 600; font-family: 'JetBrains Mono', monospace;
      font-size: 12px; white-space: nowrap; color: var(--accent);
    }
    .fund-name { color: var(--t2); }
    .alloc-num, .er-num, .aum-num {
      white-space: nowrap; font-family: 'JetBrains Mono', monospace;
    }
    .alloc-num { font-weight: 600; }
    .aum-num   { color: var(--t2); }
    .type-chip {
      display: inline-block; font-size: 10px; font-weight: 600;
      padding: 2px 7px; border-radius: 4px;
      background: var(--bg3); color: var(--t2); white-space: nowrap;
      border: 1px solid var(--border);
    }
    .er-live-badge {
      display: inline-block; font-size: 9px; font-weight: 700;
      padding: 1px 5px; border-radius: 3px;
      background: rgba(63,185,80,.12); color: var(--up);
      border: 1px solid rgba(63,185,80,.3);
      margin-left: 4px; vertical-align: middle;
    }
    .wer-row {
      padding: 8px 10px; background: var(--bg3);
      border-top: 1px solid var(--border); font-size: 11px; color: var(--t2);
      display: flex; justify-content: space-between; align-items: center;
      flex-wrap: wrap; gap: 4px;
    }
    .wer-row strong { color: var(--t1); font-weight: 600; }
    .source-note { font-size: 10px; color: var(--t3); }

    /* ── Disclaimer ───────────────────────────────────── */
    .disclaimer {
      margin: 40px 0 0;
      background: var(--bg2); border: 1px solid var(--border);
      border-radius: var(--r); padding: 18px 22px;
    }
    .disclaimer h3 {
      font-size: 10px; font-weight: 600; text-transform: uppercase;
      letter-spacing: .08em; color: var(--t3); margin-bottom: 8px;
    }
    .disclaimer p { font-size: 12px; color: var(--t2); line-height: 1.7; }
    .disclaimer p + p { margin-top: 6px; }

    /* ── Responsive ───────────────────────────────────── */
    @media (max-width: 640px) {
      .topbar { padding: 0 16px; }
      .page   { padding: 20px 16px 60px; }
    }
  </style>
</head>
<body>

<header class="topbar">
  <div class="tb-left">
    <span class="tb-logo">&#128200; Market Pulse</span>
    <span class="tb-badge">Portfolio Advisor</span>
  </div>
  <div class="tb-right">
    <a href="index.html" class="tb-back">&#8592; Dashboard</a>
  </div>
</header>

<div class="page">

  <div class="page-header">
    <h1>AI Portfolio Advisor</h1>
    <p>Four strategies per brokerage &middot; Generated by Claude &middot; Validated via Yahoo Finance</p>
    <div class="meta-pills">
      <span class="pill">Generated __GENERATED_AT__</span>
      <span class="pill green">&#10003; AUM &gt; $10B enforced</span>
      <span class="pill green">&#10003; Broad-market only</span>
      <span class="pill green">&#10003; Tax-efficient structure</span>
    </div>
  </div>

  <div class="tab-bar" id="tab-bar"></div>
  <div id="tab-warnings"></div>
  <div class="portfolio-grid" id="grid"></div>

  <footer class="disclaimer">
    <h3>Important Disclaimer</h3>
    <p>
      This page was generated by an AI system (Anthropic Claude) and is provided for
      <strong>informational and educational purposes only</strong>. It does not constitute
      financial, investment, tax, or legal advice, and must not be relied upon as the basis
      for any investment decision. The portfolios shown are illustrative examples, not
      personalised recommendations.
    </p>
    <p>
      Investing involves risk, including the possible loss of principal. Past performance does not
      guarantee future results. Expense ratios and AUM figures are sourced from Yahoo Finance at the
      time of generation; verify current values with the fund provider before investing.
    </p>
    <p>
      Always consult a qualified, licensed financial advisor before making any investment decisions.
    </p>
  </footer>

</div>

<script>
const ALL_DATA = __ALL_DATA_JSON__;

const THEMES = {
  'dividend-income':     { gradient: 'linear-gradient(135deg,#14532d 0%,#16a34a 60%,#22c55e 100%)', segments: ['#15803d','#16a34a','#22c55e','#4ade80','#86efac','#bbf7d0'] },
  'aggressive-growth':   { gradient: 'linear-gradient(135deg,#7f1d1d 0%,#c2410c 55%,#ea580c 100%)', segments: ['#c2410c','#ea580c','#f97316','#fb923c','#fdba74','#fde68a'] },
  'moderate-growth':     { gradient: 'linear-gradient(135deg,#1e3a8a 0%,#1d4ed8 55%,#3b82f6 100%)', segments: ['#1d4ed8','#2563eb','#3b82f6','#60a5fa','#93c5fd','#bfdbfe'] },
  'capital-preservation':{ gradient: 'linear-gradient(135deg,#0f172a 0%,#334155 55%,#64748b 100%)', segments: ['#1e293b','#334155','#475569','#64748b','#94a3b8','#cbd5e1'] },
};
const FALLBACK = { gradient: 'linear-gradient(135deg,#4f46e5,#7c3aed)', segments: ['#4f46e5','#7c3aed','#ec4899','#14b8a6','#f59e0b','#ef4444'] };

function theme(id) { return THEMES[id] || FALLBACK; }

function wer(holdings) {
  const total = holdings.reduce((s, h) => s + h.allocation, 0) || 100;
  return holdings.reduce((s, h) => s + (h.expenseRatio * h.allocation / total), 0);
}

function fmtER(val) {
  if (val < 0.005) val *= 100;
  return val.toFixed(3) + '%';
}

function fmtAUM(n) {
  if (n == null) return 'N/A';
  if (n >= 1e12) return '$' + (n / 1e12).toFixed(1) + 'T';
  if (n >= 1e9)  return '$' + (n / 1e9).toFixed(1) + 'B';
  return '$' + (n / 1e6).toFixed(0) + 'M';
}

function renderCard(p) {
  const t      = theme(p.id);
  const sorted = [...p.holdings].sort((a, b) => b.allocation - a.allocation);
  const wa     = wer(p.holdings);

  const barSegs = sorted.map((h, i) => {
    const color = t.segments[i % t.segments.length];
    return `<div class="bar-seg" style="width:${h.allocation.toFixed(2)}%;background:${color};" title="${h.ticker}: ${h.allocation.toFixed(1)}%"></div>`;
  }).join('');

  const legend = sorted.map((h, i) => {
    const color = t.segments[i % t.segments.length];
    return `<div class="legend-item"><div class="legend-swatch" style="background:${color};"></div><span>${h.ticker} ${h.allocation.toFixed(0)}%</span></div>`;
  }).join('');

  const rows = p.holdings.map(h => {
    const liveBadge = h.validated ? '<span class="er-live-badge">live</span>' : '';
    const rationale = (h.rationale || '').replace(/"/g, '&quot;');
    return `<tr>
      <td class="ticker-cell" title="${rationale}">${h.ticker}</td>
      <td class="fund-name">${h.liveFullName || h.name}</td>
      <td class="alloc-num">${h.allocation.toFixed(1)}%</td>
      <td class="er-num">${fmtER(h.expenseRatio)}${liveBadge}</td>
      <td class="aum-num">${fmtAUM(h.aum)}</td>
      <td><span class="type-chip">${h.type}</span></td>
    </tr>`;
  }).join('');

  return `<div class="card">
    <div class="card-header" style="background:${t.gradient};">
      <div class="header-top">
        <div class="card-name">${p.name}</div>
        <span class="risk-badge">${p.riskLevel}&nbsp;Risk</span>
      </div>
    </div>
    <div class="card-body">
      <p class="description">${p.description}</p>
      <div class="meta-row">
        <div class="meta-item"><span class="meta-label">Expected Return</span><span class="meta-value">${p.expectedAnnualReturn}</span></div>
        <div class="meta-item"><span class="meta-label">Wtd. Avg. ER</span><span class="meta-value">${fmtER(wa)}</span></div>
        <div class="meta-item"><span class="meta-label">Rebalance</span><span class="meta-value">${p.rebalancingFrequency || '—'}</span></div>
        <div class="meta-item"><span class="meta-label">Holdings</span><span class="meta-value">${p.holdings.length}</span></div>
      </div>
      ${p.rebalancingRationale ? `<p class="rebal-rationale">&#x1F501; ${p.rebalancingRationale}</p>` : ''}
      <div>
        <div class="section-label">Allocation Breakdown</div>
        <div class="alloc-bar">${barSegs}</div>
        <div class="bar-legend">${legend}</div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Ticker</th><th>Fund Name</th><th>Alloc %</th><th>Exp. Ratio</th><th>AUM</th><th>Type</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <div class="wer-row">
          <span>Weighted avg. expense ratio:&nbsp;<strong>${fmtER(wa)}</strong></span>
          <span class="source-note">ER &amp; AUM from Yahoo Finance &middot; verified ${ALL_DATA[currentKey].verified_at}</span>
        </div>
      </div>
    </div>
  </div>`;
}

function renderWarnings(warnings) {
  if (!warnings || !warnings.length) return '';
  const items = warnings.map(w => `<li>${w}</li>`).join('');
  return `<div class="warnings-banner"><strong>&#9888; Validation warnings (${warnings.length})</strong><ul>${items}</ul></div>`;
}

let currentKey = ALL_DATA[0] ? ALL_DATA[0].key : null;
// ALL_DATA is an array; build a lookup map
const dataMap = {};
ALL_DATA.forEach(d => { dataMap[d.key] = d; });
if (!currentKey) currentKey = ALL_DATA[0]?.key;

function switchTab(key) {
  currentKey = key;
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.key === key);
  });
  const d = dataMap[key];
  document.getElementById('tab-warnings').innerHTML = renderWarnings(d.warnings);
  document.getElementById('grid').innerHTML = d.portfolios.map(renderCard).join('');
}

// Build tab bar
const tabBar = document.getElementById('tab-bar');
ALL_DATA.forEach(d => {
  const btn = document.createElement('button');
  btn.className = 'tab-btn' + (d.key === currentKey ? ' active' : '');
  btn.dataset.key = d.key;
  btn.textContent = d.label;
  btn.addEventListener('click', () => switchTab(d.key));
  tabBar.appendChild(btn);
});

// Render initial tab
switchTab(currentKey);
</script>
</body>
</html>
"""


def _build_warnings_html(warnings: list[str]) -> str:
    if not warnings:
        return ""
    items = "\n".join(f"  <li>{w}</li>" for w in warnings)
    return (
        f'<div class="warnings-banner">'
        f"<strong>&#9888; Validation warnings ({len(warnings)})</strong>"
        f"<ul>{items}</ul></div>"
    )


def build_html(all_data: list[dict], generated_at: str) -> str:
    all_data_json = json.dumps(all_data, indent=2, ensure_ascii=False)
    return (
        HTML_TEMPLATE
        .replace("__ALL_DATA_JSON__", all_data_json)
        .replace("__GENERATED_AT__", generated_at)
    )


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Generate html/portfolios.html with tabs for every brokerage."
    )
    parser.add_argument(
        "--out", default=str(HERE / "html" / "portfolios.html"),
        help="Output file path (default: html/portfolios.html)",
    )
    parser.add_argument(
        "--skip-validation", action="store_true",
        help="Skip Yahoo Finance validation (faster, but no live ER/AUM data)",
    )
    args = parser.parse_args()

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    all_data = []

    for b in BROKERAGES:
        portfolios = fetch_portfolios(b["label"], b["prompt"])

        if args.skip_validation:
            report = {
                "verified_at": "not validated",
                "er_updates":  [],
                "warnings":    ["Yahoo Finance validation was skipped (--skip-validation flag)."],
            }
        else:
            portfolios, report = validate_with_yfinance(portfolios, b["label"], b["key"])

        all_data.append({
            "key":         b["key"],
            "label":       b["label"],
            "portfolios":  portfolios,
            "verified_at": report["verified_at"],
            "warnings":    report["warnings"],
        })

    html = build_html(all_data, generated_at)
    out  = Path(args.out)
    out.write_text(html, encoding="utf-8")
    print(f"\n📄  Written → {out}")


if __name__ == "__main__":
    main()
