import discord
from discord.ext import commands
import asyncio
import random

from database import (
    get_user_cash, set_user_cash,
    create_duel_request, get_duel_request, delete_duel_request,
    log_gamble, get_gamble_setting
)
from gamble_utils import gamble_only


class DuelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db


    # =====================================================================
    # PARSE BET
    # =====================================================================
    def parse_bet(self, ctx, amount_str, user_cash):
        maxbet = get_gamble_setting(self.db, ctx.guild.id, "maxbet")
        maxbet = int(maxbet) if maxbet else None

        if amount_str.lower() == "all":
            return user_cash if not maxbet else min(user_cash, maxbet)

        if not amount_str.isdigit():
            return None

        bet = int(amount_str)
        if maxbet and bet > maxbet:
            bet = maxbet

        return bet


    # =====================================================================
    # DUEL
    # =====================================================================
    @commands.command(name="duel")
    @gamble_only()
    async def duel(self, ctx, amount: str, target: discord.Member):

        guild_id = ctx.guild.id
        challenger_id = ctx.author.id
        target_id = target.id

        # ======================
        # Basic validation
        # ======================
        if target.bot:
            return await ctx.send("❌ Tidak bisa duel dengan bot.")
        if target_id == challenger_id:
            return await ctx.send("❌ Tidak bisa duel dengan diri sendiri.")

        # CASH GLOBAL !!!
        cashA = get_user_cash(self.db, challenger_id)
        cashB = get_user_cash(self.db, target_id)

        bet = self.parse_bet(ctx, amount, cashA)
        if bet is None:
            return await ctx.send("❌ Nominal tidak valid.")
        if bet < 1:
            return await ctx.send("❌ Nominal minimal 1.")
        if cashA < bet:
            return await ctx.send("❌ Saldo kamu tidak cukup.")
        if cashB < bet:
            return await ctx.send("❌ Target tidak punya saldo cukup untuk duel.")

        # ======================
        # Duel pending check
        # ======================
        if get_duel_request(self.db, guild_id, target_id):
            return await ctx.send("❌ Target sedang punya duel pending.")

        if get_duel_request(self.db, guild_id, challenger_id):
            return await ctx.send("❌ Kamu sudah membuat duel lain.")

        # ======================
        # Save duel request
        # ======================
        create_duel_request(self.db, guild_id, challenger_id, target_id, bet)

        msg = await ctx.send(
            f"🎲 {target.mention}, kamu ditantang duel oleh {ctx.author.mention}!\n"
            f"Taruhan: **{bet} coins**\n"
            f"Ketik **accept** atau **decline** dalam 30 detik."
        )

        def check(m):
            return (
                m.author.id == target_id and
                m.channel.id == ctx.channel.id and
                m.content.lower() in ["accept", "decline"]
            )

        try:
            reply = await self.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            delete_duel_request(self.db, guild_id, challenger_id)
            return await ctx.send(f"⏳ {target.mention} tidak merespon — duel dibatalkan.")

        # ======================
        # DECLINE
        # ======================
        if reply.content.lower() == "decline":
            delete_duel_request(self.db, guild_id, challenger_id)
            return await ctx.send(f"❌ {target.mention} menolak duel.")

        # ======================
        # START DUEL
        # ======================
        await ctx.send("🎲 Duel dimulai...")

        rollA = random.randint(1, 6)
        rollB = random.randint(1, 6)

        while rollA == rollB:
            await ctx.send("↪️ Seri! Roll ulang...")
            rollA = random.randint(1, 6)
            rollB = random.randint(1, 6)

        winner = challenger_id if rollA > rollB else target_id
        loser  = target_id if winner == challenger_id else challenger_id

        # ======================
        # Money transfer (GLOBAL)
        # ======================
        cashW = get_user_cash(self.db, winner)
        cashL = get_user_cash(self.db, loser)

        set_user_cash(self.db, winner, cashW + bet)
        set_user_cash(self.db, loser, cashL - bet)

        # log per-guild
        log_gamble(self.db, guild_id, challenger_id, "duel", bet,
                   "WIN" if winner == challenger_id else "LOSE")
        log_gamble(self.db, guild_id, target_id, "duel", bet,
                   "WIN" if winner == target_id else "LOSE")

        delete_duel_request(self.db, guild_id, challenger_id)

        await ctx.send(
            f"🎲 **HASIL DUEL!**\n"
            f"{ctx.author.mention}: 🎲 {rollA}\n"
            f"{target.mention}: 🎲 {rollB}\n\n"
            f"🏆 **Pemenang: {ctx.guild.get_member(winner).mention}!**\n"
            f"💰 Mendapat: **{bet} coins**"
        )


async def setup(bot):
    await bot.add_cog(DuelCog(bot))
