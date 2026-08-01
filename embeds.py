"""
Builder untuk Discord Embed yang digunakan di seluruh bot.
Semua tampilan pesan dibuat di sini agar konsisten.
"""

from __future__ import annotations

import discord
from datetime import datetime
from typing import Any

import config


def _base_embed(color: int, title: str = "", description: str = "") -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.utcnow(),
    )
    embed.set_footer(text=config.STORE_NAME)
    return embed


# ── Embed Umum ────────────────────────────────────────────────────────────────

def success(title: str, description: str = "") -> discord.Embed:
    return _base_embed(config.COLOR_SUCCESS, f"✅ {title}", description)


def error(title: str, description: str = "") -> discord.Embed:
    return _base_embed(config.COLOR_ERROR, f"❌ {title}", description)


def info(title: str, description: str = "") -> discord.Embed:
    return _base_embed(config.COLOR_INFO, f"ℹ️ {title}", description)


def warning(title: str, description: str = "") -> discord.Embed:
    return _base_embed(config.COLOR_WARNING, f"⚠️ {title}", description)


# ── Embed Produk ──────────────────────────────────────────────────────────────

def product_card(product: dict[str, Any]) -> discord.Embed:
    """Tampilkan detail satu produk."""
    stock_text = "Unlimited" if product["stock"] == -1 else str(product["stock"])
    embed = _base_embed(
        config.COLOR_STORE,
        title=f"🛒 {product['name']}",
        description=product.get("description", ""),
    )
    embed.add_field(name="💎 Robux", value=f"{product['robux_amount']:,}", inline=True)
    embed.add_field(
        name="💰 Harga",
        value=f"Rp {product['price_idr']:,.0f}",
        inline=True,
    )
    embed.add_field(name="📦 Stok", value=stock_text, inline=True)
    embed.add_field(name="🆔 ID Produk", value=str(product["id"]), inline=True)
    return embed


def product_list(products: list[dict[str, Any]]) -> discord.Embed:
    """Daftar semua produk dalam satu embed."""
    embed = _base_embed(
        config.COLOR_STORE,
        title=f"🏪 {config.STORE_NAME} — Daftar Produk",
    )
    if not products:
        embed.description = "Belum ada produk yang tersedia."
        return embed

    for p in products:
        stock_text = "∞" if p["stock"] == -1 else str(p["stock"])
        embed.add_field(
            name=f"[#{p['id']}] {p['name']}",
            value=(
                f"💎 **{p['robux_amount']:,}** Robux\n"
                f"💰 Rp {p['price_idr']:,.0f}\n"
                f"📦 Stok: {stock_text}"
            ),
            inline=True,
        )
    return embed


# ── Embed Pesanan ─────────────────────────────────────────────────────────────

STATUS_EMOJI = {
    "pending": "🕐",
    "processing": "⚙️",
    "completed": "✅",
    "cancelled": "❌",
    "refunded": "↩️",
}

STATUS_COLOR = {
    "pending": config.COLOR_WARNING,
    "processing": config.COLOR_INFO,
    "completed": config.COLOR_SUCCESS,
    "cancelled": config.COLOR_ERROR,
    "refunded": 0x95A5A6,
}


def order_detail(order: dict[str, Any]) -> discord.Embed:
    """Detail lengkap satu pesanan."""
    status = order["status"]
    emoji = STATUS_EMOJI.get(status, "❓")
    color = STATUS_COLOR.get(status, config.COLOR_INFO)

    embed = _base_embed(
        color,
        title=f"📋 Pesanan #{order['id']}",
    )
    embed.add_field(name="👤 Pembeli", value=order["username"], inline=True)
    embed.add_field(name="📦 Produk", value=order.get("product_name", "—"), inline=True)
    embed.add_field(
        name="💎 Robux",
        value=f"{order['robux_total']:,}",
        inline=True,
    )
    embed.add_field(
        name="💰 Total",
        value=f"Rp {order['total_idr']:,.0f}",
        inline=True,
    )
    embed.add_field(
        name=f"{emoji} Status",
        value=status.capitalize(),
        inline=True,
    )
    if order.get("roblox_username"):
        embed.add_field(
            name="🎮 Username Roblox",
            value=order["roblox_username"],
            inline=True,
        )
    if order.get("notes"):
        embed.add_field(name="📝 Catatan", value=order["notes"], inline=False)
    embed.add_field(
        name="🕐 Dibuat",
        value=order["created_at"],
        inline=True,
    )
    return embed


