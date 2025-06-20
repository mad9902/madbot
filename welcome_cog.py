from discord.ext import commands
import discord
from database import (
    connect_db,
    set_channel_settings,
    get_channel_settings,
    set_welcome_message,
    get_welcome_message
)

class WelcomeMessageConfig(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="setwelcomemsg")
    @commands.has_permissions(administrator=True)
    async def set_welcome_msg(self, ctx, *, message: str):
        """Set pesan welcome untuk server ini. Gunakan \\n untuk baris baru. Gunakan {guild} untuk nama server."""
        db = connect_db()
        set_welcome_message(db, ctx.guild.id, message.replace("\\n", "\n"))
        db.close()
        await ctx.send("✅ Pesan welcome berhasil disimpan ke database.")

    @commands.command(name="setchwelcome", help="Set channel khusus untuk pesan welcome.")
    async def set_welcome_channel(self, ctx, channel: discord.TextChannel):
        if ctx.author.id != ctx.guild.owner_id and ctx.author.id != 416234104317804544:
            return await ctx.send("❌ Hanya pemilik server yang bisa menggunakan command ini.")

        db = connect_db()
        set_channel_settings(db, ctx.guild.id, "welcome", channel.id)
        db.close()

        await ctx.send(f"✅ Channel welcome disetel ke {channel.mention}")

    @commands.command(name="testwelcome")
    @commands.has_permissions(administrator=True)
    async def test_welcome(self, ctx):
        """Tes kirim pesan welcome ke channel yang disetel atau ke system_channel."""
        db = connect_db()
        message = get_welcome_message(db, ctx.guild.id)
        ch_id = get_channel_settings(db, ctx.guild.id, "welcome")
        db.close()

        if not message:
            return await ctx.send("⚠️ Belum ada pesan welcome disetel. Gunakan `!setwelcomemsg`.")

        try:
            channel = await self.bot.fetch_channel(ch_id) if ch_id else ctx.guild.system_channel or ctx.channel
        except discord.DiscordException:
            return await ctx.send("❌ Gagal mendapatkan channel.")

        embed = discord.Embed(
            description=message.replace("{guild}", ctx.guild.name),
            color=discord.Color.blurple()
        )
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else None)

        await channel.send(content=f"(Test) Welcome {ctx.author.mention} to **{ctx.guild.name}**!", embed=embed)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        db = connect_db()
        message = get_welcome_message(db, member.guild.id)
        ch_id = get_channel_settings(db, member.guild.id, "welcome")
        db.close()

        if not message:
            return

        try:
            channel = await self.bot.fetch_channel(ch_id) if ch_id else member.guild.system_channel
        except discord.DiscordException:
            return

        if channel is None:
            return

        embed = discord.Embed(
            description=message.replace("{guild}", member.guild.name),
            color=discord.Color.blurple()
        )
        embed.set_author(name=member.guild.name, icon_url=member.guild.icon.url if member.guild.icon else None)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)

        await channel.send(content=f"Welcome {member.mention} to **{member.guild.name}**!", embed=embed)

async def setup(bot):
    await bot.add_cog(WelcomeMessageConfig(bot))
