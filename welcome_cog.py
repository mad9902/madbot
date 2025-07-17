from discord.ext import commands
import discord
from database import (
    connect_db,
    set_channel_settings,
    get_channel_settings,
    set_welcome_message,
    get_welcome_message,
    get_feature_status,
    set_feature_status
)

# ✅ Check hanya untuk owner server atau dev ID kamu
def is_owner_or_dev():
    async def predicate(ctx):
        return (
            ctx.author.id == ctx.guild.owner_id or
            ctx.author.id == 416234104317804544 or
            ctx.author.guild_permissions.administrator
        )
    return commands.check(predicate)

class WelcomeMessageConfig(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ✅ Set pesan welcome ke database
    @commands.command(name="togglewelcome", help="Aktif/nonaktifkan pesan welcome.")
    @is_owner_or_dev()
    async def toggle_welcome(self, ctx, status: str):
        status = status.lower()
        if status not in ["on", "off"]:
            return await ctx.send("❌ Gunakan `on` atau `off`. Contoh: `mtogglewelcome on`")

        db = connect_db()
        set_feature_status(db, ctx.guild.id, "welcome_message", status == "on")
        db.close()

        await ctx.send(f"✅ Fitur welcome_message telah {'diaktifkan' if status == 'on' else 'dinonaktifkan'}.")

    @commands.command(name="welcomestatus", help="Cek status fitur welcome_message.")
    async def welcome_status(self, ctx):
        db = connect_db()
        status = get_feature_status(db, ctx.guild.id, "welcome_message")
        db.close()
        await ctx.send(f"📣 Fitur welcome_message saat ini: {'Aktif ✅' if status else 'Nonaktif ❌'}")


    @commands.command(name="setwelcomemsg")
    @is_owner_or_dev()
    async def set_welcome_msg(self, ctx, *, message: str):
        db = connect_db()
        set_welcome_message(db, ctx.guild.id, message.replace("\\n", "\n"))
        db.close()
        await ctx.send("✅ Pesan welcome berhasil disimpan ke database.")

    # ✅ Set channel khusus welcome
    @commands.command(name="setchwelcome", help="Set channel khusus untuk pesan welcome.")
    @is_owner_or_dev()
    async def set_welcome_channel(self, ctx, channel: discord.TextChannel):
        db = connect_db()
        set_channel_settings(db, ctx.guild.id, "welcome", channel.id)
        db.close()
        await ctx.send(f"✅ Channel welcome disetel ke {channel.mention}")

    # ✅ Command tes kirim welcome
    @commands.command(name="testwelcome")
    @is_owner_or_dev()
    async def test_welcome(self, ctx):
        db = connect_db()
        message = get_welcome_message(db, ctx.guild.id)
        ch_id = get_channel_settings(db, ctx.guild.id, "welcome")
        db.close()

        if not message:
            return await ctx.send("⚠️ Belum ada pesan welcome disetel. Gunakan `msetwelcomemsg`.")

        try:
            channel = await self.bot.fetch_channel(ch_id) if ch_id else ctx.guild.system_channel or ctx.channel
        except discord.DiscordException:
            return await ctx.send("❌ Gagal mendapatkan channel.")

        embed = discord.Embed(
            title=f"Welcome to {ctx.guild.name}!",
            description=message.replace("{guild}", ctx.guild.name),
            color=discord.Color(int("C9DFEC", 16))  # Warna pastel biru muda
        )
        embed.set_author(
            name=ctx.guild.name,
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None
        )
        embed.set_thumbnail(
            url=ctx.author.avatar.url if ctx.author.avatar else None
        )
        embed.set_footer(text="Enjoy your time!")

        await channel.send(content=f"(Test) Welcome {ctx.author.mention} to **{ctx.guild.name}**!", embed=embed)

    # ✅ Event listener ketika member join
    @commands.Cog.listener()
    async def on_member_join(self, member):
        db = connect_db()
        
        # ✅ Cek apakah welcome_message di-nonaktifkan
        if not await get_feature_status(db, member.guild.id, 'welcome_message'):
            db.close()
            return

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
            title=f"Welcome to {member.guild.name}!",
            description=message.replace("{guild}", member.guild.name),
            color=discord.Color(int("C9DFEC", 16))
        )
        embed.set_author(
            name=member.guild.name,
            icon_url=member.guild.icon.url if member.guild.icon else None
        )
        embed.set_thumbnail(
            url=member.avatar.url if member.avatar else None
        )
        embed.set_footer(text="Enjoy your time!")

        await channel.send(content=f"Welcome {member.mention} to **{member.guild.name}**!", embed=embed)

# ✅ Setup function
async def setup(bot):
    await bot.add_cog(WelcomeMessageConfig(bot))
