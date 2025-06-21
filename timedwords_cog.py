import discord
from discord.ext import commands, tasks
from discord import Embed, Color
from database import (
    connect_db,
    add_timed_word,
    get_timed_words,
    set_channel_settings,
    get_channel_settings
)

ALLOWED_USER_ID = 416234104317804544
EMBED_COLOR = Color(int("C9DFEC", 16))  # Warna embed #C9DFEC

class TimedWordsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_data = {}
        self.send_timed_word.start()

    @commands.command(name="timedwords", help="Tambah pesan rutin: timedwords Judul | Isi")
    async def add_timed_word_cmd(self, ctx, *, arg: str = None):
        if not arg or "|" not in arg:
            return await ctx.send("❗ Format salah. Contoh: `timedwords Reminder | Jangan spam!`")

        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Hanya admin yang dapat menambahkan pesan rutin.")

        title, content = [x.strip() for x in arg.split("|", 1)]

        db = connect_db()
        add_timed_word(db, ctx.guild.id, title, content)
        messages = get_timed_words(db, ctx.guild.id)
        channel_id = get_channel_settings(db, ctx.guild.id, "timedwords")
        db.close()

        if not channel_id:
            channel_id = ctx.channel.id  # fallback

        self.guild_data[ctx.guild.id] = {
            "channel": channel_id,
            "messages": messages,
            "index": 0
        }

        await ctx.send(f"✅ Pesan berkala ditambahkan:\n**{title}**\n{content}")

    @commands.command(name="setchtimedwords", help="Set channel untuk pengiriman timedwords otomatis.")
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
                "index": 0
            }

        await ctx.send(f"✅ Channel untuk timedwords telah disetel ke {channel.mention}")

    @tasks.loop(minutes=30)
    async def send_timed_word(self):
        for guild_id, data in self.guild_data.items():
            channel = self.bot.get_channel(int(data["channel"]))
            if not channel or not data["messages"]:
                continue

            title, content = data["messages"][data["index"]]
            embed = Embed(
                title=f"📞 {title}",
                description=content,
                color=EMBED_COLOR
            )
            embed.set_footer(text="Pesan berkala otomatis setiap 30 menit.")

            await channel.send(embed=embed)
            data["index"] = (data["index"] + 1) % len(data["messages"])

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
                    "index": 0
                }
