"""
One-time migration script: imports users from users.csv into db.sqlite3.
Run once: python migrate_users.py
"""

import csv
from models import User, init_db

init_db()

imported = 0
skipped  = 0

with open("users.csv", newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        email = row.get("Email", "").strip().strip('"')
        if not email:
            continue
        _, created = User.get_or_create(
            email=email,
            defaults={
                "first_name":  row.get("FirstName", "").strip().strip('"'),
                "last_name":   row.get("LastName",  "").strip().strip('"'),
                "format_pref": row.get("FormatPref", "HTML").strip().strip('"'),
                "active":      True,
            },
        )
        if created:
            print(f"  imported: {email}")
            imported += 1
        else:
            print(f"  skipped (already exists): {email}")
            skipped += 1

print(f"\nDone — {imported} imported, {skipped} skipped.")
