import discord
from discord.ext import commands
from database import get_user_xp, set_user_xp, get_level_role, insert_level_role

class LevelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_level_roles = {}
        self.db = bot.db

    def calculate_level(self, xp):
        level = 0
        required_xp = 100
        while xp >= required_xp:
            xp -= required_xp
            level += 1
            required_xp = int(required_xp * 1.5)
        return level

    async def load_level_roles(self):
        if self.db is None:
            print("[ERROR] Gagal connect ke DB saat load_level_roles")
            return
        cursor = self.db.cursor()
        cursor.execute("SELECT guild_id, level, role_id FROM level_roles")
        rows = cursor.fetchall()
        cursor.close()

        self.guild_level_roles.clear()
        for guild_id, level, role_id in rows:
            if guild_id not in self.guild_level_roles:
                self.guild_level_roles[guild_id] = {}
            self.guild_level_roles[guild_id][level] = role_id

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_level_roles()

    @commands.command(name='level')
    async def level(self, ctx):
        user = ctx.author
        user_id = user.id
        guild_id = ctx.guild.id
        xp = get_user_xp(self.db, user_id, guild_id)
        level = self.calculate_level(xp)
        await ctx.send(f"🔢 {user.name}, kamu level {level} dengan {xp} XP.")

    @commands.command(name="setrolelvl")
    async def set_role_level(self, ctx, level: int, role_id: int):
        # Hanya owner server yang boleh pakai command ini
        if ctx.author.id != ctx.guild.owner_id:
            await ctx.send("❌ Hanya owner server yang dapat menggunakan command ini.")
            return

        guild_id = ctx.guild.id

        # Simpan ke database
        insert_level_role(self.db, guild_id, level, role_id)

        # Update cache lokal juga
        if guild_id not in self.guild_level_roles:
            self.guild_level_roles[guild_id] = {}
        self.guild_level_roles[guild_id][level] = role_id

        await ctx.send(f"✅ Role dengan ID `{role_id}` akan diberikan pada level `{level}`.")

    @commands.command(name="removerolelvl")
    async def remove_role_level(self, ctx, level: int):
        if ctx.author.id != ctx.guild.owner_id:
            await ctx.send("❌ Hanya owner server yang dapat menggunakan command ini.")
            return

        guild_id = ctx.guild.id
        if self.db is None:
            await ctx.send("❌ Gagal koneksi ke database.")
            return
        cursor = self.db.cursor()
        cursor.execute("DELETE FROM level_roles WHERE guild_id=%s AND level=%s", (guild_id, level))
        self.db.commit()
        cursor.close()

        if guild_id in self.guild_level_roles and level in self.guild_level_roles[guild_id]:
            del self.guild_level_roles[guild_id][level]

        await ctx.send(f"✅ Role level untuk level `{level}` telah dihapus.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.guild is None:
            return

        prefix = "!"
        if message.content.startswith(prefix):
            return

        user = message.author
        user_id = user.id
        guild_id = message.guild.id

        previous_xp = get_user_xp(self.db, user_id, guild_id)
        new_xp = previous_xp + 10
        set_user_xp(self.db, user_id, guild_id, new_xp)

        old_level = self.calculate_level(previous_xp)
        new_level = self.calculate_level(new_xp)

        if new_level > old_level:
            role_id = None
            guild_roles = self.guild_level_roles.get(guild_id)
            if guild_roles:
                role_id = guild_roles.get(new_level)

            if role_id is None:
                role_id = get_level_role(self.db, guild_id, new_level)
                if role_id:
                    if guild_id not in self.guild_level_roles:
                        self.guild_level_roles[guild_id] = {}
                    self.guild_level_roles[guild_id][new_level] = role_id

            message_content = f"🎉 {user.mention} naik ke level {new_level}!"

            if role_id:
                try:
                    role_id_int = int(role_id)
                except Exception:
                    role_id_int = None

                if role_id_int:
                    role = discord.utils.get(message.guild.roles, id=role_id_int)
                    if role and role not in user.roles:
                        bot_member = message.guild.me
                        if bot_member.top_role.position > role.position:
                            try:
                                await user.add_roles(role)
                                message_content += f" Kamu juga mendapatkan role **{role.name}**!"
                            except Exception:
                                pass

            await message.channel.send(message_content)


async def setup(bot):
    await bot.add_cog(LevelCog(bot))
