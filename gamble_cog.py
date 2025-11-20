import discord
from discord.ext import commands
from discord.ui import View, Button
import random
import os
import time
import datetime
import asyncio

from database import (
    get_user_cash, set_user_cash,
    log_gamble, get_rob_victim_protect,
    get_gamble_setting, set_gamble_setting, get_rob_stats, 
    add_rob_success, add_rob_fail, get_total_gamble_wins, get_user_protection
)

from gamble_utils import (
    gamble_only,
    comma
)

class ConfirmTransfer(View):
    def __init__(self, giver, target, amount, db):
        super().__init__(timeout=20)
        self.giver = giver
        self.target = target
        self.amount = amount
        self.db = db

    async def interaction_check(self, interaction):
        return interaction.user.id == self.giver.id

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction, button):

        giver_cash = get_user_cash(self.db, self.giver.id)

        if giver_cash < self.amount:
            return await interaction.response.edit_message(
                content="❌ Saldo kamu tidak cukup.",
                view=None
            )

        # Transfer beneran
        set_user_cash(self.db, self.giver.id, giver_cash - self.amount)
        target_cash = get_user_cash(self.db, self.target.id)
        set_user_cash(self.db, self.target.id, target_cash + self.amount)

        embed = discord.Embed(
            title="💸 Transfer Berhasil",
            description=(
                f"{self.giver.mention} telah mentransfer **{comma(self.amount)} coins** "
                f"kepada {self.target.mention}.\n\n"
                f"💰 Saldo kamu sekarang: **{comma(giver_cash - self.amount)}**"
            ),
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction, button):
        cancel_embed = discord.Embed(
            title="❌ Transfer Dibatalkan",
            description=(
                f"Transfer **{comma(self.amount)} coins** ke {self.target.mention} "
                f"dibatalkan oleh {self.giver.mention}."
            ),
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=cancel_embed, view=None)
        self.stop()


