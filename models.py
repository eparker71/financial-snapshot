"""
Database models for Financial Snapshot.
Uses SQLite via Peewee ORM. Database file: db.sqlite3
"""

import os
from peewee import SqliteDatabase, Model, CharField, BooleanField, FloatField, DateTimeField

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

    class Meta:
        table_name = "snapshots"


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    with db:
        db.create_tables([User, Snapshot], safe=True)
