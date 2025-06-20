import discord
from discord.ext import commands
from database import (
    get_user_xp,
    set_user_xp,
    get_level_role,
    insert_level_role,
    set_channel_settings,
    get_channel_settings
)
import time

class LevelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.guild_level_roles = {}  # {guild_id: {level: role_id}}
        self.last_xp = {}  # {(guild_id, user_id): timestamp}

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

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_level_roles()

    @commands.command(name="level")
    async def show_level(self, ctx):
        xp = get_user_xp(self.db, ctx.author.id, ctx.guild.id)
        level = self.calculate_level(xp)
        await ctx.send(f"🔢 {ctx.author.mention}, kamu level {level} dengan {xp} XP.")

    @commands.command(name="setrolelvl")
    async def set_role_level(self, ctx, level: int, role: discord.Role):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Hanya admin yang bisa menggunakan command ini.")

        insert_level_role(self.db, ctx.guild.id, level, role.id)
        self.guild_level_roles.setdefault(ctx.guild.id, {})[level] = role.id
        await ctx.send(f"✅ Role {role.mention} akan diberikan pada level {level}.")

    @commands.command(name="removerolelvl")
    async def remove_role_level(self, ctx, level: int):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ Hanya admin yang bisa menggunakan command ini.")
        cursor = self.db.cursor()
        cursor.execute("DELETE FROM level_roles WHERE guild_id=%s AND level=%s", (ctx.guild.id, level))
        self.db.commit()
        cursor.close()
        self.guild_level_roles.get(ctx.guild.id, {}).pop(level, None)
        await ctx.send(f"✅ Role untuk level {level} dihapus.")

    @commands.command(name="setchlevel")
    async def setchlevel(self, ctx, channel: discord.TextChannel):
        allowed_user_id = 416234104317804544
        is_admin = ctx.author.guild_permissions.administrator
        is_owner = ctx.author.id == allowed_user_id

        if not (is_admin or is_owner):
            return await ctx.send("❌ Hanya admin atau user yang diizinkan yang bisa menggunakan command ini.")

        set_channel_settings(self.db, ctx.guild.id, "level", channel.id)
        await ctx.send(f"✅ Channel level-up diatur ke {channel.mention}")


    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        now = time.time()
        key = (message.guild.id, message.author.id)
        if key in self.last_xp and now - self.last_xp[key] < 10:
            return
        self.last_xp[key] = now

        base_xp = 5
        bonus = min(len(message.content) // 20, 10)
        gained = base_xp + bonus

        user_id = message.author.id
        guild_id = message.guild.id

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

    @commands.command(name="leaderboard", help="Menampilkan 10 user dengan XP tertinggi")
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
