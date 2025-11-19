import discord
from discord.ext import commands
import random
import time
from datetime import datetime
import pytz

from database import (
    get_user_cash, set_user_cash,
    get_user_protection, set_user_protection,
    get_rob_victim_protect, set_rob_victim_protect,
    log_gamble,
    get_channel_settings, set_channel_settings,
)

JAKARTA = pytz.timezone("Asia/Jakarta")

class RobCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

        self.pending_rob = {}    # (guild,user) → info preview
        self.last_preview = {}   # anti-spam (guild,user) → timestamp
        self.preview_cd = 10     # preview cooldown: 10s


    # ============================================================
    #  UTILITY — Embed builder
    # ============================================================
    def nice_embed(self, title, desc, color=discord.Color.blurple()):
        emb = discord.Embed(
            title=title,
            description=desc,
            color=color
        )
        emb.set_footer(text="MadBot Robbery System ⚡")
        return emb


    # ============================================================
    #  ROB DISABLE/ENABLE PER SERVER
    # ============================================================
    @commands.command(name="robdisable")
    async def robdisable(self, ctx):
        if ctx.author.id not in [ctx.guild.owner_id, 416234104317804544]:
            return await ctx.send("❌ Kamu tidak punya izin.")

        set_channel_settings(self.db, ctx.guild.id, "rob_enabled", 0)
        await ctx.send("🛑 Rob system telah **dinonaktifkan** di server ini.")

    @commands.command(name="robenable")
    async def robenable(self, ctx):
        if ctx.author.id not in [ctx.guild.owner_id, 416234104317804544]:
            return await ctx.send("❌ Kamu tidak punya izin.")

        set_channel_settings(self.db, ctx.guild.id, "rob_enabled", 1)
        await ctx.send("🟢 Rob system telah **diaktifkan kembali**.")


    # ============================================================
    #   Dynamic chance
    # ============================================================
    def calculate_success_chance(self, robber_cash, victim_cash):
        if victim_cash <= 0:
            return 0.50

        ratio = robber_cash / victim_cash

        if ratio >= 2:
            bonus = +0.10
        elif ratio >= 1:
            bonus = +0.05
        elif ratio >= 0.5:
            bonus = -0.05
        else:
            bonus = -0.10

        chance = 0.50 + bonus
        chance = max(0.35, min(0.65, chance))
        return chance


    # ============================================================
    #   PREVIEW ROB
    # ============================================================
    @commands.command(name="rob")
    async def rob(self, ctx, target: discord.Member, confirm=None):
        guild_id = ctx.guild.id
        user_id  = ctx.author.id
        target_id = target.id

        # Check if rob enabled
        enabled = get_channel_settings(self.db, guild_id, "rob_enabled")
        if enabled is not None and str(enabled) == "0":
            return await ctx.send("🛑 Rob telah dimatikan di server ini.")

        # CONFIRM (rob @user confirm)
        if confirm == "confirm":
            return await self.rob_confirm(ctx, target)

        # Anti-spam preview
        now = time.time()
        if (guild_id, user_id) in self.last_preview:
            cd = now - self.last_preview[(guild_id, user_id)]
            if cd < self.preview_cd:
                remain = round(self.preview_cd - cd, 1)
                return await ctx.send(f"⏳ Tunggu **{remain}s** untuk preview lagi.")

        self.last_preview[(guild_id, user_id)] = now

        if target.bot:
            return await ctx.send("❌ Tidak bisa merampok bot.")
        if target_id == user_id:
            return await ctx.send("❌ Tidak bisa merampok diri sendiri.")

        r_cash = get_user_cash(self.db, user_id, guild_id)
        v_cash = get_user_cash(self.db, target_id, guild_id)

        if v_cash < 100:
            return await ctx.send("❌ Target terlalu miskin untuk dirampok.")

        now_ts = int(time.time())

        # VICTIM 2H COOLDOWN
        shield = get_rob_victim_protect(self.db, guild_id, target_id)
        if shield > now_ts:
            mins = (shield - now_ts) // 60
            return await ctx.send(f"🛡 {target.mention} dilindungi selama **{mins} menit** lagi.")

        # SHOP PROTECTION
        prot = get_user_protection(self.db, guild_id, target_id)
        if prot > now_ts:
            hrs = (prot - now_ts) // 3600
            mins = ((prot - now_ts) % 3600) // 60
            return await ctx.send(f"🛡 {target.mention} memiliki proteksi aktif: **{hrs} jam {mins} menit**")

        # 5–10% steal
        percent = random.randint(5, 10)
        steal = int(v_cash * (percent / 100))

        penalty = int(r_cash * 0.10)
        if penalty < 1:
            penalty = 1

        chance = self.calculate_success_chance(r_cash, v_cash)
        chance_display = int(chance * 100)

        # Cache preview
        self.pending_rob[(guild_id, user_id)] = {
            "target": target_id,
            "steal": steal,
            "penalty": penalty,
            "chance": chance
        }

        embed = self.nice_embed(
            "🔪 Robbery Preview",
            f"""
Pelaku: {ctx.author.mention}
Target: {target.mention}

💰 Target saldo: **{v_cash}**
💰 Saldo kamu: **{r_cash}**

📦 Akan merampok: **{steal} coins**
💀 Risiko gagal: kehilangan **{penalty} coins**
🎯 Chance sukses: **{chance_display}%**

Ketik:
`rob {target.mention} confirm`
untuk melanjutkan.
"""
        )
        await ctx.send(embed=embed)


    # ============================================================
    #   EXECUTE ROB
    # ============================================================
    async def rob_confirm(self, ctx, target):
        guild_id = ctx.guild.id
        user_id  = ctx.author.id
        target_id = target.id
        key = (guild_id, user_id)

        if key not in self.pending_rob:
            return await ctx.send("❌ Tidak ada rob pending.")

        data = self.pending_rob[key]
        del self.pending_rob[key]

        if data["target"] != target_id:
            return await ctx.send("❌ Target tidak sesuai preview.")

        steal   = data["steal"]
        penalty = data["penalty"]
        chance  = data["chance"]

        # Validate again from DB
        r_cash = get_user_cash(self.db, user_id, guild_id)
        v_cash = get_user_cash(self.db, target_id, guild_id)
        now_ts = int(time.time())

        # Shop protection check again
        prot = get_user_protection(self.db, guild_id, target_id)
        if prot > now_ts:
            return await ctx.send("🛡 Target mengaktifkan proteksi sebelum kamu menyerang.")

        # Victim cooldown
        shield = get_rob_victim_protect(self.db, guild_id, target_id)
        if shield > now_ts:
            return await ctx.send("🛡 Target dalam perlindungan anti-rob.")

        if v_cash < steal:
            return await ctx.send("❌ Target saldo berubah — terlalu miskin.")

        roll = random.random()

        # SUCCESS
        if roll <= chance:
            new_r = r_cash + steal
            new_v = v_cash - steal

            set_user_cash(self.db, user_id, guild_id, new_r)
            set_user_cash(self.db, target_id, guild_id, new_v)

            # 2h victim shield
            protect_until = now_ts + 7200
            set_rob_victim_protect(self.db, guild_id, target_id, protect_until)

            log_gamble(self.db, guild_id, user_id, "rob_success", steal, "WIN")
            log_gamble(self.db, guild_id, target_id, "rob_stolen", steal, "LOSE")

            embed = self.nice_embed(
                "🟢 Rob Berhasil!",
                f"""
{ctx.author.mention} merampok **{steal} coins** dari {target.mention}!

🛡 {target.mention} aman selama **2 jam** dari semua rob.

💰 Saldo kamu sekarang: **{new_r}**
""",
                color=discord.Color.green()
            )
            return await ctx.send(embed=embed)


        # FAIL
        if r_cash < penalty:
            penalty = r_cash

        new_r = r_cash - penalty
        new_v = v_cash + penalty

        set_user_cash(self.db, user_id, guild_id, new_r)
        set_user_cash(self.db, target_id, guild_id, new_v)

        log_gamble(self.db, guild_id, user_id, "rob_fail", penalty, "LOSE")
        log_gamble(self.db, guild_id, target_id, "rob_bonus", penalty, "WIN")

        embed = self.nice_embed(
            "🔴 Rob Gagal!",
            f"""
{ctx.author.mention} tertangkap mencoba merampok {target.mention}!

💀 Kamu kehilangan **{penalty} coins**
🎁 {target.mention} menerima **{penalty} coins**

💰 Saldo kamu sekarang: **{new_r}**
""",
            color=discord.Color.red()
        )
        return await ctx.send(embed=embed)


    # ============================================================
    #   BUY PROTECTION 24H
    # ============================================================
    @commands.command(name="buyprotection")
    async def buy_protection(self, ctx):
        guild_id = ctx.guild.id
        user_id  = ctx.author.id

        cash = get_user_cash(self.db, user_id, guild_id)
        if cash < 500:
            return await ctx.send("❌ Kamu butuh **500 coins**.")

        now_ts = int(time.time())
        until = now_ts + 86400  # 24h

        set_user_cash(self.db, user_id, guild_id, cash - 500)
        set_user_protection(self.db, guild_id, user_id, until)

        await ctx.send("🛡 Proteksi aktif 24 jam! Kamu aman dari semua rob.")


    # ============================================================
    #   ROB STATUS
    # ============================================================
    @commands.command(name="robstatus")
    async def robstatus(self, ctx):
        guild_id = ctx.guild.id
        user_id  = ctx.author.id

        now_ts = int(time.time())
        shop = get_user_protection(self.db, guild_id, user_id)
        shield = get_rob_victim_protect(self.db, guild_id, user_id)

        embed = self.nice_embed("🛡 Status Proteksi Rob", "")

        if shop > now_ts:
            left = shop - now_ts
            h = left // 3600
            m = (left % 3600) // 60
            embed.add_field(name="Protection 24h", value=f"Aktif {h} jam {m} menit", inline=False)
        else:
            embed.add_field(name="Protection 24h", value="Tidak aktif", inline=False)

        if shield > now_ts:
            left = shield - now_ts
            m = left // 60
            embed.add_field(name="Anti-Rob 2h", value=f"Aktif {m} menit lagi", inline=False)
        else:
            embed.add_field(name="Anti-Rob 2h", value="Tidak aktif", inline=False)

        await ctx.send(embed=embed)


    # ============================================================
    #   ROB LEADERBOARD
    # ============================================================
    @commands.command(name="roblb", aliases=["robleaderboard"])
    async def roblb(self, ctx):
        guild_id = ctx.guild.id
        cursor = self.db.cursor(dictionary=True)

        cursor.execute("""
            SELECT user_id, SUM(amount) AS total_gain
            FROM gamble_log
            WHERE guild_id=%s AND gamble_type IN ('rob_success', 'rob_bonus')
            GROUP BY user_id
            ORDER BY total_gain DESC
            LIMIT 10;
        """, (guild_id,))

        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return await ctx.send("📉 Belum ada data robbery.")

        embed = discord.Embed(
            title="🏆 Rob Leaderboard",
            description="Top 10 pencuri terbesar",
            color=discord.Color.gold()
        )

        for i, row in enumerate(rows, start=1):
            member = ctx.guild.get_member(row["user_id"])
            name = member.mention if member else f"<@{row['user_id']}>"
            embed.add_field(
                name=f"#{i} {name}",
                value=f"💰 **{row['total_gain']} coins**",
                inline=False
            )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(RobCog(bot))
