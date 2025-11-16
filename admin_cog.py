import discord
from discord.ext import commands
import os
from bot_state import OWNER_ID

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return ctx.author.id == OWNER_ID

    @commands.command(name="restartbot")
    async def restart_bot(self, ctx):
        await ctx.reply("♻️ Restarting bot container...")

        # bikin trigger file
        open("/tmp/restart_madbot", "w").close()

        await ctx.reply("🔄 Restart signal sent. Container will restart in 1-2 seconds.")

        await self.bot.close()

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
