from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import aiosqlite

_connection: aiosqlite.Connection | None = None

_PRODUCT_FIELDS = {
    "name",
    "description",
    "price",
    "live_price",
    "stock_m",
    "photo_file_id",
    "photo_kind",
    "is_active",
}

_DEFAULTS = {
    "live_enabled": "0",
    "live_url": "",
    "live_chat_id": "",
    "live_chat_title": "",
    "bot_username": "",
    "manager_name": "Григорий",
    "manager_username": "Grigori_G_979",
    "manager_phone": "",
}


def _require() -> aiosqlite.Connection:
    if _connection is None:
        raise RuntimeError("База не подключена")
    return _connection


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


async def connect(path: str) -> None:
    global _connection
    if _connection is not None:
        await _connection.close()
        _connection = None
    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        os.makedirs(folder, exist_ok=True)
    _connection = await aiosqlite.connect(path)
    _connection.row_factory = aiosqlite.Row
    await _connection.execute("PRAGMA journal_mode=WAL")
    await _connection.execute("PRAGMA foreign_keys=ON")
    await _connection.execute("PRAGMA busy_timeout=5000")
    await _init()


async def close() -> None:
    global _connection
    if _connection is not None:
        await _connection.close()
        _connection = None


async def _init() -> None:
    db = _require()
    await db.executescript(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            price REAL NOT NULL,
            live_price REAL NOT NULL,
            stock_m REAL NOT NULL DEFAULT 0,
            photo_file_id TEXT,
            photo_kind TEXT NOT NULL DEFAULT 'photo',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            client_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            company TEXT NOT NULL,
            product_id INTEGER,
            product_name TEXT NOT NULL,
            meters REAL NOT NULL,
            unit_price REAL NOT NULL,
            is_live INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            username TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            updated_at TEXT NOT NULL
        );
        """
    )
    for key, value in _DEFAULTS.items():
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
    await db.commit()


async def get_setting(key: str, default: str = "") -> str:
    cursor = await _require().execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = await cursor.fetchone()
    if row is None:
        return default
    return str(row["value"])


async def set_setting(key: str, value: str) -> None:
    await _require().execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    await _require().commit()


async def live_enabled() -> bool:
    return (await get_setting("live_enabled", "0")) == "1"


async def add_product(
    *,
    name: str,
    description: str,
    price: float,
    live_price: float,
    stock_m: float,
    photo_file_id: str | None,
    photo_kind: str,
) -> int:
    cursor = await _require().execute(
        """
        INSERT INTO products (
            name, description, price, live_price, stock_m,
            photo_file_id, photo_kind, is_active, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            name,
            description,
            price,
            live_price,
            stock_m,
            photo_file_id,
            photo_kind,
            utc_now(),
        ),
    )
    await _require().commit()
    return int(cursor.lastrowid)


async def update_product(product_id: int, **fields: Any) -> None:
    unknown = set(fields) - _PRODUCT_FIELDS
    if unknown:
        raise ValueError(f"Unknown product fields: {sorted(unknown)}")
    if not fields:
        return
    assignments = ", ".join(f"{name} = ?" for name in fields)
    values = list(fields.values())
    values.append(product_id)
    await _require().execute(
        f"UPDATE products SET {assignments} WHERE id = ?",
        values,
    )
    await _require().commit()


async def get_product(product_id: int) -> dict[str, Any] | None:
    cursor = await _require().execute("SELECT * FROM products WHERE id = ?", (product_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def list_products(*, include_hidden: bool = False) -> list[dict[str, Any]]:
    if include_hidden:
        query = "SELECT * FROM products ORDER BY id"
        cursor = await _require().execute(query)
    else:
        cursor = await _require().execute(
            "SELECT * FROM products WHERE is_active = 1 ORDER BY id"
        )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def delete_product(product_id: int) -> None:
    await _require().execute("DELETE FROM products WHERE id = ?", (product_id,))
    await _require().commit()


async def create_order(
    *,
    user_id: int,
    username: str | None,
    client_name: str,
    phone: str,
    company: str,
    product_id: int | None,
    product_name: str,
    meters: float,
    unit_price: float,
    is_live: bool,
) -> int:
    cursor = await _require().execute(
        """
        INSERT INTO orders (
            user_id, username, client_name, phone, company,
            product_id, product_name, meters, unit_price, is_live, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            username,
            client_name,
            phone,
            company,
            product_id,
            product_name,
            meters,
            unit_price,
            1 if is_live else 0,
            utc_now(),
        ),
    )
    await _require().commit()
    return int(cursor.lastrowid)


async def get_order(order_id: int) -> dict[str, Any] | None:
    cursor = await _require().execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def list_orders(offset: int, limit: int) -> list[dict[str, Any]]:
    cursor = await _require().execute(
        "SELECT * FROM orders ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def count_orders() -> int:
    cursor = await _require().execute("SELECT COUNT(*) AS total FROM orders")
    row = await cursor.fetchone()
    return int(row["total"])


async def remember_admin(user_id: int, username: str | None) -> None:
    await _require().execute(
        """
        INSERT INTO admins (user_id, username) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
        """,
        (user_id, username or ""),
    )
    await _require().commit()


async def is_admin_id(user_id: int) -> bool:
    cursor = await _require().execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
    return await cursor.fetchone() is not None


async def list_admin_ids() -> list[int]:
    cursor = await _require().execute("SELECT user_id FROM admins ORDER BY user_id")
    rows = await cursor.fetchall()
    return [int(row["user_id"]) for row in rows]


async def remember_user(user_id: int, username: str | None) -> None:
    await _require().execute(
        """
        INSERT INTO users (user_id, username, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            updated_at = excluded.updated_at
        """,
        (user_id, username or "", utc_now()),
    )
    await _require().commit()


async def list_user_ids() -> list[int]:
    cursor = await _require().execute("SELECT user_id FROM users ORDER BY user_id")
    rows = await cursor.fetchall()
    return [int(row["user_id"]) for row in rows]


async def audience_ids() -> list[int]:
    return sorted(set(await list_user_ids()) | set(await list_admin_ids()))
