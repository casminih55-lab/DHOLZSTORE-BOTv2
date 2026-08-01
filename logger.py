"""Central logging helpers used across COGs.

Provides functions to send logs to configured guild channels (via settings through DB)
and fallback to console if channels not configured.
"""
from __future__ import annotations

import traceback
from typing import Optional

import discord

import database as db
import config


async def _resolve_channel(guild: discord.Guild, key: str) -> Optional[discord.TextChannel]:
    """Fetch channel by setting key (e.g., 'log_error') or fallback to config names."""
    if not guild:
        return None
    try:
        # First check DB settings
        raw = await db.get_setting(key)
        if raw:
            try:
                cid = int(raw)
                chan = guild.get_channel(cid)
                if chan:
                    return chan
            except Exception:
                pass
    except Exception:
        pass

    # Fallbacks for common keys
    if key == "log_error":
        if config.TICKET_LOG_CHANNEL_ID:
            return guild.get_channel(config.TICKET_LOG_CHANNEL_ID)
        return discord.utils.get(guild.text_channels, name="error-log")
    if key == "log_order":
        if config.ORDER_LOG_CHANNEL_ID:
            return guild.get_channel(config.ORDER_LOG_CHANNEL_ID)
        return discord.utils.get(guild.text_channels, name=config.ORDER_LOG_CHANNEL_NAME)
    if key == "log_vouch":
        if config.VOUCH_CHANNEL_ID:
            return guild.get_channel(config.VOUCH_CHANNEL_ID)
        return discord.utils.get(guild.text_channels, name=config.VOUCH_CHANNEL_NAME)
    # generic fallback
    return None


async def send_log(guild: discord.Guild, log_type: str, content: Optional[str] = None, embed: Optional[discord.Embed] = None, file: Optional[discord.File] = None) -> None:
    """Send a log message to the configured channel for log_type.

    log_type examples: 'error', 'order', 'vouch', 'payment', 'admin'
    """
    key = f"log_{log_type}"
    chan = await _resolve_channel(guild, key)
    if not chan:
        # fallback to console
        if embed:
            print("[LOG]", log_type, embed.title if embed.title else "")
            return
        if content:
            print(f"[LOG:{log_type}] {content}")
            return
        return

    try:
        if file and embed:
            await chan.send(content=content or "", embed=embed, file=file)
        elif file:
            await chan.send(content=content or "", file=file)
        elif embed:
            await chan.send(embed=embed)
        else:
            await chan.send(content or "")
    except Exception:
        # Best-effort only
        print("[LOG] Failed to send log to channel", chan.id)


async def send_error(guild: discord.Guild, context: str, exc: Exception) -> None:
    tb = traceback.format_exc()
    title = f"Error in {context}"
    e = discord.Embed(title=title, description=f"{exc}", color=config.COLOR_ERROR)
    e.add_field(name="Traceback", value=(tb[:1024] if tb else "-"), inline=False)
    await send_log(guild, "error", embed=e)