class ConfirmGive(View):
    def __init__(self, giver, target, amount, db):
        super().__init__(timeout=20)
        self.giver = giver
        self.target = target
        self.amount = amount
        self.db = db
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction):
        # Hanya yg menjalankan command yg bisa klik
        if interaction.user.id != self.giver.id:
            await interaction.response.send_message("❌ Bukan aksi kamu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        # Update cash
        cash = get_user_cash(self.db, self.target.id)
        new_cash = cash + self.amount
        set_user_cash(self.db, self.target.id, new_cash)

        embed = discord.Embed(
            title="💸 Cash Given",
            description=(
                f"{self.giver.mention} memberikan **{comma(self.amount)} coins** kepada {self.target.mention}!\n\n"
                f"💰 Saldo baru {self.target.mention}: **{comma(new_cash)}**"
            ),
            color=discord.Color.green()
        )

        await interaction.response.edit_message(embed=embed, view=None)
        self.value = True
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: Button):

        cancel_embed = discord.Embed(
            title="❌ Transfer Dibatalkan",
            description=(
                f"Transfer **{comma(self.amount)} coins** ke {self.target.mention} "
                f"telah dibatalkan oleh {self.giver.mention}."
            ),
            color=discord.Color.red()
        )

        await interaction.response.edit_message(embed=cancel_embed, view=None)
        self.stop()


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

    # ======================================================================
    # COMMAND: give (WITH CONFIRMATION)
    # ======================================================================
    @commands.command(name="give")
    async def mtransfer(self, ctx, user: discord.Member, amount: str):

        if not amount.isdigit():
            return await ctx.send("❌ Nominal tidak valid.")

        amount = int(amount)
        if amount < 1:
            return await ctx.send("❌ Nominal harus lebih dari 0.")

        giver_cash = get_user_cash(self.db, ctx.author.id)
        if giver_cash < amount:
            return await ctx.send("❌ Saldo kamu tidak cukup untuk transfer.")

        view = ConfirmTransfer(ctx.author, user, amount, self.db)

        embed = discord.Embed(
            title="⚠️ Konfirmasi Transfer",
            description=(
                f"**{ctx.author.mention}**, kamu akan mentransfer:\n\n"
                f"💸 **{comma(amount)} coins**\n"
                f"➡️ Kepada: {user.mention}\n\n"
                f"Apakah kamu yakin?"
            ),
            color=discord.Color.orange()
        )

        await ctx.send(embed=embed, view=view)

    # ======================================================================
    # COMMAND: godmode (WITH CONFIRMATION)
    # ======================================================================
    @commands.command(name="godmode")
    async def mgive(self, ctx, user: discord.Member, amount: str):
        # Validasi nominal
        if ctx.author.id not in [416234104317804544]:
            return await ctx.send("❌ Kamu tidak punya izin menggunakan command ini.")
        
        if amount.lower() == "all":
            return await ctx.send("❌ Nominal tidak boleh 'all' untuk mgive.")

        if not amount.isdigit():
            return await ctx.send("❌ Nominal tidak valid.")

        amount = int(amount)
        if amount < 1:
            return await ctx.send("❌ Nominal harus lebih dari 0.")

        # View konfirmasi
        view = ConfirmGive(ctx.author, user, amount, self.db)

        embed = discord.Embed(
            title="⚠️ Konfirmasi Transfer",
            description=(
                f"**{ctx.author.mention}**, kamu akan memberikan:\n\n"
                f"💸 **{comma(amount)} coins**\n"
                f"➡️ Kepada: {user.mention}\n\n"
                f"Apakah kamu yakin?"
            ),
            color=discord.Color.orange()
        )

        await ctx.send(embed=embed, view=view)


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
    async def coinflip(self, ctx, arg1: str, arg2: str = None):

        # ============================
        # GUESS PARSER
        # ============================
        valid_guess = {
            "h": "HEAD", "head": "HEAD",
            "t": "TAIL", "tail": "TAIL"
        }

        guess = None
        amount_str = None

        if arg1.lower() in valid_guess:
            guess = valid_guess[arg1.lower()]
            amount_str = arg2
        else:
            amount_str = arg1
            if arg2 and arg2.lower() in valid_guess:
                guess = valid_guess[arg2.lower()]

        if not guess:
            guess = "HEAD"  # default

        if not amount_str:
            return await ctx.send("❌ Kamu belum memasukkan nominal bet.")

        bet, cash, maxbet = self.parse_bet(ctx, amount_str)
        if bet is None:
            return await ctx.send("❌ Nominal tidak valid.")
        if bet < 1:
            return await ctx.send("❌ Bet minimal 1.")
        if cash < bet:
            return await ctx.send("❌ Saldo tidak cukup.")

        # ============================
        # PATH GAMBAR — pake flip.gif
        # ============================
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        COIN_DIR = os.path.join(BASE_DIR, "media")

        flip_gif = os.path.join(COIN_DIR, "flip.gif")
        head_img = os.path.join(COIN_DIR, "head.png")
        tail_img = os.path.join(COIN_DIR, "tail.png")

        # ============================
        # STEP 1 — Flip GIF (utama)
        # ============================
        flip_embed = discord.Embed(
            title="🪙 Coinflip",
            description=f"{ctx.author.mention} melempar koin...\n\n**Berputar...**",
            color=discord.Color.blurple()
        )

        flip_file = discord.File(flip_gif, filename="flip.gif")
        flip_embed.set_image(url="attachment://flip.gif")

        msg = await ctx.send(embed=flip_embed, file=flip_file)

        # biar GIF kebaca
        await asyncio.sleep(2.0)

        # ============================
        # STEP 2 — RESULT
        # ============================
        actual = random.choice(["HEAD", "TAIL"])
        final_img = head_img if actual == "HEAD" else tail_img

        if guess == actual:
            cash += bet
            status = f"🟢 **Kamu menang! +{comma(bet)}**"
            color = discord.Color.green()
            res_code = "WIN"
        else:
            cash -= bet
            status = f"🔴 **Kamu kalah! -{comma(bet)}**"
            color = discord.Color.red()
            res_code = "LOSE"

        set_user_cash(self.db, ctx.author.id, cash)
        log_gamble(self.db, ctx.guild.id, ctx.author.id, "coinflip", bet, res_code)

        final_embed = discord.Embed(
            title="🪙 Coinflip Result",
            description=(
                f"Tebakan kamu: **{guess}**\n"
                f"Hasil koin: **{actual}**\n\n"
                f"{status}\n\n"
                f"💰 **Saldo sekarang: {comma(cash)}**"
            ),
            color=color
        )

        result_file = discord.File(final_img, filename="final.png")
        final_embed.set_image(url="attachment://final.png")

        await msg.edit(embed=final_embed, attachments=[result_file])

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

        # ================================
        # PROBABILITY TABLE
        # ================================
        symbols = ["🍆", "💖", "🍒", "💵", "🔵"]
        weights = [8, 3, 2, 1.2, 0.8]
        multipliers = {
            "🍆": 1,
            "💖": 2,
            "🍒": 3,
            "💵": 4,
            "🔵": 10
        }

        # ================================
        # DETERMINE WIN OR LOSS
        # ================================
        roll = random.random() * 100
        is_win = roll < 15.0  

        # ================================
        # GENERATE RESULT
        # ================================
        if is_win:
            # Pick symbol by weight
            chosen = random.choices(symbols, weights=weights, k=1)[0]
            r1 = r2 = r3 = chosen

        else:
            # LOSS pattern → MUST NOT be all identical
            while True:
                r1 = random.choice(symbols)
                r2 = random.choice(symbols)
                r3 = random.choice(symbols)
                if not (r1 == r2 == r3):
                    break

        # ================================
        # ANIMATION PHASE
        # ================================
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

        # ================================
        # CALCULATE RESULT
        # ================================
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

        # Save
        set_user_cash(self.db, ctx.author.id, cash)
        log_gamble(self.db, ctx.guild.id, ctx.author.id, "slots", bet, status)

        # Final embed
        result = discord.Embed(
            title="🎰 Slots Result",
            description=f"{final}\n\n{desc}\n\n💰 **Saldo: {comma(cash)}**",
            color=color
        )
        await msg.edit(embed=result)

    @commands.command(name="profile")
    async def mprofile(self, ctx, member: discord.Member = None):
        user = member or ctx.author
        uid = user.id

        # =============================
        # Ambil data dari database
        # =============================
        cash = get_user_cash(self.db, uid)

        # protection 24 jam
        active_until = get_user_protection(self.db, uid)
        now = int(time.time())

        if active_until > now:
            prot_status = "🟢 Aktif"
            left_secs = active_until - now
            left_fmt = str(datetime.timedelta(seconds=left_secs))
        else:
            prot_status = "🔴 Tidak aktif"
            left_fmt = "—"

        # victim cooldown = last robbed indicator
        last_robbed_ts = get_rob_victim_protect(self.db, uid)

        if last_robbed_ts > now:
            # artinya baru saja dirampok (karena kamu pakai protect_until)
            last_robbed = f"<t:{last_robbed_ts}:R>"
        else:
            last_robbed = "—"

        rob_stats = get_rob_stats(self.db, uid)
        rob_success = rob_stats["success"]
        rob_fail = rob_stats["fail"]

        # gamble wins
        total_gamble_wins = get_total_gamble_wins(self.db, uid)

        # =============================
        # Buat embed
        # =============================
        embed = discord.Embed(
            title=f"👤 Profile — {user.display_name}",
            color=discord.Color.gold()
        )

        embed.add_field(name="💰 Cash", value=f"**{comma(cash)}**", inline=False)

        embed.add_field(
            name="🛡 Protection (24h)",
            value=f"Status: **{prot_status}**\nTime left: **{left_fmt}**",
            inline=False
        )

        embed.add_field(
            name="📛 Last Robbed",
            value=f"{last_robbed}",
            inline=False
        )

        embed.add_field(
            name="🗡 Rob Stats",
            value=f"Success: **{rob_success}**\nFail: **{rob_fail}**",
            inline=False
        )

        embed.add_field(
            name="🎰 Total Gamble Wins",
            value=f"**{total_gamble_wins}**",
            inline=False
        )

        embed.set_thumbnail(url=user.display_avatar.url)

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(GambleCog(bot))
