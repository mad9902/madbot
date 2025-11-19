import discord
from discord.ext import commands
from datetime import datetime, timedelta
import pytz

from database import (
    get_user_cash, set_user_cash,
    get_daily_data, set_daily_data,
    log_gamble,
    get_gamble_setting
)

from gamble_utils import comma

JAKARTA = pytz.timezone("Asia/Jakarta")


class DailyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    # ======================================================================
    #   HELPER → menentukan "hari daily" berdasarkan reset jam 14:00 WIB
    # ======================================================================
    def get_daily_date(self, dt: datetime):
        """
        Daily reset 14:00 WIB.
        <14:00  -> hitung sebagai hari kemarin
        >=14:00 -> hari ini
        """
        today = dt.date()
        reset_time = dt.replace(hour=14, minute=0, second=0, microsecond=0)

        if dt < reset_time:
            return today - timedelta(days=1)
        return today

    # ======================================================================
    #   DAILY (GLOBAL CASH + GLOBAL STREAK)
    # ======================================================================
    @commands.command(name="daily")
    async def daily(self, ctx):

        guild_id = ctx.guild.id
        user_id = ctx.author.id

        # =======================================================
        # CEK GAMBLE CHANNEL (per guild)
        # =======================================================
        ch = get_gamble_setting(self.db, guild_id, "gamble_ch")
        if not ch:
            return await ctx.send(
                "❌ Channel gamble belum diset.\n"
                "Gunakan: `setgamblech #channel`"
            )

        ch = int(ch)
        if ctx.channel.id != ch:
            return await ctx.send(
                f"🎰 Command `daily` hanya bisa digunakan di <#{ch}>."
            )

        # =======================================================
        # TENTUKAN "HARI DAILY" SEKARANG
        # =======================================================
        now = datetime.now(JAKARTA)
        today_daily = self.get_daily_date(now)

        # =======================================================
        # FETCH DAILY STORAGE (GLOBAL)
        # =======================================================
        data = get_daily_data(self.db, user_id)
        last_claim = data["last_claim"]   # DATE atau None
        streak = data["streak"]

        # =======================================================
        # SUDAH CLAIM PERIODE INI?
        # =======================================================
        if last_claim == today_daily:
            return await ctx.send(
                f"📅 Kamu sudah claim daily periode ini, {ctx.author.mention}!"
            )

        # =======================================================
        # HITUNG STREAK GLOBAL
        # =======================================================
        if last_claim is None:
            streak = 1
        else:
            if last_claim == today_daily - timedelta(days=1):
                streak += 1
            else:
                streak = 1

        # =======================================================
        # HITUNG REWARD
        # =======================================================
        base = 20
        bonus = streak * 5
        reward = base + bonus

        cash_now = get_user_cash(self.db, user_id)
        new_cash = cash_now + reward
        set_user_cash(self.db, user_id, new_cash)

        # =======================================================
        # SIMPAN DAILY GLOBAL
        # =======================================================
        set_daily_data(self.db, user_id, today_daily, streak)

        # Log (opsional tetap pakai guild_id biar leaderboard per guild)
        log_gamble(self.db, user_id, "daily", reward, "WIN")

        # =======================================================
        # EMBED RESULT
        # =======================================================
        embed = discord.Embed(
            title="🎁 Daily Reward",
            description=f"""
{ctx.author.mention}, kamu claim daily!

💰 Reward: **{reward} coins**
🔥 Streak Global: **{streak} hari**
💼 Saldo sekarang: **{comma(new_cash)} coins**

_Reset setiap jam **14:00 WIB**_
""",
            color=discord.Color.green()
        )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(DailyCog(bot))
