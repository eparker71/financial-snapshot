"""Defines shared snapshot section and row schema for HTML and plain-text renderers."""

import json
import logging
from typing import Any, Dict, List, Optional

from render_utils import fmt_change, fmt_pct_change, fmt_price
from render_utils import is_market_closed

log = logging.getLogger(__name__)

SnapshotData = Dict[str, Any]
RowData = Dict[str, Any]
SectionData = Dict[str, Any]


def _load_previous_prediction_markets() -> Dict[str, float]:
    """Return id -> headline_implied_pct map for the most recent prior snapshot.

    Used to compute today's delta vs yesterday's prediction-market odds.
    Returns {} on any DB / decode failure so rendering never breaks.
    """
    try:
        from models import Snapshot
        prev = (
            Snapshot
            .select(Snapshot.prediction_markets_json)
            .where(Snapshot.prediction_markets_json.is_null(False))
            .order_by(Snapshot.timestamp.desc())
            .first()
        )
        if not prev or not prev.prediction_markets_json:
            return {}
        parsed = json.loads(prev.prediction_markets_json)
        out: Dict[str, float] = {}
        for platform_key in ("polymarket", "kalshi"):
            for m in (parsed.get(platform_key) or {}).get("markets", []):
                outcomes = m.get("outcomes") or []
                if outcomes:
                    out[m["id"]] = outcomes[0]["implied_pct"]
        return out
    except Exception as e:
        log.warning(f"Failed to load previous prediction-market snapshot: {e}")
        return {}


def _short_title(title: str, max_len: int = 44) -> str:
    title = (title or "").strip().rstrip("?")
    return title if len(title) <= max_len else title[: max_len - 1].rstrip() + "…"


def _fmt_volume(v: Optional[float]) -> str:
    if not v:
        return ""
    if v >= 1_000_000:
        return f"${v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:.0f}"


def _prediction_rows(markets: List[dict], prev_lookup: Dict[str, float]) -> List[RowData]:
    """Render one row per market with headline outcome + delta vs yesterday."""
    rows: List[RowData] = []
    for m in markets:
        outcomes = m.get("outcomes") or []
        if not outcomes:
            continue
        top = outcomes[0]
        value = f"{top['label']} @ {top['implied_pct']:.1f}%"

        today_pct = top["implied_pct"]
        prev_pct = prev_lookup.get(m["id"])
        # Fall back to platform's own previous price (Kalshi exposes prev_price; Polymarket does not)
        if prev_pct is None and top.get("prev_price") is not None:
            prev_pct = top["prev_price"] * 100
        change = ""
        if prev_pct is not None:
            delta = today_pct - prev_pct
            sign = "+" if delta >= 0 else ""
            change = f"({sign}{delta:.1f}pp vs prev)"

        runner_up = ""
        if len(outcomes) > 1:
            ru = outcomes[1]
            runner_up = f"next: {ru['label']} @ {ru['implied_pct']:.1f}% · "
        vol = _fmt_volume(m.get("volume_usd"))
        end = m.get("end_date") or ""
        sub_parts = []
        if runner_up:
            sub_parts.append(runner_up.rstrip(" ·"))
        if vol:
            sub_parts.append(f"vol {vol}/24h")
        if end:
            sub_parts.append(f"ends {end}")
        sub = " · ".join(sub_parts)

        rows.append({
            "label":  _short_title(m.get("title", "")),
            "value":  value,
            "change": change,
            "sub":    sub,
            "invert": False,  # bullish-BTC markets: higher implied prob = green
        })
    return rows


def _build_prediction_sections(data: SnapshotData) -> List[SectionData]:
    """Build 0-2 sections (Polymarket, Kalshi) for the prediction-markets block.

    Returns empty list if no prediction data is present in the snapshot dict at all.
    A platform with a fetch error still gets a section with a placeholder note.
    """
    pm = data.get("prediction_markets") or {}
    if not pm:
        return []

    prev_lookup = _load_previous_prediction_markets()
    sections: List[SectionData] = []

    for platform_key, title in (("polymarket", "🔮 Polymarket — BTC"),
                                 ("kalshi",     "🎲 Kalshi — BTC")):
        block = pm.get(platform_key) or {}
        markets = block.get("markets") or []
        rows = _prediction_rows(markets, prev_lookup)
        if not rows:
            err = block.get("error") or f"{platform_key.title()} data unavailable"
            rows = [{
                "label":  err,
                "value":  "",
                "change": "",
                "sub":    "",
                "invert": False,
            }]
        sections.append({"title": title, "rows": rows})

    return sections