def order_list(orders: list[dict[str, Any]], title: str = "Daftar Pesanan") -> discord.Embed:
    """Ringkasan beberapa pesanan dalam satu embed."""
    embed = _base_embed(config.COLOR_INFO, title=f"📋 {title}")
    if not orders:
        embed.description = "Tidak ada pesanan ditemukan."
        return embed

    lines = []
    for o in orders:
        emoji = STATUS_EMOJI.get(o["status"], "❓")
        lines.append(
            f"`#{o['id']}` {emoji} **{o.get('product_name','?')}** — "
            f"{o['robux_total']:,} Robux — Rp {o['total_idr']:,.0f}"
        )
    embed.description = "\n".join(lines)
    return embed


# ── Embed Ticket ─────────────────────────────────────────────────────────────

TICKET_TYPE_LABEL = {
    "send": "🟦 Via Send",
    "community": "🟩 Via Community",
}

TICKET_STATUS_EMOJI = {
    "open": "🔓",
    "claimed": "🙋",
    "closed": "🔒",
}

TICKET_STATUS_COLOR = {
    "open": 0x5865F2,    # Discord blurple
    "claimed": 0xFEE75C, # kuning emas
    "closed": 0x95A5A6,  # abu-abu
}


def ticket_panel() -> discord.Embed:
    """Embed panel utama Ticket System yang ditampilkan di channel order."""
    embed = discord.Embed(
        title="🛒 Robux Store — Buat Ticket Pembelian",
        description=(
            "Pilih metode pengiriman Robux yang kamu inginkan:\n\n"
            "🟦 **Via Send** — Bebas jumlah Robux, dikirim langsung ke akun Roblox kamu.\n\n"
            "🟩 **Via Community** — Minimal **500 Robux**, dikirim melalui fitur Community.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📌 Maksimal **3 ticket aktif** per user.\n"
            "📋 Nomor order otomatis dibuat (RS-0001, RS-0002, ...).\n"
            "📩 Channel ticket bersifat **private** — hanya kamu dan admin yang bisa lihat."
        ),
        color=0x5865F2,
        timestamp=datetime.utcnow(),
    )
    embed.set_footer(text=config.STORE_NAME + " • Ticket System")
    return embed


