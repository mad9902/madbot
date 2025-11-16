import discord
from discord.ext import commands
import os
import sys
from bot_state import OWNER_ID

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return ctx.author.id == OWNER_ID

    # ========== RESTART SAJA ==========
    @commands.command(name="restartbot")
    async def restart_bot(self, ctx):
        await ctx.reply("♻️ Restarting bot container...")

        open("/tmp/restart_madbot", "w").close()

        await ctx.reply("🔄 Restart signal sent.")
        await self.bot.close()
        sys.exit(0)

    # ========== FULL DEPLOY ==========
    @commands.command(name="deploybot")
    async def deploy_bot(self, ctx):
        await ctx.reply("🚀 Deploying new version...")

        open("/tmp/deploy_madbot", "w").close()

        await ctx.reply("🛠️ Deploy signal sent. Bot shutting down for update...")
        await self.bot.close()
        sys.exit(0)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
