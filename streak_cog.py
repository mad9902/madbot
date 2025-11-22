# streak_cog.py

import discord
from discord.ext import commands, tasks
from weakref import WeakKeyDictionary
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
    mark_needs_restore,
    clear_restore_flags,
    kill_streak_due_to_deadline,
    auto_process_gap,
    ensure_restore_cycle,
    force_new_day

)

from discord.ui import View, Button
import pytz
import io
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import random
from datetime import datetime, date, timedelta

BLOCKED_MESSAGES = set()   # pakai set biasa untuk simpan pesan yang diblokir

# =========================
#  Helper kecil
# =========================

async def download_image(url: str):
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return Image.open(io.BytesIO(await r.read())).convert("RGBA")


async def make_streak_card(pfp1_url, pfp2_url, emoji_url, streak):
    # Canvas
    W, H = 900, 350
    base = Image.new("RGBA", (W, H), (0, 0, 0, 255))

    # --- PANEL ---
    panel = Image.new("RGBA", (820, 260), (30, 30, 30, 255))
    mask = Image.new("L", panel.size, 0)
    dmask = ImageDraw.Draw(mask)
    dmask.rounded_rectangle((0, 0, 820, 260), radius=45, fill=255)
    panel.putalpha(mask)
    base.alpha_composite(panel, (40, 45))

    panel_x, panel_y = 40, 45

    # --- SMALL FLAMES (use DB emoji) ---
    if emoji_url:
        flame_src = await download_image(emoji_url)
    else:
        flame_src = None

    for _ in range(random.randint(4, 6)):
        if flame_src:
            f = flame_src.copy()
        else:
            f = Image.new("RGBA", (60, 60), (255,255,255,255))

        size = random.randint(40, 90)
        f = f.resize((size, size))

        # opacity
        alpha = f.split()[3]
        alpha = alpha.point(lambda p: int(p * random.uniform(0.10, 0.25)))
        f.putalpha(alpha)

        # blur
        f = f.filter(ImageFilter.GaussianBlur(1.5))

        # random position left or right
        px = random.choice([
            random.randint(panel_x+50, panel_x+260),
            random.randint(panel_x+540, panel_x+760),
        ])
        py = random.randint(panel_y+60, panel_y+180)

        base.alpha_composite(f, (px, py))

    # --- Avatar circle ---
    def circle(img, size):
        img = img.resize((size, size))
        m = Image.new("L", (size, size))
        dm = ImageDraw.Draw(m)
        dm.ellipse((0, 0, size, size), fill=255)
        out = Image.new("RGBA", (size, size))
        out.paste(img, mask=m)
        return out

    p1 = circle(await download_image(pfp1_url), 150)
    p2 = circle(await download_image(pfp2_url), 150)

    base.alpha_composite(p1, (110, 105))
    base.alpha_composite(p2, (640, 105))

    # --- BIG FLAME (use DB emoji, scaled down) ---
    if flame_src:
        big = flame_src.copy()
        big = big.resize((140, 140))  # ← setengah dari 280px
        base.alpha_composite(big, (380, 75))  # center position
    else:
        draw = ImageDraw.Draw(base)
        try:
            fnt = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 130
            )
        except:
            fnt = ImageFont.load_default()
        draw.text((450, 150), "🔥", anchor="mm", font=fnt, fill="white")

    # --- STREAK NUMBER (lowered so it doesn't overlap) ---
    try:
        font_num = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            70   # <<< dari 110 menjadi 70 (lebih kecil)
        )
    except:
        font_num = ImageFont.load_default()

    draw = ImageDraw.Draw(base)
    draw.text(
        (450, 255),   # sedikit naik (dulunya 240)
        str(streak),
        fill="white",
        font=font_num,
        anchor="mm"
    )

    buf = io.BytesIO()
    base.save(buf, format="PNG")
    buf.seek(0)
    return buf

def get_display_emoji(bot, guild_id, streak):
    """Ambil emoji custom dari DB; kalau tidak ada → fallback tier default."""
    emoji_id = get_emoji_for_streak(guild_id, streak)
    if emoji_id:
        obj = bot.get_emoji(emoji_id)
        return str(obj) if obj else f"<:e:{emoji_id}>"

    # fallback ke default
    default_emoji, _ = get_flame_tier(streak)
    return default_emoji


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



class InfoPagination(View):
    def __init__(self, pages):
        super().__init__(timeout=120)
        self.pages = pages
        self.index = 0

    async def update(self, interaction):
        embed = self.pages[self.index]
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: Button):
        self.index = (self.index - 1) % len(self.pages)
        await self.update(interaction)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: Button):
        self.index = (self.index + 1) % len(self.pages)
        await self.update(interaction)
# =========================
#  Cog utama
# =========================

