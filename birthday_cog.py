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
def generate_birthday_image(display_name: str, output_path="media/birthday_render.png"):
    from PIL import Image, ImageDraw, ImageFont
    import os

    # ============ Gambar Base ============
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    img_path = os.path.join(BASE_DIR, "..", "media", "ultahkos.png")
    base = Image.open(img_path).convert("RGBA")

    # Resize agar tidak terlalu besar (fix teks terlihat kecil)
    base = base.resize((1536, 1024), Image.LANCZOS)
    W, H = base.size

    draw = ImageDraw.Draw(base)

    # ============ Batasi nama max 10 karakter ============
    display_name = display_name.strip()
    if len(display_name) > 5:
        display_name = display_name[:5]

    # ============ Load Font ============
    font_path = os.path.join(BASE_DIR, "..", "assets", "Inter.ttf")

    if os.path.isfile(font_path):
        font = ImageFont.truetype(font_path, 180)
    else:
        print("⚠️ Font tidak ditemukan:", font_path)
        font = ImageFont.load_default()


    if os.path.isfile(font_path):
        font = ImageFont.truetype(font_path, 180)
    else:
        print("⚠️ Font tidak ditemukan, menggunakan default.")
        font = ImageFont.truetype("arial.ttf", 180)

    text = display_name

    # Hitung ukuran teks
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]

    # ============ POSISI PERSIS DI BAWAH 'Selamat Ulang Tahun' ============
    # (Dari gambar kamu, area tulisan Selamat Ulang Tahun ada di sekitar 40%–50%)
    pos_x = (W - text_w) // 2
    pos_y = int(H * 0.50)   # tweak halus → pas banget di bawah tulisan besar

    # ============ Teks dengan Outline ============
    draw.text(
        (pos_x, pos_y),
        text,
        font=font,
        fill=(250, 198, 62),   # warna #fac63e
        stroke_width=3,
        stroke_fill="black"
    )

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
            title=f"📅 Daftar Ulang Tahun (Halaman {page+1}/{len(self.chunks)})",
            color=discord.Color.blue()
        )

        for _, birthdate, display_name, wish in self.chunks[page]:
            desc = birthdate.strftime("%d %B")
            if wish:
                desc += f"\n💬 _{wish}_"
            embed.add_field(name=display_name, value=desc, inline=False)

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

        for user_id, guild_id, display_name, wish in birthdays:
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
            img_path = generate_birthday_image(display_name)
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
    @commands.command(name="setbirthday")
    async def set_birthday_cmd(self, ctx, *, arg: str = None):
        if not arg:
            return await ctx.send("❗ Format salah. Contoh: `mad setbirthday 21-06 -wish Semoga sehat selalu!`")

        arg = arg.strip()
        wish = None

        # flag -wish
        wish_match = re.search(r"-wish\s+(.+)", arg)
        if wish_match:
            wish = wish_match.group(1).strip()
            arg = arg[:wish_match.start()].strip()

        user_id = ctx.author.id
        display_name = ctx.author.display_name

        if re.fullmatch(r"\d{2}-\d{2}(?:-\d{4})?", arg):
            date_str = arg

        else:
            mention_match = re.match(r"<@!?(\d+)>\s+(\d{2}-\d{2}(?:-\d{4})?)$", arg)
            if mention_match:
                user_id = int(mention_match.group(1))
                date_str = mention_match.group(2)
                member = ctx.guild.get_member(user_id)
                display_name = member.display_name if member else f"user-{user_id}"

            else:
                parts = arg.rsplit(" ", 1)
                if len(parts) != 2:
                    return await ctx.send("❗ Format salah!")

                name, date_str = parts
                member = discord.utils.find(lambda m: name.lower() in m.display_name.lower(), ctx.guild.members)

                if member:
                    user_id = member.id
                    display_name = member.display_name
                else:
                    user_id = abs(hash(name.lower())) % (10**18)
                    display_name = name

        # parse tanggal
        try:
            parts = date_str.split("-")
            day = int(parts[0])
            month = int(parts[1])
            year = int(parts[2]) if len(parts) == 3 else 2000
            birthdate = datetime(year, month, day).date()
        except:
            return await ctx.send("❗ Format tanggal salah. Gunakan `dd-mm` atau `dd-mm-yyyy`.")

        # simpan
        db = connect_db()
        set_birthday(db, user_id, ctx.guild.id, birthdate, display_name, wish)
        db.close()

        msg = f"🎉 Ulang tahun untuk **{display_name}** disimpan: `{birthdate.strftime('%d %B')}`"
        if wish:
            msg += f"\n💬 _{wish}_"
        await ctx.send(msg)

    # =========================================================
    # COMMAND: My Birthday
    # =========================================================
    @commands.command(name="mybirthday")
    async def my_birthday(self, ctx):
        db = connect_db()
        result = get_birthday(db, ctx.author.id, ctx.guild.id)
        db.close()

        if not result:
            return await ctx.send("❌ Kamu belum menyimpan tanggal ulang tahun.")

        birthdate, _, wish = result
        msg = f"🎂 Ulang tahun kamu: `{birthdate.strftime('%d %B %Y')}`"
        if wish:
            msg += f"\n💬 _{wish}_"
        await ctx.send(msg)

    # =========================================================
    # COMMAND: Delete Birthday
    # =========================================================
    @commands.command(name="deletebirthday")
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
    @commands.command(name="birthdaylist")
    async def birthdaylist(self, ctx):
        db = connect_db()
        rows = get_all_birthdays(db, ctx.guild.id)
        db.close()

        if not rows:
            return await ctx.send("📭 Belum ada data ulang tahun.")

        chunks = [rows[i:i+10] for i in range(0, len(rows), 10)]
        view = BirthdayView(ctx, chunks)
        await view.send_initial()

    # =========================================================
    # COMMAND: Nearest Birthday
    # =========================================================
    @commands.command(name="nearestbirthday")
    async def nearest_birthday(self, ctx):
        db = connect_db()
        rows = get_all_birthdays(db, ctx.guild.id)
        db.close()

        if not rows:
            return await ctx.send("📭 Tidak ada data.")

        today = datetime.now(JAKARTA_TZ).date()
        closest = None
        min_diff = 999

        for _, birthdate, display_name, _ in rows:
            bday = birthdate.replace(year=today.year)
            if bday < today:
                bday = bday.replace(year=today.year + 1)
            diff = (bday - today).days
            if diff < min_diff:
                min_diff = diff
                closest = (display_name, birthdate)

        name, bdate = closest
        await ctx.send(f"⏰ Ulang tahun terdekat: **{name}** → `{bdate.strftime('%d %B')}` (dalam {min_diff} hari).")

    # =========================================================
    # COMMAND: Test Birthday (DEBUG)
    # =========================================================
    @commands.command(name="testbirthday")
    async def test_birthday(self, ctx):
        """Debug: kirim ucapan ulang tahun untuk pengguna dengan tanggal terdekat."""

        db = connect_db()
        rows = get_all_birthdays(db, ctx.guild.id)
        db.close()

        if not rows:
            return await ctx.send("📭 Tidak ada data ulang tahun untuk dites.")

        today = datetime.now(JAKARTA_TZ).date()
        closest = None
        min_diff = 999

        # Cari ulang tahun terdekat
        for user_id, birthdate, display_name, wish in rows:
            bday = birthdate.replace(year=today.year)
            if bday < today:
                bday = bday.replace(year=today.year + 1)

            diff = (bday - today).days
            if diff < min_diff:
                min_diff = diff
                closest = (user_id, birthdate, display_name, wish)

        user_id, birthdate, display_name, wish = closest
        guild = ctx.guild
        member = guild.get_member(user_id)

        # pakai display_name user asli kalau ada
        if member:
            display_name = member.display_name

        # =============================
        # AMBIL CHANNEL ULTAH
        # =============================
        db = connect_db()
        ch_id = get_channel_settings(db, guild.id, "birthday")
        db.close()

        channel = guild.get_channel(int(ch_id)) if ch_id else ctx.channel
        # fallback: kalau channel ulang tahun belum diset → kirim ke channel tempat command dipakai

        # =============================
        # GENERATE GAMBAR
        # =============================
        img_path = generate_birthday_image(display_name)
        unique = f"birthday_{int(datetime.now().timestamp())}.png"
        file = discord.File(img_path, filename=unique)
        content = f"🎉 Selamat ulang tahun {member.mention}!! 🎂"

        # =============================
        # BIKIN EMBED KEKINIAN
        # =============================
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

        # =============================
        # KIRIM
        # =============================
        await ctx.send("🔧 **DEBUG:** Mengirim simulasi ucapan ulang tahun…")
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

    @commands.command(name="setbirthdaych")
    async def set_birthday_channel(self, ctx, channel: discord.TextChannel):
        if ctx.author.id not in [ctx.guild.owner_id, 416234104317804544]:
            return await ctx.send("❌ Kamu tidak punya izin.")

        db = connect_db()
        set_channel_settings(db, ctx.guild.id, "birthday", channel.id)
        db.close()

        await ctx.send(f"✅ Channel ulang tahun diset ke {channel.mention}")

    @commands.command(name="testclock")
    async def test_clock(self, ctx):
        now = datetime.now(JAKARTA_TZ)
        await ctx.send(f"🕒 Waktu WIB sekarang: `{now.strftime('%Y-%m-%d %H:%M:%S')}`")
