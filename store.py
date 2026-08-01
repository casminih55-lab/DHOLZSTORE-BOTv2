"""
Cog: Store — perintah untuk melihat produk dan membuat pesanan.
Perintah slash (app_commands) digunakan agar tampil lebih rapi di Discord.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
import embeds
from validators import (
    ValidationError,
    validate_quantity,
    validate_roblox_username,
)


class Store(commands.Cog):
    """Perintah toko yang bisa digunakan semua member."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /produk ───────────────────────────────────────────────────────────────

    @app_commands.command(name="produk", description="Lihat semua produk Robux yang tersedia.")
    async def produk(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        products = await db.get_all_products(active_only=True)
        embed = embeds.product_list(products)
        await interaction.followup.send(embed=embed)

    # ── /detail_produk ────────────────────────────────────────────────────────

    @app_commands.command(
        name="detail_produk",
        description="Lihat detail satu produk berdasarkan ID.",
    )
    @app_commands.describe(id_produk="ID produk yang ingin dilihat detailnya.")
    async def detail_produk(self, interaction: discord.Interaction, id_produk: int) -> None:
        await interaction.response.defer()
        product = await db.get_product(id_produk)
        if not product or not product["is_active"]:
            await interaction.followup.send(
                embed=embeds.error("Produk Tidak Ditemukan", f"Produk dengan ID `{id_produk}` tidak ada."),
                ephemeral=True,
            )
            return
        await interaction.followup.send(embed=embeds.product_card(product))

    # ── /beli ─────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="beli",
        description="Buat pesanan Robux.",
    )
    @app_commands.describe(
        id_produk="ID produk yang ingin dibeli.",
        username_roblox="Username akun Roblox kamu.",
        jumlah="Jumlah yang ingin dibeli (default: 1).",
        catatan="Catatan tambahan untuk admin (opsional).",
    )
    async def beli(
        self,
        interaction: discord.Interaction,
        id_produk: int,
        username_roblox: str,
        jumlah: int = 1,
        catatan: str = "",
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        # Validasi input
        try:
            jumlah = validate_quantity(jumlah)
            username_roblox = validate_roblox_username(username_roblox)
        except ValidationError as e:
            await interaction.followup.send(
                embed=embeds.error("Input Tidak Valid", str(e)), ephemeral=True
            )
            return

        # Ambil produk
        product = await db.get_product(id_produk)
        if not product or not product["is_active"]:
            await interaction.followup.send(
                embed=embeds.error(
                    "Produk Tidak Ditemukan",
                    f"Produk dengan ID `{id_produk}` tidak tersedia.",
                ),
                ephemeral=True,
            )
            return

        # Cek stok
        if product["stock"] != -1 and product["stock"] < jumlah:
            await interaction.followup.send(
                embed=embeds.error(
                    "Stok Tidak Cukup",
                    f"Stok tersedia: **{product['stock']}**, kamu memesan **{jumlah}**.",
                ),
                ephemeral=True,
            )
            return

        total_idr = product["price_idr"] * jumlah
        robux_total = product["robux_amount"] * jumlah

        # Simpan pesanan
        order_id = await db.create_order(
            user_id=str(interaction.user.id),
            username=str(interaction.user),
            product_id=product["id"],
            quantity=jumlah,
            total_idr=total_idr,
            robux_total=robux_total,
            roblox_username=username_roblox,
            notes=catatan,
        )

        embed = embeds.order_confirmation(
            order_id=order_id,
            product=product,
            quantity=jumlah,
            total_idr=total_idr,
            roblox_username=username_roblox,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        # Notifikasi ke channel log admin jika dikonfigurasi
        await self._notify_admins(interaction, order_id, product, robux_total, total_idr, username_roblox)

    async def _notify_admins(
        self,
        interaction: discord.Interaction,
        order_id: int,
        product: dict,
        robux_total: int,
        total_idr: float,
        roblox_username: str,
    ) -> None:
        """Kirim notifikasi pesanan baru ke channel bernama 'order-log' jika ada."""
        if not interaction.guild:
            return
        # Prefer configured ORDER_LOG_CHANNEL_ID, then name
        log_channel = None
        if config.ORDER_LOG_CHANNEL_ID:
            try:
                log_channel = interaction.guild.get_channel(config.ORDER_LOG_CHANNEL_ID)
            except Exception:
                log_channel = None
        if not log_channel:
            log_channel = discord.utils.get(interaction.guild.text_channels, name=config.ORDER_LOG_CHANNEL_NAME)
        if not log_channel:
            return
        embed = embeds.info(
            title=f"📥 Pesanan Baru #{order_id}",
            description=(
                f"**Pembeli:** {interaction.user.mention}\n"
                f"**Produk:** {product['name']}\n"
                f"**Robux:** {robux_total:,}\n"
                f"**Total:** Rp {total_idr:,.0f}\n"
                f"**Akun Roblox:** `{roblox_username}`"
            ),
        )
        await log_channel.send(embed=embed)  # type: ignore[union-attr]


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Store(bot))
