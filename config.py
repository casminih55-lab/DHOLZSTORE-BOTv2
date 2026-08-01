"""
Konfigurasi terpusat untuk Discord Robux Store Bot.
Semua pengaturan dibaca dari file .env.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Discord ──────────────────────────────────────────────────────────────────
DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
GUILD_ID: int | None = int(os.getenv("DISCORD_GUILD_ID", 0)) or None

# ── Prefix ───────────────────────────────────────────────────────────────────
COMMAND_PREFIX: str = os.getenv("COMMAND_PREFIX", "!")

# ── Nama toko ────────────────────────────────────────────────────────────────
STORE_NAME: str = os.getenv("STORE_NAME", "Robux Store")
CURRENCY_NAME: str = os.getenv("CURRENCY_NAME", "Robux")

# ── Role ─────────────────────────────────────────────────────────────────────
ADMIN_ROLE_NAME: str = os.getenv("ADMIN_ROLE_NAME", "Admin")
MOD_ROLE_NAME: str = os.getenv("MOD_ROLE_NAME", "Moderator")
# Optional: override role IDs (angka) untuk pemeriksaan lebih presisi
ADMIN_ROLE_ID: int | None = int(os.getenv("ADMIN_ROLE_ID", "0")) or None
MOD_ROLE_ID: int | None = int(os.getenv("MOD_ROLE_ID", "0")) or None

# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/store.db")

# ── Warna embed (hex) ────────────────────────────────────────────────────────
COLOR_SUCCESS: int = 0x2ECC71   # hijau
COLOR_ERROR: int = 0xE74C3C     # merah
COLOR_INFO: int = 0x3498DB      # biru
COLOR_WARNING: int = 0xF39C12   # kuning
COLOR_STORE: int = 0x9B59B6     # ungu (tema Robux)

# ── Status order ─────────────────────────────────────────────────────────────
ORDER_STATUS_PENDING = "pending"
ORDER_STATUS_PROCESSING = "processing"
ORDER_STATUS_COMPLETED = "completed"
ORDER_STATUS_CANCELLED = "cancelled"
ORDER_STATUS_REFUNDED = "refunded"

ALL_ORDER_STATUSES = [
    ORDER_STATUS_PENDING,
    ORDER_STATUS_PROCESSING,
    ORDER_STATUS_COMPLETED,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_REFUNDED,
]

# ── Validasi ─────────────────────────────────────────────────────────────────
MIN_ROBUX_AMOUNT: int = 100
MAX_ROBUX_AMOUNT: int = 100_000
MIN_PRICE_IDR: float = 1_000.0       # Rp 1.000
MAX_PRICE_IDR: float = 10_000_000.0  # Rp 10.000.000

# ── Ticket System ─────────────────────────────────────────────────────────────
TICKET_CATEGORY_NAME: str = os.getenv("TICKET_CATEGORY_NAME", "Tickets")
TICKET_CATEGORY_ID: int | None = int(os.getenv("TICKET_CATEGORY_ID", "0")) or None
TICKET_PANEL_CHANNEL_ID: int | None = int(os.getenv("TICKET_PANEL_CHANNEL_ID", "0")) or None
TICKET_LOG_CHANNEL_ID: int | None = int(os.getenv("TICKET_LOG_CHANNEL_ID", "0")) or None
MAX_ACTIVE_TICKETS: int = 3            # Maksimal ticket aktif per user

# Tipe ticket
TICKET_TYPE_SEND = "send"
TICKET_TYPE_COMMUNITY = "community"
MIN_ROBUX_COMMUNITY: int = 500         # Minimum Robux untuk Via Community

# Status ticket
TICKET_STATUS_OPEN = "open"
TICKET_STATUS_CLAIMED = "claimed"
TICKET_STATUS_CLOSED = "closed"

# Harga per Robux (IDR)
PRICE_PER_ROBUX_SEND: int = 140
PRICE_PER_ROBUX_COMMUNITY: int = 130

# Status lifecycle order pada ticket (payment/status flow)
TICKET_ORDER_STATUS_WAITING = "waiting_payment"
TICKET_ORDER_STATUS_PAID = "paid"
TICKET_ORDER_STATUS_PROCESSING = "processing"
TICKET_ORDER_STATUS_DONE = "done"
TICKET_ORDER_STATUS_VERIFIED = "verified"
TICKET_ORDER_STATUS_REJECTED = "rejected"
TICKET_ORDER_STATUS_CANCELLED = "cancelled"

# Channel name untuk vouch
VOUCH_CHANNEL_NAME: str = os.getenv("VOUCH_CHANNEL_NAME", "vouch")
VOUCH_CHANNEL_ID: int | None = int(os.getenv("VOUCH_CHANNEL_ID", "0")) or None

# Channel untuk menampung ringkasan transaksi / order log
ORDER_LOG_CHANNEL_NAME: str = os.getenv("ORDER_LOG_CHANNEL_NAME", "order-log")
ORDER_LOG_CHANNEL_ID: int | None = int(os.getenv("ORDER_LOG_CHANNEL_ID", "0")) or None

# Optional: channel khusus untuk instruksi/payment (jika server menggunakan channel terpisah)
PAYMENT_CHANNEL_NAME: str = os.getenv("PAYMENT_CHANNEL_NAME", "")
PAYMENT_CHANNEL_ID: int | None = int(os.getenv("PAYMENT_CHANNEL_ID", "0")) or None

# Optional: ID pemilik bot (berguna untuk pembatasan khusus)
BOT_OWNER_ID: int | None = int(os.getenv("BOT_OWNER_ID", "0")) or None

# Folder untuk menyimpan transcript
TRANSCRIPTS_FOLDER: str = os.getenv("TRANSCRIPTS_FOLDER", "transcripts")

# Warna embed ticket
COLOR_TICKET: int = 0x5865F2           # Discord blurple
COLOR_CLAIMED: int = 0xFEE75C          # kuning emas (saat diklaim)


def validate_config() -> None:
    """Periksa konfigurasi wajib saat startup."""
    if not DISCORD_TOKEN:
        raise ValueError(
            "DISCORD_TOKEN tidak ditemukan di .env!\n"
            "Salin .env.example ke .env lalu isi tokennya."
        )
