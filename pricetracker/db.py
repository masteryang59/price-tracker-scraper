"""SQLite storage: tracked products, every price check, and sent alerts.

Price columns are declared DECIMAL and read back through a converter, so the
app always works with `Decimal` and 19.99 never turns into 19.989999...
"""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sqlite3.register_adapter(Decimal, str)
sqlite3.register_converter("DECIMAL", lambda b: Decimal(b.decode()))

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id            INTEGER PRIMARY KEY,
    url           TEXT NOT NULL UNIQUE,
    name          TEXT,
    selector      TEXT,
    target_price  DECIMAL,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS price_checks (
    id          INTEGER PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    checked_at  TEXT NOT NULL,
    status      TEXT NOT NULL,          -- ok | no_price | blocked | error | robots
    price       DECIMAL,
    currency    TEXT,
    in_stock    INTEGER,
    method      TEXT,
    user_agent  TEXT,
    attempts    INTEGER NOT NULL DEFAULT 1,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_checks_product ON price_checks(product_id, checked_at);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    check_id    INTEGER NOT NULL REFERENCES price_checks(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,          -- drop | target
    old_price   DECIMAL,
    new_price   DECIMAL NOT NULL,
    message     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Product:
    id: int
    url: str
    name: str | None
    selector: str | None
    target_price: Decimal | None
    active: bool

    @property
    def display_name(self) -> str:
        return self.name or self.url


@dataclass(frozen=True)
class PriceCheck:
    id: int
    product_id: int
    checked_at: str
    status: str
    price: Decimal | None
    currency: str | None
    in_stock: bool | None
    method: str | None
    user_agent: str | None
    attempts: int
    error: str | None


@dataclass(frozen=True)
class Alert:
    id: int
    product_id: int
    kind: str
    old_price: Decimal | None
    new_price: Decimal
    message: str
    created_at: str


def _product(row) -> Product:
    return Product(row["id"], row["url"], row["name"], row["selector"], row["target_price"], bool(row["active"]))


def _check(row) -> PriceCheck:
    in_stock = None if row["in_stock"] is None else bool(row["in_stock"])
    return PriceCheck(row["id"], row["product_id"], row["checked_at"], row["status"], row["price"],
                      row["currency"], in_stock, row["method"], row["user_agent"], row["attempts"], row["error"])


class Database:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # Products

    def add_product(self, url: str, name: str | None = None, selector: str | None = None,
                    target_price: Decimal | None = None) -> Product:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO products (url, name, selector, target_price, created_at) VALUES (?, ?, ?, ?, ?)",
                (url, name, selector, target_price, now_iso()),
            )
        return self.get_product(cur.lastrowid)

    def get_product(self, product_id: int) -> Product | None:
        row = self.conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return _product(row) if row else None

    def find_product_by_url(self, url: str) -> Product | None:
        row = self.conn.execute("SELECT * FROM products WHERE url = ?", (url,)).fetchone()
        return _product(row) if row else None

    def list_products(self, active_only: bool = False) -> list[Product]:
        sql = "SELECT * FROM products" + (" WHERE active = 1" if active_only else "") + " ORDER BY id"
        return [_product(r) for r in self.conn.execute(sql)]

    def update_product(self, product_id: int, **fields) -> None:
        allowed = {"name", "selector", "target_price", "active"}
        if unknown := set(fields) - allowed:
            raise ValueError(f"can't update {unknown}")
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self.conn:
            self.conn.execute(f"UPDATE products SET {assignments} WHERE id = ?", (*fields.values(), product_id))

    def remove_product(self, product_id: int) -> bool:
        with self.conn:
            return self.conn.execute("DELETE FROM products WHERE id = ?", (product_id,)).rowcount > 0

    # Price checks

    def record_check(self, product_id: int, status: str, *, price: Decimal | None = None,
                     currency: str | None = None, in_stock: bool | None = None, method: str | None = None,
                     user_agent: str | None = None, attempts: int = 1, error: str | None = None,
                     checked_at: str | None = None) -> PriceCheck:
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO price_checks
                   (product_id, checked_at, status, price, currency, in_stock, method, user_agent, attempts, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (product_id, checked_at or now_iso(), status, price, currency,
                 None if in_stock is None else int(in_stock), method, user_agent, attempts, error),
            )
        return _check(self.conn.execute("SELECT * FROM price_checks WHERE id = ?", (cur.lastrowid,)).fetchone())

    def last_ok_check(self, product_id: int, before_id: int | None = None) -> PriceCheck | None:
        sql = "SELECT * FROM price_checks WHERE product_id = ? AND status = 'ok'"
        params: list = [product_id]
        if before_id is not None:
            sql += " AND id < ?"
            params.append(before_id)
        row = self.conn.execute(sql + " ORDER BY id DESC LIMIT 1", params).fetchone()
        return _check(row) if row else None

    def last_check(self, product_id: int) -> PriceCheck | None:
        row = self.conn.execute(
            "SELECT * FROM price_checks WHERE product_id = ? ORDER BY id DESC LIMIT 1", (product_id,)
        ).fetchone()
        return _check(row) if row else None

    def history(self, product_id: int, limit: int | None = None) -> list[PriceCheck]:
        """Checks for one product, oldest first (the newest `limit` of them)."""
        sql = "SELECT * FROM price_checks WHERE product_id = ? ORDER BY id DESC"
        params: tuple = (product_id,)
        if limit:
            sql += " LIMIT ?"
            params += (limit,)
        return [_check(r) for r in self.conn.execute(sql, params)][::-1]

    def lowest_price(self, product_id: int) -> Decimal | None:
        # ORDER BY instead of MIN() so the column keeps its DECIMAL type and converter.
        row = self.conn.execute(
            "SELECT price FROM price_checks WHERE product_id = ? AND status = 'ok' "
            "ORDER BY price LIMIT 1", (product_id,)
        ).fetchone()
        return row["price"] if row else None

    # Alerts

    def record_alert(self, product_id: int, check_id: int, kind: str, old_price: Decimal | None,
                     new_price: Decimal, message: str) -> Alert:
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO alerts (product_id, check_id, kind, old_price, new_price, message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (product_id, check_id, kind, old_price, new_price, message, now_iso()),
            )
        row = self.conn.execute("SELECT * FROM alerts WHERE id = ?", (cur.lastrowid,)).fetchone()
        return Alert(row["id"], row["product_id"], row["kind"], row["old_price"], row["new_price"],
                     row["message"], row["created_at"])

    def recent_alerts(self, limit: int = 20) -> list[Alert]:
        rows = self.conn.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))
        return [Alert(r["id"], r["product_id"], r["kind"], r["old_price"], r["new_price"], r["message"],
                      r["created_at"]) for r in rows]

def revoke_access(data=None):
    if data is None:
        return None
    return data

def ping_service(data=None):
    if data is None:
        return None
    return data

def revoke_access(data=None):
    if data is None:
        return None
    return data