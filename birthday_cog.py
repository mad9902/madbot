import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from datetime import datetime, timedelta, time as dt_time
import pytz
import re
import asyncio
from PIL import Image, ImageDraw, ImageFont
import textwrap
import os
import aiohttp
from io import BytesIO

from database import (
    connect_db,
    set_birthday,
    get_birthday,
    delete_birthday,
    get_today_birthdays,
    get_channel_settings,
    get_all_birthdays,
    set_channel_settings
)

JAKARTA_TZ = pytz.timezone("Asia/Jakarta")

# ================================================================
#  PERSONALIZED BIRTHDAY IMAGE GENERATOR
# ================================================================
# def generate_birthday_image(display_name: str, output_path="media/birthday_render.png"):
#     from PIL import Image, ImageDraw, ImageFont
#     import os

#     # ============ Gambar Base ============
#     BASE_DIR = os.getcwd()
#     img_path = os.path.join(BASE_DIR, "..", "media", "ultahkos.png")
#     base = Image.open(img_path).convert("RGBA")

#     # Resize agar tidak terlalu besar (fix teks terlihat kecil)
#     base = base.resize((1536, 1024), Image.LANCZOS)
#     W, H = base.size

#     draw = ImageDraw.Draw(base)

#     # ============ Batasi nama max 10 karakter ============
#     display_name = display_name.strip()
#     if len(display_name) > 5:
#         display_name = display_name[:5]

#     # ============ Load Font ============
#     font_path = os.path.join(BASE_DIR, "..", "assets", "Inter.ttf")

#     if os.path.isfile(font_path):
#         font = ImageFont.truetype(font_path, 180)
#     else:
#         print("⚠️ Font tidak ditemukan:", font_path)
#         font = ImageFont.load_default()


#     if os.path.isfile(font_path):
#         font = ImageFont.truetype(font_path, 180)
#     else:
#         print("⚠️ Font tidak ditemukan, menggunakan default.")
#         font = ImageFont.truetype("arial.ttf", 180)

#     text = display_name

#     # Hitung ukuran teks
#     bbox = draw.textbbox((0, 0), text, font=font)
#     text_w = bbox[2] - bbox[0]

#     # ============ POSISI PERSIS DI BAWAH 'Selamat Ulang Tahun' ============
#     # (Dari gambar kamu, area tulisan Selamat Ulang Tahun ada di sekitar 40%–50%)
#     pos_x = (W - text_w) // 2
#     pos_y = int(H * 0.50)   # tweak halus → pas banget di bawah tulisan besar

#     # ============ Teks dengan Outline ============
#     draw.text(
#         (pos_x, pos_y),
#         text,
#         font=font,
#         fill=(250, 198, 62),   # warna #fac63e
#         stroke_width=3,
#         stroke_fill="black"
#     )

#     base.save(output_path)
#     return output_path

async def generate_birthday_image(display_name: str, template_url=None, output_path="media/birthday_render.png"):
    BASE_DIR = os.getcwd()
    original_url = template_url  # simpan yang asli untuk deteksi custom

    # ========== Fix extension .jpeg → .jpg (Imgur lebih suka .jpg) ==========
    # Convert .jpeg -> .jpg ONLY for Imgur
    if template_url:
        lower = template_url.lower()
        if ("imgur.com" in lower or "i.imgur.com" in lower) and lower.endswith(".jpeg"):
            template_url = template_url[:-5] + ".jpg"

    # ==========================================
    # DOWNLOAD CUSTOM TEMPLATE
    # ==========================================
    base = None
    if template_url:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "image/*"
            }

            async with aiohttp.ClientSession(headers=headers) as s:
                async with s.get(template_url, allow_redirects=True) as r:

                    print("DEBUG TEMPLATE:", template_url, "STATUS:", r.status)

                    if r.status != 200:
                        raise Exception(f"Download gagal: HTTP {r.status}")

                    data = await r.read()

                    # PIL auto-detect format
                    base = Image.open(BytesIO(data)).convert("RGBA")

        except Exception as e:
            print("❌ Gagal download template custom:", e)
            base = None

    # ========== fallback default ==========
    if base is None:
        base = Image.open(os.path.join(BASE_DIR, "media", "ultahkos.png")).convert("RGBA")

    # ========== Resize otomatis ==========
    MAX_W, MAX_H = 1536, 1536
    base.thumbnail((MAX_W, MAX_H), Image.LANCZOS)

    W, H = base.size
    draw = ImageDraw.Draw(base)

    # ==========================================
    # IF CUSTOM TEMPLATE → NO NAME TEXT
    # ==========================================
    if original_url:  # <— pake yang asli, bukan yang di-edit
        output_path = os.path.join(BASE_DIR, output_path)
        base.save(output_path)
        return output_path

    # ==========================================
    # DEFAULT TEMPLATE → Tulis Nama
    # ==========================================
    display_name = display_name.strip()[:10]

    font_path = os.path.join(BASE_DIR, "assets", "Inter.ttf")
    if os.path.isfile(font_path):
        font = ImageFont.truetype(font_path, 130)
    else:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), display_name, font=font)
    text_w = bbox[2] - bbox[0]

    pos_x = (W - text_w) // 2
    pos_y = int(H * 0.50)

    draw.text(
        (pos_x, pos_y),
        display_name,
        font=font,
        fill=(250, 198, 62),
        stroke_width=3,
        stroke_fill="black"
    )

    output_path = os.path.join(BASE_DIR, output_path)
    base.save(output_path)
    return output_path

