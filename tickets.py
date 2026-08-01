"""
Cog: Tickets — Sistem ticket pembelian Robux.

Alur:
  1. Admin kirim panel → /ticket_panel
  2. Buyer klik 🟦 Via Send / 🟩 Via Community
  3. Modal muncul: Username Roblox + Jumlah Robux
  4. Validasi → cek maks 3 aktif → buat ticket + channel private
  5. Channel berisi embed info + tombol Claim / Close
  6. Admin klik Claim → nama handler tampil di embed
  7. Admin / Buyer klik Close → channel terhapus otomatis
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands

import config
import database as db
import embeds
from validators import ValidationError, validate_roblox_username
# gunakan modul database yang telah diimport sebagai `db`


# ═══════════════════════════════════════════════════════════════════════════════
# MODAL — isian data dari buyer
# ═══════════════════════════════════════════════════════════════════════════════

class TicketModal(discord.ui.Modal):
    """Form yang muncul setelah buyer memilih metode."""

    roblox_username: discord.ui.TextInput = discord.ui.TextInput(
        label="Username Roblox",
        placeholder="Contoh: PlayerRoblox123",
        min_length=3,
        max_length=20,
        required=True,
    )
    robux_amount: discord.ui.TextInput = discord.ui.TextInput(
        label="Jumlah Robux",
        placeholder="Masukkan jumlah Robux (angka saja)",
        min_length=1,
        max_length=7,
        required=True,
    )

    def __init__(self, ticket_type: str) -> None:
        if ticket_type == config.TICKET_TYPE_COMMUNITY:
            title = "🟩 Buat Ticket — Via Community"
        else:
            title = "🟦 Buat Ticket — Via Send"
        super().__init__(title=title)
        self.ticket_type = ticket_type
        if ticket_type == config.TICKET_TYPE_COMMUNITY:
            # Override placeholder setelah super().__init__
            self.robux_amount.placeholder = f"Minimal {config.MIN_ROBUX_COMMUNITY:,} Robux"

    # ── Validasi & pembuatan ticket ───────────────────────────────────────────

    async def on_submit(self, interaction: discord.Interaction) -> None:  # noqa: C901
        await interaction.response.defer(ephemeral=True)

        # ── 1. Validasi Username Roblox ───────────────────────────────────────
        try:
            roblox_user = validate_roblox_username(str(self.roblox_username))
        except ValidationError as e:
            await interaction.followup.send(
                embed=embeds.error("Username Tidak Valid", str(e)), ephemeral=True
            )
            return

        # ── 2. Validasi Jumlah Robux ──────────────────────────────────────────
        raw = str(self.robux_amount).strip().replace(",", "").replace(".", "")
        if not raw.isdigit():
            await interaction.followup.send(
                embed=embeds.error(
                    "Jumlah Tidak Valid",
                    "Masukkan **angka** yang valid untuk jumlah Robux (tanpa simbol).",
                ),
                ephemeral=True,
            )
            return

        robux = int(raw)
        if robux <= 0:
            await interaction.followup.send(
                embed=embeds.error("Jumlah Tidak Valid", "Jumlah Robux harus lebih dari 0."),
                ephemeral=True,
            )
            return

        if self.ticket_type == config.TICKET_TYPE_COMMUNITY and robux < config.MIN_ROBUX_COMMUNITY:
            await interaction.followup.send(
                embed=embeds.error(
                    "Jumlah Kurang",
                    f"Via **Community** minimal **{config.MIN_ROBUX_COMMUNITY:,} Robux**.\n"
                    f"Kamu memasukkan **{robux:,} Robux**.",
                ),
                ephemeral=True,
            )
            return

        # ── 3. Cek batas maks ticket aktif ───────────────────────────────────
        active_count = await db.count_active_tickets(str(interaction.user.id))
        if active_count >= config.MAX_ACTIVE_TICKETS:
            await interaction.followup.send(
                embed=embeds.error(
                    "Batas Ticket Tercapai",
                    f"Kamu sudah punya **{active_count} ticket aktif** "
                    f"(maksimal {config.MAX_ACTIVE_TICKETS}).\n"
                    "Tunggu hingga ticket lama selesai sebelum membuat yang baru.",
                ),
                ephemeral=True,
            )
            return

        # ── 4. Buat ticket di database ────────────────────────────────────────
        ticket_id = await db.create_ticket(
            user_id=str(interaction.user.id),
            username=str(interaction.user),
            roblox_username=roblox_user,
            robux_amount=robux,
            ticket_type=self.ticket_type,
        )
        order_code = f"RS-{ticket_id:04d}"
        await db.set_ticket_order_code(ticket_id, order_code)

        # Jika ada produk yang cocok dengan jumlah robux, simpan referensi produk dan harga ke ticket
        try:
            products = await db.get_all_products()
            matched = None
            for p in products:
                if int(p.get("robux_amount", 0)) == robux:
                    matched = p
                    break
            if matched:
                await db.set_ticket_product(ticket_id, matched["id"], matched["name"], matched["price_idr"])
        except Exception:
            pass

        # ── 5. Buat channel private ───────────────────────────────────────────
        guild = interaction.guild
        if not guild:
            await interaction.followup.send(
                embed=embeds.error("Error", "Tidak dapat menemukan server."),
                ephemeral=True,
            )
            return

        # Prefer configured category ID, lalu fallback ke nama category lama
        category = None
        if config.TICKET_CATEGORY_ID:
            try:
                channel = guild.get_channel(config.TICKET_CATEGORY_ID)
            except Exception:
                channel = None
            if channel and isinstance(channel, discord.CategoryChannel):
                category = channel

        if not category:
            category = discord.utils.get(guild.categories, name=config.TICKET_CATEGORY_NAME)
        if not category:
            try:
                category = await guild.create_category(
                    config.TICKET_CATEGORY_NAME,
                    reason="Auto-created oleh Ticket System",
                )
            except discord.Forbidden:
                await interaction.followup.send(
                    embed=embeds.error(
                        "Permission Error",
                        "Bot tidak punya izin membuat category. Hubungi admin server.",
                    ),
                    ephemeral=True,
                )
                return

        # Permission overwrites — channel hanya visible untuk buyer + admin
        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            ),
        }
        # Prefer ADMIN_ROLE_ID if defined, else fallback to name
        admin_role = None
        if config.ADMIN_ROLE_ID:
            admin_role = discord.utils.get(guild.roles, id=config.ADMIN_ROLE_ID)
        if not admin_role:
            admin_role = discord.utils.get(guild.roles, name=config.ADMIN_ROLE_NAME)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
            )
        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
                read_message_history=True,
            )

        channel_name = f"ticket-{order_code.lower()}"   # ticket-rs-0001
        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=(
                    f"Ticket {order_code} | {interaction.user} | "
                    f"Roblox: {roblox_user} | {robux:,} Robux"
                ),
                reason=f"Ticket {order_code} dibuat oleh {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                embed=embeds.error(
                    "Permission Error",
                    "Bot tidak punya izin membuat text channel. Hubungi admin server.",
                ),
                ephemeral=True,
            )
            return

        # ── 6. Kirim embed info + tombol ke channel ───────────────────────────
        ticket_data: dict = {
            "id": ticket_id,
            "order_code": order_code,
            "user_id": str(interaction.user.id),
            "username": str(interaction.user),
            "roblox_username": roblox_user,
            "robux_amount": robux,
            "ticket_type": self.ticket_type,
            "status": config.TICKET_STATUS_OPEN,
            "handler_username": None,
            "created_at": "baru saja",
        }
        controls_view = TicketControlsView(ticket_id)
        ticket_embed = embeds.ticket_info(ticket_data, interaction.user)

        msg = await channel.send(
            content=f"✉️ {interaction.user.mention} — ticket kamu sudah dibuat!",
            embed=ticket_embed,
            view=controls_view,
        )

        # ── 7. Simpan channel_id + message_id ke DB ───────────────────────────
        await db.update_ticket_channel(ticket_id, str(channel.id), str(msg.id))

        # Kirim log ticket ke channel log jika tersedia (prioritas ID, fallback ke order log)
        ticket_log_channel = None
        if interaction.guild:
            if config.TICKET_LOG_CHANNEL_ID:
                try:
                    ticket_log_channel = interaction.guild.get_channel(config.TICKET_LOG_CHANNEL_ID)
                except Exception:
                    ticket_log_channel = None
            if not ticket_log_channel and config.ORDER_LOG_CHANNEL_ID:
                try:
                    ticket_log_channel = interaction.guild.get_channel(config.ORDER_LOG_CHANNEL_ID)
                except Exception:
                    ticket_log_channel = None
            if not ticket_log_channel:
                ticket_log_channel = discord.utils.get(
                    interaction.guild.text_channels,
                    name=config.ORDER_LOG_CHANNEL_NAME,
                )

        if (
            ticket_log_channel
            and interaction.guild
            and ticket_log_channel.permissions_for(interaction.guild.me).send_messages
        ):
            try:
                await ticket_log_channel.send(
                    embed=embeds.info(
                        "Ticket Baru",
                        f"Ticket **{order_code}** dibuat oleh {interaction.user.mention}.\n"
                        f"**Roblox:** {roblox_user}\n"
                        f"**Robux:** {robux:,}",
                    )
                )
            except Exception:
                pass

        # Register view untuk persistency antar restart
        interaction.client.add_view(controls_view, message_id=msg.id)

        # ── 8. Konfirmasi ephemeral ke buyer ──────────────────────────────────
        await interaction.followup.send(
            embed=embeds.success(
                "Ticket Berhasil Dibuat!",
                f"**Nomor Order:** `{order_code}`\n"
                f"**Channel:** {channel.mention}\n\n"
                "Tim kami akan segera menangani ticket kamu.",
            ),
            ephemeral=True,
        )


class PaymentProofModal(discord.ui.Modal):
    """Modal untuk upload bukti pembayaran oleh buyer."""

    proof: discord.ui.FileUpload = discord.ui.FileUpload(
        custom_id="payment_proof", required=True, max_values=1
    )
    notes: discord.ui.TextInput = discord.ui.TextInput(
        label="Catatan Pembayaran (opsional)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=200,
    )

    def __init__(self, ticket_id: int) -> None:
        super().__init__(title="Unggah Bukti Pembayaran")
        self.ticket_id = ticket_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        ticket = await db.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.followup.send(embed=embeds.error("Error", "Ticket tidak ditemukan."), ephemeral=True)
            return

        if ticket["user_id"] != str(interaction.user.id):
            await interaction.followup.send(embed=embeds.error("Akses Ditolak", "Hanya pembeli yang bisa mengunggah bukti pembayaran."), ephemeral=True)
            return

        attachments = self.proof.values
        if not attachments:
            await interaction.followup.send(embed=embeds.error("Error", "Tidak ada file bukti pembayaran yang diunggah."), ephemeral=True)
            return

        attachment = attachments[0]
        try:
            proof_file = await attachment.to_file()
        except Exception:
            await interaction.followup.send(embed=embeds.error("Error", "Gagal membaca file bukti pembayaran."), ephemeral=True)
            return

        notes = self.notes.value.strip() if self.notes.value else ""
        proof_status = "Pending"

        # Kirim notifikasi bukti pembayaran ke ticket channel dan channel order-log
        proof_embed = embeds.payment_proof_notification(ticket, interaction.user, notes, proof_status)
        ticket_channel = None
        if ticket.get("channel_id") and interaction.guild:
            try:
                ticket_channel = interaction.guild.get_channel(int(ticket["channel_id"]))
            except Exception:
                ticket_channel = None

        if ticket_channel and ticket_channel.permissions_for(interaction.guild.me).send_messages:
            # Kirim bukti dan pasang admin action view
            admin_view = AdminPaymentActionView(self.ticket_id)
            await ticket_channel.send(embed=proof_embed, file=proof_file, view=admin_view)

        order_log = None
        if interaction.guild:
            # Prefer configured ORDER_LOG_CHANNEL_ID, else fallback to name
            if config.ORDER_LOG_CHANNEL_ID:
                try:
                    order_log = interaction.guild.get_channel(config.ORDER_LOG_CHANNEL_ID)
                except Exception:
                    order_log = None
            if not order_log:
                order_log = discord.utils.get(interaction.guild.text_channels, name=config.ORDER_LOG_CHANNEL_NAME)
        if order_log and order_log.permissions_for(interaction.guild.me).send_messages:
            try:
                proof_file2 = await attachment.to_file()
                admin_view2 = AdminPaymentActionView(self.ticket_id)
                await order_log.send(embed=proof_embed, file=proof_file2, view=admin_view2)
            except Exception:
                pass

        # Simpan URL bukti & set status PAID
        try:
            await db.set_ticket_proof(self.ticket_id, attachment.url)
            await db.set_ticket_order_status(self.ticket_id, config.TICKET_ORDER_STATUS_PAID)
        except Exception:
            pass

        await interaction.followup.send(
            embed=embeds.success("Bukti Dikirim", "Bukti pembayaran berhasil dikirim. Tunggu verifikasi admin."),
            ephemeral=True,
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                embed=embeds.error("Terjadi Kesalahan", str(error)), ephemeral=True
            )


# ═══════════════════════════════════════════════════════════════════════════════
# BUTTONS — Claim & Close
# ═══════════════════════════════════════════════════════════════════════════════

class ClaimButton(discord.ui.Button):
    """Tombol Claim Ticket — hanya untuk admin."""

    def __init__(self, ticket_id: int) -> None:
        super().__init__(
            label="Claim Ticket",
            style=discord.ButtonStyle.primary,
            emoji="🙋",
            custom_id=f"ticket_claim:{ticket_id}",
        )
        self.ticket_id = ticket_id

    async def callback(self, interaction: discord.Interaction) -> None:
        # Hanya admin
        if not await _check_admin(interaction):
            await interaction.response.send_message(
                embed=embeds.error("Akses Ditolak", "Hanya **admin** yang bisa claim ticket."),
                ephemeral=True,
            )
            return

        ticket = await db.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message(
                embed=embeds.error("Error", "Data ticket tidak ditemukan."), ephemeral=True
            )
            return

        if ticket["status"] == config.TICKET_STATUS_CLAIMED:
            await interaction.response.send_message(
                embed=embeds.warning(
                    "Sudah Diklaim",
                    f"Ticket ini sudah diklaim oleh **{ticket['handler_username']}**.",
                ),
                ephemeral=True,
            )
            return

        if ticket["status"] == config.TICKET_STATUS_CLOSED:
            await interaction.response.send_message(
                embed=embeds.error("Ticket Ditutup", "Ticket ini sudah ditutup."), ephemeral=True
            )
            return

        # Update DB — catat handler
        handler_name = str(interaction.user)
        await db.claim_ticket(self.ticket_id, str(interaction.user.id), handler_name)

        # Rebuild ticket data untuk embed
        updated = await db.get_ticket(self.ticket_id)
        if not updated:
            return

        # Coba ambil member object buyer
        guild = interaction.guild
        buyer = None
        if guild and updated.get("user_id"):
            try:
                buyer = await guild.fetch_member(int(updated["user_id"]))
            except Exception:
                pass

        new_embed = embeds.ticket_info(updated, buyer)

        # Ganti view: Claim tombol disabled (tampilkan nama handler), Close tetap aktif
        new_view = TicketClaimedView(self.ticket_id, handler_name)

        await interaction.response.edit_message(embed=new_embed, view=new_view)

        # Notifikasi di channel
        if interaction.channel:
            await interaction.channel.send(
                embed=embeds.info(
                    "Ticket Diklaim",
                    f"{interaction.user.mention} sedang menangani ticket ini.\n"
                    f"**Handler:** {handler_name}",
                )
            )


class CloseButton(discord.ui.Button):
    """Tombol Close Ticket — admin atau pemilik ticket."""

    def __init__(self, ticket_id: int) -> None:
        super().__init__(
            label="Close Ticket",
            style=discord.ButtonStyle.danger,
            emoji="🔒",
            custom_id=f"ticket_close:{ticket_id}",
        )
        self.ticket_id = ticket_id

    async def callback(self, interaction: discord.Interaction) -> None:
        ticket = await db.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message(
                embed=embeds.error("Error", "Data ticket tidak ditemukan."), ephemeral=True
            )
            return

        if ticket["status"] == config.TICKET_STATUS_CLOSED:
            await interaction.response.send_message(
                embed=embeds.error("Ticket Ditutup", "Ticket ini sudah ditutup."),
                ephemeral=True,
            )
            return

        # Cek izin: admin ATAU pemilik ticket
        is_admin = await _check_admin(interaction)
        is_owner = ticket["user_id"] == str(interaction.user.id)
        if not is_admin and not is_owner:
            await interaction.response.send_message(
                embed=embeds.error(
                    "Akses Ditolak",
                    "Hanya **admin** atau **pemilik ticket** yang bisa menutup ticket.",
                ),
                ephemeral=True,
            )
            return

        # Update DB
        await db.close_ticket(self.ticket_id)

        # Buat transcript sebelum menghapus channel
        try:
            ticket = await db.get_ticket(self.ticket_id)
            if ticket:
                import os
                os.makedirs(config.TRANSCRIPTS_FOLDER, exist_ok=True)
                order_code = ticket.get("order_code") or f"RS-{self.ticket_id:04d}"
                filename = f"{order_code}.txt"
                path = os.path.join(config.TRANSCRIPTS_FOLDER, filename)
                # Hitung harga jika belum ada
                total = ticket.get("total_idr")
                if not total:
                    robux = int(ticket.get("robux_amount", 0))
                    rate = config.PRICE_PER_ROBUX_COMMUNITY if ticket.get("ticket_type")==config.TICKET_TYPE_COMMUNITY else config.PRICE_PER_ROBUX_SEND
                    total = robux * rate

                lines = [
                    f"Nomor Order: {order_code}",
                    f"Buyer: {ticket.get('username','-')}",
                    f"Handler: {ticket.get('handler_username','-')}",
                    f"Username Roblox: {ticket.get('roblox_username','-')}",
                    f"Jumlah Robux: {ticket.get('robux_amount',0)}",
                    f"Metode: {ticket.get('ticket_type','-')}",
                    f"Harga: Rp {float(total):,.0f}",
                    f"Metode Pembayaran: {ticket.get('payment_method','-')}",
                    f"Waktu Dibuat: {ticket.get('created_at','-')}",
                    f"Waktu Selesai: {ticket.get('closed_at') or datetime.utcnow()}",
                ]
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                # Upload transcript ke channel sebelum dihapus
                try:
                    if interaction.channel:
                        await interaction.channel.send(content="Transcript tiket:", file=discord.File(path))
                except Exception:
                    pass
        except Exception:
            pass

        # Kirim pesan penutupan, lalu hapus channel setelah 5 detik
        await interaction.response.send_message(
            embed=embeds.info(
                "Menutup Ticket",
                f"Ticket **{ticket.get('order_code', '')}** ditutup oleh {interaction.user.mention}.\n"
                "Channel akan terhapus dalam **5 detik**...",
            )
        )

        await asyncio.sleep(5)
        if interaction.channel:
            try:
                await interaction.channel.delete(
                    reason=f"Ticket {ticket.get('order_code','')} ditutup oleh {interaction.user}"
                )
            except discord.Forbidden:
                pass
            except discord.HTTPException:
                pass


class PaymentButton(discord.ui.Button):
    """Tombol Payment — buka opsi pembayaran untuk buyer."""

    def __init__(self, ticket_id: int) -> None:
        super().__init__(
            label="Payment",
            style=discord.ButtonStyle.secondary,
            emoji="💳",
            custom_id=f"ticket_payment:{ticket_id}",
        )
        self.ticket_id = ticket_id

    async def callback(self, interaction: discord.Interaction) -> None:
        ticket = await db.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message(
                embed=embeds.error("Error", "Data ticket tidak ditemukan."), ephemeral=True
            )
            return

        # Hanya buyer atau admin dapat memulai pembayaran
        is_admin = await _check_admin(interaction)
        is_owner = ticket["user_id"] == str(interaction.user.id)
        if not is_admin and not is_owner:
            await interaction.response.send_message(
                embed=embeds.error("Akses Ditolak", "Hanya pembeli atau admin yang bisa melihat opsi pembayaran."),
                ephemeral=True,
            )
            return

        view = PaymentOptionsView(self.ticket_id)
        await interaction.response.send_message(embed=embeds.info("Pilih Metode Pembayaran", "Pilih salah satu metode pembayaran berikut."), view=view, ephemeral=True)


class PaymentOptionsView(discord.ui.View):
    """Pilihan metode pembayaran."""

    def __init__(self, ticket_id: int) -> None:
        super().__init__(timeout=120)
        self.ticket_id = ticket_id

    @discord.ui.button(label="DANA", style=discord.ButtonStyle.gray, emoji="💰", custom_id="pay_dana")
    async def dana(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await _handle_payment_choice(interaction, self.ticket_id, "DANA")

    @discord.ui.button(label="SeaBank", style=discord.ButtonStyle.gray, emoji="🏦", custom_id="pay_seabank")
    async def seabank(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await _handle_payment_choice(interaction, self.ticket_id, "SeaBank")

    @discord.ui.button(label="GoPay", style=discord.ButtonStyle.gray, emoji="🟢", custom_id="pay_gopay")
    async def gopay(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await _handle_payment_choice(interaction, self.ticket_id, "GoPay")

    @discord.ui.button(label="QRIS", style=discord.ButtonStyle.gray, emoji="📱", custom_id="pay_qris")
    async def qris(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await _handle_payment_choice(interaction, self.ticket_id, "QRIS")


async def _handle_payment_choice(interaction: discord.Interaction, ticket_id: int, method: str) -> None:
    """Proses ketika buyer memilih metode pembayaran: hitung total, simpan, kirim embed instruksi."""
    await interaction.response.defer()
    ticket = await db.get_ticket(ticket_id)
    if not ticket:
        await interaction.followup.send(embed=embeds.error("Error", "Ticket tidak ditemukan."), ephemeral=True)
        return

    # Hitung harga otomatis berdasarkan tipe ticket
    robux = int(ticket.get("robux_amount", 0))
    if ticket.get("ticket_type") == config.TICKET_TYPE_COMMUNITY:
        rate = config.PRICE_PER_ROBUX_COMMUNITY
    else:
        rate = config.PRICE_PER_ROBUX_SEND
    total = robux * rate

    # Simpan info payment ke DB
    await db.set_ticket_payment(ticket_id, method, total, config.TICKET_ORDER_STATUS_WAITING)

    # Ambil kembali ticket terbaru
    updated = await db.get_ticket(ticket_id)
    # Ambil data payment dari DB untuk tampilan
    pinfo = await db.get_payment_method(method)
    display_ticket = dict(updated) if updated else {}
    if pinfo:
        display_ticket["payment_info"] = pinfo
    else:
        display_ticket["payment_info"] = {"method": method, "details": "-"}

    # Jika QRIS dan payment record berisi qris_url, siapkan file/url flag
    attach_qris = False
    if method.lower() == "qris" and display_ticket.get("payment_info", {}).get("qris_url"):
        # embed will use image URL directly
        attach_qris = False

    # Kirim embed payment ke channel ticket
    channel = None
    if interaction.channel and interaction.channel.permissions_for(interaction.guild.me).send_messages:
        channel = interaction.channel
    else:
        # Jika tidak di channel ticket (modal ephemeral), coba gunakan saved channel_id
        if updated.get("channel_id"):
            try:
                channel = interaction.guild.get_channel(int(updated["channel_id"]))
            except Exception:
                channel = None

    payment_embed = embeds.payment_details(display_ticket)

    # Kirim file QRIS jika dipilih dan file ada
    files = None
    if method.lower() == "qris":
        try:
            files = [discord.File("qris.png")]
        except Exception:
            files = None

    if channel:
        view = PaymentActionView(ticket_id)
        await channel.send(embed=payment_embed, view=view, files=files if files else None)

    await interaction.followup.send(embed=embeds.success("Metode Dipilih", f"Kamu memilih **{method}**. Instruksi pembayaran dikirim ke channel ticket."), ephemeral=True)


class PaymentActionView(discord.ui.View):
    """Tombol pada pesan instruksi pembayaran: 'Saya Sudah Bayar' untuk buyer dan 'Verifikasi Pembayaran' untuk staff."""

    def __init__(self, ticket_id: int) -> None:
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        # Tambahkan tombol untuk buyer
        self.add_item(SayaSudahBayarButton(ticket_id))
        # Tombol untuk mengunggah bukti pembayaran
        self.add_item(UploadProofButton(ticket_id))
        # Tambahkan tombol verifikasi untuk staff
        self.add_item(VerifikasiPembayaranButton(ticket_id))
        # Tambahkan tombol status yang hanya untuk staff
        self.add_item(StaffSetStatusButton(ticket_id, config.TICKET_ORDER_STATUS_PAID, label="Paid"))
        self.add_item(StaffSetStatusButton(ticket_id, config.TICKET_ORDER_STATUS_PROCESSING, label="Processing"))
        self.add_item(StaffSetStatusButton(ticket_id, config.TICKET_ORDER_STATUS_DONE, label="Done"))
        self.add_item(StaffSetStatusButton(ticket_id, config.TICKET_ORDER_STATUS_CANCELLED, label="Cancelled"))


class SayaSudahBayarButton(discord.ui.Button):
    def __init__(self, ticket_id: int) -> None:
        super().__init__(label="Saya Sudah Bayar", style=discord.ButtonStyle.success, custom_id=f"paid_notify:{ticket_id}")
        self.ticket_id = ticket_id

    async def callback(self, interaction: discord.Interaction) -> None:
        ticket = await db.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message(embed=embeds.error("Error", "Ticket tidak ditemukan."), ephemeral=True)
            return

        # Hanya owner bisa klik
        is_owner = ticket["user_id"] == str(interaction.user.id)
        if not is_owner:
            await interaction.response.send_message(embed=embeds.error("Akses Ditolak", "Hanya pembeli yang bisa menandai sudah bayar."), ephemeral=True)
            return

        await db.set_ticket_order_status(self.ticket_id, config.TICKET_ORDER_STATUS_PAID)
        updated = await db.get_ticket(self.ticket_id)
        await interaction.response.send_message(embed=embeds.success("Diterima", "Terima kasih — penjual akan segera memverifikasi pembayaran."), ephemeral=True)
        # Kirim notifikasi di channel ticket
        if interaction.channel:
            await interaction.channel.send(embed=embeds.info("Pembayaran Dilaporkan", f"{interaction.user.mention} telah menandai pembayaran untuk order {updated.get('order_code','—')}."))


class UploadProofButton(discord.ui.Button):
    def __init__(self, ticket_id: int) -> None:
        super().__init__(label="Unggah Bukti", style=discord.ButtonStyle.secondary, custom_id=f"upload_proof:{ticket_id}")
        self.ticket_id = ticket_id

    async def callback(self, interaction: discord.Interaction) -> None:
        ticket = await db.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message(embed=embeds.error("Error", "Ticket tidak ditemukan."), ephemeral=True)
            return

        # Hanya owner atau admin dapat mengunggah bukti
        is_owner = ticket["user_id"] == str(interaction.user.id)
        is_admin = await _check_admin(interaction)
        if not is_owner and not is_admin:
            await interaction.response.send_message(embed=embeds.error("Akses Ditolak", "Hanya pembeli atau admin yang bisa mengunggah bukti pembayaran."), ephemeral=True)
            return

        await interaction.response.send_modal(PaymentProofModal(self.ticket_id))


class AdminPaymentActionView(discord.ui.View):
    """View yang ditujukan untuk admin ketika bukti pembayaran diunggah."""

    def __init__(self, ticket_id: int) -> None:
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        # Tombol verify
        self.add_item(VerifyPaymentButton(ticket_id))
        # Tombol reject
        self.add_item(RejectPaymentButton(ticket_id))
        # Tombol done
        self.add_item(DoneOrderButton(ticket_id))
        # Tombol cancel
        self.add_item(StaffSetStatusButton(ticket_id, config.TICKET_ORDER_STATUS_CANCELLED, label="Cancelled"))


class VerifyPaymentButton(discord.ui.Button):
    def __init__(self, ticket_id: int) -> None:
        super().__init__(label="✅ Verify Payment", style=discord.ButtonStyle.success, custom_id=f"verify_payment_admin:{ticket_id}")
        self.ticket_id = ticket_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await _check_admin(interaction):
            await interaction.response.send_message(embed=embeds.error("Akses Ditolak", "Hanya admin yang bisa memverifikasi pembayaran."), ephemeral=True)
            return

        ticket = await db.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message(embed=embeds.error("Error", "Ticket tidak ditemukan."), ephemeral=True)
            return

        # Set order status to VERIFIED, record handler and verification time
        await db.set_ticket_verified(self.ticket_id, str(interaction.user.id), str(interaction.user))
        await db.claim_ticket(self.ticket_id, str(interaction.user.id), str(interaction.user))
        await db.log_activity(str(interaction.user.id), "VERIFY_PAYMENT", f"#{self.ticket_id}", f"Verified payment for ticket #{self.ticket_id}")

        # Notify channel
        admin_name = str(interaction.user)
        time_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        note = f"Pembayaran diverifikasi oleh {admin_name} pada {time_str}."
        if interaction.channel:
            await interaction.channel.send(embed=embeds.info("Pembayaran Diverifikasi", note))

        await interaction.response.send_message(embed=embeds.success("Diverifikasi", "Pembayaran berhasil diverifikasi."), ephemeral=True)


class RejectPaymentButton(discord.ui.Button):
    def __init__(self, ticket_id: int) -> None:
        super().__init__(label="❌ Reject Payment", style=discord.ButtonStyle.danger, custom_id=f"reject_payment_admin:{ticket_id}")
        self.ticket_id = ticket_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await _check_admin(interaction):
            await interaction.response.send_message(embed=embeds.error("Akses Ditolak", "Hanya admin yang bisa menolak bukti pembayaran."), ephemeral=True)
            return
        # Tampilkan modal untuk memasukkan alasan penolakan
        await interaction.response.send_modal(RejectReasonModal(self.ticket_id))


class RejectReasonModal(discord.ui.Modal):
    """Modal yang muncul saat admin menolak bukti pembayaran untuk menangkap alasan."""

    reason: discord.ui.TextInput = discord.ui.TextInput(
        label="Alasan Penolakan",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=300,
    )

    def __init__(self, ticket_id: int) -> None:
        super().__init__(title="Alasan Penolakan Bukti")
        self.ticket_id = ticket_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        # Simpan alasan dan tandai rejected
        reason_text = self.reason.value.strip() if self.reason.value else ""
        try:
            await db.set_ticket_rejected(self.ticket_id, reason_text, str(interaction.user.id), str(interaction.user))
            await db.log_activity(str(interaction.user.id), "REJECT_PAYMENT", f"#{self.ticket_id}", reason_text)
        except Exception:
            pass

        # Notify channel and buyer
        ticket = await db.get_ticket(self.ticket_id)
        note = f"Bukti pembayaran ditolak oleh {interaction.user.mention}. Alasan: {reason_text or '—'}\nSilakan unggah bukti yang valid atau hubungi admin."
        if interaction.channel:
            await interaction.channel.send(embed=embeds.warning("Pembayaran Ditolak", note))

        # DM buyer if possible
        try:
            guild = interaction.guild
            if guild and ticket and ticket.get("user_id"):
                buyer = await guild.fetch_member(int(ticket.get("user_id")))
                await buyer.send(embed=embeds.warning("Bukti Ditolak", f"Alasan: {reason_text or '—'}\nSilakan unggah bukti yang valid."))
        except Exception:
            pass

        await interaction.followup.send(embed=embeds.success("Ditolak", "Bukti pembayaran telah ditandai sebagai ditolak."), ephemeral=True)


class DoneOrderButton(discord.ui.Button):
    def __init__(self, ticket_id: int) -> None:
        super().__init__(label="✅ Done Order", style=discord.ButtonStyle.primary, custom_id=f"done_order_admin:{ticket_id}")
        self.ticket_id = ticket_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await _check_admin(interaction):
            await interaction.response.send_message(embed=embeds.error("Akses Ditolak", "Hanya admin yang bisa menandai order selesai."), ephemeral=True)
            return

        ticket = await db.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message(embed=embeds.error("Error", "Ticket tidak ditemukan."), ephemeral=True)
            return

        # Update order status to done and record completion metadata
        await db.set_ticket_done(self.ticket_id, str(interaction.user.id), str(interaction.user))
        await db.log_activity(str(interaction.user.id), "COMPLETE_ORDER", f"#{self.ticket_id}", f"Order completed for ticket #{self.ticket_id} by {interaction.user}")

        # Buat transaksi ringkas dari ticket dan kirim ke channel order-log
        try:
            tx_id = await db.create_transaction_from_ticket(self.ticket_id, status="done")
        except Exception:
            tx_id = 0

        # Notify buyer
        try:
            guild = interaction.guild
            if guild and ticket.get("user_id"):
                buyer = await guild.fetch_member(int(ticket.get("user_id")))
                await buyer.send(embed=embeds.success("Order Selesai", f"Order {ticket.get('order_code','-')} telah selesai. Terima kasih telah berbelanja di {config.STORE_NAME}!"))
        except Exception:
            pass

        # Kirim ringkasan transaksi ke channel order-log
        try:
            if interaction.guild:
                # Prefer configured ORDER_LOG_CHANNEL_ID, else fallback to name
                order_log = None
                if config.ORDER_LOG_CHANNEL_ID:
                    try:
                        order_log = interaction.guild.get_channel(config.ORDER_LOG_CHANNEL_ID)
                    except Exception:
                        order_log = None
                if not order_log:
                    order_log = discord.utils.get(interaction.guild.text_channels, name=config.ORDER_LOG_CHANNEL_NAME)
                if order_log and order_log.permissions_for(interaction.guild.me).send_messages:
                    tx_ticket = await db.get_ticket(self.ticket_id)
                    if tx_ticket:
                        await order_log.send(embed=embeds.transaction_log_from_ticket(tx_ticket))
        except Exception:
            pass

        if interaction.channel:
            await interaction.channel.send(embed=embeds.info("Order Selesai", f"Order {ticket.get('order_code','-')} ditandai selesai oleh {interaction.user.mention}"))

        await interaction.response.send_message(embed=embeds.success("Selesai", "Order berhasil ditandai selesai."), ephemeral=True)


class VerifikasiPembayaranButton(discord.ui.Button):
    def __init__(self, ticket_id: int) -> None:
        super().__init__(label="Verifikasi Pembayaran", style=discord.ButtonStyle.primary, custom_id=f"verify_payment:{ticket_id}")
        self.ticket_id = ticket_id

    async def callback(self, interaction: discord.Interaction) -> None:
        # Hanya staff/admin
        if not await _check_admin(interaction):
            await interaction.response.send_message(embed=embeds.error("Akses Ditolak", "Hanya staff yang bisa memverifikasi."), ephemeral=True)
            return

        ticket = await db.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message(embed=embeds.error("Error", "Ticket tidak ditemukan."), ephemeral=True)
            return

        current = ticket.get("order_status") or ""
        if current == config.TICKET_ORDER_STATUS_PAID:
            # Dari paid -> processing
            await db.set_ticket_order_status(self.ticket_id, config.TICKET_ORDER_STATUS_PROCESSING)
            await interaction.response.send_message(embed=embeds.success("Dikonfirmasi", "Pembayaran diverifikasi. Status: Processing."))
        elif current == config.TICKET_ORDER_STATUS_PROCESSING:
            # Dari processing -> done
            await db.set_ticket_order_status(self.ticket_id, config.TICKET_ORDER_STATUS_DONE)
            await interaction.response.send_message(embed=embeds.success("Selesai", "Order ditandai selesai (Done)."))
        else:
            await interaction.response.send_message(embed=embeds.warning("Tidak Bisa", "Status saat ini tidak bisa diverifikasi otomatis."), ephemeral=True)


class StaffSetStatusButton(discord.ui.Button):
    """Tombol khusus staff untuk langsung mengubah status order ke Paid/Processing/Done."""

    def __init__(self, ticket_id: int, status: str, label: str | None = None) -> None:
        lab = label or status.capitalize()
        super().__init__(label=lab, style=discord.ButtonStyle.primary, custom_id=f"staff_set_status:{ticket_id}:{status}")
        self.ticket_id = ticket_id
        self.target_status = status

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await _check_admin(interaction):
            await interaction.response.send_message(embed=embeds.error("Akses Ditolak", "Hanya staff yang bisa menekan tombol ini."), ephemeral=True)
            return

        await db.set_ticket_order_status(self.ticket_id, self.target_status)
        updated = await db.get_ticket(self.ticket_id)
        await interaction.response.send_message(embed=embeds.success("Status Diubah", f"Status order diubah menjadi **{self.target_status}**."))

        # Jika status Done, kirim ucapan terima kasih ke buyer
        if self.target_status == config.TICKET_ORDER_STATUS_DONE:
            try:
                guild = interaction.guild
                if guild and updated.get("user_id"):
                    buyer = await guild.fetch_member(int(updated["user_id"]))
                    await buyer.send(embed=embeds.success("Terima Kasih", f"Terima kasih telah berbelanja di {config.STORE_NAME}! Order {updated.get('order_code','-')} sudah selesai."))
            except Exception:
                pass



# ═══════════════════════════════════════════════════════════════════════════════
# VIEWS — kumpulan tombol
# ═══════════════════════════════════════════════════════════════════════════════

class TicketPanelView(discord.ui.View):
    """Panel utama — dua tombol metode pembelian."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Via Send",
        style=discord.ButtonStyle.blurple,
        emoji="🟦",
        custom_id="ticket_panel_send",
    )
    async def via_send(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            TicketModal(ticket_type=config.TICKET_TYPE_SEND)
        )

    @discord.ui.button(
        label="Via Community",
        style=discord.ButtonStyle.green,
        emoji="🟩",
        custom_id="ticket_panel_community",
    )
    async def via_community(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            TicketModal(ticket_type=config.TICKET_TYPE_COMMUNITY)
        )


