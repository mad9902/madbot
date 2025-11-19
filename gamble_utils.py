# utils/gamble_utils.py

import discord
from functools import wraps
from database import get_gamble_setting
import time


# =====================================================
#   GLOBAL GAMBLE COOLDOWN
# =====================================================
GAMBLE_COOLDOWN_SEC = 3
_last_gamble = {}   # (guild_id, user_id) → timestamp


def global_gamble_cooldown(guild_id, user_id):
    """
    Return None = boleh main
    Return float = sisa cooldown detik
    """
    now = time.time()
    key = (guild_id, user_id)

    if key in _last_gamble:
        diff = now - _last_gamble[key]
        if diff < GAMBLE_COOLDOWN_SEC:
            return round(GAMBLE_COOLDOWN_SEC - diff, 1)

    _last_gamble[key] = now
    return None


# =====================================================
#   CEK APAKAH COMMAND DIPAKAI DI CHANNEL GAMBLE
# =====================================================
def check_gamble_channel(db, ctx):
    ch = get_gamble_setting(db, ctx.guild.id, "gamble_ch")
    if not ch:
        return (
            "❌ Channel gamble belum diset.\n"
            "Gunakan: `setgamblech #channel`"
        )

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

            # cek channel dulu
            err = check_gamble_channel(self.db, ctx)
            if err:
                return await ctx.send(err)

            # cek global cooldown (fix utama)
            cd = global_gamble_cooldown(ctx.guild.id, ctx.author.id)
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
