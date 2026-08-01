"""
Entry point Discord Robux Store Bot.
Jalankan dengan: python main.py
"""

from __future__ import annotations

import asyncio
import os
import discord
from discord.ext import commands

import config
import admin as admin_module
import orders as orders_module
import store as store_module
import tickets as tickets_module
import embeds
from database import init_db

# ── Daftar modul cog yang akan dimuat ────────────────────────────────────────
COG_MODULES = [
    admin_module,
    orders_module,
    store_module,
    tickets_module,
]


class RobuxStoreBot(commands.Bot):
    """Subclass Bot utama dengan setup lifecycle."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix=config.COMMAND_PREFIX,
            intents=intents,
            help_command=None,  # nonaktifkan help bawaan; gunakan /help sendiri
        )

    async def setup_hook(self) -> None:
        """Dipanggil sekali saat bot login — muat cog + sync slash commands."""
        # Inisialisasi database
        await init_db()
        print("[DB] Database siap.")

        # Muat semua cog dari modul lokal
        for module in COG_MODULES:
            try:
                await module.setup(self)
                print(f"[COG] ✅ {module.__name__} dimuat.")
            except Exception as exc:
                print(f"[COG] ❌ Gagal memuat {module.__name__}: {exc}")

        # Sync slash commands ke guild tertentu (cepat) atau global (lambat ~1 jam)
        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"[SYNC] {len(synced)} slash command disync ke guild {config.GUILD_ID}.")
        else:
            synced = await self.tree.sync()
            print(f"[SYNC] {len(synced)} slash command disync secara global.")

    async def on_ready(self) -> None:
        print(f"\n{'='*50}")
        print(f"  🤖 {self.user} telah online!")
        print(f"  🏪 {config.STORE_NAME}")
        print(f"  📡 Terhubung ke {len(self.guilds)} server")
        print(f"{'='*50}\n")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{config.STORE_NAME} | /produk",
            )
        )

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        """Tangani error slash command secara global."""
        from discord import app_commands

        if isinstance(error, app_commands.CheckFailure):
            # Pesan error sudah dikirim di dalam predicate; abaikan
            return

        msg = str(error)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                embed=embeds.error("Terjadi Kesalahan", msg), ephemeral=True
            )
        else:
            await interaction.followup.send(
                embed=embeds.error("Terjadi Kesalahan", msg), ephemeral=True
            )
        print(f"[ERROR] {interaction.command} — {error}")


async def main() -> None:
    config.validate_config()
    bot = RobuxStoreBot()
    async with bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[BOT] Bot dihentikan.")
