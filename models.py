"""
Database models for Financial Snapshot.
Uses SQLite via Peewee ORM. Database file: db.sqlite3
"""

import os
from peewee import SqliteDatabase, Model, CharField, BooleanField, FloatField, DateTimeField, TextField

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
db = SqliteDatabase(os.path.join(ROOT_DIR, "db.sqlite3"))


class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    first_name  = CharField()
    last_name   = CharField()
    email       = CharField(unique=True)
    format_pref = CharField(default="HTML")  # "HTML" or "Plain"
    active      = BooleanField(default=True)

    class Meta:
        table_name = "users"


class Snapshot(BaseModel):
    """One row per application run — stores all fetched market data."""
    timestamp = DateTimeField()

    # Crypto
    btc_price        = FloatField(null=True)
    btc_change_pct   = FloatField(null=True)
    eth_price        = FloatField(null=True)
    eth_change_pct   = FloatField(null=True)
    sol_price        = FloatField(null=True)
    sol_change_pct   = FloatField(null=True)
    xrp_price        = FloatField(null=True)
    xrp_change_pct   = FloatField(null=True)
    ada_price        = FloatField(null=True)
    ada_change_pct   = FloatField(null=True)
    fear_greed_value = FloatField(null=True)
    fear_greed_label = CharField(null=True)

    # Energy
    gas_price    = FloatField(null=True)
    diesel_price = FloatField(null=True)
    gas_period   = CharField(null=True)
    oil_price    = FloatField(null=True)
    oil_change   = FloatField(null=True)
    oil_change_pct = FloatField(null=True)

    # Metals
    gold_price      = FloatField(null=True)
    gold_change     = FloatField(null=True)
    gold_change_pct = FloatField(null=True)
    silver_price      = FloatField(null=True)
    silver_change     = FloatField(null=True)
    silver_change_pct = FloatField(null=True)

    # Currencies
    usdjpy_price      = FloatField(null=True)
    usdjpy_change     = FloatField(null=True)
    usdjpy_change_pct = FloatField(null=True)
    eurusd_price      = FloatField(null=True)
    eurusd_change     = FloatField(null=True)
    eurusd_change_pct = FloatField(null=True)

    # Bonds & Interest Rates
    t2y_yield            = FloatField(null=True)
    t2y_change           = FloatField(null=True)
    t2y_change_pct       = FloatField(null=True)
    t10y_yield           = FloatField(null=True)
    t10y_change          = FloatField(null=True)
    t10y_change_pct      = FloatField(null=True)
    mortgage_rate        = FloatField(null=True)
    mortgage_mom_change  = FloatField(null=True)
    credit_card_apr      = FloatField(null=True)
    credit_card_mom_change = FloatField(null=True)

    # Futures (market closed)
    dow_futures_price      = FloatField(null=True)
    dow_futures_change     = FloatField(null=True)
    dow_futures_change_pct = FloatField(null=True)
    sp500_futures_price      = FloatField(null=True)
    sp500_futures_change     = FloatField(null=True)
    sp500_futures_change_pct = FloatField(null=True)
    nasdaq_futures_price      = FloatField(null=True)
    nasdaq_futures_change     = FloatField(null=True)
    nasdaq_futures_change_pct = FloatField(null=True)
    russell_futures_price      = FloatField(null=True)
    russell_futures_change     = FloatField(null=True)
    russell_futures_change_pct = FloatField(null=True)

    # Live indices (market open)
    dji_price      = FloatField(null=True)
    dji_change     = FloatField(null=True)
    dji_change_pct = FloatField(null=True)
    gspc_price      = FloatField(null=True)
    gspc_change     = FloatField(null=True)
    gspc_change_pct = FloatField(null=True)
    ndx_price      = FloatField(null=True)
    ndx_change     = FloatField(null=True)
    ndx_change_pct = FloatField(null=True)
    rut_price      = FloatField(null=True)
    rut_change     = FloatField(null=True)
    rut_change_pct = FloatField(null=True)

    # Volatility
    vix_price      = FloatField(null=True)
    vix_change     = FloatField(null=True)
    vix_change_pct = FloatField(null=True)

    # Magnificent 7
    aapl_price       = FloatField(null=True)
    aapl_change      = FloatField(null=True)
    aapl_change_pct  = FloatField(null=True)
    msft_price       = FloatField(null=True)
    msft_change      = FloatField(null=True)
    msft_change_pct  = FloatField(null=True)
    amzn_price       = FloatField(null=True)
    amzn_change      = FloatField(null=True)
    amzn_change_pct  = FloatField(null=True)
    googl_price      = FloatField(null=True)
    googl_change     = FloatField(null=True)
    googl_change_pct = FloatField(null=True)
    meta_price       = FloatField(null=True)
    meta_change      = FloatField(null=True)
    meta_change_pct  = FloatField(null=True)
    tsla_price       = FloatField(null=True)
    tsla_change      = FloatField(null=True)
    tsla_change_pct  = FloatField(null=True)
    nvda_price       = FloatField(null=True)
    nvda_change      = FloatField(null=True)
    nvda_change_pct  = FloatField(null=True)

    # Sector ETFs
    xlc_price       = FloatField(null=True)
    xlc_change      = FloatField(null=True)
    xlc_change_pct  = FloatField(null=True)
    xlp_price       = FloatField(null=True)
    xlp_change      = FloatField(null=True)
    xlp_change_pct  = FloatField(null=True)
    xli_price       = FloatField(null=True)
    xli_change      = FloatField(null=True)
    xli_change_pct  = FloatField(null=True)
    xlb_price       = FloatField(null=True)
    xlb_change      = FloatField(null=True)
    xlb_change_pct  = FloatField(null=True)
    xlre_price      = FloatField(null=True)
    xlre_change     = FloatField(null=True)
    xlre_change_pct = FloatField(null=True)
    xlu_price       = FloatField(null=True)
    xlu_change      = FloatField(null=True)
    xlu_change_pct  = FloatField(null=True)
    xle_price       = FloatField(null=True)
    xle_change      = FloatField(null=True)
    xle_change_pct  = FloatField(null=True)

    # Industry ETFs (replace broader sector ETFs for Technology, Health Care, Financials, Consumer Discretionary)
    smh_price       = FloatField(null=True)
    smh_change      = FloatField(null=True)
    smh_change_pct  = FloatField(null=True)
    xbi_price       = FloatField(null=True)
    xbi_change      = FloatField(null=True)
    xbi_change_pct  = FloatField(null=True)
    kre_price       = FloatField(null=True)
    kre_change      = FloatField(null=True)
    kre_change_pct  = FloatField(null=True)
    xhb_price       = FloatField(null=True)
    xhb_change      = FloatField(null=True)
    xhb_change_pct  = FloatField(null=True)

    # Consumer Prices
    eggs_price      = FloatField(null=True)
    eggs_mom_change = FloatField(null=True)
    eggs_date       = CharField(null=True)
    milk_price      = FloatField(null=True)
    milk_mom_change = FloatField(null=True)
    milk_date       = CharField(null=True)
    cpi_food_yoy    = FloatField(null=True)
    cpi_food_date   = CharField(null=True)
    cpi_shelter_yoy  = FloatField(null=True)
    cpi_shelter_date = CharField(null=True)

    # Macro Economy
    cpi_all_yoy            = FloatField(null=True)
    cpi_all_date           = CharField(null=True)
    unemployment_rate      = FloatField(null=True)
    unemployment_mom_change = FloatField(null=True)
    national_debt          = FloatField(null=True)
    national_debt_prev     = FloatField(null=True)
    national_debt_change   = FloatField(null=True)
    national_debt_date     = CharField(null=True)
    gdp_level        = FloatField(null=True)
    gdp_date         = CharField(null=True)
    gdp_growth_qoq   = FloatField(null=True)
    gdp_growth_prev  = FloatField(null=True)
    gdp_growth_date  = CharField(null=True)

    # AI Analysis
    ai_analysis    = TextField(null=True)
    watch_item     = TextField(null=True)
    anomaly_alert  = TextField(null=True)

    # Prediction markets — JSON-encoded list of normalized Polymarket + Kalshi markets
    prediction_markets_json = TextField(null=True)

    class Meta:
        table_name = "snapshots"


