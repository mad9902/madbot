import discord
from discord.ext import commands
from database import (
    get_user_xp,
    set_user_xp,
    get_level_role,
    insert_level_role,
    set_channel_settings,
    get_channel_settings,
    is_level_disabled,
    disable_level,
    enable_level,
    get_no_xp_roles,
    add_no_xp_role,
    remove_no_xp_role
)
import time

class LevelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.guild_level_roles = {} 
        self.last_xp = {} 
        self.disabled_guilds = set()
        self.no_xp_roles = {} 

    def is_admin_or_owner(self, ctx):
        return ctx.author.guild_permissions.administrator or ctx.author.id == 416234104317804544

    def calculate_level(self, xp: int) -> int:
        level = 0
        required = 100
        while xp >= required:
            xp -= required
            level += 1
            required = int(required * 1.5)
        return level

    async def load_level_roles(self):
        cursor = self.db.cursor()
        cursor.execute("SELECT guild_id, level, role_id FROM level_roles")
        for guild_id, level, role_id in cursor.fetchall():
            self.guild_level_roles.setdefault(int(guild_id), {})[int(level)] = int(role_id)
        cursor.close()

    async def load_disabled_guilds(self):
        cursor = self.db.cursor()
        cursor.execute("SELECT guild_id FROM disabled_levels")
        self.disabled_guilds = {row[0] for row in cursor.fetchall()}
        cursor.close()

    async def load_no_xp_roles(self):
        cursor = self.db.cursor()
        cursor.execute("SELECT guild_id, role_id FROM no_xp_roles")
        for guild_id, role_id in cursor.fetchall():
            self.no_xp_roles.setdefault(guild_id, set()).add(role_id)
        cursor.close()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_level_roles()
        await self.load_disabled_guilds()
        await self.load_no_xp_roles()

    @commands.command(name="level", extras={"category": "XP"})
    async def show_level(self, ctx):
        xp = get_user_xp(self.db, ctx.author.id, ctx.guild.id)
        level = self.calculate_level(xp)
        await ctx.send(f"🔢 {ctx.author.mention}, kamu level {level} dengan {xp} XP.")

    @commands.command(name="setrolelvl", extras={"category": "XP"})
    async def set_role_level(self, ctx, level: int, role: discord.Role):
        if not self.is_admin_or_owner(ctx):
            return await ctx.send("❌ Hanya admin atau user yang diizinkan yang bisa menggunakan command ini.")
        insert_level_role(self.db, ctx.guild.id, level, role.id)
        self.guild_level_roles.setdefault(ctx.guild.id, {})[level] = role.id
        await ctx.send(f"✅ Role {role.mention} akan diberikan pada level {level}.")

    @commands.command(name="removerolelvl", extras={"category": "XP"})
    async def remove_role_level(self, ctx, level: int):
        if not self.is_admin_or_owner(ctx):
            return await ctx.send("❌ Hanya admin atau user yang diizinkan yang bisa menggunakan command ini.")
        cursor = self.db.cursor()
        cursor.execute("DELETE FROM level_roles WHERE guild_id=%s AND level=%s", (ctx.guild.id, level))
        self.db.commit()
        cursor.close()
        self.guild_level_roles.get(ctx.guild.id, {}).pop(level, None)
        await ctx.send(f"✅ Role untuk level {level} dihapus.")

    @commands.command(name="setchlevel", extras={"category": "XP"})
    async def setchlevel(self, ctx, channel: discord.TextChannel):
        if not self.is_admin_or_owner(ctx):
            return await ctx.send("❌ Hanya admin atau user yang diizinkan yang bisa menggunakan command ini.")
        set_channel_settings(self.db, ctx.guild.id, "level", channel.id)
        await ctx.send(f"✅ Channel level-up diatur ke {channel.mention}")

    @commands.command(name="leveloff", extras={"category": "XP"})
    async def leveloff(self, ctx):
        if not self.is_admin_or_owner(ctx):
            return await ctx.send("❌ Hanya admin atau user yang diizinkan yang bisa menggunakan command ini.")
        disable_level(self.db, ctx.guild.id)
        self.disabled_guilds.add(ctx.guild.id)
        await ctx.send("🛑 Sistem level dinonaktifkan di server ini.")

    @commands.command(name="levelon", extras={"category": "XP"})
    async def levelon(self, ctx):
        if not self.is_admin_or_owner(ctx):
            return await ctx.send("❌ Hanya admin atau user yang diizinkan yang bisa menggunakan command ini.")
        enable_level(self.db, ctx.guild.id)
        self.disabled_guilds.discard(ctx.guild.id)
        await ctx.send("✅ Sistem level diaktifkan kembali di server ini.")

    @commands.command(name="setnoxprole", extras={"category": "XP"})
    async def set_no_xp_role(self, ctx, role: discord.Role):
        if not self.is_admin_or_owner(ctx):
            return await ctx.send("❌ Hanya admin atau user yang diizinkan yang bisa menggunakan command ini.")
        add_no_xp_role(self.db, ctx.guild.id, role.id)
        self.no_xp_roles.setdefault(ctx.guild.id, set()).add(role.id)
        await ctx.send(f"🚫 Role {role.mention} tidak akan mendapatkan XP.")

    @commands.command(name="removenoxprole", extras={"category": "XP"})
    async def remove_no_xp_role_cmd(self, ctx, role: discord.Role):
        if not self.is_admin_or_owner(ctx):
            return await ctx.send("❌ Hanya admin atau user yang diizinkan yang bisa menggunakan command ini.")
        remove_no_xp_role(self.db, ctx.guild.id, role.id)
        self.no_xp_roles.get(ctx.guild.id, set()).discard(role.id)
        await ctx.send(f"✅ Role {role.mention} kembali bisa mendapatkan XP.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        guild_id = message.guild.id
        user_id = message.author.id

        if guild_id in self.disabled_guilds:
            return

        no_xp_roles = self.no_xp_roles.get(guild_id, set())
        if any(role.id in no_xp_roles for role in message.author.roles):
            return

        now = time.time()
        key = (guild_id, user_id)
        if key in self.last_xp and now - self.last_xp[key] < 10:
            return
        self.last_xp[key] = now

        base_xp = 5
        bonus = min(len(message.content) // 20, 10)
        gained = base_xp + bonus

        xp_before = get_user_xp(self.db, user_id, guild_id)
        xp_after = xp_before + gained
        set_user_xp(self.db, user_id, guild_id, xp_after)

        level_before = self.calculate_level(xp_before)
        level_after = self.calculate_level(xp_after)

        if level_after > level_before:
            role_id = self.guild_level_roles.get(guild_id, {}).get(level_after)
            if role_id is None:
                role_id = get_level_role(self.db, guild_id, level_after)
                if role_id:
                    self.guild_level_roles.setdefault(guild_id, {})[level_after] = role_id

            msg = f"🎉 {message.author.mention} naik ke level {level_after}!"
            if role_id:
                role = message.guild.get_role(int(role_id))
                if role and role not in message.author.roles:
                    try:
                        if message.guild.me.top_role.position > role.position:
                            await message.author.add_roles(role)
                            msg += f" Kamu mendapatkan role **{role.name}**!"
                    except Exception as e:
                        print(f"[ERROR] Memberi role gagal: {e}")

            ch_id = get_channel_settings(self.db, guild_id, "level")
            channel = message.guild.get_channel(int(ch_id)) if ch_id else message.channel
            await channel.send(msg)

    @commands.command(name="leaderboard", help="Menampilkan 10 user dengan XP tertinggi", extras={"category": "XP"})
    async def leaderboard(self, ctx):
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT user_id, xp FROM user_levels
            WHERE guild_id = %s ORDER BY xp DESC LIMIT 10
        """, (ctx.guild.id,))
        results = cursor.fetchall()
        cursor.close()

        if not results:
            return await ctx.send("📉 Tidak ada data XP untuk server ini.")

        embed = discord.Embed(
            title="🏆 Leaderboard Level",
            description="Top 10 user berdasarkan XP",
            color=discord.Color.gold()
        )

        for i, (user_id, xp) in enumerate(results, start=1):
            user = ctx.guild.get_member(user_id)
            if user:
                name = user.display_name
            else:
                try:
                    user = await self.bot.fetch_user(user_id)
                    name = f"{user.name}#{user.discriminator}"
                except:
                    name = f"`{user_id}`"

            level = self.calculate_level(xp)
            embed.add_field(
                name=f"#{i} {name}",
                value=f"⭐ Level {level} – {xp} XP",
                inline=False
            )

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(LevelCog(bot))
