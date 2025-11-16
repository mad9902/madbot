import discord
from discord.ext import commands
import os
import subprocess
from bot_state import OWNER_ID

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ===== CHECK: Hanya OWNER ID =====
    async def cog_check(self, ctx):
        return ctx.author.id == OWNER_ID

    @commands.command(name="restartbot")
    async def restart_bot(self, ctx):
        """Restart Docker container MadBot (owner only)."""
        await ctx.reply("♻️ Restarting bot container...")

        try:
            # Jalankan command docker
            subprocess.run(
                ["docker", "compose", "restart", "madbot-service"],
                check=True
            )
        except Exception as e:
            await ctx.reply(f"❌ Gagal restart: `{e}`")
            return

        # Shutdown bot supaya container restart dengan bersih
        await ctx.reply("🔄 Bot is restarting...")
        await self.bot.close()

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
