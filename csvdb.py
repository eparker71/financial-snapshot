"""
csvdb.py — Use CSV files like a simple database.

Usage:
    db = CsvDB("users.csv")
    db.insert({"name": "Alice", "age": "30", "city": "NYC"})
    db.find(name="Alice")
    db.update({"name": "Alice"}, city="Boston")
    db.delete(name="Alice")
"""

import csv
import os
import uuid
import shutil
import tempfile
from typing import Any


class CsvDB:
    """A lightweight CSV-backed database table."""

    ID_FIELD = "_id"

    def __init__(self, filepath: str, auto_id: bool = True):
        """
        Args:
            filepath:  Path to the CSV file (created if it doesn't exist).
            auto_id:   Automatically add a unique '_id' column to each row.
        """
        self.filepath = filepath
        self.auto_id = auto_id
        self._fieldnames: list[str] | None = None

        if os.path.exists(filepath):
            self._load_fieldnames()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        """Insert a row. Returns the inserted row (with _id if auto_id)."""
        row = dict(row)  # don't mutate caller's dict
        if self.auto_id and self.ID_FIELD not in row:
            row[self.ID_FIELD] = str(uuid.uuid4())

        if self._fieldnames is None:
            # First insert — define the schema from this row
            self._fieldnames = list(row.keys())
            self._write_all([row])
        else:
            # Ensure all known columns are present
            for field in self._fieldnames:
                row.setdefault(field, "")
            # Append new columns if this row has extras
            new_fields = [k for k in row if k not in self._fieldnames]
            if new_fields:
                self._fieldnames.extend(new_fields)
                self._write_all(self._read_all() + [row])
            else:
                self._append(row)

        return row

    def find(self, **filters) -> list[dict[str, Any]]:
        """
        Return all rows matching ALL provided filters.

        db.find(city="NYC", age="30")   # exact match
        db.find()                        # return everything
        """
        return [r for r in self._read_all() if self._matches(r, filters)]

    def find_one(self, **filters) -> dict[str, Any] | None:
        """Return the first matching row, or None."""
        for row in self._read_all():
            if self._matches(row, filters):
                return row
        return None

    def update(self, match: dict[str, Any], **new_values) -> int:
        """
        Update all rows that match `match` dict with `new_values`.
        Returns number of rows updated.

        db.update({"name": "Alice"}, city="Boston", age="31")
        """
        updated = 0
        rows = self._read_all()
        for row in rows:
            if self._matches(row, match):
                row.update(new_values)
                updated += 1
        if updated:
            self._write_all(rows)
        return updated

    def update_by_id(self, row_id: str, **new_values) -> bool:
        """Update a single row by its _id. Returns True if found."""
        return self.update({self.ID_FIELD: row_id}, **new_values) > 0

    def delete(self, **filters) -> int:
        """
        Delete all rows matching filters.
        Returns number of rows deleted.

        db.delete(name="Alice")
        """
        rows = self._read_all()
        kept = [r for r in rows if not self._matches(r, filters)]
        deleted = len(rows) - len(kept)
        if deleted:
            self._write_all(kept)
        return deleted

    def delete_by_id(self, row_id: str) -> bool:
        """Delete a single row by its _id. Returns True if found."""
        return self.delete(**{self.ID_FIELD: row_id}) > 0

    def all(self) -> list[dict[str, Any]]:
        """Return every row."""
        return self._read_all()

    def count(self, **filters) -> int:
        """Count rows matching filters (or all rows if no filters)."""
        return len(self.find(**filters)) if filters else len(self._read_all())

    def column(self, field: str) -> list[Any]:
        """Return all values from a single column.

        db.column("email")  # ['alice@example.com', 'bob@example.com', ...]
        """
        print(field)
        return [row[field] for row in self._read_all() if field in row]

    def clear(self) -> None:
        """Delete all rows but keep the file and its headers."""
        self._write_all([])

    @property
    def columns(self) -> list[str]:
        """Return the column names."""
        return list(self._fieldnames or [])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _matches(self, row: dict, filters: dict) -> bool:
        return all(str(row.get(k, "")) == str(v) for k, v in filters.items())

    def _load_fieldnames(self) -> None:
        with open(self.filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            self._fieldnames = reader.fieldnames or []

    def _read_all(self) -> list[dict[str, Any]]:
        if not os.path.exists(self.filepath):
            return []
        with open(self.filepath, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _write_all(self, rows: list[dict[str, Any]]) -> None:
        if not self._fieldnames:
            return
        # Write to a temp file first, then replace (atomic-ish)
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(self.filepath) or ".")
        try:
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self._fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            shutil.move(tmp_path, self.filepath)
        except Exception:
            os.unlink(tmp_path)
            raise

    def _append(self, row: dict[str, Any]) -> None:
        with open(self.filepath, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._fieldnames, extrasaction="ignore")
            if f.tell() == 0:
                writer.writeheader()
            writer.writerow(row)