class TicketControlsView(discord.ui.View):
    """Tombol Claim + Close di channel ticket (status: open)."""

    def __init__(self, ticket_id: int) -> None:
        super().__init__(timeout=None)
        self.add_item(ClaimButton(ticket_id))
        self.add_item(CloseButton(ticket_id))
        self.add_item(PaymentButton(ticket_id))


class TicketClaimedView(discord.ui.View):
    """Tampilan setelah ticket diklaim — Claim disabled dengan nama handler, Close tetap aktif."""

    def __init__(self, ticket_id: int, handler_name: str) -> None:
        super().__init__(timeout=None)
        # Tombol informasi handler — disabled (tidak interaktif)
        info_btn = discord.ui.Button(
            label=f"Handler: {handler_name}",
            style=discord.ButtonStyle.secondary,
            emoji="🙋",
            custom_id=f"ticket_handler_info:{ticket_id}",
            disabled=True,
        )
        self.add_item(info_btn)
        self.add_item(CloseButton(ticket_id))
        self.add_item(PaymentButton(ticket_id))


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER
# ═══════════════════════════════════════════════════════════════════════════════

async def _check_admin(interaction: discord.Interaction) -> bool:
    """Periksa apakah interaksi berasal dari admin server."""
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    if interaction.user.guild_permissions.administrator:
        return True
    # Prefer role ID if configured, else fallback to name
    admin_role = None
    if config.ADMIN_ROLE_ID:
        admin_role = discord.utils.get(interaction.guild.roles, id=config.ADMIN_ROLE_ID)
    if not admin_role:
        admin_role = discord.utils.get(interaction.guild.roles, name=config.ADMIN_ROLE_NAME)
    return bool(admin_role and admin_role in interaction.user.roles)


