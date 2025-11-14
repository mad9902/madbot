# streak_cog.py

import discord
from discord.ext import commands

from database import (
    get_streak_pair,
    create_streak_pair,
    set_streak_status,
    get_pending_streak_requests,
    get_active_streaks,
    get_streak_settings,
    upsert_streak_settings,
    apply_streak_update,
    get_tier_emojis,
    set_tier_emoji,
    delete_tier_emoji,
    get_emoji_for_streak,
)

# =========================
#  Helper kecil
# =========================

def get_flame_tier(streak: int):
    """
    Menentukan level api + teks berdasarkan current_streak.
    Kamu bisa ganti emoji sesuai keinginan (custom emoji juga bisa).
    """
    if streak >= 200:
        return "🔥🔥🔥🔥🔥", "LEGENDARY"
    elif streak >= 100:
        return "🔥🔥🔥🔥", "MYTHIC"
    elif streak >= 30:
        return "🔥🔥🔥", "EPIC"
    elif streak >= 10:
        return "🔥🔥", "RARE"
    elif streak >= 5:
        return "🔥", "UNCOMMON"
    elif streak > 0:
        return "✨", "COMMON"
    else:
        return "❄️", "BELUM NYALA"


def format_pair_mention(pair_row):
    return f"<@{pair_row['user1_id']}> × <@{pair_row['user2_id']}>"


# =========================
#  Cog utama
# =========================

