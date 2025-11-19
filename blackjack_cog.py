import discord
from discord.ext import commands
import asyncio
import random
import time

from database import (
    get_user_cash, set_user_cash,
    get_gamble_setting, log_gamble
)
from gamble_utils import gamble_only, comma


CARD_BACK = "🂠"

def render_card(card):
    return f"`[{card}]`"

def render_hand(cards):
    return " ".join(render_card(c) for c in cards)


class BlackjackCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.active_games = {}   # (guild, user)
        self.last_bj = {}        # cooldown
        self.cooldown = 5        # 5s cooldown


    # DECK
    def new_deck(self):
        ranks = ["A","2","3","4","5","6","7","8","9","10","J","Q","K"]
        suits = ["♠","♥","♦","♣"]
        deck = [f"{r}{s}" for r in ranks for s in suits]
        random.shuffle(deck)
        return deck

    def draw(self, deck):
        return deck.pop()

    def hand_value(self, cards):
        total = 0
        aces = 0
        for c in cards:
            r = c[:-1]
            if r in ["J","Q","K"]:
                total += 10
            elif r == "A":
                aces += 1
                total += 11
            else:
                total += int(r)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    def parse_bet(self, ctx, bet_str):
        cash = get_user_cash(self.db, ctx.author.id, ctx.guild.id)
        maxbet = get_gamble_setting(self.db, ctx.guild.id, "maxbet")
        maxbet = int(maxbet) if maxbet else None

        if bet_str.lower() == "all":
            return cash if not maxbet else min(cash, maxbet), cash

        if not bet_str.isdigit():
            return None, cash

        bet = int(bet_str)
        if bet < 1:
            return None, cash

        if maxbet and bet > maxbet:
            bet = maxbet

        return bet, cash


    def on_cooldown(self, user_id):
        now = time.time()
        if user_id in self.last_bj:
            diff = now - self.last_bj[user_id]
            if diff < self.cooldown:
                return round(self.cooldown - diff, 1)
        self.last_bj[user_id] = now
        return None


    # ====================================================================
    #                           COMMAND
    # ====================================================================
    @commands.command(name="blackjack", aliases=["bj"])
    @gamble_only()   # <— WARRANTY GAK BISA DI LUAR CHANNEL GAMBLE
    async def blackjack(self, ctx, bet: str):

        guild_id = ctx.guild.id
        user_id = ctx.author.id
        key = (guild_id, user_id)

        # cooldown
        cd = self.on_cooldown(user_id)
        if cd:
            return await ctx.send(f"⏳ Tunggu **{cd}s** lagi.")

        if key in self.active_games:
            return await ctx.send("❌ Kamu masih dalam game blackjack lain.")

        # parse bet
        bet, cash = self.parse_bet(ctx, bet)
        if bet is None:
            return await ctx.send("❌ Nominal tidak valid.")

        if bet > cash:
            return await ctx.send("❌ Saldo tidak cukup.")

        # INIT DECK & HANDS
        deck = self.new_deck()
        player = [self.draw(deck), self.draw(deck)]
        dealer = [self.draw(deck), self.draw(deck)]

        game = {
            "deck": deck,
            "player": player,
            "dealer": dealer,
            "bet": bet,
            "msg": None,
        }
        self.active_games[key] = game


        # ---------------------------------------------------------------
        # EMBED BUILDER
        # ---------------------------------------------------------------
        async def build_embed(title="🃏 Blackjack — MadBot Casino", reveal_dealer=False):
            p_val = self.hand_value(player)

            if reveal_dealer:
                d_hand = render_hand(dealer)
                d_val = self.hand_value(dealer)
            else:
                d_hand = f"{render_card(dealer[0])} {render_card(CARD_BACK)}"
                d_val = "?"

            emb = discord.Embed(title=title, color=discord.Color.gold())
            emb.add_field(
                name="🧑 Pemain",
                value=f"{render_hand(player)}\n**Total: {p_val}**",
                inline=False
            )
            emb.add_field(
                name="🤵 Dealer",
                value=f"{d_hand}\n**Total: {d_val}**",
                inline=False
            )
            emb.set_footer(text="🟩 HIT  |  🟥 STAND  |  🏳️ SURRENDER")
            return emb


        # DEALING ANIMATION
        msg = await ctx.send(embed=await build_embed("🃏 Mengocok & membagikan..."))
        game["msg"] = msg

        await asyncio.sleep(0.6)
        await msg.edit(embed=await build_embed("🃏 Memberikan kartu pertama..."))
        await asyncio.sleep(0.6)
        await msg.edit(embed=await build_embed("🃏 Memberikan kartu kedua..."))
        await asyncio.sleep(0.6)
        await msg.edit(embed=await build_embed("🃏 Giliran kamu!"))

        await msg.add_reaction("🟩")
        await msg.add_reaction("🟥")
        await msg.add_reaction("🏳️")


        # ---------------------------------------------------------------
        # REACTION LOOP
        # ---------------------------------------------------------------
        def check(reaction, user):
            return (
                user.id == user_id and
                reaction.message.id == msg.id and
                str(reaction.emoji) in ["🟩","🟥","🏳️"]
            )

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=45, check=check)
            except asyncio.TimeoutError:
                del self.active_games[key]
                return await msg.edit(embed=discord.Embed(
                    title="⏳ Timeout",
                    description="Game dibatalkan.",
                    color=discord.Color.red()
                ))

            emoji = str(reaction.emoji)


            # ======================================================
            # HIT
            # ======================================================
            if emoji == "🟩":
                card = self.draw(deck)
                player.append(card)

                await asyncio.sleep(0.5)
                await msg.edit(embed=await build_embed("🟩 Kamu mengambil kartu..."))

                # BUST
                if self.hand_value(player) > 21:
                    new_cash = cash - bet
                    set_user_cash(self.db, user_id, guild_id, new_cash)
                    log_gamble(self.db, guild_id, user_id, "blackjack", bet, "LOSE")

                    del self.active_games[key]
                    return await msg.edit(embed=discord.Embed(
                        title="💥 Bust!",
                        description=f"Kamu: {render_hand(player)} (**{self.hand_value(player)}**)\n\n🔴 Kalah **-{comma(bet)}**",
                        color=discord.Color.red()
                    ))
                continue


            # ======================================================
            # SURRENDER
            # ======================================================
            if emoji == "🏳️":
                loss = bet // 2
                new_cash = cash - loss
                set_user_cash(self.db, user_id, guild_id, new_cash)
                log_gamble(self.db, guild_id, user_id, "blackjack", loss, "LOSE")

                del self.active_games[key]
                return await msg.edit(embed=discord.Embed(
                    title="🏳️ Menyerah!",
                    description=f"Kamu menyerah dan kehilangan **-{comma(loss)}**",
                    color=discord.Color.orange()
                ))


            # ======================================================
            # STAND
            # ======================================================
            if emoji == "🟥":
                break


        # ============================================================
        # DEALER TURN
        # ============================================================
        await msg.edit(embed=await build_embed("🤵 Dealer membuka kartu...", reveal_dealer=True))
        await asyncio.sleep(1)

        while self.hand_value(dealer) < 17:
            dealer.append(self.draw(deck))
            await msg.edit(embed=await build_embed("🤵 Dealer mengambil kartu...", reveal_dealer=True))
            await asyncio.sleep(1)


        # ============================================================
        # RESULT
        # ============================================================
        p = self.hand_value(player)
        d = self.hand_value(dealer)

        # WIN
        if d > 21 or p > d:
            win = bet

            # Natural blackjack 3:2
            if p == 21 and len(player) == 2:
                win = int(bet * 1.5)

            new_cash = cash + win
            set_user_cash(self.db, user_id, guild_id, new_cash)
            log_gamble(self.db, guild_id, user_id, "blackjack", bet, "WIN")

            result = f"🟢 Menang **+{comma(win)}**"
            color = discord.Color.green()

        # LOSE
        elif d > p:
            new_cash = cash - bet
            set_user_cash(self.db, user_id, guild_id, new_cash)
            log_gamble(self.db, guild_id, user_id, "blackjack", bet, "LOSE")

            result = f"🔴 Kalah **-{comma(bet)}**"
            color = discord.Color.red()

        # PUSH
        else:
            result = "⚪ Seri (push)"
            color = discord.Color.greyple()

        del self.active_games[key]

        final = discord.Embed(
            title="🟣 Hasil Blackjack",
            description=f"""
**Kamu:** {render_hand(player)} (**{p}**)  
**Dealer:** {render_hand(dealer)} (**{d}**)  

{result}
""",
            color=color
        )
        await msg.edit(embed=final)



async def setup(bot):
    await bot.add_cog(BlackjackCog(bot))