def build_snapshot_sections(data: SnapshotData, market_closed: bool | None = None) -> List[SectionData]:
    if market_closed is None:
        market_closed = is_market_closed()
    market_open = not market_closed

    sections: List[SectionData] = []

    # Crypto
    btc_pct = data.get("btc_change_pct")
    eth_pct = data.get("eth_change_pct")
    sol_pct = data.get("sol_change_pct")
    xrp_pct = data.get("xrp_change_pct")
    ada_pct = data.get("ada_change_pct")
    fg_val, fg_label = data.get("fear_greed", (None, None))

    crypto_rows: List[RowData] = [
        {
            "label": "Bitcoin (BTC)",
            "value": fmt_price(data.get("btc_price")),
            "change": f"({'+' if (btc_pct or 0) >= 0 else ''}{btc_pct:.2f}% 24h)" if btc_pct is not None else "",
            "sub": "",
            "invert": False,
        },
        {
            "label": "Ethereum (ETH)",
            "value": fmt_price(data.get("eth_price")),
            "change": f"({'+' if (eth_pct or 0) >= 0 else ''}{eth_pct:.2f}% 24h)" if eth_pct is not None else "",
            "sub": "",
            "invert": False,
        },
        {
            "label": "Solana (SOL)",
            "value": fmt_price(data.get("sol_price")),
            "change": f"({'+' if (sol_pct or 0) >= 0 else ''}{sol_pct:.2f}% 24h)" if sol_pct is not None else "",
            "sub": "",
            "invert": False,
        },
        {
            "label": "Ripple (XRP)",
            "value": fmt_price(data.get("xrp_price")),
            "change": f"({'+' if (xrp_pct or 0) >= 0 else ''}{xrp_pct:.2f}% 24h)" if xrp_pct is not None else "",
            "sub": "",
            "invert": False,
        },
        {
            "label": "Cardano (ADA)",
            "value": fmt_price(data.get("ada_price")),
            "change": f"({'+' if (ada_pct or 0) >= 0 else ''}{ada_pct:.2f}% 24h)" if ada_pct is not None else "",
            "sub": "",
            "invert": False,
        },
        {
            "label": "Fear & Greed",
            "value": f"{fg_val} – {fg_label}" if fg_val is not None else "N/A",
            "change": "",
            "sub": "",
            "invert": False,
        },
    ]
    sections.append({"title": "🪙 Cryptocurrencies", "rows": crypto_rows})

    # Energy
    gas_price, diesel_price, gas_period = data.get("gas", (None, None, None))
    oil_p, oil_c, oil_pct = data.get("oil", (None, None, None))

    energy_rows: List[RowData] = [
        {
            "label": "US Avg Gas (regular)",
            "value": f"${gas_price:.3f}/gal" if gas_price else "N/A",
            "change": "",
            "sub": f"EIA week ending {gas_period}" if gas_period else "EIA (add EIA_API_KEY for live data)",
            "invert": False,
        },
        {
            "label": "US Avg Diesel",
            "value": f"${diesel_price:.3f}/gal" if diesel_price else "N/A",
            "change": "",
            "sub": f"EIA week ending {gas_period}" if gas_period else "",
            "invert": False,
        },
        {
            "label": "Crude Oil (WTI)",
            "value": fmt_price(oil_p, 2),
            "change": fmt_change(oil_c, oil_pct),
            "sub": "",
            "invert": False,
        },
    ]
    sections.append({"title": "⛽ Energy", "rows": energy_rows})

    # Metals
    gold_p, gold_c, gold_pct = data.get("gold", (None, None, None))
    silv_p, silv_c, silv_pct = data.get("silver", (None, None, None))
    metals_rows: List[RowData] = [
        {
            "label": "Gold (GC=F)",
            "value": fmt_price(gold_p, 2),
            "change": fmt_change(gold_c, gold_pct),
            "sub": "",
            "invert": False,
        },
        {
            "label": "Silver (SI=F)",
            "value": fmt_price(silv_p, 2),
            "change": fmt_change(silv_c, silv_pct),
            "sub": "",
            "invert": False,
        },
    ]
    sections.append({"title": "🥇 Metals", "rows": metals_rows})

    # Currencies
    jpyusd_p, jpyusd_c, jpyusd_pct = data.get("usdjpy", (None, None, None))
    eurusd_p, eurusd_c, eurusd_pct = data.get("eurusd", (None, None, None))
    fx_rows: List[RowData] = [
        {
            "label": "USD/JPY",
            "value": fmt_price(jpyusd_p, 2, prefix="¥"),
            "change": fmt_change(jpyusd_c, jpyusd_pct),
            "sub": "",
            "invert": False,
        },
        {
            "label": "EUR/USD",
            "value": fmt_price(eurusd_p, 4, prefix=""),
            "change": fmt_change(eurusd_c, eurusd_pct),
            "sub": "",
            "invert": False,
        },
    ]
    sections.append({"title": "💱 Currencies", "rows": fx_rows})

    # Bonds & Interest Rates
    t2_p, t2_c, t2_pct = data.get("t2y", (None, None, None))
    t10_p, t10_c, t10_pct = data.get("t10y", (None, None, None))
    mort_val, mort_mom, _ = data.get("ev_mortgage", (None, None, None))
    cc_val, cc_mom, _ = data.get("ev_credit_card", (None, None, None))

    bond_rows: List[RowData] = [
        {
            "label": "US 2-Year Treasury",
            "value": f"{t2_p:.3f}%" if t2_p else "N/A",
            "change": fmt_change(t2_c, t2_pct, 3),
            "sub": "",
            "invert": True,
        },
        {
            "label": "US 10-Year Treasury",
            "value": f"{t10_p:.3f}%" if t10_p else "N/A",
            "change": fmt_change(t10_c, t10_pct, 3),
            "sub": "",
            "invert": True,
        },
    ]
    if mort_val is not None:
        bond_rows.append(
            {
                "label": "30-Year Mortgage Rate",
                "value": f"{mort_val:.2f}%",
                "change": fmt_pct_change(mort_mom, suffix="pp MoM"),
                "sub": "Freddie Mac weekly average",
                "invert": True,
            }
        )
    if cc_val is not None:
        bond_rows.append(
            {
                "label": "Credit Card APR",
                "value": f"{cc_val:.2f}%",
                "change": fmt_pct_change(cc_mom, suffix="pp MoM"),
                "sub": "Fed avg interest rate on revolving balances",
                "invert": True,
            }
        )
    sections.append({"title": "🏦 Bonds & Interest Rates", "rows": bond_rows})

    # Market-specific sections
    dj_p, dj_c, dj_pct = data.get("dow", (None, None, None))
    sp_p, sp_c, sp_pct = data.get("sp500", (None, None, None))
    nq_p, nq_c, nq_pct = data.get("nasdaq", (None, None, None))
    rty_p, rty_c, rty_pct = data.get("russell", (None, None, None))
    dji_p, dji_c, dji_pct = data.get("dji", (None, None, None))
    gspc_p, gspc_c, gspc_pct = data.get("gspc", (None, None, None))
    ndx_p, ndx_c, ndx_pct = data.get("ndx", (None, None, None))
    rut_p, rut_c, rut_pct = data.get("rut", (None, None, None))
    vix_p, vix_c, vix_pct = data.get("vix", (None, None, None))

    # Magnificent 7
    mag7_stocks = [
        ("Apple (AAPL)",    "aapl"),
        ("Microsoft (MSFT)", "msft"),
        ("Amazon (AMZN)",   "amzn"),
        ("Alphabet (GOOGL)", "googl"),
        ("Meta (META)",     "meta"),
        ("Tesla (TSLA)",    "tsla"),
        ("Nvidia (NVDA)",   "nvda"),
    ]
    mag7_rows: List[RowData] = []
    for label, key in mag7_stocks:
        p, c, pct = data.get(key, (None, None, None))
        mag7_rows.append({
            "label": label,
            "value": fmt_price(p, 2),
            "change": fmt_change(c, pct),
            "sub": "",
            "invert": False,
        })

    # Sector ETFs
    sector_etfs = [
        ("Semiconductors",          "smh"),
        ("Communication Services",  "xlc"),
        ("Homebuilders",            "xhb"),
        ("Consumer Staples",        "xlp"),
        ("Biotech",                 "xbi"),
        ("Regional Banks",          "kre"),
        ("Industrials",             "xli"),
        ("Materials",               "xlb"),
        ("Real Estate",             "xlre"),
        ("Utilities",               "xlu"),
        ("Energy",                  "xle"),
    ]
    sector_rows_raw = []
    for label, key in sector_etfs:
        p, c, pct = data.get(key, (None, None, None))
        sector_rows_raw.append((label, key.upper(), p, c, pct))
    sector_rows_raw.sort(key=lambda x: x[4] if x[4] is not None else float("-inf"), reverse=True)
    sector_rows: List[RowData] = [
        {
            "label": f"{label} ({ticker})",
            "value": fmt_price(p, 2),
            "change": fmt_change(c, pct),
            "sub": "",
            "invert": False,
        }
        for label, ticker, p, c, pct in sector_rows_raw
    ]

    if market_closed:
        futures_rows: List[RowData] = [
            {
                "label": "Dow Jones (YM=F)",
                "value": fmt_price(dj_p, 2),
                "change": fmt_change(dj_c, dj_pct),
                "sub": "",
                "invert": False,
            },
            {
                "label": "S&P 500 (ES=F)",
                "value": fmt_price(sp_p, 2),
                "change": fmt_change(sp_c, sp_pct),
                "sub": "",
                "invert": False,
            },
            {
                "label": "Nasdaq 100 (NQ=F)",
                "value": fmt_price(nq_p, 2),
                "change": fmt_change(nq_c, nq_pct),
                "sub": "",
                "invert": False,
            },
            {
                "label": "Russell 2000 (RTY=F)",
                "value": fmt_price(rty_p, 2),
                "change": fmt_change(rty_c, rty_pct),
                "sub": "",
                "invert": False,
            },
        ]
        sections.insert(0, {"title": "📈 US Market Futures", "rows": futures_rows})
        sections.insert(1, {"title": "💎 Magnificent 7", "rows": mag7_rows})
        sections.insert(2, {"title": "📊 Sector Performance", "rows": sector_rows})
    else:
        index_rows: List[RowData] = [
            {
                "label": "Dow Jones (^DJI)",
                "value": fmt_price(dji_p, 2),
                "change": fmt_change(dji_c, dji_pct),
                "sub": "",
                "invert": False,
            },
            {
                "label": "S&P 500 (^GSPC)",
                "value": fmt_price(gspc_p, 2),
                "change": fmt_change(gspc_c, gspc_pct),
                "sub": "",
                "invert": False,
            },
            {
                "label": "Nasdaq 100 (^NDX)",
                "value": fmt_price(ndx_p, 2),
                "change": fmt_change(ndx_c, ndx_pct),
                "sub": "",
                "invert": False,
            },
            {
                "label": "Russell 2000 (^RUT)",
                "value": fmt_price(rut_p, 2),
                "change": fmt_change(rut_c, rut_pct),
                "sub": "",
                "invert": False,
            },
        ]
        sections.insert(0, {"title": "📈 US Markets", "rows": index_rows})
        sections.insert(1, {"title": "⚡ Volatility", "rows": [
            {
                "label": "VIX",
                "value": fmt_price(vix_p, 2, prefix=""),
                "change": fmt_change(vix_c, vix_pct),
                "sub": "",
                "invert": True,
            }
        ]})
        sections.insert(2, {"title": "💎 Magnificent 7", "rows": mag7_rows})
        sections.insert(3, {"title": "📊 Sector Performance", "rows": sector_rows})

    # Prediction Markets — slot between live market data and everyday-economy section
    sections.extend(_build_prediction_sections(data))

    # Consumer Prices
    eggs_val, eggs_mom, eggs_date = data.get("ev_eggs", (None, None, None))
    milk_val, milk_mom, milk_date = data.get("ev_milk", (None, None, None))
    cpi_food_pct, cpi_food_date = data.get("ev_cpi_food", (None, None))
    cpi_shelter_pct, cpi_shelter_date = data.get("ev_cpi_shelter", (None, None))

    consumer_rows: List[RowData] = []
    if eggs_val is not None:
        consumer_rows.append(
            {
                "label": "Eggs, Grade A Large",
                "value": f"${eggs_val:.2f}/doz",
                "change": fmt_pct_change(eggs_mom, suffix="% MoM"),
                "sub": f"BLS monthly · latest: {eggs_date}",
                "invert": True,
            }
        )
    if milk_val is not None:
        consumer_rows.append(
            {
                "label": "Milk, whole",
                "value": f"${milk_val:.2f}/gal",
                "change": fmt_pct_change(milk_mom, suffix="% MoM"),
                "sub": f"BLS monthly · latest: {milk_date}",
                "invert": True,
            }
        )
    if cpi_food_pct is not None:
        consumer_rows.append(
            {
                "label": "CPI – Food at Home",
                "value": fmt_pct_change(cpi_food_pct, suffix="% YoY"),
                "change": "",
                "sub": f"Grocery inflation · {cpi_food_date}",
                "invert": True,
            }
        )
    if cpi_shelter_pct is not None:
        consumer_rows.append(
            {
                "label": "CPI – Shelter",
                "value": fmt_pct_change(cpi_shelter_pct, suffix="% YoY"),
                "change": "",
                "sub": f"Rent & housing costs · {cpi_shelter_date}",
                "invert": True,
            }
        )
    if consumer_rows:
        sections.append({"title": "🛒 Consumer Prices", "rows": consumer_rows})

    # Macro Economy
    cpi_all_pct, cpi_all_date = data.get("ev_cpi_all", (None, None))
    unemp_val, unemp_mom, _ = data.get("ev_unemployment", (None, None, None))
    debt_val, debt_prev, debt_change, debt_date = data.get("national_debt", (None, None, None, None))
    gdp_level, gdp_date, gdp_growth, gdp_growth_prev, gdp_growth_date = data.get("ev_gdp", (None, None, None, None, None))

    macro_rows: List[RowData] = []
    if gdp_growth is not None:
        gdp_level_str = f" · level: ${gdp_level/1000:.2f}T" if gdp_level is not None else ""
        macro_rows.append(
            {
                "label": "Real GDP Growth",
                "value": fmt_pct_change(gdp_growth, suffix="% QoQ ann."),
                "change": "",
                "sub": f"BEA quarterly · {gdp_growth_date}{gdp_level_str}",
                "invert": False,
            }
        )
    if cpi_all_pct is not None:
        macro_rows.append(
            {
                "label": "CPI – All Items",
                "value": fmt_pct_change(cpi_all_pct, suffix="% YoY"),
                "change": "",
                "sub": f"Headline inflation · {cpi_all_date}",
                "invert": True,
            }
        )
    if unemp_val is not None:
        macro_rows.append(
            {
                "label": "Unemployment Rate",
                "value": f"{unemp_val:.1f}%",
                "change": fmt_pct_change(unemp_mom, suffix="pp MoM"),
                "sub": "",
                "invert": True,
            }
        )
    if debt_val is not None:
        debt_trillions = debt_val / 1e12
        change_billions = debt_change / 1e9 if debt_change is not None else None
        chg_str = f"({'+' if (change_billions or 0) >= 0 else ''}{change_billions:,.1f}B DoD)" if change_billions is not None else ""
        macro_rows.append(
            {
                "label": "US National Debt",
                "value": f"${debt_trillions:,.2f}T",
                "change": chg_str,
                "sub": f"US Treasury · as of {debt_date}",
                "invert": True,
            }
        )
    if macro_rows:
        sections.append({"title": "📉 Macro Economy", "rows": macro_rows})

    return sections
