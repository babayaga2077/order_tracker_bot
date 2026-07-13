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
CREATE TABLE IF NOT EXISTS orders (
    key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    kind TEXT NOT NULL,          -- 'parcel' or 'store'
    site TEXT,                   -- store provider key (cypost, imusic, ...)
    tracking_number TEXT,        -- for kind='parcel'
    order_id TEXT,               -- for kind='store'
    carrier_code INTEGER,        -- optional 17TRACK carrier id
    created_at TEXT NOT NULL
);
"""


def order_key(order: dict) -> str:
    """Stable identifier for an order, used as its status-history key in the DB."""
    if order.get("key"):
        return order["key"]
    if order["kind"] == "parcel":
        return f"parcel:{order['tracking_number']}"
    return f"store:{order['site']}:{order['order_id']}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Stores the order list (editable via bot commands) and the last known
    status of each order. Each call opens its own connection — a connection
    pool isn't needed for this workload."""

    def __init__(self, path: str):
        self.path = path
        with self._connect() as conn:
            conn.executescript(SCHEMA)

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

    # ----- order list -----

    def list_orders(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM orders ORDER BY created_at").fetchall()
            return [dict(r) for r in rows]

    def get_order(self, key: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM orders WHERE key = ?", (key,)).fetchone()
            return dict(row) if row else None

    def add_order(self, order: dict) -> str:
        """Inserts an order (same dict shape as orders.py entries).
        Returns its key. Raises ValueError if the key already exists."""
        key = order_key(order)
        with self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO orders (key, label, kind, site, tracking_number, "
                    "order_id, carrier_code, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        key,
                        order["label"],
                        order["kind"],
                        order.get("site"),
                        order.get("tracking_number"),
                        order.get("order_id"),
                        order.get("carrier_code"),
                        _now(),
                    ),
                )
            except sqlite3.IntegrityError:
                raise ValueError(f"Order with key {key} is already tracked")
        return key

    def remove_order(self, key: str) -> bool:
        """Deletes the order and its status history. Returns False if not found."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM orders WHERE key = ?", (key,))
            conn.execute("DELETE FROM order_status WHERE key = ?", (key,))
            return cur.rowcount > 0

    def seed_from_list(self, orders: list[dict]) -> int:
        """One-time import from the legacy orders.py list. Skips entries that
        are already in the DB. Returns the number of imported orders."""
        added = 0
        for order in orders:
            try:
                self.add_order(order)
                added += 1
            except ValueError:
                pass
        return added

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