# ================================================================
# VIEW PAGING
# ================================================================
class BirthdayView(View):
    def __init__(self, ctx, chunks):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.chunks = chunks
        self.current_page = 0

        btn_prev = Button(label="⬅️ Previous", style=discord.ButtonStyle.secondary)
        btn_prev.callback = self.prev_page
        self.add_item(btn_prev)

        btn_next = Button(label="➡️ Next", style=discord.ButtonStyle.secondary)
        btn_next.callback = self.next_page
        self.add_item(btn_next)

    async def send_initial(self):
        embed = self.make_embed(self.current_page)
        await self.ctx.send(embed=embed, view=self)

    def make_embed(self, page):
        embed = discord.Embed(
            title=f"🎂 Daftar Ulang Tahun — Halaman {page+1}/{len(self.chunks)}",
            color=discord.Color.gold()
        )

        today = datetime.now(JAKARTA_TZ).date()
        rows = self.chunks[page]

        for index, row in enumerate(rows, start=1):
            user_id, birthdate, display_name, wish, template_url = row
            user_mention = f"<@{user_id}>"
            date_str = birthdate.strftime("%d %B")

            # --- hitung countdown ---
            this_year = birthdate.replace(year=today.year)
            if this_year < today:
                this_year = this_year.replace(year=today.year + 1)

            diff = (this_year - today).days

            if diff == 0:
                countdown = "🎉 **Hari ini!**"
            elif diff == 1:
                countdown = "⏳ **Besok (1 hari lagi)**"
            else:
                countdown = f"⏳ **{diff} hari lagi**"

            # --- format rapi ---
            value = (
                f"👤 **User:** {user_mention}\n"
                f"📅 **Tanggal:** `{date_str}`\n"
                f"{countdown}\n"
            )

            if wish:
                value += f"💌 **Wish:** _{wish}_\n"

            if template_url:
                value += "🖼️ **Custom template:** ✔️\n"

            # garis pemisah antar user
            value += "───"

            embed.add_field(
                name=f"**#{index}** — 🎉 {display_name}",
                value=value,
                inline=False
            )

        embed.set_footer(text="Gunakan mad nearestbirthday untuk melihat yang terdekat ✨")
        return embed

    async def prev_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.make_embed(self.current_page), view=self)

    async def next_page(self, interaction: discord.Interaction):
        if self.current_page < len(self.chunks)-1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.make_embed(self.current_page), view=self)


