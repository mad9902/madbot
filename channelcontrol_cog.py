import discord
from discord.ext import commands

class ChannelControl(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="disablechannel")
    @commands.has_permissions(administrator=True)
    async def disable_channel_cmd(self, ctx, channel: discord.abc.GuildChannel = None):
        if not channel:
            channel = ctx.channel

        self.bot.channel_manager.disable_channel(ctx.guild.id, channel.id)
        await ctx.send(f"🔒 Bot DISABLED di {channel.mention}")

    @commands.command(name="enablechannel")
    @commands.has_permissions(administrator=True)
    async def enable_channel_cmd(self, ctx, channel: discord.abc.GuildChannel = None):
        if not channel:
            channel = ctx.channel

        self.bot.channel_manager.enable_channel(ctx.guild.id, channel.id)
        await ctx.send(f"🔓 Bot ENABLED kembali di {channel.mention}")

async def setup(bot):
    await bot.add_cog(ChannelControl(bot))
