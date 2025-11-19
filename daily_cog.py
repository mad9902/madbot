import discord
from discord.ext import commands
from datetime import datetime, timedelta
import pytz

from database import (
    get_user_cash, set_user_cash,
    get_daily_data, set_daily_data,
    log_gamble
)

JAKARTA = pytz.timezone("Asia/Jakarta")


class DailyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db


    # ============================================================
    #  HELPER: CHECK IF USER CAN CLAIM TODAY (14:00 WIB reset)
    # ============================================================
    def is_new_day(self, last_claim_date):
        """
        last_claim_date di DB disimpan sebagai DATE (YYYY-MM-DD)
        Reset harian jam 14:00 WIB
        """

        now = datetime.now(JAKARTA)
        today = now.date()

        # Reset berlaku jam 14:00 WIB
        reset_time = JAKARTA.localize(datetime(
            year=now.year,
            month=now.month,
            day=now.day,
            hour=14, minute=0, second=0
        ))

        # Jika belum pernah claim
        if not last_claim_date:
            return True

        # Jika claim dilakukan hari ini sebelum reset
        if last_claim_date == today and now < reset_time:
            return False  # belum reset

        # Jika claim dilakukan setelah reset tadi
        if last_claim_date == today and now >= reset_time:
            return False  # sudah claim hari ini

        # Jika last_claim_date beda hari → cek apakah reset sudah lewat
        if last_claim_date < today:
            # Jika reset jam 14 belum terjadi hari ini (misal pagi)
            if now < reset_time:
                # user claim kemarin, reset belum lewat
                return False
            else:
                # reset sudah lewat hari ini → claim OK
                return True

        return True


    # ============================================================
    #  DAILY COMMAND
    # ============================================================
    @commands.command(name="daily")
    async def daily(self, ctx):
        guild_id = ctx.guild.id
        user_id = ctx.author.id

        # Ambil data daily user
        data = get_daily_data(self.db, guild_id, user_id)
        last_claim = data["last_claim"]
        streak = data["streak"]

        # ================================================
        #  CEK APAKAH BOLEH CLAIM
        # ================================================
        if not self.is_new_day(last_claim):
            return await ctx.send(f"📅 Kamu sudah claim hari ini, {ctx.author.mention}!")

        # ================================================
        #  STREAK LOGIC
        # ================================================
        now_jkt = datetime.now(JAKARTA)
        today = now_jkt.date()

        # Jika claim kemarin di hari yang berbeda dan reset sudah lewat → streak lanjut
        if last_claim:
            time_diff = today - last_claim
            if time_diff.days == 1:
                streak += 1
            else:
                streak = 1
        else:
            streak = 1

        # ================================================
        #  HITUNG REWARD
        # ================================================
        base_reward = 20
        reward_bonus = streak * 5
        reward = base_reward + reward_bonus

        # Tambah cash user
        cash_now = get_user_cash(self.db, user_id, guild_id)
        new_cash = cash_now + reward
        set_user_cash(self.db, user_id, guild_id, new_cash)

        # Simpan daily data
        set_daily_data(self.db, guild_id, user_id, today, streak)

        # Log
        log_gamble(self.db, guild_id, user_id, "daily", reward, "WIN")

        # ================================================
        #  RESPONSE
        # ================================================
        embed = discord.Embed(
            title="🎁 Daily Reward",
            description=f"""
{ctx.author.mention}, kamu mendapatkan **{reward} coins!**

📅 Streak: **{streak} hari**
💰 Total saldo: **{new_cash} coins**
""",
            color=discord.Color.green()
        )

        embed.set_footer(text="Reset harian jam 14:00 WIB")

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(DailyCog(bot))