# ================================================================
# BIRTHDAY MAIN COG
# ================================================================
class Birthday(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.birthday_loop.start()

    # LOOP JAM 00:00 WIB (saat ini debug jam 17:00)
    @tasks.loop(time=dt_time(17, 0))
    async def birthday_loop(self):
        print("🔔 Running birthday check at 00:00 WIB...")

        db = connect_db()
        birthdays = get_today_birthdays(db)
        db.close()

        for user_id, guild_id, display_name, wish, template_url in birthdays:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            ch_id = get_channel_settings(connect_db(), guild_id, "birthday")
            channel = guild.get_channel(int(ch_id)) if ch_id else guild.system_channel

            if not channel:
                continue

            member = guild.get_member(user_id)

            if member:
                display_name = member.display_name

            # GENERATE GAMBAR
            img_path = await generate_birthday_image(display_name, template_url)
            unique = f"birthday_{int(datetime.now().timestamp())}.png"
            file = discord.File(img_path, filename=unique)
            content = f"🎉 Selamat ulang tahun {member.mention}!! 🎂"

            # EMBED (dengan mention)
            embed = discord.Embed(
                title="🎉 Selamat Ulang Tahun! 🎂",
                description=f"{member.mention if member else f'**{display_name}**'}",
                color=discord.Color.gold()
            )

            today_str = datetime.now(JAKARTA_TZ).strftime("%d %B %Y")
            embed.add_field(name="📅 Tanggal", value=f"`{today_str}`", inline=True)

            if wish:
                embed.add_field(name="💌 Pesan Spesial", value=f"_{wish}_", inline=False)

            if member and member.avatar:
                embed.set_thumbnail(url=member.avatar.url)

            embed.set_image(url=f"attachment://{unique}")
            embed.set_footer(text=f"Dirayakan oleh {guild.name}")
            embed.timestamp = datetime.utcnow()

            await channel.send(
                content=content,
                file=file,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    users=True,
                    roles=False,
                    everyone=True,
                    replied_user=True
                )
            )




    @birthday_loop.before_loop
    async def before_loop(self):
        print("⏳ Birthday loop waiting for bot to be ready...")
        await self.bot.wait_until_ready()
        print("✅ Birthday loop activated at next 00:00 WIB.")

    # =========================================================
    # COMMAND: Set Birthday
    # =========================================================
    @commands.command(name="setbirthday", extras={"category": "Birthday"})
    async def set_birthday_cmd(self, ctx, *, arg: str = None):
        if not arg:
            return await ctx.send("❗ Format: `mad setbirthday @user 21-06 -wish text -img https://link.png`")

        arg = arg.strip()
        wish = None
        template_url = None

        # ----- parse -wish -----
        wish_match = re.search(r"-wish\s+(.+?)(?=\s+-img|$)", arg)
        if wish_match:
            wish = wish_match.group(1).strip()
            arg = arg.replace(wish_match.group(0), "").strip()

        # ----- parse -img -----
        img_match = re.search(r"-img\s+(https?://\S+)", arg)
        if img_match:
            template_url = img_match.group(1).strip()
            arg = arg.replace(img_match.group(0), "").strip()

        # ----- parse tanggal + user -----
        user_id = ctx.author.id
        display_name = ctx.author.display_name

        mention_match = re.match(r"<@!?(\d+)>\s+(\d{2}-\d{2}(?:-\d{4})?)$", arg)
        if mention_match:
            user_id = int(mention_match.group(1))
            date_str = mention_match.group(2)
            member = ctx.guild.get_member(user_id)
            display_name = member.display_name if member else f"user-{user_id}"
        else:
            # fallback user sendiri
            date_str = arg

        # ----- parse tanggal -----
        try:
            d,m,*y = date_str.split("-")
            y = int(y[0]) if y else 2000
            birthdate = datetime(int(y), int(m), int(d)).date()
        except:
            return await ctx.send("❗ Format tanggal salah! (dd-mm atau dd-mm-yyyy)")

        # ----- save ke DB -----
        db = connect_db()
        set_birthday(db, user_id, ctx.guild.id, birthdate, display_name, wish, template_url)
        db.close()

        msg = f"🎉 Birthday **{display_name}** disimpan!"
        if wish: msg += f"\n💬 _{wish}_"
        if template_url: msg += f"\n🖼️ Custom template: {template_url}"

        await ctx.send(msg)

    # =========================================================
    # COMMAND: My Birthday
    # =========================================================
    @commands.command(name="mybirthday", extras={"category": "Birthday"})
    async def my_birthday(self, ctx):
        db = connect_db()
        result = get_birthday(db, ctx.author.id, ctx.guild.id)
        db.close()

        if not result:
            return await ctx.send("❌ Kamu belum menyimpan tanggal ulang tahun.")

        birthdate, display_name, wish, template_url = result
        msg = f"🎂 Ulang tahun kamu: `{birthdate.strftime('%d %B %Y')}`"
        if wish:
            msg += f"\n💬 _{wish}_"
        if template_url:
            msg += f"\n🖼️ Custom template terpasang."

        await ctx.send(msg)

    # =========================================================
    # COMMAND: Delete Birthday
    # =========================================================
    @commands.command(name="deletebirthday", extras={"category": "Birthday"})
    async def delete_birthday_cmd(self, ctx, *, name: str = None):
        db = connect_db()

        if not name:
            delete_birthday(db, ctx.author.id, ctx.guild.id)
            db.close()
            return await ctx.send("🗑️ Ulang tahun kamu dihapus.")

        allowed = [ctx.guild.owner_id, 416234104317804544]
        if ctx.author.id not in allowed:
            db.close()
            return await ctx.send("❌ Kamu tidak punya izin.")

        mention = re.match(r"<@!?(\d+)>", name)
        if mention:
            user_id = int(mention.group(1))
        else:
            member = discord.utils.find(lambda m: name.lower() in m.display_name.lower(), ctx.guild.members)
            if member:
                user_id = member.id
            else:
                rows = get_all_birthdays(db, ctx.guild.id)
                match = next((r for r in rows if r[2].lower() == name.lower()), None)
                if not match:
                    db.close()
                    return await ctx.send("❌ Tidak ditemukan.")
                user_id = match[0]

        delete_birthday(db, user_id, ctx.guild.id)
        db.close()
        await ctx.send(f"🗑️ Ulang tahun **{name}** dihapus.")

    # =========================================================
    # COMMAND: Birthday List
    # =========================================================
    @commands.command(name="birthdaylist", extras={"category": "Birthday"})
    async def birthdaylist(self, ctx):
        db = connect_db()
        rows = get_all_birthdays(db, ctx.guild.id)
        db.close()

        if not rows:
            return await ctx.send("📭 Belum ada data ulang tahun.")

        today = datetime.now(JAKARTA_TZ).date()

        # ---------- SORT BY NEAREST ----------
        def nearest_sort(row):
            user_id, birthdate, display_name, wish, template_url = row

            bday_this_year = birthdate.replace(year=today.year)
            if bday_this_year < today:
                bday_this_year = bday_this_year.replace(year=today.year + 1)

            diff = (bday_this_year - today).days
            return diff

        rows.sort(key=nearest_sort)

        # ---------- PAGINATION SPLIT ----------
        chunks = [rows[i:i+10] for i in range(0, len(rows), 10)]

        view = BirthdayView(ctx, chunks)
        await view.send_initial()

    # =========================================================
    # COMMAND: Nearest Birthday
    # =========================================================
    @commands.command(name="nearestbirthday", extras={"category": "Birthday"})
    async def nearest_birthday(self, ctx):
        db = connect_db()
        rows = get_all_birthdays(db, ctx.guild.id)
        db.close()

        if not rows:
            return await ctx.send("📭 Tidak ada data.")

        today = datetime.now(JAKARTA_TZ).date()
        closest = None
        min_diff = 999

        for _, birthdate, display_name, wish, template_url in rows:
            bday = birthdate.replace(year=today.year)
            if bday < today:
                bday = bday.replace(year=today.year + 1)
            diff = (bday - today).days

            if diff < min_diff:
                min_diff = diff
                closest = (display_name, birthdate)

        name, bdate = closest
        await ctx.send(
            f"⏰ Ulang tahun terdekat: **{name}** → `{bdate.strftime('%d %B')}` (dalam {min_diff} hari)."
        )

    # =========================================================
    # COMMAND: Late Birthday
    # =========================================================
        # =========================================================
    # COMMAND: Late Birthday (Manual Trigger)
    # =========================================================
    @commands.command(name="latebirthday", extras={"category": "Birthday"})
    async def late_birthday(self, ctx, user: discord.Member):
        # ====== PERMISSION CHECK ======
        allowed = [ctx.guild.owner_id, 416234104317804544]
        if ctx.author.id not in allowed:
            return await ctx.send("❌ Kamu tidak punya izin.")

        # ====== FETCH DATA ======
        db = connect_db()
        result = get_birthday(db, user.id, ctx.guild.id)
        db.close()

        if not result:
            return await ctx.send("❌ User ini belum menyimpan tanggal ulang tahun.")

        birthdate, display_name, wish, template_url = result

        # update display name real-time
        display_name = user.display_name

        # ====== GENERATE IMAGE ======
        img_path = await generate_birthday_image(display_name, template_url)
        unique = f"birthday_{int(datetime.now().timestamp())}.png"
        file = discord.File(img_path, filename=unique)

        # ====== EMBED ======
        embed = discord.Embed(
            title="🎉 Selamat Ulang Tahun! Lebih baik telat daripada tidak sama sekali 🎂",
            description=f"{user.mention}",
            color=discord.Color.gold()
        )

        # format tanggal ulang tahun user
        bday_str = birthdate.strftime("%d %B")
        embed.add_field(name="📅 Tanggal Ulang Tahun", value=f"`{bday_str}`", inline=True)

        if wish:
            embed.add_field(name="💌 Wish", value=f"_{wish}_", inline=False)

        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)

        embed.set_image(url=f"attachment://{unique}")
        embed.set_footer(text=f"Manual dipicu oleh {ctx.author.display_name}")
        embed.timestamp = datetime.utcnow()

        # ====== SEND MESSAGE ======
        await ctx.send(
            content=f"🎉Selamat ulang tahun {user.mention}!! 🎂",
            file=file,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=True,
                replied_user=True
            )
        )
    # =========================================================
    # COMMAND: Test Birthday (DEBUG)
    # =========================================================
    @commands.command(name="testbirthday", extras={"category": "Birthday"})
    async def test_birthday(self, ctx):
        db = connect_db()
        rows = get_all_birthdays(db, ctx.guild.id)
        db.close()

        if not rows:
            return await ctx.send("📭 Tidak ada data ulang tahun untuk dites.")

        today = datetime.now(JAKARTA_TZ).date()
        closest = None
        min_diff = 999

        # Cari ulang tahun terdekat
        for user_id, birthdate, display_name, wish, template_url in rows:
            print("DEBUG TEMPLATE:", template_url)
            bday = birthdate.replace(year=today.year)
            if bday < today:
                bday = bday.replace(year=today.year + 1)

            diff = (bday - today).days
            if diff < min_diff:
                min_diff = diff
                closest = (user_id, birthdate, display_name, wish, template_url)

        user_id, birthdate, display_name, wish, template_url = closest
        guild = ctx.guild
        member = guild.get_member(user_id)

        # override nama biar sesuai display_name terkini
        if member:
            display_name = member.display_name

        # ambil channel ulang tahun
        db = connect_db()
        ch_id = get_channel_settings(db, guild.id, "birthday")
        db.close()

        channel = guild.get_channel(int(ch_id)) if ch_id else ctx.channel

        # ==== GENERATE GAMBAR ====
        img_path = await generate_birthday_image(display_name, template_url)
        unique = f"birthday_{int(datetime.now().timestamp())}.png"
        file = discord.File(img_path, filename=unique)

        content = f"🎉 (TEST) Selamat ulang tahun {member.mention}!! 🎂"

        # ==== EMBED ====
        embed = discord.Embed(
            title="🎉 Selamat Ulang Tahun! (TEST MODE) 🎂",
            description=f"{member.mention if member else f'**{display_name}**'}",
            color=discord.Color.gold()
        )

        today_str = datetime.now(JAKARTA_TZ).strftime("%d %B %Y")
        embed.add_field(name="📅 Tanggal", value=f"`{today_str}`", inline=True)

        if wish:
            embed.add_field(name="💌 Wish", value=f"_{wish}_", inline=False)

        if member and member.avatar:
            embed.set_thumbnail(url=member.avatar.url)

        embed.set_image(url=f"attachment://{unique}")
        embed.set_footer(text=f"Dirayakan oleh {guild.name}")
        embed.timestamp = datetime.utcnow()

        await ctx.send("🔧 **DEBUG:** Mengirim simulasi ulang tahun…")
        await channel.send(
            content=content,
            file=file,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                users=True,
                roles=False,
                everyone=True,
                replied_user=True
            )
        )

    # =========================================================
    # COMMAND: Check Time
    # =========================================================

    @commands.command(name="setbirthdaych", extras={"category": "Birthday"})
    async def set_birthday_channel(self, ctx, channel: discord.TextChannel):
        if ctx.author.id not in [ctx.guild.owner_id, 416234104317804544]:
            return await ctx.send("❌ Kamu tidak punya izin.")

        db = connect_db()
        set_channel_settings(db, ctx.guild.id, "birthday", channel.id)
        db.close()

        await ctx.send(f"✅ Channel ulang tahun diset ke {channel.mention}")

    @commands.command(name="testclock", extras={"category": "Birthday"})
    async def test_clock(self, ctx):
        now = datetime.now(JAKARTA_TZ)
        await ctx.send(f"🕒 Waktu WIB sekarang: `{now.strftime('%Y-%m-%d %H:%M:%S')}`")
