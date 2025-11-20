import discord
from discord.ext import commands
import os
import sys
from bot_state import OWNER_ID
from database import connect_db


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        return ctx.author.id == OWNER_ID

    # ==========================
    # 🔥 INTERNAL: WIPE FUNCTION
    # ==========================
    def wipe_bot_data(self):
        db = connect_db()
        cursor = db.cursor()

        tables_to_clear = [
            "user_cash",
            "gamble_log",
            "user_daily",
            "user_rob_protect",
            "user_protection",
            "duel_pending",
            "rob_stats",

            "streak_pairs",
            "streak_logs",

            "discord_logs",
            "user_last_active",

            "werewolf_votes",
            "werewolf_players",
            "werewolf_logs",
            "werewolf_games",
            "werewolf_leaderboards"
        ]

        # DELETE agar aman dari FK
        for table in tables_to_clear:
            try:
                cursor.execute(f"DELETE FROM {table};")
            except Exception as e:
                print(f"[WARN] DELETE gagal pada {table}: {e}")

        # Reset auto increment
        for table in tables_to_clear:
            try:
                cursor.execute(f"ALTER TABLE {table} AUTO_INCREMENT = 1;")
            except Exception as e:
                print(f"[WARN] Reset AUTO_INCREMENT gagal pada {table}: {e}")

        db.commit()
        cursor.close()
        db.close()

        print("✅ Semua data bot berhasil dihapus (struktur aman).")

    # ==========================
    # 💥 COMMAND: WIPE DATA
    # ==========================
    @commands.command(name="wipedata")
    async def wipe_data_cmd(self, ctx):
        await ctx.reply("🧹 Menghapus seluruh data bot...")

        try:
            self.wipe_bot_data()
            await ctx.reply("✅ Semua data berhasil dihapus!")
        except Exception as e:
            await ctx.reply(f"❌ Gagal menghapus data:\n```\n{e}\n```")
            return

    # ==========================
    # 🔁 RESTART SAJA
    # ==========================
    @commands.command(name="restartbot")
    async def restart_bot(self, ctx):
        await ctx.reply("♻️ Restarting bot container...")

        open("/tmp/restart_madbot", "w").close()

        await ctx.reply("🔄 Restart signal sent.")
        await self.bot.close()
        sys.exit(0)

    # ==========================
    # 🚀 FULL DEPLOY
    # ==========================
    @commands.command(name="deploybot")
    async def deploy_bot(self, ctx):
        await ctx.reply("🚀 Deploying new version...")

        open("/tmp/deploy_madbot", "w").close()

        await ctx.reply("🛠️ Deploy signal sent. Bot shutting down for update...")
        await self.bot.close()
        sys.exit(0)


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
