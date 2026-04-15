"""
Database models for Financial Snapshot.
Uses SQLite via Peewee ORM. Database file: db.sqlite3
"""

import os
from peewee import SqliteDatabase, Model, CharField, BooleanField

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


def init_db():
    """Create tables if they don't exist. Safe to call on every startup."""
    with db:
        db.create_tables([User], safe=True)