def ticket_info(ticket: dict[str, Any], buyer: Any = None) -> discord.Embed:
    """Embed info ticket yang ditampilkan di dalam channel ticket."""
    status = ticket.get("status", "open")
    ttype = ticket.get("ticket_type", "send")
    emoji = TICKET_STATUS_EMOJI.get(status, "❓")
    color = TICKET_STATUS_COLOR.get(status, 0x5865F2)

    embed = discord.Embed(
        title=f"📋 Ticket {ticket.get('order_code', '')}",
        color=color,
        timestamp=datetime.utcnow(),
    )
    embed.add_field(
        name="👤 Pembeli",
        value=buyer.mention if buyer else ticket.get("username", "—"),
        inline=True,
    )
    embed.add_field(
        name="🎮 Username Roblox",
        value=f"`{ticket.get('roblox_username', '—')}`",
        inline=True,
    )
    embed.add_field(
        name="💎 Jumlah Robux",
        value=f"**{ticket.get('robux_amount', 0):,}** Robux",
        inline=True,
    )
    embed.add_field(
        name="📦 Metode",
        value=TICKET_TYPE_LABEL.get(ttype, ttype),
        inline=True,
    )
    embed.add_field(
        name=f"{emoji} Status",
        value=status.capitalize(),
        inline=True,
    )
    # Tampilkan status order (payment) jika ada
    order_status = ticket.get("order_status")
    if order_status:
        embed.add_field(name="💳 Order Status", value=order_status.replace("_", " ").capitalize(), inline=True)
    # Tampilkan metode pembayaran dan total jika sudah diatur
    if ticket.get("payment_method"):
        embed.add_field(name="💸 Metode Bayar", value=ticket.get("payment_method", "—"), inline=True)
    if ticket.get("total_idr"):
        embed.add_field(name="💰 Total Bayar", value=f"Rp {float(ticket.get('total_idr',0)):,.0f}", inline=True)
    if ticket.get("handler_username"):
        embed.add_field(
            name="🙋 Handler",
            value=f"**{ticket['handler_username']}**",
            inline=True,
        )
    embed.add_field(
        name="🕐 Dibuat",
        value=ticket.get("created_at", "—"),
        inline=False,
    )
    embed.set_footer(text=config.STORE_NAME + " • Ticket System")
    return embed


def ticket_list_embed(
    tickets: list[dict[str, Any]], title: str = "Daftar Ticket"
) -> discord.Embed:
    """Ringkasan daftar ticket dalam satu embed."""
    embed = _base_embed(config.COLOR_INFO, title=f"🎟️ {title}")
    if not tickets:
        embed.description = "Tidak ada ticket ditemukan."
        return embed

    lines = []
    for t in tickets:
        status = t.get("status", "open")
        s_emoji = TICKET_STATUS_EMOJI.get(status, "❓")
        ttype = TICKET_TYPE_LABEL.get(t.get("ticket_type", "send"), "—")
        handler = f" — Handler: {t['handler_username']}" if t.get("handler_username") else ""
        lines.append(
            f"`{t.get('order_code','—')}` {s_emoji} "
            f"**{t.get('roblox_username','—')}** | "
            f"{t.get('robux_amount', 0):,} Robux | {ttype}{handler}"
        )
    embed.description = "\n".join(lines)
    return embed


def ticket_transaction_list(tickets: list[dict[str, Any]], title: str = "Riwayat Transaksi") -> discord.Embed:
    """Ringkasan transaksi ticket/pembayaran untuk admin."""
    embed = _base_embed(config.COLOR_INFO, title=f"💳 {title}")
    if not tickets:
        embed.description = "Tidak ada transaksi ditemukan."
        return embed

    lines = []
    for t in tickets:
        order_status = t.get("order_status") or "pending"
        status_label = order_status.replace("_", " ").capitalize()
        amount = f"{t.get('robux_amount',0):,} Robux"
        total = f"Rp {float(t.get('total_idr',0)):,.0f}"
        method = t.get("payment_method", "—")
        handler = t.get("handler_username") or "—"
        time_label = t.get("completed_at") or t.get("verified_at") or t.get("proof_uploaded_at") or t.get("created_at", "—")
        lines.append(
            f"`{t.get('order_code','—')}` — **{t.get('username','—')}** | {amount} | {total} | {method} | {status_label} | {handler} | {time_label}"
        )
    embed.description = "\n".join(lines)
    return embed


# ── Embed Konfirmasi Order ────────────────────────────────────────────────────

def order_confirmation(
    order_id: int,
    product: dict[str, Any],
    quantity: int,
    total_idr: float,
    roblox_username: str,
) -> discord.Embed:
    embed = _base_embed(
        config.COLOR_SUCCESS,
        title="🎉 Pesanan Berhasil Dibuat!",
        description=(
            "Tim kami akan segera memproses pesananmu.\n"
            "Pantau status dengan perintah `/cek_order`."
        ),
    )
    embed.add_field(name="🆔 ID Pesanan", value=f"#{order_id}", inline=True)
    embed.add_field(name="📦 Produk", value=product["name"], inline=True)
    embed.add_field(
        name="💎 Total Robux",
        value=f"{product['robux_amount'] * quantity:,}",
        inline=True,
    )
    embed.add_field(
        name="💰 Total Bayar",
        value=f"Rp {total_idr:,.0f}",
        inline=True,
    )
    embed.add_field(name="🎮 Akun Roblox", value=roblox_username, inline=True)
    return embed