class StreakCog(commands.Cog):
    """Fitur pasangan streak berbasis 'api @tag' + reaction."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------
    # Listener 1: detect "api @user" di channel streak
    # ---------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Flow:
        - Hanya di guild + bukan bot
        - Hanya di channel streak yang sudah diset
        - Pesan diawali kata 'api' dan mention tepat 1 user
        - Bot akan otomatis react 🔥 ke pesan tersebut
        (streak baru naik kalau target react 🔥 balik, di listener on_raw_reaction_add)
        """
        if message.author.bot or message.guild is None:
            return

        guild = message.guild
        guild_id = guild.id

        settings = get_streak_settings(guild_id)
        if not settings:
            return  # belum ada setting streak

        cmd_channel_id = settings.get("command_channel_id")
        if cmd_channel_id is None or message.channel.id != cmd_channel_id:
            return  # hanya aktif di channel yang diset

        content = message.content.strip()
        if not content:
            return

        # cek apakah pesan diawali kata 'api' (case-insensitive)
        parts = content.split()
        if len(parts) < 2:
            return

        if parts[0].lower() != "api":
            return

        # ambil mention
        mentions = [m for m in message.mentions if not m.bot and m.id != message.author.id]
        if len(mentions) != 1:
            return

        target = mentions[0]

        # cek apakah mereka sudah punya pasangan streak ACTIVE
        pair = get_streak_pair(guild_id, message.author.id, target.id)
        if not pair:
            # bisa kamu ganti jadi silent kalau nggak mau spam
            await message.channel.send(
                f"{message.author.mention}, kamu belum punya pasangan streak dengan {target.mention}.\n"
                f"Gunakan `!streak request {target.mention}` dulu."
            )
            return

        if pair["status"] != "ACTIVE":
            await message.channel.send(
                f"Pasangan streak dengan {target.mention} belum ACTIVE (status sekarang: `{pair['status']}`)."
            )
            return

        # semua valid -> bot react 🔥
        try:
            emoji_id = get_emoji_for_streak(guild_id, pair["current_streak"])
            e = self.bot.get_emoji(emoji_id) if emoji_id else None
            await message.add_reaction(e or "🔥")
        except discord.Forbidden:
            pass

    # -------------------------------------------------
    # Listener 2: kalau target react 🔥 -> streak naik
    # -------------------------------------------------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """
        - Dipanggil tiap kali ada reaction masuk.
        - Dicek:
          - bukan bot
          - guild + channel = channel streak
          - emoji = 🔥
          - message content diawali 'api' dan mention 1 user
          - reactor = user yang di-mention (bukan author)
        - Kalau semua valid -> apply_streak_update(is_restore=False)
        """
        if payload.user_id == self.bot.user.id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return

        member = guild.get_member(payload.user_id)
        if member is None or member.bot:
            return

        # cek emoji (unicode api)
        if payload.emoji.name != "🔥":
            return

        settings = get_streak_settings(guild.id)
        if not settings:
            return

        cmd_channel_id = settings.get("command_channel_id")
        if cmd_channel_id is None or payload.channel_id != cmd_channel_id:
            return  # hanya proses reaction di channel streak

        channel = guild.get_channel(payload.channel_id)
        if channel is None:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden):
            return

        # pastikan pesan bukan dari bot lain
        if message.author.bot or message.guild is None:
            return

        content = message.content.strip()
        parts = content.split()
        if len(parts) < 2 or parts[0].lower() != "api":
            return

        # cek mention di pesan
        mentions = [m for m in message.mentions if not m.bot and m.id != message.author.id]
        if len(mentions) != 1:
            return

        target = mentions[0]

        # React HARUS datang dari user yang di-mention
        if member.id != target.id:
            return

        # Tidak perlu naikkan streak kalau author sendiri yang react,
        # sudah difilter di atas (member == target).
        guild_id = guild.id

        # cek pasangan
        pair = get_streak_pair(guild_id, message.author.id, target.id)
        if not pair or pair["status"] != "ACTIVE":
            return  # diam saja, tidak ada pasangan aktif

        # apply update normal (bukan restore)
        result = apply_streak_update(
            guild_id=guild_id,
            user1_id=pair["user1_id"],
            user2_id=pair["user2_id"],
            channel_id=payload.channel_id,
            message_id=payload.message_id,
            author_id=member.id,  # yang merespon api
            is_restore=False,
        )

        if not result["ok"]:
            # beberapa reason:
            # - already_updated_today: sudah pernah tercatat hari ini
            # - restore_quota_reached: cuma buat restore
            # ...dst.
            # di sini kita diam saja biar nggak spam
            return

        new_pair = result["pair"]
        streak_now = new_pair["current_streak"]
        before = result["before"]
        broken = result["broken"]
        emoji, tier = get_flame_tier(streak_now)

        # Kirim info singkat di channel
        desc_channel = channel  # alias biar pendek
        if broken:
            text = (
                f"{emoji} Streak {format_pair_mention(new_pair)} **PUTUS** "
                f"dan mulai lagi dari **{streak_now}**."
            )
        else:
            # hanya kirim kalau beneran naik
            if streak_now == before:
                return
            text = (
                f"{emoji} Streak {format_pair_mention(new_pair)} naik dari "
                f"**{before}** ➜ **{streak_now}** ({tier})"
            )

        try:
            await desc_channel.send(text)
        except discord.Forbidden:
            pass

        # Kirim log ke log_channel kalau diset
        log_channel_id = settings.get("log_channel_id")
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                embed = discord.Embed(
                    title=f"{emoji} Streak Update",
                    description=format_pair_mention(new_pair),
                    colour=discord.Colour.orange(),
                )
                embed.add_field(name="Sebelum", value=str(before))
                embed.add_field(name="Sesudah", value=str(streak_now))
                embed.add_field(name="Tier", value=tier, inline=False)
                if result["delta_days"] is not None:
                    embed.set_footer(text=f"Gap hari: {result['delta_days']}")
                try:
                    await log_channel.send(embed=embed)
                except discord.Forbidden:
                    pass

    # =========================
    #  COMMAND GROUP !streak
    # =========================

    @commands.group(name="streak", invoke_without_command=True)
    async def streak_group(self, ctx: commands.Context, member: discord.Member = None):
        """
        - !streak @user -> info pair kamu dengan user tsb
        - !streak request @user -> ajukan pasangan streak
        - !streak accept @user  -> terima
        - !streak deny @user    -> tolak
        - !streak restore @user -> restore kalau bolong 1 hari (max 5x/bulan)
        - !streak top           -> leaderboard
        - !streak setchannel ...-> set channel streak
        """
        if member is None:
            return await ctx.send(
                "Gunakan: `!streak request @user`, `!streak accept @user`, "
                "`!streak deny @user`, `!streak @user` untuk info."
            )

        guild_id = ctx.guild.id
        pair = get_streak_pair(guild_id, ctx.author.id, member.id)
        if not pair:
            return await ctx.send("Kamu belum punya pasangan streak dengan orang itu.")

        emoji, tier = get_flame_tier(pair["current_streak"])
        status = pair["status"]

        embed = discord.Embed(
            title=f"{emoji} Streak Info",
            colour=discord.Colour.orange()
        )
        embed.add_field(name="Pasangan", value=format_pair_mention(pair), inline=False)
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Streak Sekarang", value=str(pair["current_streak"]), inline=True)
        embed.add_field(name="Max Streak", value=str(pair["max_streak"]), inline=True)
        embed.add_field(name="Tier", value=tier, inline=True)
        if pair["last_update_date"]:
            embed.set_footer(text=f"Terakhir nyala: {pair['last_update_date']}")

        await ctx.send(embed=embed)

    # ----- !streak request @user -----

    @streak_group.command(name="request")
    async def streak_request(self, ctx: commands.Context, member: discord.Member):
        """Ajukan pasangan streak dengan user lain."""
        if member.bot:
            return await ctx.send("Tidak bisa ngajak bot jadi pasangan streak.")
        if member.id == ctx.author.id:
            return await ctx.send("Tidak bisa streak dengan diri sendiri 😅")

        guild_id = ctx.guild.id
        pair = create_streak_pair(guild_id, ctx.author.id, member.id, ctx.author.id)

        if pair["status"] == "PENDING":
            await ctx.send(
                f"Permintaan streak dibuat: {format_pair_mention(pair)}\n"
                f"{member.mention}, ketik `!streak accept {ctx.author.mention}` untuk menerima."
            )
        elif pair["status"] == "ACTIVE":
            await ctx.send(
                f"Kalian sudah jadi pasangan streak: {format_pair_mention(pair)} "
                f"(streak {pair['current_streak']})."
            )
        else:
            await ctx.send(
                f"Permintaan streak ditemukan dengan status: **{pair['status']}**."
            )

    # ----- !streak accept @user -----

    @streak_group.command(name="accept")
    async def streak_accept(self, ctx: commands.Context, member: discord.Member):
        """Terima permintaan streak dari user lain."""
        guild_id = ctx.guild.id
        pair = get_streak_pair(guild_id, ctx.author.id, member.id)
        if not pair:
            return await ctx.send("Tidak ada permintaan streak yang cocok.")
        if pair["status"] != "PENDING":
            return await ctx.send(
                f"Permintaan ini tidak dalam status PENDING (sekarang: {pair['status']})."
            )

        if ctx.author.id not in (pair["user1_id"], pair["user2_id"]):
            return await ctx.send("Kamu bukan bagian dari pasangan streak ini.")

        set_streak_status(pair["id"], "ACTIVE")
        await ctx.send(
            f"✅ Permintaan streak diterima! Sekarang {format_pair_mention(pair)} resmi jadi pasangan streak."
        )

    # ----- !streak deny @user -----

    @streak_group.command(name="deny")
    async def streak_deny(self, ctx: commands.Context, member: discord.Member):
        """Tolak permintaan streak."""
        guild_id = ctx.guild.id
        pair = get_streak_pair(guild_id, ctx.author.id, member.id)
        if not pair:
            return await ctx.send("Tidak ada permintaan streak yang cocok.")
        if pair["status"] != "PENDING":
            return await ctx.send(
                f"Permintaan ini tidak dalam status PENDING (sekarang: {pair['status']})."
            )

        set_streak_status(pair["id"], "DENIED")
        await ctx.send(
            f"❌ Permintaan streak ditolak. ({format_pair_mention(pair)})"
        )

    # ----- !streak restore @user -----

    @streak_group.command(name="restore")
    async def streak_restore(self, ctx: commands.Context, member: discord.Member):
        """
        Restore streak kalau bolong 1 hari (gap = 2 hari),
        dengan limit 5x per bulan per pasangan (di-handle di database.py).
        """
        guild_id = ctx.guild.id
        pair = get_streak_pair(guild_id, ctx.author.id, member.id)
        if not pair or pair["status"] != "ACTIVE":
            return await ctx.send("Kamu belum punya pasangan streak aktif dengan orang itu.")

        result = apply_streak_update(
            guild_id=guild_id,
            user1_id=pair["user1_id"],
            user2_id=pair["user2_id"],
            channel_id=ctx.channel.id,
            message_id=ctx.message.id,
            author_id=ctx.author.id,
            is_restore=True,
        )

        if not result["ok"]:
            reason = result["reason"]
            if reason == "already_updated_today":
                msg = "Hari ini sudah pernah dihitung untuk streak ini."
            elif reason == "restore_quota_reached":
                msg = "Jatah restore bulan ini sudah habis (max 5x per pasangan)."
            elif reason == "pair_not_active":
                msg = "Pasangan streak belum ACTIVE."
            elif reason == "pair_not_found":
                msg = "Pasangan streak tidak ditemukan."
            else:
                msg = f"Gagal restore streak ({reason})."
            return await ctx.send(msg)

        new_pair = result["pair"]
        emoji, tier = get_flame_tier(new_pair["current_streak"])

        await ctx.send(
            f"{emoji} Streak {format_pair_mention(new_pair)} berhasil di-**RESTORE** "
            f"menjadi **{new_pair['current_streak']}** (gap hari: {result['delta_days']})."
        )

    # ----- !streak top -----

    @streak_group.command(name="top")
    async def streak_top(self, ctx: commands.Context):
        """Leaderboard pasangan streak aktif di server ini."""
        guild_id = ctx.guild.id
        rows = get_active_streaks(guild_id, limit=10, offset=0, order_by="current")
        if not rows:
            return await ctx.send("Belum ada pasangan streak aktif di server ini.")

        lines = []
        for i, row in enumerate(rows, start=1):
            emoji, tier = get_flame_tier(row["current_streak"])
            lines.append(
                f"**#{i}** {emoji} {format_pair_mention(row)} — "
                f"`{row['current_streak']}x` (Max {row['max_streak']}, {tier})"
            )

        embed = discord.Embed(
            title="🔥 Top Streak Pairs",
            description="\n".join(lines),
            colour=discord.Colour.orange()
        )
        await ctx.send(embed=embed)

    # ----- !streak setchannel -----

    @streak_group.command(name="setchannel")
    async def streak_setchannel(self, ctx: commands.Context, tipe: str, channel: discord.TextChannel):
        """
        Set channel streak:
        - !streak setchannel command #streak
        - !streak setchannel log #streak-log
        """

        DEV_ID = 416234104317804544
        is_admin = ctx.author.guild_permissions.manage_guild
        is_dev = ctx.author.id == DEV_ID

        if not (is_admin or is_dev):
            return await ctx.send("❌ Kamu tidak punya izin untuk set channel streak.")

        tipe = tipe.lower()
        guild_id = ctx.guild.id
        settings = get_streak_settings(guild_id) or {}

        command_id = settings.get("command_channel_id")
        log_id = settings.get("log_channel_id")

        if tipe == "command":
            command_id = channel.id
        elif tipe == "log":
            log_id = channel.id
        else:
            return await ctx.send("Tipe harus `command` atau `log`.")

        upsert_streak_settings(
            guild_id=guild_id,
            command_channel_id=command_id,
            log_channel_id=log_id,
            auto_update=True,
        )

        await ctx.send(f"✅ Channel **{tipe}** streak di-set ke {channel.mention}.")


    # ----- !streak pending -----

    @streak_group.command(name="pending")
    async def streak_pending(self, ctx: commands.Context):
        """
        Lihat permintaan streak PENDING yang melibatkan user yang menjalankan command.
        """
        guild_id = ctx.guild.id
        me_id = ctx.author.id

        # Ambil hanya PENDING yang melibatkan user
        rows = get_pending_streak_requests(
            guild_id=guild_id,
            target_user_id=me_id,   # ← ini penting
            limit=50,
            offset=0
        )

        if not rows:
            return await ctx.send("Tidak ada permintaan streak PENDING yang melibatkan kamu.")

        lines = []
        for row in rows:
            u1 = row["user1_id"]
            u2 = row["user2_id"]
            initiator = row["initiator_id"]

            other_id = u1 if u2 == me_id else u2

            # contoh tampilan:
            # - Dengan @partner (initiator: @siapa_yang_minta)
            lines.append(
                f"- Dengan <@{other_id}> (initiator: <@{initiator}>)"
            )

        await ctx.send("Permintaan streak PENDING yang melibatkan kamu:\n" + "\n".join(lines))



    @commands.command(name="helpstreak")
    async def helpstreak(self, ctx: commands.Context):
        """
        Help streak dengan pagination.
        """
        # Ambil prefix bot secara dinamis
        try:
            prefix = (await self.bot.get_prefix(ctx.message))[0]
        except:
            prefix = "!"

        # ==========================
        # PAGE 1 — CARA KERJA
        # ==========================
        page1 = discord.Embed(
            title="🔥 Panduan Fitur Streak — Halaman 1/4",
            description="Dasar cara kerja fitur pasangan streak.",
            colour=discord.Colour.orange(),
        )
        page1.add_field(
            name="📌 Cara Kerja Utama",
            value=(
                "1. Admin set channel streak:\n"
                f"   • `{prefix}streak setchannel command #streak`\n"
                f"   • `{prefix}streak setchannel log #streak-log`\n\n"
                "2. Buat pasangan streak:\n"
                f"   • `{prefix}streak request @user`\n"
                f"   • `{prefix}streak accept @user`\n\n"
                "3. Jika status pasangan sudah **ACTIVE**:\n"
                "   • Kirim pesan: `api @pasangan`\n"
                "   • Bot react 🔥 otomatis\n"
                "   • User yang di-mention harus react 🔥 kembali → streak naik."
            ),
            inline=False,
        )

        # ==========================
        # PAGE 2 — ATURAN + RESTORE
        # ==========================
        page2 = discord.Embed(
            title="🔥 Panduan Fitur Streak — Halaman 2/4",
            description="Aturan perhitungan streak dan restore.",
            colour=discord.Colour.orange(),
        )

        page2.add_field(
            name="🔥 Aturan Streak Harian",
            value=(
                "• Hitungan streak per **hari**.\n"
                "• Jika sudah dihitung hari ini → reaction berikutnya **tidak menambah** streak.\n"
                "• Bolong 1 hari (gap = 2): bisa restore.\n"
                "• Bolong ≥ 2 hari (gap ≥ 3): streak **putus**."
            ),
            inline=False,
        )

        page2.add_field(
            name="♻️ Aturan Restore",
            value=(
                f"• `{prefix}streak restore @user` untuk pulihkan streak.\n"
                "• Syarat restore:\n"
                "  - Pasangan streak **ACTIVE**.\n"
                "  - Gap = **2 hari**.\n"
                "• Batas restore: **5x per bulan per pasangan**.\n"
                "• Gap ≥ 3 tidak bisa restore."
            ),
            inline=False,
        )

        # ==========================
        # PAGE 3 — TIER + CUSTOM EMOJI
        # ==========================
        page3 = discord.Embed(
            title="🔥 Panduan Fitur Streak — Halaman 3/4",
            description="Tier api & custom emoji tier.",
            colour=discord.Colour.orange(),
        )

        page3.add_field(
            name="🔥 Tier Api Default",
            value=(
                "• 1–4 : ✨ COMMON\n"
                "• 5–9 : 🔥 UNCOMMON\n"
                "• 10–29 : 🔥🔥 RARE\n"
                "• 30–99 : 🔥🔥🔥 EPIC\n"
                "• 100–199 : 🔥🔥🔥🔥 MYTHIC\n"
                "• 200+ : 🔥🔥🔥🔥🔥 LEGENDARY"
            ),
            inline=False,
        )

        page3.add_field(
            name="🎨 Custom Emoji Tier",
            value=(
                "Kamu bisa ganti emoji sesuai streak tertentu.\n"
                "Gunakan:\n"
                f"• `{prefix}streak tiers set <min_streak> <emoji>`\n"
                f"• `{prefix}streak tiers delete <min_streak>`\n"
                f"• `{prefix}streak tiers list`\n\n"
                "Contoh:\n"
                f"• `{prefix}streak tiers set 5 <:flame5:1234567890>`\n"
                f"• `{prefix}streak tiers set 100 <:epic:9876543210>`"
            ),
            inline=False,
        )

        # ==========================
        # PAGE 4 — COMMAND LIST
        # ==========================
        page4 = discord.Embed(
            title="🔥 Panduan Fitur Streak — Halaman 4/4",
            description="Daftar lengkap command streak.",
            colour=discord.Colour.orange(),
        )

        page4.add_field(
            name="📜 Daftar Command",
            value=(
                f"• `{prefix}streak request @user` — ajukan pasangan streak.\n"
                f"• `{prefix}streak accept @user` — terima.\n"
                f"• `{prefix}streak deny @user` — tolak.\n"
                f"• `{prefix}streak @user` — info pasangan.\n"
                f"• `{prefix}streak restore @user` — pulihkan streak.\n"
                f"• `{prefix}streak top` — leaderboard.\n"
                f"• `{prefix}streak pending` — lihat request pending.\n"
                f"• `{prefix}streak setchannel command #ch` — set channel.\n"
                f"• `{prefix}streak setchannel log #ch` — set channel log.\n"
                f"• `{prefix}streak tiers ...` — pengaturan emoji tier."
            ),
            inline=False,
        )

        pages = [page1, page2, page3, page4]
        current = 0

        # Send first page
        msg = await ctx.send(embed=pages[current])

        # Add buttons
        await msg.add_reaction("◀️")
        await msg.add_reaction("▶️")

        def check(reaction, user):
            return (
                user == ctx.author
                and reaction.message.id == msg.id
                and str(reaction.emoji) in ["◀️", "▶️"]
            )

        # Pagination loop
        while True:
            try:
                reaction, user = await self.bot.wait_for(
                    "reaction_add", timeout=120, check=check
                )
            except:
                break

            if str(reaction.emoji) == "▶️":
                current = (current + 1) % len(pages)
            elif str(reaction.emoji) == "◀️":
                current = (current - 1) % len(pages)

            await msg.edit(embed=pages[current])
            try:
                await msg.remove_reaction(reaction.emoji, user)
            except:
                pass

    def format_tier_emoji(bot, emoji_id):
        """
        Kembalikan emoji object jika ada (server emoji),
        kalau tidak ada → tampilkan <:id:id>.
        """
        if not emoji_id:
            return "🔥"  # fallback

        obj = bot.get_emoji(int(emoji_id))
        if obj:
            return str(obj)
        return f"<:e:{emoji_id}>"
    
    # =========================
    #  COMMAND: mstreak tiers ...
    # =========================

    @streak_group.group(name="tiers", invoke_without_command=True)
    async def tiers(self, ctx: commands.Context):
        await ctx.send(
            "Gunakan:\n"
            "`mstreak tiers <min_streak> <emoji>` - set emoji\n"
            "`mstreak tiers delete <min_streak>` - hapus emoji\n"
            "`mstreak tiers list` - list emoji tier"
        )

    # -----------------------------
    # SET EMOJI TIER
    # -----------------------------
    @tiers.command(name="set")
    async def tiers_set(self, ctx: commands.Context, min_streak: int, emoji: str):
        """
        mstreak tiers set <min_streak> <emoji>
        Cukup kirim emoji custom server atau emoji ID.
        """
        DEV_ID = 416234104317804544
        if not (ctx.author.guild_permissions.manage_guild or ctx.author.id == DEV_ID):
            return await ctx.send("❌ Kamu tidak punya izin.")

        import re

        # --- Ambil ID dari format <:name:id> atau <a:name:id> ---
        match = re.search(r"<a?:\w+:(\d+)>", emoji)
        if match:
            emoji_id = int(match.group(1))
        # --- Atau user langsung kirim ID ---
        elif emoji.isdigit():
            emoji_id = int(emoji)
        else:
            return await ctx.send("❌ Kirim emoji custom server (contoh: <:flame:1234567890>)")

        # Simpan ke DB
        set_tier_emoji(ctx.guild.id, min_streak, emoji_id)

        obj = self.bot.get_emoji(emoji_id)
        disp = str(obj) if obj else f"<:e:{emoji_id}>"

        await ctx.send(f"✅ Emoji untuk streak ≥ **{min_streak}** di-set ke {disp}")

    # -----------------------------
    # DELETE EMOJI TIER
    # -----------------------------
    @tiers.command(name="delete")
    async def tiers_delete(self, ctx: commands.Context, min_streak: int):
        """
        mstreak tiers delete <min_streak>
        """

        DEV_ID = 416234104317804544
        if not (ctx.author.guild_permissions.manage_guild or ctx.author.id == DEV_ID):
            return await ctx.send("❌ Kamu tidak punya izin.")

        delete_tier_emoji(ctx.guild.id, min_streak)
        await ctx.send(f"🗑️ Emoji untuk streak ≥ **{min_streak}** telah dihapus.")

    # -----------------------------
    # LIST EMOJI TIER
    # -----------------------------
    @tiers.command(name="list")
    async def tiers_list(self, ctx: commands.Context):
        """
        mstreak tiers list
        """
        rows = get_tier_emojis(ctx.guild.id)
        if not rows:
            return await ctx.send("Belum ada emoji tier yang di-set.")

        out = []
        for r in rows:
            eid = r["emoji_id"]
            obj = self.bot.get_emoji(eid)
            disp = obj if obj else f"<:e:{eid}>"
            out.append(f"- Streak ≥ **{r['min_streak']}** : {disp}")

        await ctx.send("🔥 **Daftar Emoji Tier:**\n" + "\n".join(out))

async def setup(bot: commands.Bot):
    await bot.add_cog(StreakCog(bot))
