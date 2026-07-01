import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS order_status (
    key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    last_status TEXT,
    last_detail TEXT,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Stores only the last known status of each order, across script runs
    (the script is one-shot — the order list itself lives in orders.py in
    the repo, not in the DB). Each call opens its own connection — a
    connection pool isn't needed for this workload."""

    def __init__(self, path: str):
        self.path = path
        with self._connect() as conn:
            conn.execute(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def get_status(self, key: str) -> Optional[dict]:
        """Returns {"label", "last_status", "last_detail", "updated_at"}
        or None if this order is being checked for the first time."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM order_status WHERE key = ?", (key,)
            ).fetchone()
            return dict(row) if row else None

    def set_status(self, key: str, label: str, status: str, detail: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO order_status (key, label, last_status, last_detail, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET "
                "label = excluded.label, last_status = excluded.last_status, "
                "last_detail = excluded.last_detail, updated_at = excluded.updated_at",
                (key, label, status, detail, _now()),
            )

    def prune_missing(self, active_keys: list[str]) -> int:
        """Deletes DB rows for orders no longer present in orders.py
        (removed from the list by hand). Returns the number of deleted rows."""
        with self._connect() as conn:
            if not active_keys:
                cur = conn.execute("DELETE FROM order_status")
            else:
                placeholders = ",".join("?" for _ in active_keys)
                cur = conn.execute(
                    f"DELETE FROM order_status WHERE key NOT IN ({placeholders})",
                    active_keys,
                )
            return cur.rowcount
