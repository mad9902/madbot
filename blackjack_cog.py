import discord
from discord.ext import commands
import asyncio
import random
import time

from database import (
    get_user_cash, set_user_cash,
    log_gamble,
    get_gamble_setting
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

        self.active_games = {}        # (guild, user)
        self.last_bj = {}             # cooldown
        self.cooldown = 5             # seconds

    # ============================================================
    # COOLDOWN
    # ============================================================
    def on_cooldown(self, user_id):
        now = time.time()
        if user_id in self.last_bj:
            diff = now - self.last_bj[user_id]
            if diff < self.cooldown:
                return round(self.cooldown - diff, 1)
        self.last_bj[user_id] = now
        return None

    # ============================================================
    # DECK
    # ============================================================
    def new_deck(self):
        ranks = ["A","2","3","4","5","6","7","8","9","10","J","Q","K"]
        suits = ["♠","♥","♦","♣"]
        deck = [f"{r}{s}" for r in ranks for s in suits]
        random.shuffle(deck)
        return deck

    def draw(self, deck, bias_high=False):
        if bias_high:
            # cari kartu tinggi
            for i, c in enumerate(deck):
                r = c[:-1]
                if r in ["10","J","Q","K","A"]:
                    return deck.pop(i)
        return deck.pop()
    
    def smart_dealer_draw(self, deck, dealer_hand, player_val):
        # pilih kartu yang bikin dealer menang tapi ga bust
        for i, c in enumerate(deck):
            test = dealer_hand + [c]
            v = self.hand_value(test)
            if 17 <= v <= 21 and v >= player_val:
                return deck.pop(i)
        return deck.pop()  # fallback normal


    # ============================================================
    # HAND VALUE
    # ============================================================
    def hand_value(self, cards):
        total = 0
        aces = 0

        for c in cards:
            r = c[:-1]
            if r in ["J","Q","K"]:
                total += 10
            elif r == "A":
                total += 11
                aces += 1
            else:
                total += int(r)

        while total > 21 and aces:
            total -= 10
            aces -= 1

        return total

    # ============================================================
    # MAIN COMMAND
    # ============================================================
    @commands.command(name="blackjack", aliases=["bj"])
    @gamble_only()
    async def blackjack(self, ctx, bet: str):

        guild_id = ctx.guild.id
        user_id = ctx.author.id

        # cooldown
        cd = self.on_cooldown(user_id)
        if cd:
            return await ctx.send(f"⏳ Tunggu **{cd}s** sebelum bermain lagi.")

        # active game check
        key = (guild_id, user_id)
        if key in self.active_games:
            return await ctx.send("❌ Kamu masih dalam permainan blackjack.")

        # parse bet (GLOBAL CASH)
        cash = get_user_cash(self.db, user_id)
        maxbet = get_gamble_setting(self.db, guild_id, "maxbet")
        maxbet = int(maxbet) if maxbet else None

        if bet.lower() == "all":
            bet = cash if maxbet is None else min(cash, maxbet)
        elif bet.isdigit():
            bet = int(bet)
            if maxbet and bet > maxbet:
                bet = maxbet
        else:
            return await ctx.send("❌ Nominal tidak valid.")

        if bet < 1:
            return await ctx.send("❌ Minimal bet 1.")
        if cash < bet:
            return await ctx.send("❌ Saldo tidak cukup.")

        # init game
        deck = self.new_deck()
        player = [self.draw(deck), self.draw(deck)]
        dealer = [self.draw(deck), self.draw(deck)]

        game = {
            "deck": deck,
            "player": player,
            "dealer": dealer,
            "bet": bet
        }
        self.active_games[key] = game

        # ============================================================
        # EMBED BUILDER
        # ============================================================
        async def build_embed(reveal=False, title="🃏 Blackjack — {user}"):
            p_val = self.hand_value(player)
            d_val = self.hand_value(dealer) if reveal else "?"
            d_cards = (
                render_hand(dealer) if reveal
                else f"{render_card(dealer[0])} {render_card(CARD_BACK)}"
            )

            emb = discord.Embed(
                title=title.format(user=ctx.author.display_name),
                color=discord.Color.gold()
            )

            emb.add_field(
                name="🧑 Pemain",
                value=f"{render_hand(player)}\n**Total: {p_val}**",
                inline=False
            )
            emb.add_field(
                name="🤵 Dealer",
                value=f"{d_cards}\n**Total: {d_val}**",
                inline=False
            )
            emb.set_footer(text="HIT = 🟩 | STAND = 🟥 | SURRENDER = 🏳️")

            return emb
        
        # dealing animation
        msg = await ctx.send(embed=await build_embed(title="🃏 Mengocok kartu..."))
        await asyncio.sleep(0.7)
        await msg.edit(embed=await build_embed(
            reveal=False,
            title="🃏 Kartu dibagikan — {user}"
        ))
        await asyncio.sleep(0.7)
        await msg.edit(embed=await build_embed(
            reveal=False,
            title="🃏 Giliran {user}!"
        ))
        await msg.add_reaction("🟩")  # hit
        await msg.add_reaction("🟥")  # stand
        await msg.add_reaction("🏳️") # surrender

        # ============================================================
        # REACTION LOOP
        # ============================================================
        def check(reaction, user):
            return (
                user.id == user_id and
                reaction.message.id == msg.id and
                str(reaction.emoji) in ["🟩","🟥","🏳️"]
            )

        while True:
            try:
                reaction, user = await self.bot.wait_for(
                    "reaction_add", timeout=45, check=check
                )
            except asyncio.TimeoutError:
                del self.active_games[key]
                return await msg.edit(embed=discord.Embed(
                    title="⏳ Timeout",
                    description="Game dibatalkan.",
                    color=discord.Color.red()
                ))

            emoji = str(reaction.emoji)
            # Auto unreact biar ga numpuk (🟩 x2, 🟥 x3, dll)
            try:
                await msg.remove_reaction(emoji, user)
            except:
                pass


            # ------------------------------
            # HIT
            # ------------------------------
            if emoji == "🟩":
                player.append(self.draw(deck, bias_high=True))
                await msg.edit(embed=await build_embed(
                    reveal=False,
                    title="🟩 {user} mengambil kartu..."
                ))
                await asyncio.sleep(0.4)

                if self.hand_value(player) > 21:
                    new_cash = cash - bet
                    set_user_cash(self.db, user_id, new_cash)
                    log_gamble(self.db, ctx.guild.id, user_id, "blackjack", bet, "LOSE")
                    del self.active_games[key]

                    return await msg.edit(embed=discord.Embed(
                        title="💥 Bust!",
                        description=f"Kamu: {render_hand(player)} (**{self.hand_value(player)}**)\n\n🔴 Kalah **-{comma(bet)}**",
                        color=discord.Color.red()
                    ))

                continue

            # ------------------------------
            # SURRENDER
            # ------------------------------
            if emoji == "🏳️":
                loss = bet // 2
                new_cash = cash - loss
                set_user_cash(self.db, user_id, new_cash)
                log_gamble(self.db, ctx.guild.id, user_id, "blackjack", loss, "LOSE")
                del self.active_games[key]

                return await msg.edit(embed=discord.Embed(
                    title="🏳️ Menyerah!",
                    description=f"Kamu kehilangan **-{comma(loss)}**",
                    color=discord.Color.orange()
                ))

            # ------------------------------
            # STAND
            # ------------------------------
            if emoji == "🟥":
                break

        # ============================================================
        # DEALER TURN
        # ============================================================
        p_val = self.hand_value(player)

        await msg.edit(embed=await build_embed(
            reveal=True,
            title="🤵 Dealer membuka kartu — melawan {user}"
        ))
        await asyncio.sleep(1)

        while self.hand_value(dealer) < 17:
            dealer.append(self.smart_dealer_draw(deck, dealer, p_val))
            await msg.edit(embed=await build_embed(
                reveal=True,
                title="🤵 Dealer mengambil kartu — melawan {user}"
            ))
            await asyncio.sleep(1)


        # ============================================================
        # RESULT
        # ============================================================
        p_val = self.hand_value(player)
        d_val = self.hand_value(dealer)

        if d_val > 21 or p_val > d_val:
            win = bet
            if p_val == 21 and len(player) == 2:
                win = int(bet * 1)  # atau 1x bet biar lebih parah


            new_cash = cash + win
            set_user_cash(self.db, user_id, new_cash)
            log_gamble(self.db, ctx.guild.id, user_id, "blackjack", bet, "WIN")

            result = f"🟢 Menang **+{comma(win)}**"
            color = discord.Color.green()

        elif d_val > p_val:
            new_cash = cash - bet
            set_user_cash(self.db, user_id, new_cash)
            log_gamble(self.db, ctx.guild.id, user_id, "blackjack", bet, "LOSE")


            result = f"🔴 Kalah **-{comma(bet)}**"
            color = discord.Color.red()

        else:
            result = "⚪ Seri (push)"
            color = discord.Color.greyple()

        del self.active_games[key]

        final = discord.Embed(
            title="🟣 Hasil Blackjack",
            description=f"""
**Kamu:** {render_hand(player)} (**{p_val}**)  
**Dealer:** {render_hand(dealer)} (**{d_val}**)  

{result}
""",
            color=color
        )
        await msg.edit(embed=final)


async def setup(bot):
    await bot.add_cog(BlackjackCog(bot))
