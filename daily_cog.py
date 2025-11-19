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
        Mengubah datetime ke "hari daily".
        Jika waktu < 14:00 → masih dianggap HARI SEBELUMNYA.
        Jika >= 14:00 → hari ini.
        """
        date = dt.date()
        reset_point = dt.replace(hour=14, minute=0, second=0, microsecond=0)

        # Sebelum jam 14:00 → masih hitung hari sebelumnya
        if dt < reset_point:
            return date - timedelta(days=1)
        # Setelah / sama dengan jam 14:00 → hari ini
        return date

    # ======================================================================
    #   DAILY COMMAND (hanya bisa di channel gamble)
    # ======================================================================
    @commands.command(name="daily")
    async def daily(self, ctx):
        guild_id = ctx.guild.id
        user_id = ctx.author.id

        # -------------------------------------------------------------
        # CEK CHANNEL GAMBLE
        # -------------------------------------------------------------
        ch = get_gamble_setting(self.db, guild_id, "gamble_ch")
        if not ch:
            return await ctx.send(
                "❌ Channel gamble belum diset.\n"
                "Set terlebih dahulu dengan: `setgamblech #channel`"
            )

        ch = int(ch)
        if ctx.channel.id != ch:
            return await ctx.send(f"🎰 Command `daily` hanya bisa dipakai di <#{ch}>.")

        # -------------------------------------------------------------
        # HITUNG "HARI DAILY" BERDASARKAN RESET 14:00 WIB
        # -------------------------------------------------------------
        now = datetime.now(JAKARTA)
        today_daily = self.get_daily_date(now)

        # Ambil data daily user
        data = get_daily_data(self.db, guild_id, user_id)
        last_claim = data["last_claim"]   # tipe DATE atau None
        streak = data["streak"]

        # -------------------------------------------------------------
        # SUDAH CLAIM UNTUK PERIODE INI?
        # -------------------------------------------------------------
        if last_claim == today_daily:
            return await ctx.send(
                f"📅 Kamu sudah claim daily untuk periode ini, {ctx.author.mention}!"
            )

        # -------------------------------------------------------------
        # HITUNG STREAK
        # -------------------------------------------------------------
        if last_claim is None:
            # Pertama kali claim
            streak = 1
        else:
            # Kalau terakhir claim adalah "hari daily" kemarin → lanjut streak
            if last_claim == today_daily - timedelta(days=1):
                streak += 1
            else:
                # Lewat sehari / lebih → reset streak
                streak = 1

        # -------------------------------------------------------------
        # HITUNG REWARD
        # -------------------------------------------------------------
        base = 20
        bonus = streak * 5
        reward = base + bonus

        cash_now = get_user_cash(self.db, user_id, guild_id)
        new_cash = cash_now + reward
        set_user_cash(self.db, user_id, guild_id, new_cash)

        # Simpan data daily
        set_daily_data(self.db, guild_id, user_id, today_daily, streak)

        # Log ke gamble_log
        log_gamble(self.db, guild_id, user_id, "daily", reward, "WIN")

        # -------------------------------------------------------------
        # RESPONSE EMBED
        # -------------------------------------------------------------
        embed = discord.Embed(
            title="🎁 Daily Reward",
            description=f"""
{ctx.author.mention}, kamu claim daily!

💰 Reward: **{reward} coins**
🔥 Streak: **{streak} hari**
💼 Saldo sekarang: **{new_cash} coins**

_Reset setiap jam **14:00 WIB**_
""",
            color=discord.Color.green()
        )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(DailyCog(bot))
