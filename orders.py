"""
Cog: Orders — perintah untuk mengecek dan mengelola pesanan.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import database as db
import embeds


class Orders(commands.Cog):
    """Perintah pesanan yang bisa digunakan semua member."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /cek_order ────────────────────────────────────────────────────────────

    @app_commands.command(
        name="cek_order",
        description="Cek status pesanan berdasarkan ID pesanan.",
    )
    @app_commands.describe(id_pesanan="ID pesanan yang ingin dicek.")
    async def cek_order(self, interaction: discord.Interaction, id_pesanan: int) -> None:
        await interaction.response.defer(ephemeral=True)
        order = await db.get_order(id_pesanan)

        if not order:
            await interaction.followup.send(
                embed=embeds.error(
                    "Pesanan Tidak Ditemukan",
                    f"Tidak ada pesanan dengan ID `#{id_pesanan}`.",
                ),
                ephemeral=True,
            )
            return

        # User hanya boleh lihat pesanannya sendiri (kecuali admin)
        is_own_order = order["user_id"] == str(interaction.user.id)
        is_admin = await _is_admin(interaction)

        if not is_own_order and not is_admin:
            await interaction.followup.send(
                embed=embeds.error("Akses Ditolak", "Kamu hanya bisa melihat pesananmu sendiri."),
                ephemeral=True,
            )
            return

        await interaction.followup.send(embed=embeds.order_detail(order), ephemeral=True)

    # ── /riwayat_order ────────────────────────────────────────────────────────

    @app_commands.command(
        name="riwayat_order",
        description="Lihat 10 pesanan terakhirmu.",
    )
    async def riwayat_order(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        orders = await db.get_user_orders(str(interaction.user.id), limit=10)
        embed = embeds.order_list(orders, title=f"Riwayat Pesanan — {interaction.user.display_name}")
        await interaction.followup.send(embed=embed, ephemeral=True)


# ── Helper ────────────────────────────────────────────────────────────────────

async def _is_admin(interaction: discord.Interaction) -> bool:
    """Periksa apakah user memiliki role admin atau izin administrator."""
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    if interaction.user.guild_permissions.administrator:
        return True
    import config
    # Prefer ADMIN_ROLE_ID if provided
    admin_role = None
    if config.ADMIN_ROLE_ID:
        admin_role = discord.utils.get(interaction.guild.roles, id=config.ADMIN_ROLE_ID)
    if not admin_role:
        admin_role = discord.utils.get(interaction.guild.roles, name=config.ADMIN_ROLE_NAME)
    return admin_role in interaction.user.roles if admin_role else False


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Orders(bot))
