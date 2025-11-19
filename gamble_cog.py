import discord
from discord.ext import commands
import random
import time
import asyncio

from database import (
    get_user_cash, set_user_cash,
    log_gamble,
    get_gamble_setting, set_gamble_setting
)

from gamble_utils import (
    gamble_only,
    comma
)


class GambleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

        # Earn system
        self.last_earn = {}
        self.last_message = {}

        # Cooldown
        self.gamble_cooldown = 3
        self.last_gamble = {}


    # =====================================================
    # AUTO EARN SYSTEM (GLOBAL CASH)
    # =====================================================
    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return

        user = message.author.id
        guild = message.guild.id

        content = message.content.strip()
        if len(content) < 5:
            return

        # anti-spam: same message
        if (guild, user) in self.last_message:
            if self.last_message[(guild, user)] == content:
                return
        self.last_message[(guild, user)] = content

        # 10s cooldown
        now = time.time()
        if (guild, user) in self.last_earn:
            if now - self.last_earn[(guild, user)] < 10:
                return
        self.last_earn[(guild, user)] = now

        # reward calculation
        gain = 3 + min(len(content) // 30, 7)

        cash = get_user_cash(self.db, user)
        set_user_cash(self.db, user, cash + gain)


    # =====================================================
    # LOCAL GAMBLE COOLDOWN
    # =====================================================
    def gamble_on_cooldown(self, ctx):
        user = ctx.author.id
        now = time.time()

        if user in self.last_gamble:
            diff = now - self.last_gamble[user]
            if diff < self.gamble_cooldown:
                return round(self.gamble_cooldown - diff, 1)

        self.last_gamble[user] = now
        return None


    # =====================================================
    # SET GAMBLE CHANNEL
    # =====================================================
    @commands.command(name="setgamblech")
    async def set_gamble_channel(self, ctx, channel: discord.TextChannel):
        if ctx.author.id not in [ctx.guild.owner_id, 416234104317804544]:
            return await ctx.send("❌ Kamu tidak punya izin.")

        set_gamble_setting(self.db, ctx.guild.id, "gamble_ch", channel.id)
        await ctx.send(f"🎰 Channel gamble telah diatur ke {channel.mention}")


    # =====================================================
    # SET MAXBET (per guild)
    # =====================================================
    @commands.command(name="setmaxbet")
    async def set_maxbet(self, ctx, amount: int):
        if ctx.author.id not in [ctx.guild.owner_id, 416234104317804544]:
            return await ctx.send("❌ Kamu tidak punya izin.")

        if amount < 1:
            return await ctx.send("❌ Maxbet harus > 0.")

        set_gamble_setting(self.db, ctx.guild.id, "maxbet", amount)
        await ctx.send(f"🔒 Maxbet ditetapkan ke **{amount} coins**")


    # =====================================================
    # BALANCE (GLOBAL CASH)
    # =====================================================
    @commands.command(name="bal", aliases=["balance"])
    @gamble_only()
    async def balance(self, ctx):
        cash = get_user_cash(self.db, ctx.author.id)
        await ctx.send(f"💰 Saldo kamu: **{comma(cash)} coins**")


    # =====================================================
    # PARSE BET (GLOBAL CASH)
    # =====================================================
    def parse_bet(self, ctx, amount_str):
        user = ctx.author.id
        guild = ctx.guild.id

        cash = get_user_cash(self.db, user)

        maxbet = get_gamble_setting(self.db, guild, "maxbet")
        maxbet = int(maxbet) if maxbet else None

        if amount_str.lower() == "all":
            bet = cash if not maxbet else min(cash, maxbet)
            return bet, cash, maxbet

        if not amount_str.isdigit():
            return None, cash, maxbet

        bet = int(amount_str)
        if maxbet and bet > maxbet:
            bet = maxbet

        return bet, cash, maxbet


    # =====================================================
    # COINFLIP
    # =====================================================
    @commands.command(name="cf", aliases=["coinflip"])
    @gamble_only()
    async def coinflip(self, ctx, amount: str):

        bet, cash, maxbet = self.parse_bet(ctx, amount)
        if bet is None:
            return await ctx.send("❌ Nominal tidak valid.")
        if bet < 1:
            return await ctx.send("❌ Bet minimal 1.")
        if cash < bet:
            return await ctx.send("❌ Saldo tidak cukup.")

        result = random.choice(["WIN", "LOSE"])

        if result == "WIN":
            cash += bet
            msg = f"🟢 MENANG! +{comma(bet)}"
        else:
            cash -= bet
            msg = f"🔴 KALAH! -{comma(bet)}"

        set_user_cash(self.db, ctx.author.id, cash)
        log_gamble(self.db, ctx.guild.id, ctx.author.id, "coinflip", bet, result)

        await ctx.send(f"{ctx.author.mention} {msg}\n💰 Saldo: **{comma(cash)}**")


    # =====================================================
    # SLOTS
    # =====================================================
    @commands.command(name="slots")
    @gamble_only()
    async def slots(self, ctx, amount: str):

        bet, cash, maxbet = self.parse_bet(ctx, amount)
        if bet is None:
            return await ctx.send("❌ Nominal tidak valid.")
        if bet < 1:
            return await ctx.send("❌ Bet minimal 1.")
        if cash < bet:
            return await ctx.send("❌ Saldo tidak cukup.")

        symbols = ["🍒", "🍋", "🔔", "⭐", "7️⃣"]
        multipliers = {
            "🍒": 2,
            "🍋": 3,
            "🔔": 5,
            "⭐": 8,
            "7️⃣": 10
        }

        # 8% win chance
        if random.random() < 0.12:
            r = random.choice(symbols)
            r1 = r2 = r3 = r
            is_win = True
        else:
            while True:
                r1 = random.choice(symbols)
                r2 = random.choice(symbols)
                r3 = random.choice(symbols)
                if not (r1 == r2 == r3):
                    break
            is_win = False

        spin1 = f"[ {random.choice(symbols)} | ❔ | ❔ ]"
        spin2 = f"[ {r1} | {random.choice(symbols)} | ❔ ]"
        final = f"[ {r1} | {r2} | {r3} ]"

        embed = discord.Embed(
            title="🎰 Slots Machine",
            description=f"**Menarik tuas...**\n\n{spin1}",
            color=discord.Color.gold()
        )
        msg = await ctx.send(embed=embed)

        await asyncio.sleep(0.6)
        embed.description = f"**Berputar...**\n\n{spin2}"
        await msg.edit(embed=embed)

        await asyncio.sleep(0.6)
        embed.description = f"**Hasil:**\n\n{final}"
        await msg.edit(embed=embed)

        if is_win:
            multi = multipliers[r1]
            win_amount = bet * multi
            cash += win_amount

            desc = (
                f"🟢 **MENANG!** {r1*3}\n"
                f"Multiplier x{multi}\n"
                f"**+{comma(win_amount)} coins**"
            )
            color = discord.Color.green()
            status = "WIN"
        else:
            cash -= bet
            desc = f"🔴 **KALAH! -{comma(bet)} coins**"
            color = discord.Color.red()
            status = "LOSE"

        set_user_cash(self.db, ctx.author.id, cash)
        log_gamble(self.db, ctx.guild.id, ctx.author.id, "slots", bet, status)

        result = discord.Embed(
            title="🎰 Slots Result",
            description=f"{final}\n\n{desc}\n\n💰 **Saldo: {comma(cash)}**",
            color=color
        )
        await msg.edit(embed=result)


async def setup(bot):
    await bot.add_cog(GambleCog(bot))