class StreakCog(commands.Cog):
    """Fitur pasangan streak berbasis 'api @tag' + reaction."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.daily_reset_check.start()
        self.last_reset_date = None
        self.sent_warnings = {}   # key: pair_id -> date
        self.sent_deaths = {}     # key: pair_id -> date

    @tasks.loop(minutes=1)
    async def daily_reset_check(self):
        wib = pytz.timezone("Asia/Jakarta")
        now = datetime.now(wib)
        today = now.date()

        # ============================
        #  RESET HARIAN JAM 00:00 WIB
        # ============================
        if self.last_reset_date != today:
            print("[STREAK] Reset harian berjalan (jam 00:00)")
            await self.process_daily_reset()
            self.last_reset_date = today



    @daily_reset_check.before_loop
    async def before_daily_reset(self):
        await self.bot.wait_until_ready()
        wib = pytz.timezone("Asia/Jakarta")
        self.last_reset_date = datetime.now(wib).date()

    def cog_unload(self):
        self.daily_reset_check.cancel()


    async def process_daily_reset(self):
        """
        Auto check jam 00:00 WIB:
        - Hitung delta hari masing-masing pasangan
        - Jika butuh restore → kirim WARNING
        - Jika deadline restore lewat → auto BROKEN + kirim embed kematian
        - Jika delta >= 3 → auto BROKEN + kirim embed kematian
        - Jika kuota restore habis → auto BROKEN + kirim embed kematian
        """

        wib = pytz.timezone("Asia/Jakarta")
        today = datetime.now(wib).date()

        for guild in self.bot.guilds:
            settings = get_streak_settings(guild.id)
            if not settings:
                continue

            log_channel_id = settings.get("log_channel_id")
            log_channel = guild.get_channel(log_channel_id) if log_channel_id else None

            rows = get_active_streaks(guild.id, limit=5000, offset=0)
            if not rows:
                continue

            for pair in rows:
                pair = ensure_restore_cycle(pair)
                last = pair["last_update_date"]

                # kalau NULL (belum pernah nyala), jangan dihitung delta
                if last is None:
                    # skip pasangan ini, karena belum pernah punya streak harian
                    continue

                # Convert last date
                if isinstance(last, str):
                    try:
                        last = datetime.strptime(last, "%Y-%m-%d").date()
                    except:
                        last = today


                delta = (today - last).days
                deadline = pair.get("restore_deadline")

                # Convert deadline
                if isinstance(deadline, str):
                    try:
                        deadline = datetime.strptime(deadline, "%Y-%m-%d").date()
                    except:
                        deadline = None

                # -------------------------------
                # CASE A — NEED RESTORE (delta 2)
                # -------------------------------
                if delta == 2:

                    # ⚠️ CEK KUOTA RESTORE HABIS → LANGSUNG MATI
                    if pair.get("restore_used_this_cycle", 0) >= 5:
                        kill_streak_due_to_deadline(pair["id"])
                        dead = get_streak_pair(guild.id, pair["user1_id"], pair["user2_id"])
                        if log_channel:
                            await self.send_streak_dead(
                                guild,
                                dead,
                                restore_left_override="0 / 5"
                            )
                        continue

                    # ⚠️ Jika kuota ada → baru peringatan
                    mark_needs_restore(pair["id"], today)
                    updated = get_streak_pair(guild.id, pair["user1_id"], pair["user2_id"])
                    await self.send_warning_near_dead(guild, updated)
                    continue

                # -------------------------------
                # CASE B — TERLAMBAT RESTORE
                # -------------------------------
                if pair["needs_restore"] == 1 and deadline:
                    if today > deadline:
                        kill_streak_due_to_deadline(pair["id"])
                        dead = get_streak_pair(guild.id, pair["user1_id"], pair["user2_id"])

                        if log_channel:
                            await self.send_streak_dead(guild, dead)

                        continue

                # -------------------------------
                # CASE C — DELTA >= 3 → auto mati
                # -------------------------------
                if delta >= 3:
                    kill_streak_due_to_deadline(pair["id"])
                    dead = get_streak_pair(guild.id, pair["user1_id"], pair["user2_id"])

                    if log_channel:
                        await self.send_streak_dead(guild, dead)

                    continue

                # -------------------------------
                # CASE D — KUOTA RESTORE HABIS
                # -------------------------------
                if pair.get("restore_used_this_cycle", 0) >= 5 and pair.get("needs_restore", 0) == 1:
                    kill_streak_due_to_deadline(pair["id"])
                    dead = get_streak_pair(guild.id, pair["user1_id"], pair["user2_id"])

                    if log_channel:
                        await self.send_streak_dead(
                            guild, 
                            dead, 
                            restore_left_override="0 / 5"
                        )

                    continue


    async def send_warning_near_dead(self, guild, pair):
        """Kirim embed warning ke log channel."""
        settings = get_streak_settings(guild.id)
        if not settings or not settings.get("log_channel_id"):
            return

        log_channel = guild.get_channel(settings["log_channel_id"])
        if not log_channel:
            return

        embed = discord.Embed(
            title="⚠️ Streak Hampir Mati!",
            description=(
                f"{format_pair_mention(pair)}\n"
                f"Streak kalian **bolong 1 hari**.\n"
                f"Aktifkan kembali dengan `api @user` sebelum:\n"
                f"**{pair['restore_deadline']}**"
            ),
            colour=discord.Colour.gold()
        )
        # --- Hitung sisa restore bulan ini ---
        pair = ensure_restore_cycle(pair)
        used = pair.get("restore_used_this_cycle", 0) or 0
        left = max(0, 5 - used)

        embed.add_field(
            name="♻️ Sisa Restore Bulan Ini",
            value=f"{left} / 5",
            inline=True
        )

        embed.set_footer(text="Jika tidak, besok streak mati total 💀")
        # Prevent spam — hanya kirim 1x per hari
        today = date.today()

        # pair_id sebagai key
        pair_id = pair["id"]

        last_sent = getattr(self, "sent_warnings", {}).get(pair_id)
        if last_sent == today:
            return  # sudah kirim hari ini, jangan spam

        # simpan state
        self.sent_warnings[pair_id] = today

        await log_channel.send(embed=embed)


    async def send_streak_dead(self, guild, pair, restore_left_override=None):
        """
        Kirim embed kematian streak.
        Jika restore_left_override diberikan → pakai angka itu.
        Kalau tidak → pakai sisa restore berdasarkan pair saat ini.
        """

        settings = get_streak_settings(guild.id)
        if not settings or not settings.get("log_channel_id"):
            return

        log_channel = guild.get_channel(settings["log_channel_id"])
        if not log_channel:
            return

        embed = discord.Embed(
            title="💀 Streak Mati Total",
            description=(
                f"{format_pair_mention(pair)}\n"
                f"Tidak menyalakan api sampai deadline.\n"
                f"Streak telah **putus permanen**."
            ),
            colour=discord.Colour.red()
        )

        # --- Ambil restore sebelum mati ---
        # (used_after mati = 0, jadi harus override manual biar benar)
        used = pair.get("restore_used_this_cycle", 0) or 0

        if restore_left_override is not None:
            # Jika kamu kirim override → langsung pakai angka ini
            left_display = restore_left_override
        else:
            # Fallback (dipakai kalau mati karena gap ≥ 3, bukan restore habis)
            left_display = f"{max(0, 5 - used)} / 5"

        embed.add_field(
            name="♻️ Sisa Restore Bulan Ini (reset)",
            value=left_display,
            inline=True
        )

        today = date.today()

        pair_id = pair["id"]

        last_dead = getattr(self, "sent_deaths", {}).get(pair_id)
        if last_dead == today:
            return  # sudah kirim embed mati hari ini

        # simpan state
        self.sent_deaths[pair_id] = today

        await log_channel.send(embed=embed)

    # ---------------------------------------------
    # Listener 1: detect "api @user" di channel streak
    # ---------------------------------------------
    # -------------------------------------------------
    # Listener 2: kalau target react 🔥 -> streak naik
    # -------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        
        if message.author.bot or message.guild is None:
            return

        guild = message.guild
        guild_id = guild.id

        settings = get_streak_settings(guild_id)
        if not settings:
            return

        cmd_channel_id = settings.get("command_channel_id")
        # ❌ Cegah API di channel log
        log_channel_id = settings.get("log_channel_id")

        if log_channel_id and message.channel.id == log_channel_id:
            if message.content.lower().startswith("api "):
                await message.channel.send(
                    "❌ Tidak bisa menyalakan api di channel log.\nGunakan channel command."
                )
            BLOCKED_MESSAGES.add(message.id)
            return  # ⬅ FIX PENTING: stop SELURUH fungsi

        if cmd_channel_id is None or message.channel.id != cmd_channel_id:
            return

        content = message.content.strip()
        if not content:
            return

        parts = content.split()
        if len(parts) < 2:
            return
        if parts[0].lower() != "api":
            return

        mentions = [m for m in message.mentions if not m.bot and m.id != message.author.id]
        if len(mentions) != 1:
            return

        target = mentions[0]

        pair = get_streak_pair(guild_id, message.author.id, target.id)

        # ★ AUTO GAP PROCESSING
        pair = auto_process_gap(pair)

        # REFRESH pair dari DB supaya status up to date
        pair = get_streak_pair(guild_id, message.author.id, target.id)

        # Jika baru masuk mode restore (delta = 1)
        # === Warning logic masuk mode restore ===

        if not pair:
            await message.channel.send(
                f"{message.author.mention}, pasangan streak ini tidak valid lagi."
            )
            return

        # ★ Jika streak sudah mati karena lewat deadline
        if pair["status"] == "BROKEN":
            await self.send_streak_dead(message.guild, pair)
            await message.channel.send(
                f"💀 Streak kalian sudah mati karena tidak menyalakan api sampai deadline.\n"
                f"Mulai ulang dengan `mstreak request`."
            )
            return

        # ★ mode needs_restore, bot tetap react tapi hanya memberi peringatan
        # ★ Jika butuh restore → cek apakah streak seharusnya sudah MATI
        if pair["needs_restore"] == 1:

            # Cek delta lagi untuk memastikan (supaya tidak salah warning)
            last = pair.get("last_update_date")
            if isinstance(last, str):
                last = datetime.strptime(last, "%Y-%m-%d").date()

            today = date.today()
            delta = (today - last).days

            # Jika delta >= 3 → ini bukan restore lagi, harus MATI
            if delta >= 3:
                # ambil restore sebelum mati
                pair_cycle = ensure_restore_cycle(pair)
                used_before = pair_cycle.get("restore_used_this_cycle", 0)
                left_before = f"{max(0, 5 - used_before)} / 5"

                kill_streak_due_to_deadline(pair["id"])
                dead = get_streak_pair(guild_id, pair["user1_id"], pair["user2_id"])

                await self.send_streak_dead(message.guild, dead, restore_left_override=left_before)

                await message.channel.send("💀 Streak kalian sudah mati karena **terlambat restore**.")
                return

            # Cek deadline lewat
            try:
                deadline = datetime.strptime(pair["restore_deadline"], "%Y-%m-%d").date()
            except:
                deadline = today

            if today > deadline:
                # ambil restore sebelum mati
                pair_cycle = ensure_restore_cycle(pair)
                used_before = pair_cycle.get("restore_used_this_cycle", 0)
                left_before = f"{max(0, 5 - used_before)} / 5"

                kill_streak_due_to_deadline(pair["id"])
                dead = get_streak_pair(guild_id, pair["user1_id"], pair["user2_id"])

                await self.send_streak_dead(message.guild, dead, restore_left_override=left_before)

                await message.channel.send("💀 Streak kalian sudah mati karena **terlambat restore**.")
                return
            
            # 🔥 FIX: langsung mati jika kuota restore habis
            pair_cycle = ensure_restore_cycle(pair)

            if pair_cycle.get("restore_used_this_cycle", 0) >= 5:
                # override MUST be 0/5 untuk kematian karena restore habis
                restore_before = "0 / 5"

                kill_streak_due_to_deadline(pair["id"])
                dead = get_streak_pair(guild_id, pair["user1_id"], pair["user2_id"])

                await self.send_streak_dead(
                    message.guild,
                    dead,
                    restore_left_override=restore_before
                )

                await message.channel.send("💀 Streak kalian mati karena kuota restore sudah habis (5x/bulan).")
                return



            # Kalau belum lewat deadline → kasih warning kuning
            u1 = pair["user1_id"]
            u2 = pair["user2_id"]

            user_a = message.author.display_name
            user_b = guild.get_member(u1).display_name if u1 != message.author.id else guild.get_member(u2).display_name

            await message.add_reaction("⚠️")
            await message.channel.send(
                f"⚠️ Streak kalian **butuh restore**."
                f"\nSalah satu dari kalian dapat mengetik:"
                f"\n`mstreak restore @{user_a}` **atau** `mstreak restore @{user_b}`"
                f"\nAtau cukup react ⚠️ pada pesan `api @user` tadi."
                f"\nSebelum **{pair['restore_deadline']}**."
            )
            return


        if not pair:
            await message.channel.send(
                f"{message.author.mention}, kamu belum punya pasangan streak dengan {target.mention}.\n"
                f"Gunakan `mstreak request {target.mention}` dulu."
            )
            return

        if pair["status"] != "ACTIVE":
            await message.channel.send(
                f"Pasangan streak dengan {target.mention} belum ACTIVE (status sekarang: `{pair['status']}`)."
            )
            return

        # react emoji (custom atau fallback)
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

        # Ignore bot reaction
        if payload.user_id == self.bot.user.id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        settings = get_streak_settings(guild.id)
        if not settings:
            return

        cmd_channel_id = settings.get("command_channel_id")
        if cmd_channel_id is None or payload.channel_id != cmd_channel_id:
            return

        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except:
            return

        if message.author.bot or not message.guild:
            return

        # Check message format "api @user"
        content = message.content.strip().lower()
        parts = content.split()
        if len(parts) < 2 or parts[0] != "api":
            return

        mentions = [m for m in message.mentions if not m.bot and m.id != message.author.id]
        if len(mentions) != 1:
            return

        target = mentions[0]

        # only target can react
        if member.id != target.id:
            return
        

        guild_id = guild.id
        pair = get_streak_pair(guild_id, message.author.id, target.id)
        if not pair:
            return
        
        # =====================================================
        #  AUTO RESTORE VIA REACTION (⚠️ atau custom restore emoji)
        # =====================================================

        RESTORE_EMOJIS = ["⚠️", "warning", "restore"]

        if pair.get("needs_restore", 0) == 1:
            # 🔥 FIX: kuota restore habis = langsung mati
            pair_cycle = ensure_restore_cycle(pair)
            if pair_cycle.get("restore_used_this_cycle", 0) >= 5:
                restore_before = "0 / 5"   # override for restore-death

                kill_streak_due_to_deadline(pair["id"])
                dead = get_streak_pair(guild.id, pair["user1_id"], pair["user2_id"])

                await channel.send("💀 Streak kalian mati karena kuota restore sudah habis (5x/bulan).")

                await self.send_streak_dead(
                    guild,
                    dead,
                    restore_left_override=restore_before
                )
                return

            # Check apakah emoji restore
            em = payload.emoji

            is_restore_emoji = False
            if em.name in RESTORE_EMOJIS:
                is_restore_emoji = True
            if hasattr(em, "id") and str(em.id) in RESTORE_EMOJIS:
                is_restore_emoji = True

            if is_restore_emoji:
                today = date.today()

                # Cek deadline restore
                deadline = pair.get("restore_deadline")
                if isinstance(deadline, str):
                    try:
                        deadline = datetime.strptime(deadline, "%Y-%m-%d").date()
                    except:
                        deadline = today

                if today > deadline:
                    kill_streak_due_to_deadline(pair["id"])
                    dead_pair = get_streak_pair(guild.id, pair["user1_id"], pair["user2_id"])
                    await channel.send("💀 Terlambat restore → streak mati total.")
                    await self.send_streak_dead(guild, dead_pair)
                    return

                # Jalankan restore
                result = apply_streak_update(
                    guild_id=guild.id,
                    user1_id=pair["user1_id"],
                    user2_id=pair["user2_id"],
                    channel_id=payload.channel_id,
                    message_id=payload.message_id,
                    author_id=member.id,
                    is_restore=True,
                    today=today
                )

                if not result["ok"]:
                    # kalau kuota restore habis → langsung MATI
                    if result.get("reason") == "restore_quota_reached":
                        kill_streak_due_to_deadline(pair["id"])
                        dead = get_streak_pair(guild_id, pair["user1_id"], pair["user2_id"])
                        await channel.send("💀 Streak kalian mati karena kuota restore sudah habis (5x/bulan).")
                        await self.send_streak_dead(guild, dead)
                        return

                    # selain itu → gagal biasa
                    await channel.send("❌ Gagal restore streak.")
                    return


                clear_restore_flags(pair["id"])
                new_pair = ensure_restore_cycle(result["pair"])

                used = new_pair.get("restore_used_this_cycle", 0)
                left = max(0, 5 - used)

                emoji = get_display_emoji(self.bot, guild.id, new_pair["current_streak"])

                await channel.send(
                    f"{emoji} **RESTORE BERHASIL (via reaction)!**\n"
                    f"Streak sekarang: **{new_pair['current_streak']}**\n"
                    f"♻️ Sisa restore bulan ini: **{left} / 5** (reset)"
                )
                return


        # --- Validate emoji
        allowed = ["🔥"]
        custom_emoji_id = get_emoji_for_streak(guild.id, pair["current_streak"])
        if custom_emoji_id:
            allowed.append(str(custom_emoji_id))

        if payload.emoji.name != "🔥" and str(payload.emoji.id) not in allowed:
            return

        # TIME LOGIC
        wib = pytz.timezone("Asia/Jakarta")
        today = datetime.now(wib).date()

        last = pair.get("last_update_date")
        if isinstance(last, str):
            try:
                last = datetime.strptime(last, "%Y-%m-%d").date()
            except:
                last = today

        if last == (today - timedelta(days=1)):
            try:
                from database import force_new_day
                force_new_day(pair["id"])
            except Exception as e:
                print("[STREAK] force_new_day ERROR:", e)

            pair = get_streak_pair(guild_id, message.author.id, target.id)
            if not pair:
                return

        # AUTO GAP
        gap_check = auto_process_gap(pair)
        if not gap_check:
            return

        if gap_check.get("needs_restore", 0) == 1:
            await self.send_warning_near_dead(guild, gap_check)

        pair = gap_check

        # BROKEN STATE
        if pair["status"] == "BROKEN":
            await self.send_streak_dead(guild, pair)
            await channel.send("💀 Streak kalian sudah mati karena melewati batas restore.")
            return

        # RESTORE MODE
        # ===== HARD OVERRIDE: restore terlambat =====
        if pair.get("needs_restore", 0) == 1 and pair.get("restore_deadline"):
            try:
                deadline = datetime.strptime(pair["restore_deadline"], "%Y-%m-%d").date()
            except:
                deadline = date.today()

            today = date.today()

            # Jika sudah LEWAT hari deadline → MATI OTOMATIS
            if today > deadline:
                kill_streak_due_to_deadline(pair["id"])
                dead_pair = get_streak_pair(guild_id, pair["user1_id"], pair["user2_id"])

                await channel.send("💀 Terlambat restore, streak mati total.")
                await self.send_streak_dead(guild, dead_pair)
                return

            # Check deadline
            if pair.get("restore_deadline"):
                dead = datetime.strptime(pair["restore_deadline"], "%Y-%m-%d").date()
                if today > dead:
                    kill_streak_due_to_deadline(pair["id"])
                    await channel.send("💀 Terlambat restore → streak mati total.")
                    return

            result = apply_streak_update(
                guild_id=guild_id,
                user1_id=pair["user1_id"],
                user2_id=pair["user2_id"],
                channel_id=payload.channel_id,
                message_id=payload.message_id,
                author_id=member.id,
                is_restore=True,
                today=today,
            )

            if not result["ok"]:
                # kalau kuota restore habis → langsung MATI
                if result.get("reason") == "restore_quota_reached":
                    kill_streak_due_to_deadline(pair["id"])
                    dead = get_streak_pair(guild_id, pair["user1_id"], pair["user2_id"])
                    await channel.send("💀 Streak kalian mati karena kuota restore sudah habis (5x/bulan).")
                    await self.send_streak_dead(guild, dead)
                    return

                # selain itu → gagal biasa
                await channel.send("❌ Gagal restore streak.")
                return


            clear_restore_flags(pair["id"])
            new_pair = result["pair"]

            # Count restore
            new_pair = ensure_restore_cycle(new_pair)
            used = new_pair.get("restore_used_this_cycle", 0)
            left = max(0, 5 - used)

            emoji = get_display_emoji(self.bot, guild_id, new_pair["current_streak"])

            await channel.send(
                f"{emoji} **RESTORE BERHASIL!** Streak kembali menyala 🔥\n"
                f"(hari terakhir restore: {result['delta_days']})\n"
                f"♻️ Sisa restore bulan ini: **{left} / 5**"
            )
            return

        # NORMAL UPDATE
        if pair["status"] != "ACTIVE":
            return

        result = apply_streak_update(
            guild_id=guild_id,
            user1_id=pair["user1_id"],
            user2_id=pair["user2_id"],
            channel_id=payload.channel_id,
            message_id=payload.message_id,
            author_id=member.id,
            is_restore=False,
            today=today,
        )

        if not result["ok"]:
            return
        
        before = result["before"]

        new_pair = result["pair"]
        streak_now = new_pair["current_streak"]
        broken = result["broken"]

        if streak_now == before:
            return

        emoji = get_display_emoji(self.bot, guild_id, streak_now)
        _, tier = get_flame_tier(streak_now)

        # TEXT MESSAGE
        if broken:
            text = (
                f"{emoji} Streak {format_pair_mention(new_pair)} **PUTUS** "
                f"dan mulai dari **{streak_now}**."
            )
        else:
            text = (
                f"{emoji} Streak {format_pair_mention(new_pair)} naik "
                f"dari **{before}** ➜ **{streak_now}** ({tier})"
            )

        try:
            await channel.send(text)
        except:
            pass

        # LOG CHANNEL
        log_channel_id = settings.get("log_channel_id")
        if not log_channel_id:
            return

        log_channel = guild.get_channel(log_channel_id)
        if not log_channel:
            return

        # CARD
        pfp1 = message.author.display_avatar.with_size(512).with_format("png").url
        pfp2 = target.display_avatar.with_size(512).with_format("png").url

        emoji_id = get_emoji_for_streak(guild_id, streak_now)
        emoji_url = None
        if emoji_id:
            e = self.bot.get_emoji(emoji_id)
            if e and hasattr(e, "url"):
                emoji_url = e.url

        card = await make_streak_card(pfp1, pfp2, emoji_url, streak_now)
        file = discord.File(card, filename="streak.png")

        embed = discord.Embed(
            title=f"{emoji} Streak Update",
            description=format_pair_mention(new_pair),
            colour=discord.Colour.orange(),
        )
        embed.set_image(url="attachment://streak.png")
        embed.add_field(name="Sebelum", value=str(before))
        embed.add_field(name="Sesudah", value=str(streak_now))
        embed.add_field(name="Tier", value=tier, inline=False)

        new_pair = ensure_restore_cycle(new_pair)
        used = new_pair.get("restore_used_this_cycle", 0)
        left = max(0, 5 - used)

        embed.add_field(
            name="♻️ Sisa Restore Bulan Ini",
            value=f"{left} / 5",
            inline=True,
        )

        if result["delta_days"] is not None:
            embed.set_footer(text=f"Gap hari: {result['delta_days']}")

        try:
            await log_channel.send(file=file, embed=embed)
        except:
            pass

    # =========================
    #  COMMAND GROUP mstreak
    # =========================

    @commands.group(name="streak", invoke_without_command=True)
    async def streak_group(self, ctx: commands.Context, member: discord.Member = None):
        """
        - mstreak @user -> info pair kamu dengan user tsb
        - mstreak request @user -> ajukan pasangan streak
        - mstreak accept @user  -> terima
        - mstreak deny @user    -> tolak
        - mstreak restore @user -> restore kalau bolong 1 hari (max 5x/bulan)
        - mstreak top           -> leaderboard
        - mstreak setchannel ...-> set channel streak
        """
        if member is None:
            return await ctx.send(
                "Gunakan: `mstreak request @user`, `mstreak accept @user`, "
                "`mstreak deny @user`, `mstreak @user` untuk info."
            )

        guild_id = ctx.guild.id
        pair = get_streak_pair(guild_id, ctx.author.id, member.id)

        # ★ APPLY AUTO GAP SYSTEM
        pair = auto_process_gap(pair)

        if not pair:
            return await ctx.send("Data pasangan tidak ditemukan.")

        # ★ Jika streak sudah mati karena lewat deadline
        if pair["status"] == "BROKEN":
            return await ctx.send(
                "💀 Streak pasangan ini sudah mati karena melewati batas restore.\n"
                "Mulai ulang dengan `mstreak request @user`."
            )

        if not pair:
            return await ctx.send("Kamu belum punya pasangan streak dengan orang itu.")

        emoji = get_display_emoji(self.bot, guild_id, pair["current_streak"])
        _, tier = get_flame_tier(pair["current_streak"])

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
        # ★ Informasi jika sedang butuh restore
        pair = ensure_restore_cycle(pair)  # pastikan bulan update

        used = pair.get("restore_used_this_cycle", 0) or 0
        left = max(0, 5 - used)

        embed.add_field(
            name="♻️ Sisa Restore Bulan Ini",
            value=f"{left} / 5",
            inline=True
        )
        if pair.get("needs_restore", 0) == 1:
            embed.add_field(
                name="⚠️ Status Restore",
                value=f"Butuh restore sebelum `{pair['restore_deadline']}`",
                inline=False
            )
        if pair["last_update_date"]:
            embed.set_footer(text=f"Terakhir nyala: {pair['last_update_date']}")

        await ctx.send(embed=embed)

    # ----- mstreak myinfo -----
    @streak_group.command(name="myinfo")
    async def streak_myinfo(self, ctx: commands.Context):
        """Info personal: siapa yang belum nyalain api, pending request, dan pasangan aktif."""
        guild_id = ctx.guild.id
        me = ctx.author

        wib = pytz.timezone("Asia/Jakarta")
        today = datetime.now(wib).date()

        # Ambil semua pasangan aktif di server
        all_pairs = get_active_streaks(guild_id, limit=5000, offset=0)

        # ======================================================
        #  PAGE 1 — PASANGAN AKTIF YANG BELUM NYALAIN API HARI INI
        # ======================================================
        emb1 = discord.Embed(
            title="🔥 Belum Nyalain Api Hari Ini",
            colour=discord.Colour.orange()
        )

        pending_today = []
        for p in all_pairs:
            if me.id not in (p["user1_id"], p["user2_id"]):
                continue  # skip pasangan yang bukan milik kita

            pair = ensure_restore_cycle(p)
            last = pair["last_update_date"]

            if isinstance(last, str):
                try:
                    last = datetime.strptime(last, "%Y-%m-%d").date()
                except:
                    last = today

            if last != today:  # BELUM nyala
                other_id = pair["user1_id"] if pair["user2_id"] == me.id else pair["user2_id"]
                emoji = get_display_emoji(self.bot, guild_id, pair["current_streak"])
                pending_today.append(
                    f"{emoji} Dengan <@{other_id}> (last: `{pair['last_update_date']}`)"
                )

        if not pending_today:
            emb1.description = "🎉 Kamu sudah menyalakan api dengan semua pasangan hari ini!"
        else:
            emb1.description = "\n".join(pending_today)

        # ======================================================
        #  PAGE 2 — PENDING REQUEST YANG MELIBATKAN KITA
        # ======================================================
        pendings = get_pending_streak_requests(
            guild_id=guild_id,
            target_user_id=me.id,
            limit=50,
            offset=0
        )

        emb2 = discord.Embed(
            title="⏳ Pending Streak Kamu",
            colour=discord.Colour.orange()
        )

        if not pendings:
            emb2.description = "Tidak ada pending request."
        else:
            lines = []
            for row in pendings:
                u1 = row["user1_id"]
                u2 = row["user2_id"]
                initiator = row["initiator_id"]

                other_id = u1 if me.id == u2 else u2

                lines.append(
                    f"- Dengan <@{other_id}> (initiator: <@{initiator}>)"
                )
            emb2.description = "\n".join(lines)

        # ======================================================
        #  PAGE 3 — SEMUA PASANGAN AKTIF KITA
        # ======================================================
        emb3 = discord.Embed(
            title="💞 Pasangan Streak Kamu",
            colour=discord.Colour.orange()
        )

        lines = []
        for p in all_pairs:
            if me.id not in (p["user1_id"], p["user2_id"]):
                continue

            pair = ensure_restore_cycle(p)
            streak = pair["current_streak"]
            emoji = get_display_emoji(self.bot, guild_id, streak)

            other_id = pair["user1_id"] if pair["user2_id"] == me.id else pair["user2_id"]

            status = "ACTIVE"
            if pair.get("needs_restore", 0) == 1:
                status = f"⚠️ RESTORE (deadline {pair['restore_deadline']})"

            lines.append(
                f"{emoji} <@{other_id}> — `{streak}x` ({status})"
            )

        if not lines:
            emb3.description = "Kamu belum punya pasangan streak."
        else:
            emb3.description = "\n".join(lines)

        # ======================================================
        #  SEND PAGINATION
        # ======================================================
        pages = [emb1, emb2, emb3]
        view = InfoPagination(pages)

        await ctx.send(embed=pages[0], view=view)

    # ----- mstreakinfo -----
    @streak_group.command(name="info")
    async def streak_info(self, ctx: commands.Context):
        """Melihat status streak lengkap: pending, active, dan siapa yg belum nyala hari ini."""
        guild_id = ctx.guild.id
        me = ctx.author

        wib = pytz.timezone("Asia/Jakarta")
        today = datetime.now(wib).date()

        # ================================
        # 1) PENDING REQUESTS
        # ================================
        pendings = get_pending_streak_requests(
            guild_id=guild_id,
            target_user_id=me.id,
            limit=100,
            offset=0
        )

        emb1 = discord.Embed(
            title="⏳ Pending Streak Requests",
            colour=discord.Colour.orange()
        )

        if not pendings:
            emb1.description = "Tidak ada permintaan streak yang pending."
        else:
            lines = []
            for row in pendings:
                u1 = row["user1_id"]
                u2 = row["user2_id"]
                initiator = row["initiator_id"]

                other_id = u1 if me.id == u2 else u2
                lines.append(
                    f"- Dengan <@{other_id}> (initiator: <@{initiator}>)"
                )
            emb1.description = "\n".join(lines)

        # ================================
        # 2) ACTIVE STREAK LIST
        # ================================
        active_pairs = get_active_streaks(guild_id, limit=5000, offset=0)

        emb2 = discord.Embed(
            title="🔥 Active Streak Status",
            colour=discord.Colour.orange()
        )

        if not active_pairs:
            emb2.description = "Belum ada pasangan streak aktif."
        else:
            lines = []
            for p in active_pairs:
                u1 = p["user1_id"]
                u2 = p["user2_id"]
                pair = ensure_restore_cycle(p)

                streak = pair["current_streak"]
                last = pair["last_update_date"]
                needs = pair.get("needs_restore", 0)
                deadline = pair.get("restore_deadline")

                emoji = get_display_emoji(self.bot, guild_id, streak)

                if needs == 1:
                    stat = f"⚠️ RESTORE (deadline {deadline})"
                else:
                    stat = "ACTIVE"

                lines.append(
                    f"{emoji} <@{u1}> × <@{u2}> — `{streak}x` ({stat})\n"
                    f"Terakhir nyala: `{last}`"
                )

            emb2.description = "\n\n".join(lines)

        # ================================
        # 3) WHO HAS NOT LIT TODAY
        # ================================
        emb3 = discord.Embed(
            title="📅 Yang Belum Nyalain Api Hari Ini",
            colour=discord.Colour.red()
        )

        if not active_pairs:
            emb3.description = "Tidak ada pasangan streak aktif."
        else:
            pending_today = []

            for p in active_pairs:
                row = ensure_restore_cycle(p)
                last = row["last_update_date"]

                if isinstance(last, str):
                    try:
                        last = datetime.strptime(last, "%Y-%m-%d").date()
                    except:
                        last = today

                if last != today:  # belum nyala hari ini
                    emoji = get_display_emoji(self.bot, guild_id, row["current_streak"])
                    pending_today.append(
                        f"{emoji} <@{row['user1_id']}> × <@{row['user2_id']}>"
                        f"\nLast: `{row['last_update_date']}`\n"
                    )

            if not pending_today:
                emb3.description = "🎉 Semua pasangan sudah menyalakan api hari ini!"
            else:
                emb3.description = "\n".join(pending_today)

        # ================================
        # SEND PAGINATION
        # ================================
        pages = [emb1, emb2, emb3]
        view = InfoPagination(pages)
        await ctx.send(embed=pages[0], view=view)
    # ----- mstreak request @user -----

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
                f"{member.mention}, ketik `mstreak accept` {ctx.author.mention} untuk menerima."
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

    # ----- mstreak accept @user -----

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

    # ----- mstreak deny @user -----

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

    # ----- mstreak restore @user -----

    @streak_group.command(name="restore")
    async def streak_restore(self, ctx, member: discord.Member):
        guild_id = ctx.guild.id

        pair = get_streak_pair(guild_id, ctx.author.id, member.id)

        # ★ AUTO GAP SYSTEM
        pair = auto_process_gap(pair)

        if not pair:
            return await ctx.send("Pasangan streak tidak ditemukan.")

        # ★ Sudah mati → tidak bisa restore
        if pair["status"] == "BROKEN":
            return await ctx.send(
                "💀 Terlambat restore. Streak sudah mati total."
            )

        if pair["status"] != "ACTIVE":
            return await ctx.send(
                f"Pasangan streak belum ACTIVE (status: `{pair['status']}`)."
            )

        # ★ Tidak butuh restore
        if pair.get("needs_restore", 0) != 1:
            return await ctx.send(
                "⚠️ Pasangan ini tidak membutuhkan restore (gap hari bukan 2)."
            )
        
        # ★ APPLY RESTORE
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
            if result.get("reason") == "restore_quota_reached":
                kill_streak_due_to_deadline(pair["id"])
                dead = get_streak_pair(guild_id, pair["user1_id"], pair["user2_id"])
                await ctx.send("💀 Streak kalian mati karena kuota restore sudah habis (5x/bulan).")
                await self.send_streak_dead(ctx.guild, dead)
                return

            return await ctx.send(f"❌ Gagal restore ({result['reason']}).")

        
        before = result["before"]

        # ★ CLEAR RESTORE FLAGS
        clear_restore_flags(pair["id"])

        new_pair = result["pair"]
        emoji = get_display_emoji(self.bot, guild_id, new_pair["current_streak"])

        # --- Hitung sisa restore bulan ini ---
        pair_after = ensure_restore_cycle(new_pair)
        used = pair_after.get("restore_used_this_cycle", 0) or 0
        left = max(0, 5 - used)

        # === Kirim teks sederhana (opsional) ===
        await ctx.send(
            f"{emoji} **RESTORE BERHASIL!** Streak {format_pair_mention(new_pair)}"
            f"\nDari **{before if 'before' in result else new_pair['current_streak'] - 1}** ➜ **{new_pair['current_streak']}**"
            f"\n(gap: {result['delta_days']})"
            f"\n♻️ Sisa restore bulan ini: **{left} / 5**"
        )

        # === Kirim EMBED + CARD seperti reaction-update ===
        guild = ctx.guild
        log_channel_id = get_streak_settings(guild.id).get("log_channel_id")
        log_channel = guild.get_channel(log_channel_id) if log_channel_id else None

        if log_channel:
            author = ctx.author
            partner_id = new_pair["user1_id"] if author.id == new_pair["user2_id"] else new_pair["user2_id"]
            partner = guild.get_member(partner_id)

            # avatar
            pfp1 = author.display_avatar.with_size(512).with_format("png").url
            pfp2 = partner.display_avatar.with_size(512).with_format("png").url

            # emoji tier
            emoji_id = get_emoji_for_streak(guild.id, new_pair["current_streak"])
            emoji_url = None
            if emoji_id:
                e = self.bot.get_emoji(emoji_id)
                if e and hasattr(e, "url"):
                    emoji_url = e.url

            # generate card
            card = await make_streak_card(pfp1, pfp2, emoji_url, new_pair["current_streak"])
            file = discord.File(card, filename="streak_restore.png")

            # embed info
            embed = discord.Embed(
                title=f"{emoji} Restore Streak",
                description=format_pair_mention(new_pair),
                colour=discord.Colour.green()
            )
            embed.set_image(url="attachment://streak_restore.png")
            embed.add_field(name="Gap Hari", value=str(result["delta_days"]), inline=True)
            embed.add_field(name="Sisa Restore Bulan Ini", value=f"{left} / 5", inline=True)

            await log_channel.send(file=file, embed=embed)

    # ----- mstreak top -----

    @streak_group.command(name="top")
    async def streak_top(self, ctx: commands.Context):
        """Leaderboard pasangan streak aktif di server ini."""
        guild_id = ctx.guild.id
        rows = get_active_streaks(guild_id, limit=10, offset=0, order_by="current")
        if not rows:
            return await ctx.send("Belum ada pasangan streak aktif di server ini.")

        lines = []
        for i, row in enumerate(rows, start=1):
            streak = row["current_streak"]

            # --- Ambil emoji custom untuk streak ini ---
            custom_id = get_emoji_for_streak(guild_id, streak)
            if custom_id:
                custom_obj = self.bot.get_emoji(custom_id)
                emoji = str(custom_obj) if custom_obj else f"<:e:{custom_id}>"
            else:
                emoji, _ = get_flame_tier(streak)

            # Gunakan tier teks default tetap sama
            _, tier = get_flame_tier(streak)

            lines.append(
                f"**#{i}** {emoji} {format_pair_mention(row)} — "
                f"`{streak}x` (Max {row['max_streak']}, {tier})"
            )

        embed = discord.Embed(
            title="🔥 Top Streak Pairs",
            description="\n".join(lines),
            colour=discord.Colour.orange()
        )
        await ctx.send(embed=embed)


    # ----- mstreak setchannel -----

    @streak_group.command(name="setchannel")
    async def streak_setchannel(self, ctx: commands.Context, tipe: str, channel: discord.TextChannel):
        """
        Set channel streak:
        - mstreak setchannel command #streak
        - mstreak setchannel log #streak-log
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


    # ----- mstreak pending -----

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



    @commands.command(name="helpstreak", extras={"category": "Streak"})
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
                f"• `{prefix}streak info` — lihat daftar streak server."
                f"• `{prefix}streak myinfo` — lihat daftar streak pribadi."
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
