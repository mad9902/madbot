from discord.ext import commands
import discord
from datetime import datetime

from database import (
    connect_db,
    set_channel_settings,
    get_channel_settings,
    set_welcome_message,
    get_welcome_message,
    get_feature_status,
    set_feature_status
)

INVISIBLE = "\u200b" 

# Permission check
def is_owner_or_dev():
    async def predicate(ctx):
        return (
            ctx.author.id == ctx.guild.owner_id or
            ctx.author.id == 416234104317804544 or
            ctx.author.guild_permissions.administrator
        )
    return commands.check(predicate)


class MemberGreetingConfig(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ====================================================
    #   🟩 WELCOME CONFIG
    # ====================================================
    @commands.command(name="togglewelcome", extras={"category": "Welcome"})
    @is_owner_or_dev()
    async def toggle_welcome(self, ctx, status: str):
        status = status.lower()
        if status not in ["on", "off"]:
            return await ctx.send("❌ Gunakan `on` atau `off`.")

        db = connect_db()
        set_feature_status(db, ctx.guild.id, "welcome_message", status == "on")
        db.close()
        await ctx.send(f"✅ Welcome message {'enabled' if status == 'on' else 'disabled'}.")

    @commands.command(name="setwelcomemsg", extras={"category": "Welcome"})
    @is_owner_or_dev()
    async def set_welcome_msg(self, ctx, *, message: str):
        db = connect_db()
        set_welcome_message(db, ctx.guild.id, "welcome", message)
        db.close()
        await ctx.send("✅ Pesan welcome disimpan.")

    @commands.command(name="setchwelcome", extras={"category": "Welcome"})
    @is_owner_or_dev()
    async def set_welcome_channel(self, ctx, channel: discord.TextChannel):
        db = connect_db()
        set_channel_settings(db, ctx.guild.id, "welcome", channel.id)
        db.close()
        await ctx.send(f"✅ Welcome channel → {channel.mention}")

    @commands.command(name="testwelcome", extras={"category": "Welcome"})
    @is_owner_or_dev()
    async def test_welcome(self, ctx):
        db = connect_db()
        message = get_welcome_message(db, ctx.guild.id, "welcome")
        ch_id = get_channel_settings(db, ctx.guild.id, "welcome")
        db.close()

        if not message:
            return await ctx.send("⚠ Belum ada pesan welcome.")

        channel = await self.bot.fetch_channel(ch_id) if ch_id else ctx.channel

        humans = [m for m in ctx.guild.members if not m.bot]
        human_count = len(humans)

        embed = discord.Embed(
            title="• WELCOME •",
            description=message.replace("{guild}", ctx.guild.name),
            color=0xFFAE00
        )
        embed.set_author(name=f"Tester! (you're the {human_count} members)",
                         icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else None)
        embed.set_footer(text="Have Fun!!")

        file = discord.File("media/welcome.png", filename="welcome.png")
        embed.set_image(url="attachment://welcome.png")

        await channel.send(
            content=f"(Test) Welcome {ctx.author.mention}!",
            embed=embed,
            file=file
        )

        await self.send_join_log(ctx.author, is_test=True)

    # ====================================================
    #   LOG CHANNEL CONFIG
    # ====================================================
    @commands.command(name="setgreetsch", extras={"category": "Welcome"})
    @is_owner_or_dev()
    async def set_log_channel(self, ctx, channel: discord.TextChannel):
        db = connect_db()
        set_channel_settings(db, ctx.guild.id, "member_log", channel.id)
        db.close()
        await ctx.send(f"📝 Log join/leave disetel ke {channel.mention}")

    # REAL MEMBER JOIN
    @commands.Cog.listener()
    async def on_member_join(self, member):
        db = connect_db()
        if not get_feature_status(db, member.guild.id, "welcome_message"):
            db.close()
            return

        message = get_welcome_message(db, member.guild.id, "welcome")
        ch_id = get_channel_settings(db, member.guild.id, "welcome")
        db.close()

        if not message:
            return

        channel = await self.bot.fetch_channel(ch_id) if ch_id else member.guild.system_channel

        humans = [m for m in member.guild.members if not m.bot]
        human_count = len(humans)

        embed = discord.Embed(
            title="• WELCOME •",
            description=message.replace("{guild}", member.guild.name),
            color=0xFFAE00
        )
        embed.set_author(name=f"You are the {human_count} member!",
                         icon_url=member.guild.icon.url if member.guild.icon else None)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        embed.set_footer(text="Have Fun!!")

        file = discord.File("media/welcome.png", filename="welcome.png")
        embed.set_image(url="attachment://welcome.png")

        await channel.send(
            content=f"Welcome {member.mention}!",
            embed=embed,
            file=file
        )

        await self.send_join_log(member)


    # ====================================================
    #   🟥 GOODBYE CONFIG
    # ====================================================
    @commands.command(name="togglegoodbye", extras={"category": "Welcome"})
    @is_owner_or_dev()
    async def toggle_goodbye(self, ctx, status: str):
        status = status.lower()
        if status not in ["on", "off"]:
            return await ctx.send("❌ Gunakan `on` atau `off`.")

        db = connect_db()
        set_feature_status(db, ctx.guild.id, "goodbye_message", status == "on")
        db.close()
        await ctx.send(f"👋 Goodbye message {'enabled' if status == 'on' else 'disabled'}.")

    @commands.command(name="setgoodbyemsg", extras={"category": "Welcome"})
    @is_owner_or_dev()
    async def set_goodbye_msg(self, ctx, *, message: str):
        db = connect_db()
        set_welcome_message(db, ctx.guild.id, "goodbye", message)
        db.close()
        await ctx.send("✅ Pesan goodbye disimpan.")

    @commands.command(name="setchgoodbye", extras={"category": "Welcome"})
    @is_owner_or_dev()
    async def set_goodbye_channel(self, ctx, channel: discord.TextChannel):
        db = connect_db()
        set_channel_settings(db, ctx.guild.id, "goodbye", channel.id)
        db.close()
        await ctx.send(f"👋 Goodbye channel → {channel.mention}")

    @commands.command(name="testgoodbye", extras={"category": "Welcome"})
    @is_owner_or_dev()
    async def test_goodbye(self, ctx):
        db = connect_db()
        message = get_welcome_message(db, ctx.guild.id, "goodbye")
        ch_id = get_channel_settings(db, ctx.guild.id, "goodbye")
        db.close()

        if not message:
            return await ctx.send("⚠ Belum ada pesan goodbye.")

        channel = await self.bot.fetch_channel(ch_id) if ch_id else ctx.channel

        embed = discord.Embed(
            description=message.replace("{guild}", ctx.guild.name),
            color=0xFFAE00
        )
        embed.set_author(
            name=INVISIBLE,
            icon_url=ctx.guild.icon.url if ctx.guild.icon else None
        )
        embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else None)
        embed.set_footer(text="We will miss you :(")

        file = discord.File("media/goodbye.png", filename="goodbye.png")
        embed.set_image(url="attachment://goodbye.png")

        await channel.send(
            content=f"Goodbye {ctx.author.mention}!",
            embed=embed,
            file=file
        )

        await self.send_leave_log(ctx.author, is_test=True)

    # REAL MEMBER LEAVE
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        db = connect_db()
        if not get_feature_status(db, member.guild.id, "goodbye_message"):
            db.close()
            return

        message = get_welcome_message(db, member.guild.id, "goodbye")
        ch_id = get_channel_settings(db, member.guild.id, "goodbye")
        db.close()

        if not message:
            return

        channel = await self.bot.fetch_channel(ch_id)

        embed = discord.Embed(
            description=message.replace("{guild}", member.guild.name),
            color=0xFFAE00
        )
        embed.set_author(
            name=INVISIBLE,
            icon_url=member.guild.icon.url if member.guild.icon else None
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        embed.set_footer(text="We will miss you :(")

        file = discord.File("media/goodbye.png", filename="goodbye.png")
        embed.set_image(url="attachment://goodbye.png")

        await channel.send(
            content=f"Goodbye {member.mention}",
            embed=embed,
            file=file
        )

        await self.send_leave_log(member)


    # ====================================================
    #   LOGGING HELPERS
    # ====================================================
    async def send_join_log(self, member, is_test=False):
        db = connect_db()
        log_ch_id = get_channel_settings(db, member.guild.id, "member_log")
        db.close()

        if not log_ch_id:
            return
        
        try:
            log_channel = await self.bot.fetch_channel(log_ch_id)
        except:
            return

        title = f"[TEST] {member.name} joined the server" if is_test else f"{member.name} joined the server"

        embed = discord.Embed(title=title, color=0x2ECC71)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Account creation",
                        value=member.created_at.strftime("%B %d, %Y %I:%M %p"),
                        inline=True)
        embed.set_footer(text=f"{member.guild.name} • Today at {datetime.now().strftime('%I:%M %p')}")

        await log_channel.send(embed=embed)

    async def send_leave_log(self, member, is_test=False):
        db = connect_db()
        log_ch_id = get_channel_settings(db, member.guild.id, "member_log")
        db.close()

        if not log_ch_id:
            return

        try:
            log_channel = await self.bot.fetch_channel(log_ch_id)
        except:
            return

        title = f"[TEST] {member.name} left the server" if is_test else f"{member.name} left the server"

        embed = discord.Embed(title=title, color=0xE74C3C)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        embed.add_field(name="User", value=member.mention, inline=True)
        embed.add_field(name="Joined date",
                        value=member.joined_at.strftime("%B %d, %Y %I:%M %p") if member.joined_at else "-",
                        inline=True)

        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        embed.add_field(name="Roles",
                        value=" ".join(roles) if roles else "No roles",
                        inline=False)

        embed.set_footer(text=f"{member.guild.name} • Today at {datetime.now().strftime('%I:%M %p')}")

        await log_channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(MemberGreetingConfig(bot))
