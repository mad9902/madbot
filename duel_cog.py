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

        # CASH GLOBAL !!!
        cashA = get_user_cash(self.db, challenger_id)
        cashB = get_user_cash(self.db, target_id)

        bet = self.parse_bet(ctx, amount, cashA)
        bet_f = f"{bet:,}".replace(",", ".")

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

        # Embed challenge
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

        msg = await ctx.send(embed=challenge_embed)

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
            return await ctx.send(embed=timeout_embed)

        # ======================
        # DECLINE
        # ======================
        if reply.content.lower() == "decline":
            delete_duel_request(self.db, guild_id, challenger_id)
            declined = discord.Embed(
                title="❌ Duel Ditolak",
                description=f"{target.mention} menolak duel dari {challenger.mention}.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=declined)

        # ======================
        # START DUEL (ANIMASI)
        # ======================
        start_embed = discord.Embed(
            title="🎲 Duel Dimulai!",
            description=(
                f"{challenger.mention} vs {target.mention}\n\n"
                f"Taruhan: **{bet} coins**\n\n"
                "Mengocok dadu..."
            ),
            color=discord.Color.blurple()
        )
        start_msg = await ctx.send(embed=start_embed)

        # Animasi roll: edit beberapa kali
        dice_faces = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
        anim_steps = 5

        rollA = rollB = None

        for _ in range(anim_steps):
            rollA = random.randint(1, 6)
            rollB = random.randint(1, 6)

            anim_embed = discord.Embed(
                title="🎲 Mengocok Dadu...",
                description=(
                    f"{challenger.mention}: {dice_faces[rollA - 1]} (`{rollA}`)\n"
                    f"{target.mention}: {dice_faces[rollB - 1]} (`{rollB}`)\n\n"
                    "Siapa yang akan menang...?"
                ),
                color=discord.Color.blurple()
            )

            await start_msg.edit(embed=anim_embed)
            await asyncio.sleep(0.7)

        # Kalau seri, ulang sampai beda (tanpa animasi panjang biar nggak kelamaan)
        while rollA == rollB:
            rollA = random.randint(1, 6)
            rollB = random.randint(1, 6)

        winner = challenger_id if rollA > rollB else target_id
        loser = target_id if winner == challenger_id else challenger_id

        # ======================
        # Money transfer (GLOBAL)
        # ======================
        cashW = get_user_cash(self.db, winner)
        cashL = get_user_cash(self.db, loser)

        set_user_cash(self.db, winner, cashW + bet)
        set_user_cash(self.db, loser, cashL - bet)

        # log per-guild
        log_gamble(
            self.db, ctx.guild.id, challenger_id, "duel", bet,
            "WIN" if winner == challenger_id else "LOSE"
        )
        log_gamble(
            self.db, ctx.guild.id, target_id, "duel", bet,
            "WIN" if winner == target_id else "LOSE"
        )

        delete_duel_request(self.db, guild_id, challenger_id)

        winner_member = ctx.guild.get_member(winner)
        loser_member = ctx.guild.get_member(loser)

        result_embed = discord.Embed(
            title="🏆 Hasil Duel!",
            color=discord.Color.green()
            if winner == challenger_id else discord.Color.gold()
        )
        result_embed.add_field(
            name="🎲 Roll",
            value=(
                f"{challenger.mention}: {dice_faces[rollA - 1]} (`{rollA}`)\n"
                f"{target.mention}: {dice_faces[rollB - 1]} (`{rollB}`)"
            ),
            inline=False
        )
        result_embed.add_field(
            name="Pemenang",
            value=f"🏆 {winner_member.mention}",
            inline=False
        )
        result_embed.add_field(
            name="Hadiah",
            value=f"💰 **+{bet} coins** untuk {winner_member.mention}\n"
                  f"💸 **-{bet} coins** untuk {loser_member.mention}",
            inline=False
        )
        result_embed.set_footer(text="Duel menggunakan global cash")

        await start_msg.edit(embed=result_embed)


async def setup(bot):
    await bot.add_cog(DuelCog(bot))