def payment_details(ticket: dict[str, Any]) -> discord.Embed:
    """Embed instruksi pembayaran lengkap yang dikirim setelah pembeli memilih metode."""
    embed = _base_embed(config.COLOR_INFO, title="📬 Instruksi Pembayaran")
    embed.add_field(name="🆔 Nomor Order", value=ticket.get("order_code", "—"), inline=True)
    embed.add_field(name="👤 Pembeli", value=ticket.get("username", "—"), inline=True)
    embed.add_field(name="💎 Jumlah Robux", value=f"{ticket.get('robux_amount',0):,} Robux", inline=True)
    embed.add_field(name="💸 Metode Bayar", value=ticket.get("payment_method", "—"), inline=True)
    embed.add_field(name="💰 Total", value=f"Rp {float(ticket.get('total_idr',0)):,.0f}", inline=True)
    # Jika ada payment_info, tampilkan detailnya
    pinfo = ticket.get("payment_info") or {}
    if pinfo:
        method = (pinfo.get("method") or ticket.get("payment_method") or "").strip().lower()
        if method == "qris":
            qurl = pinfo.get("qris_url")
            if qurl:
                try:
                    embed.set_image(url=qurl)
                except Exception:
                    pass
            else:
                embed.add_field(name="📱 QRIS", value="Silakan lihat lampiran gambar.", inline=True)
        elif method in {"dana", "gopay", "seabank"}:
            num = pinfo.get("details") or pinfo.get("number") or "—"
            owner = pinfo.get("owner_name") or "—"
            embed.add_field(name="📲 Nomor/Acc", value=num, inline=True)
            embed.add_field(name="👤 Atas Nama", value=owner, inline=True)
        else:
            num = pinfo.get("details") or pinfo.get("number") or "—"
            owner = pinfo.get("owner_name") or "—"
            if num != "—" or owner != "—":
                embed.add_field(name="📲 Nomor/Acc", value=num, inline=True)
                embed.add_field(name="👤 Atas Nama", value=owner, inline=True)
    if ticket.get("order_status"):
        status = ticket.get("order_status").replace("_", " ").capitalize()
        status_label = {
            "Waiting payment": "Pending",
            "Paid": "Paid",
            "Processing": "Processing",
            "Verified": "Verified",
            "Done": "Done",
        }.get(status, status)
        embed.add_field(name="🕐 Status Pembayaran", value=status_label, inline=True)
    embed.set_footer(text=config.STORE_NAME + " • Payment")
    return embed


def payment_panel(methods: list[dict[str, Any]]) -> discord.Embed:
    """Embed panel yang menampilkan semua metode pembayaran aktif."""
    embed = _base_embed(config.COLOR_STORE, title="💳 Payment Panel")
    if not methods:
        embed.description = (
            "Belum ada metode pembayaran yang dikonfigurasi. "
            "Silakan admin gunakan `/payment set` untuk menambahkan DANA, GoPay, SeaBank, atau QRIS."
        )
        return embed

    for m in methods:
        method = m.get("method", "—")
        details = m.get("details") or "Tidak ada detail."
        owner = m.get("owner_name") or "Tidak ada nama pemilik."
        line = f"**Detail:** {details}\n**Atas nama:** {owner}"
        if method.lower() == "qris":
            qris_url = m.get("qris_url")
            if qris_url:
                line += f"\n**QRIS:** [Lihat QRIS]({qris_url})"
            else:
                line += "\n**QRIS:** Belum terpasang URL."
        embed.add_field(name=f"💳 {method}", value=line, inline=False)

    embed.add_field(
        name="📌 Cara Bayar",
        value=(
            "Pilih metode pembayaran di menu ticket, lalu unggah bukti pembayaran ketika sudah transfer/scan.\n"
            "Admin/staff akan menerima notifikasi dan memverifikasi pembayaran."
        ),
        inline=False,
    )
    embed.set_footer(text=config.STORE_NAME + " • Payment Panel")
    return embed


