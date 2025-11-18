import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from datetime import datetime, timedelta, time as dt_time
import pytz
import re
import asyncio

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


# ================================
# VIEW UNTUK PAGING
# ================================
class BirthdayView(View):
    def __init__(self, ctx, chunks):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.chunks = chunks
        self.current_page = 0
        self.message = None

        btn_prev = Button(label="⬅️ Previous", style=discord.ButtonStyle.secondary)
        btn_prev.callback = self.prev_page
        self.add_item(btn_prev)

        btn_next = Button(label="➡️ Next", style=discord.ButtonStyle.secondary)
        btn_next.callback = self.next_page
        self.add_item(btn_next)

    async def send_initial(self):
        embed = self.make_embed(self.current_page)
        self.message = await self.ctx.send(embed=embed, view=self)

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



# ================================
# BIRTHDAY COG ULTRA EDITION
# ================================
class Birthday(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.birthday_loop.start()

    # LOOP SUPER AKURAT JAM 00:00 WIB
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

            # Ambil channel birthday
            ch_id = get_channel_settings(connect_db(), guild_id, "birthday")
            channel = guild.get_channel(int(ch_id)) if ch_id else guild.system_channel

            if channel:
                member = guild.get_member(user_id)

                # nama tampil persis seperti display_name
                if member:
                    display_name = member.display_name
                else:
                    display_name = display_name  # fallback dari DB

                # ========== EMBED ULANG TAHUN PREMIUM DENGAN GAMBAR ==========
                embed = discord.Embed(
                    title="🎉 Selamat Ulang Tahun! 🎂",
                    description=f"**{display_name}**",
                    color=discord.Color.gold()
                )

                # tambahkan tanggal
                today_str = datetime.now(JAKARTA_TZ).strftime("%d %B %Y")
                embed.add_field(name="📅 Tanggal", value=f"`{today_str}`", inline=True)

                # wish kalau ada
                if wish:
                    embed.add_field(name="💌 Pesan Spesial", value=f"_{wish}_", inline=False)

                # avatar
                if member and member.avatar:
                    embed.set_thumbnail(url=member.avatar.url)

                # attach file image banner ultah
                file = discord.File("media/ultahkos.png", filename="ultahkos.png")
                embed.set_image(url="attachment://ultahkos.png")

                embed.set_footer(text=f"Dirayakan oleh {guild.name}")
                embed.timestamp = datetime.utcnow()

                await channel.send(file=file, embed=embed)

    @birthday_loop.before_loop
    async def before_loop(self):
        print("⏳ Birthday loop waiting for bot to be ready...")
        await self.bot.wait_until_ready()
        print("✅ Birthday loop activated at next 00:00 WIB.")

    # ================================
    # COMMANDS
    # ================================

    @commands.command(name="setbirthday")
    async def set_birthday_cmd(self, ctx, *, arg: str = None):
        if not arg:
            return await ctx.send("❗ Format salah. Contoh: `mad setbirthday 21-06 -wish Semoga sehat selalu!`")

        arg = arg.strip()
        wish = None

        # Ambil flag -wish
        wish_match = re.search(r"-wish\s+(.+)", arg)
        if wish_match:
            wish = wish_match.group(1).strip()
            arg = arg[:wish_match.start()].strip()

        user_id = ctx.author.id
        display_name = ctx.author.display_name

        # ================================
        # CASE 1 — user sendiri (dd-mm / dd-mm-yyyy)
        # ================================
        if re.fullmatch(r"\d{2}-\d{2}(?:-\d{4})?", arg):
            date_str = arg

        else:
            # ================================
            # CASE 2 — mention format
            # ================================
            mention_match = re.match(r"<@!?(\d+)>\s+(\d{2}-\d{2}(?:-\d{4})?)$", arg)
            if mention_match:
                user_id = int(mention_match.group(1))
                date_str = mention_match.group(2)
                member = ctx.guild.get_member(user_id)
                display_name = member.display_name if member else f"user-{user_id}"

            else:
                # ================================
                # CASE 3 — nama manual + tanggal
                # ================================
                parts = arg.rsplit(" ", 1)
                if len(parts) != 2:
                    return await ctx.send("❗ Format salah!")

                name, date_str = parts
                member = discord.utils.find(lambda m: name.lower() in m.display_name.lower(), ctx.guild.members)

                if member:
                    user_id = member.id
                    display_name = member.display_name
                else:
                    # fallback pseudo ID
                    user_id = abs(hash(name.lower())) % (10**18)
                    display_name = name

        # ================================
        # PARSE TANGGAL (tahun opsional)
        # ================================
        try:
            parts = date_str.split("-")
            day = int(parts[0])
            month = int(parts[1])
            year = int(parts[2]) if len(parts) == 3 else 2000  # dummy year
            birthdate = datetime(year, month, day).date()
        except:
            return await ctx.send("❗ Format tanggal salah. Gunakan `dd-mm` atau `dd-mm-yyyy`.")

        # ================================
        # SIMPAN KE DB
        # ================================
        db = connect_db()
        set_birthday(db, user_id, ctx.guild.id, birthdate, display_name, wish)
        db.close()

        msg = f"🎉 Ulang tahun untuk **{display_name}** disimpan: `{birthdate.strftime('%d %B')}`"
        if wish:
            msg += f"\n💬 _{wish}_"
        await ctx.send(msg)
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

    @commands.command(name="deletebirthday")
    async def delete_birthday_cmd(self, ctx, *, name: str = None):
        db = connect_db()

        # Hapus diri sendiri
        if not name:
            delete_birthday(db, ctx.author.id, ctx.guild.id)
            db.close()
            return await ctx.send("🗑️ Ulang tahun kamu dihapus.")

        # Izin admin
        allowed = [ctx.guild.owner_id, 416234104317804544]
        if ctx.author.id not in allowed:
            db.close()
            return await ctx.send("❌ Kamu tidak punya izin.")

        # Mention
        mention = re.match(r"<@!?(\d+)>", name)
        if mention:
            user_id = int(mention.group(1))
        else:
            # Cari member berdasarkan display name
            member = discord.utils.find(lambda m: name.lower() in m.display_name.lower(), ctx.guild.members)
            if member:
                user_id = member.id
            else:
                # Cari langsung di DB
                rows = get_all_birthdays(db, ctx.guild.id)
                match = next((r for r in rows if r[2].lower() == name.lower()), None)
                if not match:
                    db.close()
                    return await ctx.send("❌ Tidak ditemukan.")
                user_id = match[0]

        delete_birthday(db, user_id, ctx.guild.id)
        db.close()
        await ctx.send(f"🗑️ Ulang tahun **{name}** dihapus.")

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

        # cari ulang tahun terdekat (tanpa tunggu tanggal asli)
        for user_id, birthdate, display_name, wish in rows:
            bday = birthdate.replace(year=today.year)
            if bday < today:
                bday = bday.replace(year=today.year + 1)
            diff = (bday - today).days
            if diff < min_diff:
                min_diff = diff
                closest = (user_id, display_name, wish)

        user_id, display_name, wish = closest
        guild = ctx.guild
        member = guild.get_member(user_id)

        if member:
            display_name = member.display_name
            mention = member.mention
        else:
            mention = f"**{display_name}**"

        # UCAPAN ULTAH (SAMA KAYA LOOP ASLI)
        embed = discord.Embed(
            title="🎉 Selamat Ulang Tahun! 🎂",
            description=f"**{display_name}**",
            color=discord.Color.gold()
        )

        today_str = datetime.now(JAKARTA_TZ).strftime("%d %B %Y")
        embed.add_field(name="📅 Tanggal", value=f"`{today_str}`", inline=True)

        if wish:
            embed.add_field(name="💌 Pesan Spesial", value=f"_{wish}_", inline=False)

        if member and member.avatar:
            embed.set_thumbnail(url=member.avatar.url)

        # attach banner ulang tahun
        file = discord.File("media/ultahkos.png", filename="ultahkos.png")
        embed.set_image(url="attachment://ultahkos.png")

        embed.set_footer(text=f"Dirayakan oleh {guild.name}")
        embed.timestamp = datetime.utcnow()

        await ctx.send("🔧 **DEBUG:** Mengirim simulasi ucapan ulang tahun…")
        await ctx.send(file=file, embed=embed)


    @commands.command(name="testclock")
    async def test_clock(self, ctx):
        now = datetime.now(JAKARTA_TZ)
        await ctx.send(f"🕒 Waktu WIB sekarang: `{now.strftime('%Y-%m-%d %H:%M:%S')}`")
