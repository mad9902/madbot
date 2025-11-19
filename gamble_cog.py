import discord
from discord.ext import commands
import random
import time

from database import (
    connect_db,
    get_user_cash, set_user_cash,
    log_gamble,
    get_channel_settings, set_channel_settings
)


class GambleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

        # Anti SPAM earn system
        self.last_earn = {}       # (guild, user): timestamp
        self.last_message = {}    # (guild, user): last content

        # Gamble cooldown
        self.gamble_cooldown = 3  # 3 seconds
        self.last_gamble = {}     # (guild, user): timestamp


    # =====================================================================
    #   earn cash from chatting
    # =====================================================================
    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return

        guild_id = message.guild.id
        user_id  = message.author.id

        content = message.content.strip()
        if len(content) < 5:
            return

        # anti duplicate
        if (guild_id, user_id) in self.last_message:
            if self.last_message[(guild_id, user_id)] == content:
                return

        self.last_message[(guild_id, user_id)] = content

        now = time.time()
        key = (guild_id, user_id)

        # cooldown 10s
        if key in self.last_earn and now - self.last_earn[key] < 10:
            return

        self.last_earn[key] = now

        # reward calc
        base = 3
        bonus = min(len(content) // 30, 7)
        gained = base + bonus

        cash_now = get_user_cash(self.db, user_id, guild_id)
        set_user_cash(self.db, user_id, guild_id, cash_now + gained)


    # =====================================================================
    #  set gamble channel
    # =====================================================================
    @commands.command(name="setgamblech")
    async def set_gamble_channel(self, ctx, channel: discord.TextChannel):
        if ctx.author.id not in [ctx.guild.owner_id, 416234104317804544]:
            return await ctx.send("❌ Kamu tidak punya izin.")

        db = connect_db()
        set_channel_settings(db, ctx.guild.id, "gamble", channel.id)
        db.close()

        await ctx.send(f"🎰 Channel gamble diatur ke {channel.mention}")


    # =====================================================================
    #  set maxbet
    # =====================================================================
    @commands.command(name="setmaxbet")
    async def set_maxbet(self, ctx, amount: int):
        if ctx.author.id not in [ctx.guild.owner_id, 416234104317804544]:
            return await ctx.send("❌ Kamu tidak punya izin.")

        if amount < 1:
            return await ctx.send("❌ Maxbet harus > 0.")

        db = connect_db()
        set_channel_settings(db, ctx.guild.id, "maxbet", amount)
        db.close()

        await ctx.send(f"🔒 Maxbet diset ke **{amount} coins**")


    # =====================================================================
    #  show balance
    # =====================================================================
    @commands.command(name="bal", aliases=["balance"])
    async def balance(self, ctx):
        cash = get_user_cash(self.db, ctx.author.id, ctx.guild.id)
        await ctx.send(f"💰 Saldo kamu: **{cash} coins**")


    # =====================================================================
    #  local cooldown
    # =====================================================================
    def gamble_on_cooldown(self, ctx):
        key = (ctx.guild.id, ctx.author.id)
        now = time.time()

        if key in self.last_gamble:
            diff = now - self.last_gamble[key]
            if diff < self.gamble_cooldown:
                return round(self.gamble_cooldown - diff, 1)

        self.last_gamble[key] = now
        return None


    # =====================================================================
    #  parse amount OR all
    # =====================================================================
    def parse_bet(self, ctx, amount_str):
        guild_id = ctx.guild.id
        user_id = ctx.author.id

        cash = get_user_cash(self.db, user_id, guild_id)
        maxbet = get_channel_settings(self.db, guild_id, "maxbet")
        maxbet = int(maxbet) if maxbet else None

        # all
        if amount_str.lower() == "all":
            bet = cash if maxbet is None else min(cash, maxbet)
            return bet, cash, maxbet

        # normal number
        if not amount_str.isdigit():
            return None, cash, maxbet

        bet = int(amount_str)

        if maxbet and bet > maxbet:
            bet = maxbet

        return bet, cash, maxbet


    # =====================================================================
    #  COINFLIP
    # =====================================================================
    @commands.command(name="cf", aliases=["coinflip"])
    async def coinflip(self, ctx, amount: str):

        # channel
        allowed = get_channel_settings(self.db, ctx.guild.id, "gamble")
        if allowed and ctx.channel.id != int(allowed):
            return await ctx.send(f"🎰 Command hanya bisa di <#{allowed}>.")

        # cooldown
        cd = self.gamble_on_cooldown(ctx)
        if cd:
            return await ctx.send(f"⏳ Tunggu **{cd}s** dulu.")

        bet, cash, maxbet = self.parse_bet(ctx, amount)
        if bet is None:
            return await ctx.send("❌ Nominal tidak valid.")
        if bet < 1:
            return await ctx.send("❌ Nominal harus > 0.")
        if cash < bet:
            return await ctx.send("❌ Saldo tidak cukup.")

        # result
        result = random.choice(["WIN", "LOSE"])

        if result == "WIN":
            cash += bet
            msg = f"🟢 MENANG! +{bet}"
        else:
            cash -= bet
            msg = f"🔴 KALAH! -{bet}"

        set_user_cash(self.db, ctx.author.id, ctx.guild.id, cash)
        log_gamble(self.db, ctx.guild.id, ctx.author.id, "coinflip", bet, result)

        await ctx.send(
            f"{ctx.author.mention} {msg}\n💰 Saldo: **{cash}**"
        )


    # =====================================================================
    #  SLOTS BASIC
    # =====================================================================
    @commands.command(name="slots")
    async def slots(self, ctx, amount: str):

        allowed = get_channel_settings(self.db, ctx.guild.id, "gamble")
        if allowed and ctx.channel.id != int(allowed):
            return await ctx.send(f"🎰 Command hanya bisa di <#{allowed}>.")

        # cooldown
        cd = self.gamble_on_cooldown(ctx)
        if cd:
            return await ctx.send(f"⏳ Tunggu **{cd}s** dulu.")

        bet, cash, maxbet = self.parse_bet(ctx, amount)
        if bet is None:
            return await ctx.send("❌ Nominal tidak valid.")
        if bet < 1:
            return await ctx.send("❌ Nominal harus > 0.")
        if cash < bet:
            return await ctx.send("❌ Saldo tidak cukup.")

        symbols = ["🍒", "⭐", "🍋", "🔔", "7️⃣"]
        r1 = random.choice(symbols)
        r2 = random.choice(symbols)
        r3 = random.choice(symbols)

        board = f"[ {r1} | {r2} | {r3} ]"

        if r1 == r2 == r3:
            multi = 10
        elif r1 == r2 or r2 == r3 or r1 == r3:
            multi = random.choice([2, 4, 5])
        else:
            multi = 0

        if multi > 0:
            win = bet * multi
            cash += win
            msg = f"🟢 MENANG x{multi}! +{win}"
        else:
            cash -= bet
            msg = f"🔴 KALAH! -{bet}"

        set_user_cash(self.db, ctx.author.id, ctx.guild.id, cash)
        log_gamble(self.db, ctx.guild.id, ctx.author.id, "slots", bet, "WIN" if multi > 0 else "LOSE")

        await ctx.send(
            f"{ctx.author.mention}\n🎰 {board}\n{msg}\n💰 Saldo: **{cash}**"
        )


async def setup(bot):
    await bot.add_cog(GambleCog(bot))
