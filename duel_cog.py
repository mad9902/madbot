import discord
from discord.ext import commands
import asyncio
import random
import time

from database import (
    get_user_cash, set_user_cash,
    create_duel_request, get_duel_request, delete_duel_request,
    get_channel_settings,
    log_gamble
)


class DuelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.pending_accept = {}  # key: (guild, target) → challenger


    # =====================================================================
    #   Convert <amount> or "all"
    # =====================================================================
    def parse_bet(self, ctx, amount_str, user_cash, maxbet):
        if amount_str.lower() == "all":
            return user_cash if not maxbet else min(user_cash, maxbet)

        if not amount_str.isdigit():
            return None

        bet = int(amount_str)
        if maxbet and bet > maxbet:
            bet = maxbet

        return bet


    # =====================================================================
    #   DUEL COMMAND: duel <amount> @target
    # =====================================================================
    @commands.command(name="duel")
    async def duel(self, ctx, amount: str, target: discord.Member):
        guild_id = ctx.guild.id
        challenger_id = ctx.author.id
        target_id = target.id

        # ==========================
        #   VALIDASI
        # ==========================
        if target.bot:
            return await ctx.send("❌ Tidak bisa duel dengan bot.")
        if target_id == challenger_id:
            return await ctx.send("❌ Tidak bisa duel dengan diri sendiri.")

        # Gamble channel check
        allow = get_channel_settings(self.db, guild_id, "gamble")
        if allow and ctx.channel.id != int(allow):
            return await ctx.send(f"🎰 Gunakan command ini di <#{allow}>.")

        maxbet = get_channel_settings(self.db, guild_id, "maxbet")
        maxbet = int(maxbet) if maxbet else None

        cashA = get_user_cash(self.db, challenger_id, guild_id)
        cashB = get_user_cash(self.db, target_id, guild_id)

        bet = self.parse_bet(ctx, amount, cashA, maxbet)
        if bet is None:
            return await ctx.send("❌ Nominal tidak valid.")
        if bet < 1:
            return await ctx.send("❌ Nominal harus lebih dari 0.")
        if cashA < bet:
            return await ctx.send("❌ Kamu tidak punya saldo cukup.")
        if cashB < bet:
            return await ctx.send("❌ Target tidak punya saldo cukup untuk duel.")

        # ==========================
        #   CHECK IF TARGET IS BUSY
        # ==========================
        active_req = get_duel_request(self.db, guild_id, target_id)
        if active_req:
            return await ctx.send("❌ Target sedang dalam duel pending lain.")

        active_req_2 = get_duel_request(self.db, guild_id, challenger_id)
        if active_req_2:
            return await ctx.send("❌ Kamu sudah membuat duel lain.")

        # ==========================
        #   SIMPAN REQUEST
        # ==========================
        create_duel_request(self.db, guild_id, challenger_id, target_id, bet)
        self.pending_accept[(guild_id, target_id)] = challenger_id

        # ==========================
        #   SEND REQUEST MESSAGE
        # ==========================
        msg = await ctx.send(
            f"🎲 {target.mention}, kamu ditantang duel oleh {ctx.author.mention}!\n"
            f"Taruhan: **{bet} coins**\n"
            f"Ketik `accept` atau `decline` dalam 30 detik."
        )

        # Wait for response
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
            return await ctx.send(f"⏳ Duel expired. {target.mention} tidak merespon.")

        # ==========================
        #   ACCEPT OR DECLINE
        # ==========================
        if reply.content.lower() == "decline":
            delete_duel_request(self.db, guild_id, challenger_id)
            return await ctx.send(f"❌ {target.mention} menolak duel.")

        # ==========================
        #   PROCEED DUEL (ACCEPT)
        # ==========================
        await ctx.send("🎲 Duel dimulai!")

        rollA = random.randint(1, 6)
        rollB = random.randint(1, 6)

        # auto rematch if tie
        while rollA == rollB:
            await ctx.send("↪️ Seri! Roll ulang...")
            rollA = random.randint(1, 6)
            rollB = random.randint(1, 6)

        winner = challenger_id if rollA > rollB else target_id
        loser  = target_id if winner == challenger_id else challenger_id

        # apply money
        cashW = get_user_cash(self.db, winner, guild_id)
        cashL = get_user_cash(self.db, loser, guild_id)

        cashW += bet
        cashL -= bet

        set_user_cash(self.db, winner, guild_id, cashW)
        set_user_cash(self.db, loser, guild_id, cashL)

        log_gamble(self.db, guild_id, challenger_id, "duel", bet, "WIN" if winner == challenger_id else "LOSE")
        log_gamble(self.db, guild_id, target_id,     "duel", bet, "WIN" if winner == target_id else "LOSE")

        delete_duel_request(self.db, guild_id, challenger_id)
        self.pending_accept.pop((guild_id, target_id), None)

        # ==========================
        #   OUTPUT RESULT
        # ==========================
        await ctx.send(
            f"🎲 **HASIL DUEL!**\n"
            f"{ctx.author.mention}: 🎲 {rollA}\n"
            f"{target.mention}: 🎲 {rollB}\n\n"
            f"🏆 **Pemenang: {ctx.guild.get_member(winner).mention}!**\n"
            f"💰 Mendapat: **{bet} coins**"
        )


async def setup(bot):
    await bot.add_cog(DuelCog(bot))
