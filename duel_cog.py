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

    # HOLD SYSTEM
    def hold_amount(self, uid, amt):
        self.bot.hold_balance[uid] = self.bot.hold_balance.get(uid, 0) + amt

    def release_amount(self, uid, amt):
        if uid in self.bot.hold_balance:
            self.bot.hold_balance[uid] = max(0, self.bot.hold_balance[uid] - amt)

    def get_available(self, uid):
        return get_user_cash(self.db, uid) - self.bot.hold_balance.get(uid, 0)

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
    # DUEL COMMAND
    # =====================================================================
    @commands.command(name="duel")
    @gamble_only()
    async def duel(self, ctx, target: discord.Member, amount: str):

        guild_id = ctx.guild.id
        challenger = ctx.author
        challenger_id = challenger.id
        target_id = target.id

        # ======================
        # Basic validation
        # ======================
        if target.bot:
            return await ctx.send("❌ Tidak bisa duel dengan bot.")
        if target_id == challenger_id:
            return await ctx.send("❌ Tidak bisa duel dengan diri sendiri.")

        # Ambil cash GLOBAL
        cashA = self.get_available(challenger_id)
        cashB = self.get_available(target_id)

        bet = self.parse_bet(ctx, amount, cashA)
        if bet is None:
            return await ctx.send("❌ Nominal tidak valid.")
        if bet < 1:
            return await ctx.send("❌ Nominal minimal 1.")
        if cashA < bet:
            return await ctx.send("❌ Saldo kamu tidak cukup.")
        if cashB < bet:
            return await ctx.send("❌ Target tidak punya saldo cukup untuk duel.")

        bet_f = f"{bet:,}".replace(",", ".")

        # ======================
        # Duel pending check
        # ======================
        if get_duel_request(self.db, guild_id, target_id):
            return await ctx.send("❌ Target sedang punya duel pending.")
        if get_duel_request(self.db, guild_id, challenger_id):
            return await ctx.send("❌ Kamu sudah membuat duel lain.")

        # ======================
        # Simpan duel request
        # ======================
        create_duel_request(self.db, guild_id, challenger_id, target_id, bet)
        self.hold_amount(challenger_id, bet)
        self.hold_amount(target_id, bet)


        # ======================
        # Kirim challenge embed
        # ======================
        challenge_embed = discord.Embed(
            title="⚔️ Duel Challenge!",
            description=(
                f"{target.mention}, kamu ditantang duel oleh {challenger.mention}!\n\n"
                f"💰 **Taruhan:** `{bet_f}` coins\n\n"
                "Ketik **`accept`** untuk menerima atau **`decline`** untuk menolak "
                "dalam waktu **30 detik**."
            ),
            color=discord.Color.orange()
        )
        challenge_embed.set_footer(text="Duel menggunakan global cash")

        await ctx.send(embed=challenge_embed)

        # Tunggu jawaban target
        def check(m: discord.Message):
            return (
                m.author.id == target_id 
                and m.channel.id == ctx.channel.id 
                and m.content.lower() in ["accept", "decline"]
            )

        try:
            reply = await self.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            delete_duel_request(self.db, guild_id, challenger_id)
            timeout_embed = discord.Embed(
                title="⏳ Duel Expired",
                description=f"{target.mention} tidak merespon tepat waktu.\nDuel dibatalkan.",
                color=discord.Color.red()
            )
            self.release_amount(challenger_id, bet)
            self.release_amount(target_id, bet)

            return await ctx.send(embed=timeout_embed)

        # Declined
        if reply.content.lower() == "decline":
            delete_duel_request(self.db, guild_id, challenger_id)
            declined = discord.Embed(
                title="❌ Duel Ditolak",
                description=f"{target.mention} menolak duel dari {challenger.mention}.",
                color=discord.Color.red()
            )
            self.release_amount(challenger_id, bet)
            self.release_amount(target_id, bet)

            return await ctx.send(embed=declined)

        # ======================
        # START DUEL (GIF ANIMATION)
        # ======================

        # STEP 1 — Embed awal
        start_embed = discord.Embed(
            title="🎲 Duel Dimulai!",
            description=(
                f"{challenger.mention} vs {target.mention}\n\n"
                f"Taruhan: **{bet_f} coins**\n\n"
                "**Mengocok dadu...**"
            ),
            color=discord.Color.blurple()
        )

        start_msg = await ctx.send(embed=start_embed)
        await asyncio.sleep(1)

        # STEP 2 — GIF rolling
        rolling_embed = discord.Embed(
            title="🎲 Mengocok Dadu...",
            description="Dadu sedang diputar...\n\n**Tunggu sebentar!**",
            color=discord.Color.blurple()
        )

        rolling_file = discord.File("media/dice-game.gif", filename="dice.gif")
        rolling_embed.set_image(url="attachment://dice.gif")

        await start_msg.edit(embed=rolling_embed, attachments=[rolling_file])
        await asyncio.sleep(2)

        # STEP 3 — Tentukan roll
        rollA = random.randint(1, 6)
        rollB = random.randint(1, 6)

        while rollA == rollB:
            rollA = random.randint(1, 6)
            rollB = random.randint(1, 6)

        winner = challenger_id if rollA > rollB else target_id
        loser = target_id if winner == challenger_id else challenger_id

        # ======================
        # MONEY TRANSFER
        # ======================
        cashW = get_user_cash(self.db, winner)
        cashL = get_user_cash(self.db, loser)

        set_user_cash(self.db, winner, cashW + bet)
        set_user_cash(self.db, loser, cashL - bet)

        # Log
        log_gamble(self.db, guild_id, challenger_id, "duel", bet,
                   "WIN" if winner == challenger_id else "LOSE")
        log_gamble(self.db, guild_id, target_id, "duel", bet,
                   "WIN" if winner == target_id else "LOSE")

        # Hapus duel request
        delete_duel_request(self.db, guild_id, challenger_id)
        self.release_amount(challenger_id, bet)
        self.release_amount(target_id, bet)


        # ======================
        # FINAL RESULT (PNG)
        # ======================
        winner_member = ctx.guild.get_member(winner)
        loser_member = ctx.guild.get_member(loser)

        final_embed = discord.Embed(
            title="🏆 Hasil Duel!",
            description=(
                f"{challenger.mention}: **{rollA}**\n"
                f"{target.mention}: **{rollB}**\n\n"
                f"🏆 **Pemenang: {winner_member.mention}!**"
            ),
            color=discord.Color.green() if winner == challenger_id else discord.Color.gold()
        )

        final_embed.add_field(
            name="💰 Hadiah",
            value=(
                f"**+{bet_f} coins** → {winner_member.mention}\n"
                f"**-{bet_f} coins** → {loser_member.mention}"
            ),
            inline=False
        )

        fileA = discord.File(f"media/dice-{rollA}.png", filename="diceA.png")
        fileB = discord.File(f"media/dice-{rollB}.png", filename="diceB.png")

        final_embed.set_thumbnail(url="attachment://diceA.png")
        final_embed.set_image(url="attachment://diceB.png")

        await start_msg.edit(embed=final_embed, attachments=[fileA, fileB])

        # =====================================================================
    # ADMIN COMMAND — CLEAR DUEL
    # =====================================================================
    @commands.command(name="clearduel")
    async def mclear_duel(self, ctx, target: discord.Member):

        # Hanya admin / owner / ID spesifik
        if not ctx.author.guild_permissions.manage_guild and ctx.author.id != 416234104317804544:
            return await ctx.send("❌ Kamu tidak punya izin untuk menggunakan command ini.")

        guild_id = ctx.guild.id
        target_id = target.id

        # Cek apakah user punya duel pending
        pending = get_duel_request(self.db, guild_id, target_id)
        if not pending:
            return await ctx.send(f"ℹ️ {target.mention} **tidak memiliki duel pending.**")

        # Hapus duel pending
        delete_duel_request(self.db, guild_id, target_id)

        await ctx.send(f"✅ Duel pending milik {target.mention} telah dibersihkan.")

async def setup(bot):
    await bot.add_cog(DuelCog(bot))