# ═══════════════════════════════════════════════════════════════════════════════
# COG
# ═══════════════════════════════════════════════════════════════════════════════

class Tickets(commands.Cog):
    """Sistem ticket pembelian Robux."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """
        Daftarkan semua persistent views saat cog dimuat.
        Penting agar tombol tetap berfungsi setelah bot restart.
        """
        # Panel view — selalu sama, daftarkan sekali
        self.bot.add_view(TicketPanelView())

        # Controls view untuk setiap ticket yang masih aktif
        active = await db.get_active_tickets()
        registered = 0
        for ticket in active:
            tid = ticket["id"]
            status = ticket["status"]
            if status == config.TICKET_STATUS_CLAIMED:
                handler = ticket.get("handler_username") or "Admin"
                self.bot.add_view(TicketClaimedView(tid, handler))
            else:
                # Register view with payment button as well
                self.bot.add_view(TicketControlsView(tid))
            registered += 1
        print(f"[TICKET] {registered} view aktif di-register ulang.")

    # ── Slash Commands ────────────────────────────────────────────────────────

    @app_commands.command(
        name="ticket_panel",
        description="[Admin] Kirim panel ticket ke channel ini.",
    )
    async def ticket_panel(self, interaction: discord.Interaction) -> None:
        """Deploy embed panel + tombol Via Send / Via Community."""
        if not await _check_admin(interaction):
            await interaction.response.send_message(
                embed=embeds.error("Akses Ditolak", "Hanya **admin** yang bisa mengirim panel ticket."),
                ephemeral=True,
            )
            return

        panel_embed = embeds.ticket_panel()
        view = TicketPanelView()

        target_channel = None
        if config.TICKET_PANEL_CHANNEL_ID and interaction.guild:
            try:
                target_channel = interaction.guild.get_channel(config.TICKET_PANEL_CHANNEL_ID)
            except Exception:
                target_channel = None

        if target_channel and isinstance(target_channel, discord.abc.Messageable):
            try:
                await target_channel.send(embed=panel_embed, view=view)
            except discord.Forbidden:
                await interaction.response.send_message(
                    embed=embeds.error("Permission Error", "Bot tidak punya izin mengirim panel ke channel target."),
                    ephemeral=True,
                )
                return
            except discord.HTTPException:
                await interaction.response.send_message(
                    embed=embeds.error("Error", "Gagal mengirim panel ke channel target."),
                    ephemeral=True,
                )
                return

            await interaction.response.send_message(
                embed=embeds.success("Panel Ticket Dikirim", f"Panel ticket dikirim ke {target_channel.mention}."),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(embed=panel_embed, view=view)

    @app_commands.command(
        name="ticket_list",
        description="[Admin] Lihat daftar semua ticket (terbaru 25).",
    )
    @app_commands.describe(status="Filter berdasarkan status ticket.")
    @app_commands.choices(
        status=[
            app_commands.Choice(name="Semua", value="all"),
            app_commands.Choice(name="Open 🔓", value="open"),
            app_commands.Choice(name="Claimed 🙋", value="claimed"),
            app_commands.Choice(name="Closed 🔒", value="closed"),
        ]
    )
    async def ticket_list(
        self, interaction: discord.Interaction, status: str = "all"
    ) -> None:
        if not await _check_admin(interaction):
            await interaction.response.send_message(
                embed=embeds.error("Akses Ditolak", "Hanya admin."), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        filter_status = None if status == "all" else status
        tickets = await db.get_all_tickets(status=filter_status, limit=25)
        title = "Semua Ticket" if not filter_status else f"Ticket [{filter_status.capitalize()}]"
        await interaction.followup.send(
            embed=embeds.ticket_list_embed(tickets, title=title), ephemeral=True
        )

    @app_commands.command(
        name="payment_panel",
        description="Tampilkan panel metode pembayaran yang tersedia.",
    )
    async def payment_panel(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        methods = await db.get_all_payment_methods()
        panel = embeds.payment_panel(methods)
        await interaction.followup.send(embed=panel)

    @app_commands.command(
        name="my_tickets",
        description="Lihat semua ticket aktifmu.",
    )
    async def my_tickets(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        tickets = await db.get_user_tickets(str(interaction.user.id))
        await interaction.followup.send(
            embed=embeds.ticket_list_embed(tickets, title="Ticket Saya"),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tickets(bot))
