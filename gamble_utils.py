# utils/gamble_utils.py
import discord
from functools import wraps
from database import get_gamble_setting


# =====================================================
#   CEK APAKAH COMMAND DIPAKAI DI CHANNEL GAMBLE
# =====================================================
def check_gamble_channel(db, ctx):
    ch = get_gamble_setting(db, ctx.guild.id, "gamble_ch")
    if not ch:
        return f"❌ Channel gamble belum diset.\nGunakan: `setgamblech #channel`"

    ch = int(ch)
    if ctx.channel.id != ch:
        return f"🎰 Command hanya bisa digunakan di <#{ch}>."
    return None


# =====================================================
#   DECORATOR — untuk semua command gamble
# =====================================================
def gamble_only():
    def wrapper(func):
        @wraps(func)
        async def inner(self, ctx, *args, **kwargs):

            # cek channel
            err = check_gamble_channel(self.db, ctx)
            if err:
                return await ctx.send(err)

            # cek cooldown local
            cd = self.gamble_on_cooldown(ctx)
            if cd:
                return await ctx.send(f"⏳ Tunggu **{cd}s** dulu.")

            return await func(self, ctx, *args, **kwargs)

        return inner
    return wrapper


# =====================================================
#   HELPER: angka → format
# =====================================================
def comma(num):
    return f"{num:,}"
