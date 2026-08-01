"""
Cog: Admin — perintah manajemen produk dan pesanan khusus admin.
Semua perintah di sini hanya bisa diakses oleh member dengan role Admin
atau izin administrator di server.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from typing import Any, Optional
import re

import config
import database as db
import embeds
from validators import (
    ValidationError,
    validate_robux_amount,
    validate_price,
    validate_stock,
    validate_order_status,
)


def is_admin():
    """Check decorator untuk slash commands admin."""
    async def predicate(interaction: Any) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False
        if interaction.user.guild_permissions.administrator:
            return True
        # Prefer role ID if configured, fallback to name
        admin_role = None
        if config.ADMIN_ROLE_ID:
            admin_role = discord.utils.get(interaction.guild.roles, id=config.ADMIN_ROLE_ID)
        if not admin_role:
            admin_role = discord.utils.get(interaction.guild.roles, name=config.ADMIN_ROLE_NAME)
        if admin_role and admin_role in interaction.user.roles:
            return True
        await interaction.response.send_message(
            embed=embeds.error("Akses Ditolak", "Perintah ini hanya untuk admin."),
            ephemeral=True,
        )
        return False
    return app_commands.check(predicate)


class Admin(commands.Cog):
    """Perintah admin untuk mengelola toko."""

    payment = app_commands.Group(name="payment", description="[Admin] Kelola info pembayaran")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @payment.command(name="set")
    @is_admin()
    @app_commands.describe(method="Metode pembayaran: DANA, GoPay, SeaBank, QRIS", details="Nomor atau detail akun", owner="Atas nama (opsional)", qris_url="URL gambar QRIS (opsional)")
    async def payment_set(
        self,
        interaction: discord.Interaction,
        method: str,
        details: str | None = None,
        owner: str | None = None,
        qris_url: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        method_key = db.normalize_payment_method(method)
        await db.set_payment_method(method_key, details or "", owner or "", qris_url or "")
        await interaction.followup.send(embed=embeds.success("Updated", f"Payment method `{method_key}` diperbarui."), ephemeral=True)

    @payment.command(name="show")
    @is_admin()
    async def payment_show(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        methods = await db.get_all_payment_methods()
        if not methods:
            await interaction.followup.send(embed=embeds.warning("Kosong", "Belum ada metode pembayaran yang diset."), ephemeral=True)
            return
        lines = []
        for m in methods:
            line = f"**{m['method']}** — {m.get('details','-')} | {m.get('owner_name','-')}"
            if m.get('qris_url'):
                line += " | QRIS image: set"
            lines.append(line)
        e = embeds.info("Payment Methods", "\n".join(lines))
        await interaction.followup.send(embed=e, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # Parse vouch messages starting with +vouch
        if message.author.bot or not message.guild or not message.content:
            return

        content = message.content.strip()
        if not content.lower().startswith("+vouch "):
            return

        # Expected format: +vouch robux @handler 200 Robux via send|community
        match = re.match(
            r"^\+vouch\s+robux\s+<@!?(?P<handler_id>\d+)>\s+(?P<amount>\d+)\s+robux\s+via\s+(?P<via>send|community)\s*$",
            content,
            re.IGNORECASE,
        )
        if not match:
            return

        handler_id = match.group("handler_id")
        amt = int(match.group("amount"))
        via = match.group("via").lower()

        if not message.mentions:
            return
        handler = message.mentions[0]
        if str(handler.id) != handler_id:
            return

        ticket = await db.find_done_ticket_for_vouch(
            str(message.author.id), str(handler.id), amt, via
        )
        if not ticket:
            await message.channel.send(
                embed=embeds.error(
                    "Vouch Gagal",
                    "Tidak ditemukan transaksi Done yang cocok. Pastikan order sudah selesai dan format vouch benar.",
                ),
                delete_after=15,
            )
            return

        existing_vouch = await db.get_vouch_by_ticket(ticket["id"])
        if existing_vouch:
            await message.channel.send(
                embed=embeds.warning(
                    "Vouch Sudah Tercatat",
                    "Vouch untuk order ini sudah terdaftar sebelumnya.",
                ),
                delete_after=15,
            )
            return

        transaction_id = await db.get_transaction_id_for_ticket(ticket["id"])
        await db.create_vouch(
            ticket_id=ticket["id"],
            transaction_id=transaction_id,
            buyer_id=str(message.author.id),
            buyer_username=str(message.author),
            handler_id=str(handler.id),
            handler_username=str(handler),
            robux_amount=amt,
            total_idr=float(ticket.get("total_idr") or 0),
            payment_method=ticket.get("payment_method") or "",
            via=via,
        )

        # Kirim log vouch ke channel yang diset
        guild = message.guild
        target_chan = None
        if config.VOUCH_CHANNEL_ID:
            target_chan = guild.get_channel(config.VOUCH_CHANNEL_ID)
        if not target_chan:
            target_chan = discord.utils.get(guild.text_channels, name=config.VOUCH_CHANNEL_NAME)
        if not target_chan:
            target_chan = message.channel

        await target_chan.send(embed=embeds.vouch_log_embed(ticket))
        try:
            await message.add_reaction("✅")
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════════════════
    # Manajemen Produk
    # ═══════════════════════════════════════════════════════════════════════════

    @app_commands.command(
        name="tambah_produk",
        description="[Admin] Tambah produk Robux baru ke toko.",
    )
    @app_commands.describe(
        nama="Nama produk (contoh: Paket 1.000 Robux).",
        robux="Jumlah Robux yang diberikan.",
        harga="Harga dalam Rupiah (IDR).",
        deskripsi="Deskripsi singkat produk.",
        stok="Jumlah stok (-1 = unlimited).",
    )
    @is_admin()
    async def tambah_produk(
        self,
        interaction: Any,
        nama: str,
        robux: int,
        harga: float,
        deskripsi: str = "",
        stok: int = -1,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            robux = validate_robux_amount(robux)
            harga = validate_price(harga)
            stok = validate_stock(stok)
        except ValidationError as e:
            await interaction.followup.send(
                embed=embeds.error("Input Tidak Valid", str(e)), ephemeral=True
            )
            return

        product_id = await db.create_product(
            name=nama, description=deskripsi, robux_amount=robux, price_idr=harga, stock=stok
        )
        await db.log_activity(
            str(interaction.user.id), "CREATE_PRODUCT", f"#{product_id}", nama
        )
        product = await db.get_product(product_id)
        await interaction.followup.send(
            embed=embeds.success("Produk Ditambahkan!", f"ID produk baru: `#{product_id}`"),
            ephemeral=True,
        )
        if product:
            await interaction.followup.send(embed=embeds.product_card(product), ephemeral=True)

    # ── /edit_produk ──────────────────────────────────────────────────────────

    @app_commands.command(
        name="edit_produk",
        description="[Admin] Edit detail produk yang sudah ada.",
    )
    @app_commands.describe(
        id_produk="ID produk yang ingin diedit.",
        nama="Nama baru (kosongkan jika tidak diubah).",
        robux="Jumlah Robux baru.",
        harga="Harga IDR baru.",
        deskripsi="Deskripsi baru.",
        stok="Stok baru (-1 = unlimited).",
    )
    @is_admin()
    async def edit_produk(
        self,
        interaction: Any,
        id_produk: int,
        nama: Optional[str] = None,
        robux: Optional[int] = None,
        harga: Optional[float] = None,
        deskripsi: Optional[str] = None,
        stok: Optional[int] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        product = await db.get_product(id_produk)
        if not product:
            await interaction.followup.send(
                embed=embeds.error("Tidak Ditemukan", f"Produk `#{id_produk}` tidak ada."),
                ephemeral=True,
            )
            return

        updates: dict = {}
        try:
            if nama is not None:
                updates["name"] = nama
            if robux is not None:
                updates["robux_amount"] = validate_robux_amount(robux)
            if harga is not None:
                updates["price_idr"] = validate_price(harga)
            if deskripsi is not None:
                updates["description"] = deskripsi
            if stok is not None:
                updates["stock"] = validate_stock(stok)
        except ValidationError as e:
            await interaction.followup.send(
                embed=embeds.error("Input Tidak Valid", str(e)), ephemeral=True
            )
            return

        if not updates:
            await interaction.followup.send(
                embed=embeds.warning("Tidak Ada Perubahan", "Tidak ada field yang diubah."),
                ephemeral=True,
            )
            return

        await db.update_product(id_produk, **updates)
        await db.log_activity(
            str(interaction.user.id), "EDIT_PRODUCT", f"#{id_produk}", str(updates)
        )
        updated = await db.get_product(id_produk)
        await interaction.followup.send(
            embed=embeds.success("Produk Diperbarui", f"Produk `#{id_produk}` berhasil diupdate."),
            ephemeral=True,
        )
        if updated:
            await interaction.followup.send(embed=embeds.product_card(updated), ephemeral=True)

    # ── /hapus_produk ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="hapus_produk",
        description="[Admin] Nonaktifkan produk dari toko.",
    )
    @app_commands.describe(id_produk="ID produk yang ingin dihapus.")
    @is_admin()
    async def hapus_produk(self, interaction: Any, id_produk: int) -> None:
        await interaction.response.defer(ephemeral=True)
        product = await db.get_product(id_produk)
        if not product:
            await interaction.followup.send(
                embed=embeds.error("Tidak Ditemukan", f"Produk `#{id_produk}` tidak ada."),
                ephemeral=True,
            )
            return
        await db.delete_product(id_produk)
        await db.log_activity(
            str(interaction.user.id), "DELETE_PRODUCT", f"#{id_produk}", product["name"]
        )
        await interaction.followup.send(
            embed=embeds.success(
                "Produk Dinonaktifkan",
                f"**{product['name']}** telah dinonaktifkan dari toko.",
            ),
            ephemeral=True,
        )

    # ── /semua_produk ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="semua_produk",
        description="[Admin] Lihat semua produk termasuk yang nonaktif.",
    )
    @is_admin()
    async def semua_produk(self, interaction: Any) -> None:
        await interaction.response.defer(ephemeral=True)
        products = await db.get_all_products(active_only=False)
        embed = embeds.product_list(products)
        embed.title = "🔧 Semua Produk (Admin View)"
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # Manajemen Pesanan
    # ═══════════════════════════════════════════════════════════════════════════

    @app_commands.command(
        name="ubah_status",
        description="[Admin] Ubah status pesanan.",
    )
    @app_commands.describe(
        id_pesanan="ID pesanan yang akan diubah statusnya.",
        status="Status baru pesanan.",
    )
    @app_commands.choices(
        status=[
            app_commands.Choice(name="Pending 🕐", value="pending"),
            app_commands.Choice(name="Processing ⚙️", value="processing"),
            app_commands.Choice(name="Completed ✅", value="completed"),
            app_commands.Choice(name="Cancelled ❌", value="cancelled"),
            app_commands.Choice(name="Refunded ↩️", value="refunded"),
        ]
    )
    @is_admin()
    async def ubah_status(
        self,
        interaction: Any,
        id_pesanan: int,
        status: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        order = await db.get_order(id_pesanan)
        if not order:
            await interaction.followup.send(
                embed=embeds.error("Tidak Ditemukan", f"Pesanan `#{id_pesanan}` tidak ada."),
                ephemeral=True,
            )
            return

        old_status = order["status"]
        await db.update_order_status(id_pesanan, status)
        await db.log_activity(
            str(interaction.user.id),
            "UPDATE_ORDER_STATUS",
            f"#{id_pesanan}",
            f"{old_status} → {status}",
        )

        # Notifikasi ke pembeli via DM
        guild = interaction.guild
        if guild:
            try:
                buyer = await guild.fetch_member(int(order["user_id"]))
                dm_embed = embeds.order_detail(await db.get_order(id_pesanan) or order)
                dm_embed.title = f"📬 Update Pesanan #{id_pesanan}"
                dm_embed.description = f"Status pesananmu berubah dari **{old_status}** → **{status}**."
                await buyer.send(embed=dm_embed)
            except Exception:
                pass  # DM mungkin dinonaktifkan oleh user

        await interaction.followup.send(
            embed=embeds.success(
                "Status Diperbarui",
                f"Pesanan `#{id_pesanan}`: **{old_status}** → **{status}**",
            ),
            ephemeral=True,
        )

    # ── /daftar_order ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="daftar_order",
        description="[Admin] Lihat daftar pesanan dengan filter status.",
    )
    @app_commands.describe(status="Filter berdasarkan status (kosongkan untuk semua).")
    @app_commands.choices(
        status=[
            app_commands.Choice(name="Semua", value="all"),
            app_commands.Choice(name="Pending 🕐", value="pending"),
            app_commands.Choice(name="Processing ⚙️", value="processing"),
            app_commands.Choice(name="Completed ✅", value="completed"),
            app_commands.Choice(name="Cancelled ❌", value="cancelled"),
            app_commands.Choice(name="Refunded ↩️", value="refunded"),
        ]
    )
    @is_admin()
    async def daftar_order(
        self,
        interaction: Any,
        status: str = "all",
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        filter_status = None if status == "all" else status
        orders = await db.get_all_orders(status=filter_status, limit=25)
        title = "Daftar Pesanan" if not filter_status else f"Pesanan [{filter_status.capitalize()}]"
        await interaction.followup.send(
            embed=embeds.order_list(orders, title=title), ephemeral=True
        )

    @app_commands.command(
        name="riwayat_transaksi",
        description="[Admin] Lihat riwayat transaksi ticket/payment dengan filter status dan buyer.",
    )
    @app_commands.describe(
        status="Filter status transaksi.",
        buyer="Cari transaksi berdasarkan buyer mention atau nama.",
    )
    @app_commands.choices(
        status=[
            app_commands.Choice(name="Semua", value="all"),
            app_commands.Choice(name="Pending 🕐", value="pending"),
            app_commands.Choice(name="Waiting Payment", value="waiting_payment"),
            app_commands.Choice(name="Paid ✅", value="paid"),
            app_commands.Choice(name="Processing ⚙️", value="processing"),
            app_commands.Choice(name="Verified ✅", value="verified"),
            app_commands.Choice(name="Done ✅", value="done"),
            app_commands.Choice(name="Rejected ❌", value="rejected"),
            app_commands.Choice(name="Cancelled ❌", value="cancelled"),
        ]
    )
    @is_admin()
    async def riwayat_transaksi(
        self,
        interaction: Any,
        status: str = "all",
        buyer: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        transactions = await db.get_ticket_transactions(status=status, buyer_query=buyer, limit=25)
        title = "Riwayat Transaksi"
        if status and status != "all":
            title = f"Riwayat Transaksi [{status.replace('_', ' ').capitalize()}]"
        if buyer:
            title += f" — {buyer}"
        await interaction.followup.send(
            embed=embeds.ticket_transaction_list(transactions, title=title),
            ephemeral=True,
        )

    # ── /detail_order ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="detail_order",
        description="[Admin] Lihat detail lengkap satu pesanan.",
    )
    @app_commands.describe(id_pesanan="ID pesanan.")
    @is_admin()
    async def detail_order(self, interaction: Any, id_pesanan: int) -> None:
        await interaction.response.defer(ephemeral=True)
        order = await db.get_order(id_pesanan)
        if not order:
            await interaction.followup.send(
                embed=embeds.error("Tidak Ditemukan", f"Pesanan `#{id_pesanan}` tidak ada."),
                ephemeral=True,
            )
            return
        await interaction.followup.send(embed=embeds.order_detail(order), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
