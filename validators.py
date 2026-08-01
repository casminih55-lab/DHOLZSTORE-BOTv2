"""
Fungsi validasi input untuk perintah-perintah bot.
"""

from __future__ import annotations

import re
import config


class ValidationError(Exception):
    """Dilempar saat input tidak valid; pesannya langsung ditampilkan ke user."""
    pass


def validate_robux_amount(amount: int) -> int:
    """Pastikan jumlah Robux dalam rentang yang diperbolehkan."""
    if amount < config.MIN_ROBUX_AMOUNT:
        raise ValidationError(
            f"Jumlah Robux minimum adalah {config.MIN_ROBUX_AMOUNT:,}."
        )
    if amount > config.MAX_ROBUX_AMOUNT:
        raise ValidationError(
            f"Jumlah Robux maksimum adalah {config.MAX_ROBUX_AMOUNT:,}."
        )
    return amount


def validate_price(price: float) -> float:
    """Pastikan harga dalam rentang yang wajar (IDR)."""
    if price < config.MIN_PRICE_IDR:
        raise ValidationError(
            f"Harga minimum adalah Rp {config.MIN_PRICE_IDR:,.0f}."
        )
    if price > config.MAX_PRICE_IDR:
        raise ValidationError(
            f"Harga maksimum adalah Rp {config.MAX_PRICE_IDR:,.0f}."
        )
    return price


def validate_quantity(quantity: int) -> int:
    """Pastikan kuantitas positif."""
    if quantity < 1:
        raise ValidationError("Kuantitas harus minimal 1.")
    if quantity > 100:
        raise ValidationError("Kuantitas maksimal 100 per transaksi.")
    return quantity


def validate_roblox_username(username: str) -> str:
    """
    Username Roblox: 3-20 karakter, hanya huruf, angka, dan underscore.
    Tidak boleh dimulai/diakhiri dengan underscore.
    """
    username = username.strip()
    if len(username) < 3:
        raise ValidationError("Username Roblox minimal 3 karakter.")
    if len(username) > 20:
        raise ValidationError("Username Roblox maksimal 20 karakter.")
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$", username):
        raise ValidationError(
            "Username Roblox hanya boleh mengandung huruf, angka, dan underscore, "
            "serta tidak boleh diawali/diakhiri underscore."
        )
    return username


def validate_order_status(status: str) -> str:
    """Pastikan status pesanan valid."""
    status = status.lower().strip()
    if status not in config.ALL_ORDER_STATUSES:
        valid = ", ".join(config.ALL_ORDER_STATUSES)
        raise ValidationError(f"Status tidak valid. Pilihan: {valid}")
    return status


def validate_stock(stock: int) -> int:
    """Validasi nilai stok (-1 = unlimited, >= 0 = terbatas)."""
    if stock < -1:
        raise ValidationError("Stok tidak valid. Gunakan -1 untuk unlimited.")
    return stock
