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
    get_gamble_setting, set_gamble_setting
)

from gamble_utils import gamble_only, comma

JAKARTA = pytz.timezone("Asia/Jakarta")


class RobCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

        self.pending_rob = {}       # (guild, user) → preview data
        self.last_preview = {}      # anti spam
        self.preview_cd = 10        # seconds

    # =============================================================
    # Helper embed
    # =============================================================
    def nice_embed(self, title, desc, color=discord.Color.blurple()):
        emb = discord.Embed(title=title, description=desc, color=color)
        emb.set_footer(text="MadBot Robbery System ⚡")
        return emb

    # =============================================================
    # Admin
    # =============================================================
    @commands.command(name="robdisable")
    async def rob_disable(self, ctx):
        if ctx.author.id not in [ctx.guild.owner_id, 416234104317804544]:
            return await ctx.send("❌ Kamu tidak punya izin.")
        set_gamble_setting(self.db, ctx.guild.id, "rob_enabled", "0")
        await ctx.send("🛑 Rob system dinonaktifkan.")

    @commands.command(name="robenable")
    async def rob_enable(self, ctx):
        if ctx.author.id not in [ctx.guild.owner_id, 416234104317804544]:
            return await ctx.send("❌ Kamu tidak punya izin.")
        set_gamble_setting(self.db, ctx.guild.id, "rob_enabled", "1")
        await ctx.send("🟢 Rob system diaktifkan.")

    # =============================================================
    # Success Chance
    # =============================================================
    def calculate_success_chance(self, robber_cash, victim_cash):
        if victim_cash <= 0:
            return 0.50

        ratio = robber_cash / victim_cash

        if ratio >= 2:
            bonus = 0.10
        elif ratio >= 1:
            bonus = 0.05
        elif ratio >= 0.5:
            bonus = -0.05
        else:
            bonus = -0.10

        chance = 0.50 + bonus
        return max(0.35, min(0.65, chance))

    # =============================================================
    # ROB PREVIEW
    # =============================================================
    @commands.command(name="rob")
    @gamble_only()
    async def rob(self, ctx, target: discord.Member, confirm=None):

        guild_id = ctx.guild.id
        user_id = ctx.author.id

        # ============================================================
        #  AUTO-REMOVE PROTECTION WHEN USER TRIES TO ROB
        # ============================================================
        now_ts = int(time.time())

        # Remove 2h shield
        if get_rob_victim_protect(self.db, user_id) > now_ts:
            set_rob_victim_protect(self.db, user_id, 0)

        # Remove 24h shop protection
        if get_user_protection(self.db, user_id) > now_ts:
            set_user_protection(self.db, user_id, 0)

        # rob enabled?
        enabled = get_gamble_setting(self.db, guild_id, "rob_enabled")
        if enabled == "0":
            return await ctx.send("🛑 Rob dimatikan di server ini.")

        # confirm path
        if confirm == "confirm":
            return await self.rob_confirm(ctx, target)

        # preview anti spam
        now = time.time()
        key = (guild_id, user_id)

        if key in self.last_preview and now - self.last_preview[key] < self.preview_cd:
            rem = round(self.preview_cd - (now - self.last_preview[key]), 1)
            return await ctx.send(f"⏳ Tunggu **{rem}s** lagi.")
        self.last_preview[key] = now

        # validations
        if target.bot:
            return await ctx.send("❌ Tidak bisa merampok bot.")
        if target.id == user_id:
            return await ctx.send("❌ Tidak bisa merampok diri sendiri.")

        # GLOBAL CASH
        r_cash = get_user_cash(self.db, user_id)
        v_cash = get_user_cash(self.db, target.id)

        if v_cash < 10:
            return await ctx.send("❌ Target terlalu miskin.")

        now_ts = int(time.time())

        # 2h victim shield (GLOBAL)
        vshield = get_rob_victim_protect(self.db, target.id)
        if vshield > now_ts:
            mins = (vshield - now_ts) // 60
            return await ctx.send(f"🛡 Target aman selama **{mins} menit**.")

        # 24h shop protection (GLOBAL)
        shop = get_user_protection(self.db, target.id)
        if shop > now_ts:
            hrs = (shop - now_ts) // 3600
            mins = ((shop - now_ts) % 3600) // 60
            return await ctx.send(f"🛡 Target punya proteksi **{hrs} jam {mins} menit**.")

        # compute steal
        percent = random.randint(5, 10)
        steal = int(v_cash * percent / 100)
        penalty = max(1, int(r_cash * 0.10))
        chance = self.calculate_success_chance(r_cash, v_cash)

        self.pending_rob[key] = {
            "target": target.id,
            "steal": steal,
            "penalty": penalty,
            "chance": chance
        }

        embed = self.nice_embed(
            "🔪 Robbery Preview",
            f"""
Pelaku: {ctx.author.mention}
Target: {target.mention}

💰 Target saldo: **{comma(v_cash)}**
💰 Saldo kamu: **{comma(r_cash)}**

📦 Akan merampok: **{comma(steal)} coins**
💀 Risiko gagal: **-{comma(penalty)} coins**
🎯 Chance sukses: **{int(chance*100)}%**

Ketik:
**rob {target.mention} confirm**
untuk melanjutkan.
"""
        )
        return await ctx.send(embed=embed)

    # =============================================================
    # ROB CONFIRM
    # =============================================================
    async def rob_confirm(self, ctx, target: discord.Member):

        guild_id = ctx.guild.id
        user_id = ctx.author.id
        key = (guild_id, user_id)

        # ============================================================
        #  AUTO-REMOVE PROTECTION WHEN USER CONFIRMS ROB
        # ============================================================
        now_ts = int(time.time())

        # Remove 2h shield
        if get_rob_victim_protect(self.db, user_id) > now_ts:
            set_rob_victim_protect(self.db, user_id, 0)

        # Remove 24h shop protection
        if get_user_protection(self.db, user_id) > now_ts:
            set_user_protection(self.db, user_id, 0)

        if key not in self.pending_rob:
            return await ctx.send("❌ Tidak ada rob pending.")

        data = self.pending_rob[key]
        del self.pending_rob[key]

        if data["target"] != target.id:
            return await ctx.send("❌ Target tidak sesuai preview.")

        steal = data["steal"]
        penalty = data["penalty"]
        chance = data["chance"]

        now_ts = int(time.time())

        # GLOBAL CASH
        r_cash = get_user_cash(self.db, user_id)
        v_cash = get_user_cash(self.db, target.id)

        # protections (GLOBAL)
        if get_user_protection(self.db, target.id) > now_ts:
            return await ctx.send("🛡 Target mengaktifkan proteksi sebelum diserang.")
        if get_rob_victim_protect(self.db, target.id) > now_ts:
            return await ctx.send("🛡 Target sedang aman dari rob.")

        if v_cash < steal:
            return await ctx.send("❌ Target saldo berubah, rob dibatalkan.")

        # =============================================================
        # SUCCESS
        # =============================================================
        if random.random() <= chance:
            new_r = r_cash + steal
            new_v = v_cash - steal

            set_user_cash(self.db, user_id, new_r)
            set_user_cash(self.db, target.id, new_v)

            # 2h shield (GLOBAL)
            set_rob_victim_protect(self.db, target.id, now_ts + 7200)

            log_gamble(self.db, ctx.guild.id, user_id, "rob_success", steal, "WIN")
            log_gamble(self.db, ctx.guild.id, target.id, "rob_stolen", steal, "LOSE")

            emb = self.nice_embed(
                "🟢 Rob Berhasil!",
                f"""
{ctx.author.mention} merampok **{comma(steal)} coins** dari {target.mention}!  

🛡 {target.mention} aman selama **2 jam**.

💰 Saldo kamu sekarang: **{comma(new_r)}**
""",
                discord.Color.green()
            )
            return await ctx.send(embed=emb)

        # =============================================================
        # FAIL
        # =============================================================
        penalty = min(penalty, r_cash)

        new_r = r_cash - penalty
        new_v = v_cash + penalty

        set_user_cash(self.db, user_id, new_r)
        set_user_cash(self.db, target.id, new_v)

        log_gamble(self.db, ctx.guild.id, user_id, "rob_fail", penalty, "LOSE")
        log_gamble(self.db, ctx.guild.id, target.id, "rob_bonus", penalty, "WIN")

        emb = self.nice_embed(
            "🔴 Rob Gagal!",
            f"""
{ctx.author.mention} tertangkap merampok {target.mention}!

💀 Kamu kehilangan **{comma(penalty)} coins**
🎁 {target.mention} menerima **{comma(penalty)} coins**

💰 Saldo kamu sekarang: **{comma(new_r)}**
""",
            discord.Color.red()
        )
        return await ctx.send(embed=emb)

    # =============================================================
    # BUY PROTECTION (GLOBAL)
    # =============================================================
    @commands.command(name="buyprotection")
    async def buy_protection(self, ctx):

        user = ctx.author.id
        now_ts = int(time.time())

        cash = get_user_cash(self.db, user)
        active = get_user_protection(self.db, user)

        if active > now_ts:
            left = active - now_ts
            h = left // 3600
            m = (left % 3600) // 60
            return await ctx.send(f"❌ Kamu sudah punya proteksi **{h} jam {m} menit**.")

        if cash < 500:
            return await ctx.send("❌ Butuh **500 coins**.")

        set_user_cash(self.db, user, cash - 500)
        set_user_protection(self.db, user, now_ts + 86400)

        await ctx.send("🛡 Proteksi aktif **24 jam**!")

    # =============================================================
    # ROB STATUS (GLOBAL)
    # =============================================================
    @commands.command(name="robstatus")
    async def robstatus(self, ctx):

        user = ctx.author.id
        now_ts = int(time.time())

        shop = get_user_protection(self.db, user)
        shield = get_rob_victim_protect(self.db, user)

        emb = self.nice_embed("🛡 Status Rob", "")

        if shop > now_ts:
            left = shop - now_ts
            h = left // 3600
            m = (left % 3600) // 60
            emb.add_field(name="Protection 24h", value=f"Aktif {h} jam {m} menit", inline=False)
        else:
            emb.add_field(name="Protection 24h", value="Tidak aktif", inline=False)

        if shield > now_ts:
            mins = (shield - now_ts) // 60
            emb.add_field(name="Anti-Rob 2h", value=f"Aktif {mins} menit", inline=False)
        else:
            emb.add_field(name="Anti-Rob 2h", value="Tidak aktif", inline=False)

        await ctx.send(embed=emb)

    # =============================================================
    # LEADERBOARD (per guild)
    # =============================================================
    @commands.command(name="roblb", aliases=["robleaderboard"])
    async def roblb(self, ctx):

        guild = ctx.guild.id
        cursor = self.db.cursor(dictionary=True)

        cursor.execute("""
            SELECT user_id, SUM(amount) AS total_gain
            FROM gamble_log
            WHERE guild_id=%s AND gamble_type IN ('rob_success','rob_bonus')
            GROUP BY user_id
            ORDER BY total_gain DESC
            LIMIT 10
        """, (guild,))

        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return await ctx.send("📉 Belum ada data robbery.")

        emb = discord.Embed(
            title="🏆 Rob Leaderboard",
            description="Top 10 pencuri terbesar",
            color=discord.Color.gold()
        )

        for i, row in enumerate(rows, start=1):
            user = ctx.guild.get_member(row["user_id"])
            name = user.mention if user else f"<@{row['user_id']}>"
            emb.add_field(
                name=f"#{i} {name}",
                value=f"💰 **{comma(row['total_gain'])} coins**",
                inline=False
            )

        await ctx.send(embed=emb)


async def setup(bot):
    await bot.add_cog(RobCog(bot))
