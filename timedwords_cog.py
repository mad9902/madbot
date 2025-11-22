import discord
from discord.ext import commands, tasks
from discord import Embed, Color
from datetime import datetime, timedelta
from database import (
    connect_db,
    add_timed_word,
    get_timed_words,
    set_channel_settings,
    get_channel_settings,
    remove_timed_word
)

ALLOWED_USER_ID = 416234104317804544
EMBED_COLOR = Color(int("C9DFEC", 16))

class TimedWordsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_data = {}
        self.send_timed_word.start()

    @commands.command(name="timedwords", help="Tambah pesan rutin: timedwords [interval] Judul | Isi\nContoh: `timedwords 5 Reminder | Jangan spam!` atau `timedwords Reminder | Jangan spam!` (default 30 menit)", extras={"category": "TimedWords"})
    async def add_timed_word_cmd(self, ctx, *, arg: str = None):
        if not arg or "|" not in arg:
            return await ctx.send("❗ Format salah. Contoh: `timedwords [5] Reminder | Jangan spam!`")

        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Hanya admin yang dapat menambahkan pesan rutin.")

        parts = arg.split("|", 1)
        left = parts[0].strip()
        content = parts[1].strip()

        # Coba deteksi jika ada angka interval di depan
        try:
            first_space = left.index(" ")
            possible_interval = left[:first_space]
            interval = int(possible_interval)
            if interval < 1 or interval > 1440:
                return await ctx.send("⚠️ Interval harus antara 1–1440 menit.")
            title = left[first_space:].strip()
        except (ValueError, IndexError):
            # Tidak ada angka di awal → pakai default 30
            interval = 30
            title = left

        db = connect_db()
        add_timed_word(db, ctx.guild.id, title, content, interval)
        messages = get_timed_words(db, ctx.guild.id)
        channel_id = get_channel_settings(db, ctx.guild.id, "timedwords")
        db.close()

        if not channel_id:
            channel_id = ctx.channel.id

        self.guild_data[ctx.guild.id] = {
            "channel": channel_id,
            "messages": messages,
            "index": 0,
            "last_sent": None
        }

        await ctx.send(f"✅ Pesan berkala ditambahkan setiap {interval} menit:\n**{title}**\n{content}")


    @commands.command(name="setchtimedwords", help="Set channel untuk pengiriman timedwords otomatis.", extras={"category": "TimedWords"})
    async def set_timedwords_channel(self, ctx, channel: discord.TextChannel):
        if ctx.author.id != ctx.guild.owner_id and ctx.author.id != ALLOWED_USER_ID:
            return await ctx.send("❌ Hanya pemilik server atau user tertentu yang dapat mengatur channel ini.")

        db = connect_db()
        set_channel_settings(db, ctx.guild.id, "timedwords", channel.id)
        messages = get_timed_words(db, ctx.guild.id)
        db.close()

        if messages:
            self.guild_data[ctx.guild.id] = {
                "channel": channel.id,
                "messages": messages,
                "index": 0,
                "last_sent": None
            }

        await ctx.send(f"✅ Channel untuk timedwords telah disetel ke {channel.mention}")

    @tasks.loop(minutes=1)
    async def send_timed_word(self):
        now = datetime.utcnow()
        for guild_id, data in self.guild_data.items():
            channel = self.bot.get_channel(int(data["channel"]))
            if not channel or not data["messages"]:
                continue

            index = data["index"]
            title, content, interval = data["messages"][index]
            last_sent = data.get("last_sent")

            if last_sent is None or now - last_sent >= timedelta(minutes=interval):
                embed = Embed(
                    title=f"📞 {title}",
                    description=content,
                    color=EMBED_COLOR
                )
                embed.set_footer(text=f"Pesan otomatis setiap {interval} menit.")

                await channel.send(embed=embed)
                data["index"] = (index + 1) % len(data["messages"])
                data["last_sent"] = now

    @send_timed_word.before_loop
    async def before_send_timed_word(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            db = connect_db()
            channel_id = get_channel_settings(db, guild.id, "timedwords")
            messages = get_timed_words(db, guild.id)
            db.close()
            if channel_id and messages:
                self.guild_data[guild.id] = {
                    "channel": int(channel_id),
                    "messages": messages,
                    "index": 0,
                    "last_sent": None
                }

    @commands.command(name="listtimedwords", help="Menampilkan semua pesan berkala yang telah ditambahkan.", extras={"category": "TimedWords"})
    async def list_timedwords(self, ctx):
        db = connect_db()
        messages = get_timed_words(db, ctx.guild.id)
        db.close()

        if not messages:
            return await ctx.send("🚫 Tidak ada pesan berkala yang tersimpan.")

        pages = []
        per_page = 5
        for i in range(0, len(messages), per_page):
            chunk = messages[i:i + per_page]
            desc = ""
            for title, content, interval in chunk:
                desc += f"📌 **{title}** ({interval} menit)\n{content}\n\n"

            embed = Embed(
                title=f"🗂️ Daftar Pesan Berkala ({i+1}–{min(i+per_page, len(messages))} dari {len(messages)})",
                description=desc,
                color=EMBED_COLOR
            )
            embed.set_footer(text="Gunakan `removetimedword <judul>` untuk menghapus pesan.")
            pages.append(embed)

        if len(pages) == 1:
            await ctx.send(embed=pages[0])
        else:
            from discord import ui

            class PaginationView(ui.View):
                def __init__(self, embeds):
                    super().__init__(timeout=60)
                    self.embeds = embeds
                    self.current = 0
                    self.update_buttons()

                def update_buttons(self):
                    self.previous.disabled = self.current == 0
                    self.next.disabled = self.current == len(self.embeds) - 1

                @ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
                async def previous(self, interaction: discord.Interaction, button: ui.Button):
                    if self.current > 0:
                        self.current -= 1
                        self.update_buttons()
                        await interaction.response.edit_message(embed=self.embeds[self.current], view=self)

                @ui.button(label="➡️", style=discord.ButtonStyle.secondary)
                async def next(self, interaction: discord.Interaction, button: ui.Button):
                    if self.current < len(self.embeds) - 1:
                        self.current += 1
                        self.update_buttons()
                        await interaction.response.edit_message(embed=self.embeds[self.current], view=self)

            await ctx.send(embed=pages[0], view=PaginationView(pages))

    @commands.command(name="removetimedwords", help="Hapus pesan berkala berdasarkan judul.", extras={"category": "TimedWords"})
    async def remove_timedword(self, ctx, *, title: str = None):
        if not title:
            return await ctx.send("❗ Format salah. Contoh: `removetimedword Reminder`")

        db = connect_db()
        messages = get_timed_words(db, ctx.guild.id)
        matched = [msg for msg in messages if msg[0].lower() == title.lower()]

        if not matched:
            db.close()
            return await ctx.send("⚠️ Tidak ditemukan pesan dengan judul tersebut.")

        remove_timed_word(db, ctx.guild.id, matched[0][0])
        updated = get_timed_words(db, ctx.guild.id)
        db.close()

        if ctx.guild.id in self.guild_data:
            self.guild_data[ctx.guild.id]["messages"] = updated
            self.guild_data[ctx.guild.id]["index"] = 0
            self.guild_data[ctx.guild.id]["last_sent"] = None

        await ctx.send(f"🗑️ Pesan berkala dengan judul '**{matched[0][0]}**' berhasil dihapus.")
