"""
Lapisan database menggunakan aiosqlite (async SQLite).
Menyimpan produk, pesanan, dan pengguna.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import aiosqlite
from datetime import datetime
from typing import Any

import config


def normalize_payment_method(method: str | None) -> str:
    """Normalisasi nama metode pembayaran ke format yang konsisten."""
    if not method:
        return ""
    raw = method.strip()
    if not raw:
        return ""
    mapping = {
        "dana": "DANA",
        "gopay": "GoPay",
        "seabank": "SeaBank",
        "qris": "QRIS",
    }
    return mapping.get(raw.lower(), raw)


@asynccontextmanager
async def get_db() -> aiosqlite.Connection:
    """Buka koneksi database (row_factory diset ke dict-like)."""
    os.makedirs(os.path.dirname(config.DATABASE_PATH), exist_ok=True)
    db = aiosqlite.connect(config.DATABASE_PATH)
    async with db as conn:
        conn.row_factory = aiosqlite.Row
        yield conn


async def init_db() -> None:
    """Buat semua tabel jika belum ada."""
    async with get_db() as db:
        await db.executescript(
            """
            -- Produk / paket Robux yang dijual
            CREATE TABLE IF NOT EXISTS products (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                description TEXT    NOT NULL DEFAULT '',
                robux_amount INTEGER NOT NULL,
                price_idr   REAL    NOT NULL,
                stock       INTEGER NOT NULL DEFAULT -1,  -- -1 = unlimited
                is_active   INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            -- Pesanan dari pembeli
            CREATE TABLE IF NOT EXISTS orders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT    NOT NULL,
                username    TEXT    NOT NULL,
                product_id  INTEGER NOT NULL REFERENCES products(id),
                quantity    INTEGER NOT NULL DEFAULT 1,
                total_idr   REAL    NOT NULL,
                robux_total INTEGER NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'pending',
                roblox_username TEXT,
                notes       TEXT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            -- Log aktivitas admin
            CREATE TABLE IF NOT EXISTS activity_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id    TEXT    NOT NULL,
                action      TEXT    NOT NULL,
                target      TEXT,
                details     TEXT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            -- Ticket pembelian Robux
            CREATE TABLE IF NOT EXISTS tickets (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                order_code       TEXT    NOT NULL DEFAULT '',   -- RS-0001
                user_id          TEXT    NOT NULL,
                username         TEXT    NOT NULL,
                roblox_username  TEXT    NOT NULL,
                robux_amount     INTEGER NOT NULL,
                ticket_type      TEXT    NOT NULL,              -- 'send' / 'community'
                status           TEXT    NOT NULL DEFAULT 'open', -- open / claimed / closed
                channel_id       TEXT,
                message_id       TEXT,                          -- ID pesan kontrol di channel
                handler_id       TEXT,
                handler_username TEXT,
                created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
                closed_at        TEXT
            );

            -- Payment methods (DANA, GoPay, SeaBank, QRIS)
            CREATE TABLE IF NOT EXISTS payment_methods (
                method      TEXT PRIMARY KEY,
                details     TEXT,
                owner_name  TEXT,
                qris_url    TEXT,
                updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        await db.commit()
        # Pastikan kolom baru untuk fitur pembayaran ada (migrasi ringan)
        # Tambahkan kolom jika belum ada agar tidak merusak database lama
        async with db.execute("PRAGMA table_info(tickets)") as cur:
            rows = await cur.fetchall()
            cols = {r[1] for r in rows}
        # Kolom yang kita perlukan: payment_method, order_status, total_idr
        if "payment_method" not in cols:
            await db.execute("ALTER TABLE tickets ADD COLUMN payment_method TEXT")
        if "order_status" not in cols:
            await db.execute("ALTER TABLE tickets ADD COLUMN order_status TEXT DEFAULT ''")
        if "total_idr" not in cols:
            await db.execute("ALTER TABLE tickets ADD COLUMN total_idr REAL DEFAULT 0")
        # Tambahan kolom untuk menyimpan referensi produk dan bukti/verifikasi
        if "product_id" not in cols:
            await db.execute("ALTER TABLE tickets ADD COLUMN product_id INTEGER")
        if "product_name" not in cols:
            await db.execute("ALTER TABLE tickets ADD COLUMN product_name TEXT")
        if "price_idr" not in cols:
            await db.execute("ALTER TABLE tickets ADD COLUMN price_idr REAL DEFAULT 0")
        if "verified_at" not in cols:
            await db.execute("ALTER TABLE tickets ADD COLUMN verified_at TEXT")
        if "verified_by" not in cols:
            await db.execute("ALTER TABLE tickets ADD COLUMN verified_by TEXT")
        if "proof_url" not in cols:
            await db.execute("ALTER TABLE tickets ADD COLUMN proof_url TEXT")
        if "proof_uploaded_at" not in cols:
            await db.execute("ALTER TABLE tickets ADD COLUMN proof_uploaded_at TEXT")
        if "rejected_reason" not in cols:
            await db.execute("ALTER TABLE tickets ADD COLUMN rejected_reason TEXT")
        if "completed_at" not in cols:
            await db.execute("ALTER TABLE tickets ADD COLUMN completed_at TEXT")
        await db.commit()

        # Buat tabel transactions untuk menyimpan log transaksi (ringkas)
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER,
                user_id TEXT,
                username TEXT,
                robux_amount INTEGER,
                total_idr REAL,
                payment_method TEXT,
                verified_by TEXT,
                verified_at TEXT,
                status TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS vouches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL UNIQUE,
                transaction_id INTEGER,
                buyer_id TEXT NOT NULL,
                buyer_username TEXT NOT NULL,
                handler_id TEXT NOT NULL,
                handler_username TEXT NOT NULL,
                robux_amount INTEGER NOT NULL,
                total_idr REAL NOT NULL,
                payment_method TEXT,
                via TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'done',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        await db.commit()


async def set_payment_method(method: str, details: str | None = None, owner_name: str | None = None, qris_url: str | None = None) -> None:
    """Insert or update payment method details."""
    method_key = normalize_payment_method(method)
    async with get_db() as db:
        await db.execute(
            "REPLACE INTO payment_methods (method, details, owner_name, qris_url, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
            (method_key, details or "", owner_name or "", qris_url or ""),
        )
        await db.commit()


async def get_payment_method(method: str) -> dict | None:
    method_key = normalize_payment_method(method)
    async with get_db() as db:
        async with db.execute("SELECT * FROM payment_methods WHERE method = ?", (method_key,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_all_payment_methods() -> list[dict]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM payment_methods ORDER BY method ASC") as cur:
            return [dict(r) for r in await cur.fetchall()]


# ── Produk ────────────────────────────────────────────────────────────────────

async def get_all_products(active_only: bool = True) -> list[dict]:
    async with get_db() as db:
        query = "SELECT * FROM products"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY robux_amount ASC"
        async with db.execute(query) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_product(product_id: int) -> dict | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def create_product(
    name: str,
    description: str,
    robux_amount: int,
    price_idr: float,
    stock: int = -1,
) -> int:
    async with get_db() as db:
        cur = await db.execute(
            """
            INSERT INTO products (name, description, robux_amount, price_idr, stock)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, description, robux_amount, price_idr, stock),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def update_product(product_id: int, **fields: Any) -> bool:
    if not fields:
        return False
    allowed = {"name", "description", "robux_amount", "price_idr", "stock", "is_active"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [product_id]
    async with get_db() as db:
        await db.execute(
            f"UPDATE products SET {set_clause} WHERE id = ?", values
        )
        await db.commit()
    return True


async def delete_product(product_id: int) -> bool:
    async with get_db() as db:
        await db.execute(
            "UPDATE products SET is_active = 0, updated_at = datetime('now') WHERE id = ?",
            (product_id,),
        )
        await db.commit()
    return True


# ── Pesanan ───────────────────────────────────────────────────────────────────

async def create_order(
    user_id: str,
    username: str,
    product_id: int,
    quantity: int,
    total_idr: float,
    robux_total: int,
    roblox_username: str = "",
    notes: str = "",
) -> int:
    async with get_db() as db:
        cur = await db.execute(
            """
            INSERT INTO orders
                (user_id, username, product_id, quantity, total_idr,
                 robux_total, roblox_username, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, product_id, quantity, total_idr,
             robux_total, roblox_username, notes),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def get_order(order_id: int) -> dict | None:
    async with get_db() as db:
        async with db.execute(
            """
            SELECT o.*, p.name AS product_name
            FROM orders o
            JOIN products p ON o.product_id = p.id
            WHERE o.id = ?
            """,
            (order_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user_orders(user_id: str, limit: int = 10) -> list[dict]:
    async with get_db() as db:
        async with db.execute(
            """
            SELECT o.*, p.name AS product_name
            FROM orders o
            JOIN products p ON o.product_id = p.id
            WHERE o.user_id = ?
            ORDER BY o.created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_all_orders(status: str | None = None, limit: int = 25) -> list[dict]:
    async with get_db() as db:
        query = """
            SELECT o.*, p.name AS product_name
            FROM orders o
            JOIN products p ON o.product_id = p.id
        """
        params: list[Any] = []
        if status:
            query += " WHERE o.status = ?"
            params.append(status)
        query += " ORDER BY o.created_at DESC LIMIT ?"
        params.append(limit)
        async with db.execute(query, params) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def update_order_status(order_id: int, status: str) -> bool:
    async with get_db() as db:
        await db.execute(
            "UPDATE orders SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, order_id),
        )
        await db.commit()
    return True


# ── Activity Log ──────────────────────────────────────────────────────────────

async def log_activity(
    admin_id: str, action: str, target: str = "", details: str = ""
) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO activity_log (admin_id, action, target, details) VALUES (?, ?, ?, ?)",
            (admin_id, action, target, details),
        )
        await db.commit()


# ── Tickets ───────────────────────────────────────────────────────────────────

async def count_active_tickets(user_id: str) -> int:
    """Hitung ticket aktif (open/claimed) milik user."""
    async with get_db() as db:
        async with db.execute(
            "SELECT COUNT(*) FROM tickets WHERE user_id = ? AND status IN ('open', 'claimed')",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0


async def create_ticket(
    user_id: str,
    username: str,
    roblox_username: str,
    robux_amount: int,
    ticket_type: str,
) -> int:
    """Buat ticket baru dan kembalikan ID-nya."""
    async with get_db() as db:
        cur = await db.execute(
            """
            INSERT INTO tickets (user_id, username, roblox_username, robux_amount, ticket_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, username, roblox_username, robux_amount, ticket_type),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def set_ticket_order_code(ticket_id: int, order_code: str) -> None:
    """Set nomor order RS-XXXX setelah insert (saat ID sudah diketahui)."""
    async with get_db() as db:
        await db.execute(
            "UPDATE tickets SET order_code = ? WHERE id = ?",
            (order_code, ticket_id),
        )
        await db.commit()


async def update_ticket_channel(ticket_id: int, channel_id: str, message_id: str) -> None:
    """Simpan channel_id dan message_id pesan kontrol ke DB."""
    async with get_db() as db:
        await db.execute(
            "UPDATE tickets SET channel_id = ?, message_id = ? WHERE id = ?",
            (channel_id, message_id, ticket_id),
        )
        await db.commit()


async def get_ticket(ticket_id: int) -> dict | None:
    """Ambil satu ticket berdasarkan ID."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_active_tickets() -> list[dict]:
    """Ambil semua ticket yang masih open atau claimed (untuk re-register views)."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM tickets WHERE status IN ('open', 'claimed') ORDER BY id ASC"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_user_tickets(user_id: str, limit: int = 10) -> list[dict]:
    """Ambil ticket milik satu user (terbaru duluan)."""
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM tickets WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_all_tickets(status: str | None = None, limit: int = 25) -> list[dict]:
    """Ambil semua ticket dengan filter status opsional."""
    async with get_db() as db:
        if status:
            query = "SELECT * FROM tickets WHERE status = ? ORDER BY created_at DESC LIMIT ?"
            params: tuple = (status, limit)
        else:
            query = "SELECT * FROM tickets ORDER BY created_at DESC LIMIT ?"
            params = (limit,)
        async with db.execute(query, params) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_ticket_transactions(status: str | None = None, buyer_query: str | None = None, limit: int = 25) -> list[dict]:
    """Ambil riwayat transaksi ticket dengan filter status dan buyer opsional."""
    async with get_db() as db:
        clauses: list[str] = []
        params: list[Any] = []

        if status and status.lower() not in ("all", ""):
            normalized = status.lower()
            if normalized == "pending":
                normalized = config.TICKET_ORDER_STATUS_WAITING
            clauses.append("order_status = ?")
            params.append(normalized)

        if buyer_query:
            query_text = buyer_query.strip()
            if query_text.startswith("<@") and query_text.endswith(">"):
                query_text = query_text.strip("<@!>")
            if query_text.isdigit():
                clauses.append("(user_id = ? OR username LIKE ?)")
                params.extend([query_text, f"%{query_text}%"])
            else:
                clauses.append("username LIKE ?")
                params.append(f"%{query_text}%")

        query = "SELECT * FROM tickets"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with db.execute(query, tuple(params)) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def claim_ticket(ticket_id: int, handler_id: str, handler_username: str) -> None:
    """Tandai ticket sebagai claimed oleh handler."""
    async with get_db() as db:
        await db.execute(
            """
            UPDATE tickets
            SET status = 'claimed', handler_id = ?, handler_username = ?
            WHERE id = ?
            """,
            (handler_id, handler_username, ticket_id),
        )
        await db.commit()

 
async def set_ticket_payment(ticket_id: int, payment_method: str, total_idr: float, order_status: str) -> None:
    """Simpan metode pembayaran, total, dan status order pada ticket."""
    method_key = normalize_payment_method(payment_method)
    async with get_db() as db:
        await db.execute(
            "UPDATE tickets SET payment_method = ?, total_idr = ?, order_status = ? WHERE id = ?",
            (method_key, float(total_idr), order_status, ticket_id),
        )
        await db.commit()


async def set_ticket_proof(ticket_id: int, proof_url: str) -> None:
    """Simpan URL bukti pembayaran dan timestamp unggahan."""
    async with get_db() as db:
        await db.execute(
            "UPDATE tickets SET proof_url = ?, proof_uploaded_at = datetime('now') WHERE id = ?",
            (proof_url, ticket_id),
        )
        await db.commit()


async def set_ticket_product(ticket_id: int, product_id: int, product_name: str, price_idr: float) -> None:
    """Simpan referensi produk dan harga pada ticket."""
    async with get_db() as db:
        await db.execute(
            "UPDATE tickets SET product_id = ?, product_name = ?, price_idr = ? WHERE id = ?",
            (product_id, product_name, float(price_idr), ticket_id),
        )
        await db.commit()


async def set_ticket_verified(ticket_id: int, verifier_id: str, verifier_name: str) -> None:
    """Tandai ticket sebagai verified dan catat admin serta waktu verifikasi."""
    async with get_db() as db:
        await db.execute(
            "UPDATE tickets SET order_status = ?, verified_by = ?, verified_at = datetime('now') WHERE id = ?",
            ("verified", verifier_name, ticket_id),
        )
        # juga set handler jika belum ada
        await db.execute(
            "UPDATE tickets SET handler_id = COALESCE(handler_id, ?), handler_username = COALESCE(handler_username, ?) WHERE id = ?",
            (verifier_id, verifier_name, ticket_id),
        )
        await db.commit()


async def set_ticket_rejected(ticket_id: int, reason: str | None, admin_id: str, admin_name: str) -> None:
    """Tandai ticket sebagai rejected, simpan alasan dan admin yang menolak."""
    async with get_db() as db:
        await db.execute(
            "UPDATE tickets SET order_status = ?, rejected_reason = ?, verified_by = ?, verified_at = datetime('now') WHERE id = ?",
            ("rejected", reason or "", admin_name, ticket_id),
        )
        await db.execute(
            "UPDATE tickets SET handler_id = COALESCE(handler_id, ?), handler_username = COALESCE(handler_username, ?) WHERE id = ?",
            (admin_id, admin_name, ticket_id),
        )
        await db.commit()


async def set_ticket_done(ticket_id: int, admin_id: str, admin_name: str) -> None:
    """Tandai ticket sebagai done dan catat waktu selesai serta handler jika perlu."""
    async with get_db() as db:
        await db.execute(
            "UPDATE tickets SET order_status = ?, completed_at = datetime('now'), verified_by = ? WHERE id = ?",
            ("done", admin_name, ticket_id),
        )
        await db.execute(
            "UPDATE tickets SET handler_id = COALESCE(handler_id, ?), handler_username = COALESCE(handler_username, ?) WHERE id = ?",
            (admin_id, admin_name, ticket_id),
        )
        await db.commit()


async def create_transaction_from_ticket(ticket_id: int, status: str = "done") -> int:
    """Buat entri transaksi ringkas di tabel `transactions` berdasarkan data ticket saat ini.

    Mengembalikan ID transaksi yang dibuat.
    """
    ticket = await get_ticket(ticket_id)
    if not ticket:
        return 0
    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO transactions (ticket_id, user_id, username, robux_amount, total_idr, payment_method, verified_by, verified_at, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ticket_id,
                ticket.get("user_id"),
                ticket.get("username"),
                ticket.get("robux_amount"),
                float(ticket.get("total_idr") or 0),
                ticket.get("payment_method"),
                ticket.get("verified_by"),
                ticket.get("verified_at"),
                status,
            ),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def get_transaction_id_for_ticket(ticket_id: int) -> int | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT id FROM transactions WHERE ticket_id = ? ORDER BY created_at DESC LIMIT 1",
            (ticket_id,),
        ) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else None


async def find_done_ticket_for_vouch(
    buyer_id: str,
    handler_id: str,
    robux_amount: int,
    ticket_type: str,
) -> dict | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM tickets WHERE user_id = ? AND handler_id = ? AND robux_amount = ? AND ticket_type = ? AND order_status = ? ORDER BY completed_at DESC LIMIT 1",
            (buyer_id, handler_id, robux_amount, ticket_type, config.TICKET_ORDER_STATUS_DONE),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_vouch_by_ticket(ticket_id: int) -> dict | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM vouches WHERE ticket_id = ?",
            (ticket_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def create_vouch(
    ticket_id: int,
    transaction_id: int | None,
    buyer_id: str,
    buyer_username: str,
    handler_id: str,
    handler_username: str,
    robux_amount: int,
    total_idr: float,
    payment_method: str | None,
    via: str,
) -> int:
    async with get_db() as db:
        cur = await db.execute(
            "INSERT OR IGNORE INTO vouches (ticket_id, transaction_id, buyer_id, buyer_username, handler_id, handler_username, robux_amount, total_idr, payment_method, via, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ticket_id,
                transaction_id,
                buyer_id,
                buyer_username,
                handler_id,
                handler_username,
                robux_amount,
                float(total_idr),
                payment_method or "",
                via,
                config.TICKET_ORDER_STATUS_DONE,
            ),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def set_ticket_order_status(ticket_id: int, order_status: str) -> None:
    """Update hanya order_status kolom pada ticket."""
    async with get_db() as db:
        await db.execute(
            "UPDATE tickets SET order_status = ? WHERE id = ?",
            (order_status, ticket_id),
        )
        await db.commit()


async def close_ticket(ticket_id: int) -> None:
    """Tutup ticket dan catat waktu penutupan."""
    async with get_db() as db:
        await db.execute(
            """
            UPDATE tickets
            SET status = 'closed', closed_at = datetime('now')
            WHERE id = ?
            """,
            (ticket_id,),
        )
        await db.commit()
