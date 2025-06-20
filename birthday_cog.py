import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
from datetime import datetime
import re
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

class BirthdayView(View):
    def __init__(self, ctx, chunks):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.chunks = chunks
        self.current_page = 0
        self.message = None

        self.prev_button = Button(label="⬅️ Previous", style=discord.ButtonStyle.secondary)
        self.next_button = Button(label="➡️ Next", style=discord.ButtonStyle.secondary)

        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page

        self.add_item(self.prev_button)
        self.add_item(self.next_button)

    async def send_initial(self):
        embed = self.make_embed(self.current_page)
        self.message = await self.ctx.send(embed=embed, view=self)

    def make_embed(self, page_index):
        embed = discord.Embed(
            title=f"📅 Daftar Ulang Tahun (Halaman {page_index + 1}/{len(self.chunks)})",
            color=discord.Color.blue()
        )
        for _, birthdate, display_name in self.chunks[page_index]:
            embed.add_field(
                name=display_name,
                value=birthdate.strftime("%d %B"),
                inline=False
            )
        return embed

    async def prev_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.make_embed(self.current_page), view=self)

    async def next_page(self, interaction: discord.Interaction):
        if self.current_page < len(self.chunks) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.make_embed(self.current_page), view=self)

class Birthday(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="setbirthday", help="Set ulang tahun kamu (format: dd-mm-yyyy). Bisa mention user atau masukkan nama.")
    async def set_birthday(self, ctx, *, arg: str = None):
        if not arg:
            return await ctx.send("❗ Format salah. Contoh: `mad setbirthday 21-06-2002`, `mad setbirthday @user 21-06-2002`, atau `mad setbirthday killa 21-06-2002`")

        arg = arg.strip()

        # ✅ Jika hanya tanggal → untuk diri sendiri
        if re.fullmatch(r"\d{2}-\d{2}-\d{4}", arg):
            user_id = ctx.author.id
            display_name = ctx.author.display_name
            date_str = arg
            try:
                birthdate = datetime.strptime(date_str, "%d-%m-%Y").date()
            except ValueError:
                return await ctx.send("❗ Format tanggal salah. Gunakan `dd-mm-yyyy`")

            db = connect_db()
            set_birthday(db, user_id, ctx.guild.id, birthdate, display_name)
            db.close()

            return await ctx.send(f"🎉 Ulang tahun untuk **{display_name}** telah disimpan: `{birthdate.strftime('%d %B %Y')}`")

        # ✅ Jika mention user
        mention_match = re.match(r"<@!?(\d+)>\s+(\d{2}-\d{2}-\d{4})$", arg)
        if mention_match:
            user_id = int(mention_match.group(1))
            date_str = mention_match.group(2)
            member = ctx.guild.get_member(user_id)
            display_name = member.display_name if member else f"user-{user_id}"
        else:
            # ✅ Nama bebas + tanggal
            parts = arg.rsplit(" ", 1)
            if len(parts) != 2:
                return await ctx.send("❗ Format salah. Gunakan `mad setbirthday <tanggal>` atau `mad setbirthday @user <tanggal>` atau `mad setbirthday nama <tanggal>`")

            name, date_str = parts
            member = discord.utils.find(lambda m: name.lower() in m.display_name.lower(), ctx.guild.members)
            if member:
                user_id = member.id
                display_name = member.display_name
            else:
                user_id = abs(hash(name.lower())) % (10**18)  # ID unik simulasi
                display_name = name

        try:
            birthdate = datetime.strptime(date_str, "%d-%m-%Y").date()
        except ValueError:
            return await ctx.send("❗ Format tanggal salah. Gunakan `dd-mm-yyyy`")

        db = connect_db()
        set_birthday(db, user_id, ctx.guild.id, birthdate, display_name)
        db.close()

        await ctx.send(f"🎉 Ulang tahun untuk **{display_name}** telah disimpan: `{birthdate.strftime('%d %B %Y')}`")


    @commands.command(name="mybirthday", help="Lihat ulang tahun kamu yang tersimpan")
    async def my_birthday(self, ctx):
        db = connect_db()
        bday = get_birthday(db, ctx.author.id, ctx.guild.id)
        db.close()

        if bday:
            await ctx.send(f"🎂 Ulang tahun kamu adalah: `{bday.strftime('%d %B %Y')}`")
        else:
            await ctx.send("❌ Kamu belum menyimpan tanggal ulang tahun.")

    @commands.command(name="deletebirthday", help="Hapus ulang tahun kamu atau orang lain (nama/display name)")
    async def delete_birthday(self, ctx, *, name: str = None):
        db = connect_db()

        if not name:
            delete_birthday(db, ctx.author.id, ctx.guild.id)
            db.close()
            return await ctx.send("🗑️ Ulang tahun kamu berhasil dihapus.")

        # Batasi hanya owner atau admin
        allowed_ids = [ctx.guild.owner_id, 416234104317804544]
        if ctx.author.id not in allowed_ids:
            db.close()
            return await ctx.send("❌ Kamu tidak punya izin menghapus ulang tahun orang lain.")

        # Cek mention dulu
        mention_match = re.match(r"<@!?(\d+)>", name)
        if mention_match:
            user_id = int(mention_match.group(1))
            display_name = name
        else:
            # Cari member berdasarkan nama
            member = discord.utils.find(lambda m: name.lower() in m.display_name.lower(), ctx.guild.members)
            if member:
                user_id = member.id
                display_name = member.display_name
            else:
                # Fallback ke ID hash
                user_id = abs(hash(name.lower())) % (10**18)
                display_name = name

        delete_birthday(db, user_id, ctx.guild.id)
        db.close()

        await ctx.send(f"🗑️ Ulang tahun untuk **{display_name}** telah dihapus.")

    @tasks.loop(hours=24)
    async def birthday_loop(self):
        await self.bot.wait_until_ready()
        db = connect_db()
        birthdays = get_today_birthdays(db)
        db.close()

        for user_id, guild_id, display_name in birthdays:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            channel_id = get_channel_settings(connect_db(), guild_id, "birthday")
            channel = guild.get_channel(int(channel_id)) if channel_id else guild.system_channel

            if channel:
                await channel.send(f"🎉 Selamat ulang tahun **{display_name}**! 🎂 Semoga harimu menyenangkan!")

    @birthday_loop.before_loop
    async def before_birthday_loop(self):
        await self.bot.wait_until_ready()

    @commands.command(name="birthdaylist", help="Menampilkan daftar ulang tahun semua member server")
    async def birthdaylist(self, ctx):
        db = connect_db()
        data = get_all_birthdays(db, ctx.guild.id)
        db.close()

        if not data:
            return await ctx.send("📭 Belum ada ulang tahun yang tercatat.")

        # Kelompokkan per 25 entri
        batch_size = 10
        chunks = [data[i:i + batch_size] for i in range(0, len(data), batch_size)]

        view = BirthdayView(ctx, chunks)
        await view.send_initial()

    @commands.command(name="nearestbirthday", help="Menampilkan ulang tahun terdekat")
    async def nearest_birthday(self, ctx):
        db = connect_db()
        data = get_all_birthdays(db, ctx.guild.id)
        db.close()

        if not data:
            return await ctx.send("📭 Belum ada ulang tahun yang tercatat.")

        today = datetime.today().date()
        closest = None
        min_diff = 366  # maksimal selisih hari dalam setahun

        for _, birthdate, display_name in data:
            bday_this_year = birthdate.replace(year=today.year)
            if bday_this_year < today:
                bday_this_year = bday_this_year.replace(year=today.year + 1)

            diff = (bday_this_year - today).days
            if diff < min_diff:
                min_diff = diff
                closest = (display_name, birthdate)

        if closest:
            display_name, birthdate = closest
            await ctx.send(
                f"⏰ Ulang tahun terdekat adalah milik **{display_name}** pada `{birthdate.strftime('%d %B')}` (dalam {min_diff} hari)."
            )

    @commands.command(name="setbirthdaych", help="Set channel khusus untuk ucapan ulang tahun")
    async def set_birthday_channel(self, ctx, channel: discord.TextChannel):
        if ctx.author.id != ctx.guild.owner_id and ctx.author.id != 416234104317804544:
            return await ctx.send("❌ Hanya pemilik server yang bisa menggunakan command ini.")

        db = connect_db()
        set_channel_settings(db, ctx.guild.id, "birthday", channel.id)
        db.close()

        await ctx.send(f"✅ Channel ulang tahun disetel ke {channel.mention}")