def _migrate_add_columns():
    """Add new columns to the snapshots table if they don't exist yet."""
    cursor = db.execute_sql("PRAGMA table_info(snapshots)")
    existing = {row[1] for row in cursor.fetchall()}
    new_cols = [
        ("aapl_price", "REAL"), ("aapl_change", "REAL"), ("aapl_change_pct", "REAL"),
        ("msft_price", "REAL"), ("msft_change", "REAL"), ("msft_change_pct", "REAL"),
        ("amzn_price", "REAL"), ("amzn_change", "REAL"), ("amzn_change_pct", "REAL"),
        ("googl_price", "REAL"), ("googl_change", "REAL"), ("googl_change_pct", "REAL"),
        ("meta_price", "REAL"), ("meta_change", "REAL"), ("meta_change_pct", "REAL"),
        ("tsla_price", "REAL"), ("tsla_change", "REAL"), ("tsla_change_pct", "REAL"),
        ("nvda_price", "REAL"), ("nvda_change", "REAL"), ("nvda_change_pct", "REAL"),
        ("ai_analysis",   "TEXT"),
        ("watch_item",    "TEXT"),
        ("anomaly_alert", "TEXT"),
        ("xlk_price", "REAL"), ("xlk_change", "REAL"), ("xlk_change_pct", "REAL"),
        ("xlc_price", "REAL"), ("xlc_change", "REAL"), ("xlc_change_pct", "REAL"),
        ("xly_price", "REAL"), ("xly_change", "REAL"), ("xly_change_pct", "REAL"),
        ("xlp_price", "REAL"), ("xlp_change", "REAL"), ("xlp_change_pct", "REAL"),
        ("xlv_price", "REAL"), ("xlv_change", "REAL"), ("xlv_change_pct", "REAL"),
        ("xlf_price", "REAL"), ("xlf_change", "REAL"), ("xlf_change_pct", "REAL"),
        ("xli_price", "REAL"), ("xli_change", "REAL"), ("xli_change_pct", "REAL"),
        ("xlb_price", "REAL"), ("xlb_change", "REAL"), ("xlb_change_pct", "REAL"),
        ("xlre_price", "REAL"), ("xlre_change", "REAL"), ("xlre_change_pct", "REAL"),
        ("xlu_price", "REAL"), ("xlu_change", "REAL"), ("xlu_change_pct", "REAL"),
        ("xle_price", "REAL"), ("xle_change", "REAL"), ("xle_change_pct", "REAL"),
        ("prediction_markets_json", "TEXT"),
        ("smh_price", "REAL"), ("smh_change", "REAL"), ("smh_change_pct", "REAL"),
        ("xbi_price", "REAL"), ("xbi_change", "REAL"), ("xbi_change_pct", "REAL"),
        ("kre_price", "REAL"), ("kre_change", "REAL"), ("kre_change_pct", "REAL"),
        ("xhb_price", "REAL"), ("xhb_change", "REAL"), ("xhb_change_pct", "REAL"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing:
            db.execute_sql(f"ALTER TABLE snapshots ADD COLUMN {col_name} {col_type}")


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    with db:
        db.create_tables([User, Snapshot], safe=True)
        _migrate_add_columns()