def transaction_log_from_ticket(ticket: dict[str, Any]) -> discord.Embed:
    """Buat embed ringkasan transaksi berdasarkan ticket (untuk channel order-log)."""
    embed = _base_embed(config.COLOR_STORE, title=f"🧾 Transaksi — {ticket.get('order_code','-')}")
    embed.add_field(name="👤 Pembeli", value=ticket.get('username','-'), inline=True)
    embed.add_field(name="💎 Robux", value=f"{ticket.get('robux_amount',0):,} Robux", inline=True)
    embed.add_field(name="💰 Total", value=f"Rp {float(ticket.get('total_idr',0)):,.0f}", inline=True)
    embed.add_field(name="💸 Metode", value=ticket.get('payment_method','-'), inline=True)
    if ticket.get('handler_username'):
        embed.add_field(name="🙋 Handler", value=ticket.get('handler_username'), inline=True)
    if ticket.get('verified_by'):
        embed.add_field(name="✅ Diverifikasi Oleh", value=ticket.get('verified_by'), inline=True)
    if ticket.get('verified_at'):
        embed.add_field(name="🕐 Waktu Verifikasi", value=ticket.get('verified_at'), inline=True)
    embed.add_field(name="🆔 Order Code", value=ticket.get('order_code','-'), inline=True)
    embed.set_footer(text=config.STORE_NAME + " • Transaction Log")
    return embed
    return embed


def payment_proof_notification(ticket: dict[str, Any], buyer: Any, notes: str, status: str) -> discord.Embed:
    embed = _base_embed(config.COLOR_INFO, title="📌 Bukti Pembayaran Diterima")
    embed.add_field(name="🆔 Nomor Order", value=ticket.get("order_code", "—"), inline=True)
    embed.add_field(name="👤 Buyer", value=str(buyer), inline=True)
    embed.add_field(name="💸 Metode", value=ticket.get("payment_method", "—"), inline=True)
    embed.add_field(name="🕐 Waktu", value=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), inline=True)
    embed.add_field(name="🔖 Status", value=status, inline=True)
    if notes:
        embed.add_field(name="📝 Catatan", value=notes, inline=False)
    embed.set_footer(text=config.STORE_NAME + " • Payment Proof")
    return embed


def vouch_log_embed(ticket: dict[str, Any]) -> discord.Embed:
    embed = _base_embed(config.COLOR_SUCCESS, title="✅ VOUCH BERHASIL")
    embed.add_field(name="Buyer", value=ticket.get("username", "—"), inline=False)
    embed.add_field(name="Seller/Admin", value=ticket.get("handler_username", "—"), inline=False)
    embed.add_field(name="Produk", value=f"Robux ({int(ticket.get('robux_amount', 0)):,})", inline=False)
    embed.add_field(name="Harga", value=f"Rp {float(ticket.get('total_idr', 0)):,.0f}", inline=False)
    embed.add_field(name="Metode Pembayaran", value=ticket.get("payment_method", "—"), inline=False)
    embed.add_field(name="Status", value="Done ✅", inline=False)
    embed.add_field(name="Waktu", value=ticket.get("completed_at") or ticket.get("created_at") or "—", inline=False)
    embed.add_field(name="Order Code", value=ticket.get("order_code", "—"), inline=False)
    embed.set_footer(text=config.STORE_NAME + " • Vouch")
    return embed
