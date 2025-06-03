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

class LevelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_level_roles = {}  # Format: {guild_id(int): {level(int): role_id(int)}}
        self.db = bot.db

    def calculate_level(self, xp: int) -> int:
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
            guild_id = int(guild_id)
            level = int(level)
            role_id = int(role_id)
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
        if ctx.author.id != ctx.guild.owner_id and ctx.author.id != 416234104317804544:
            await ctx.send("❌ Hanya pemilik server yang bisa menggunakan command ini.")
            return

        guild_id = ctx.guild.id

        insert_level_role(self.db, guild_id, level, role_id)

        if guild_id not in self.guild_level_roles:
            self.guild_level_roles[guild_id] = {}
        self.guild_level_roles[guild_id][level] = role_id

        await ctx.send(f"✅ Role dengan ID `{role_id}` akan diberikan pada level `{level}`.")

    @commands.command(name="removerolelvl")
    async def remove_role_level(self, ctx, level: int):
        if ctx.author.id != ctx.guild.owner_id and ctx.author.id != 416234104317804544:
            await ctx.send("❌ Hanya pemilik server yang bisa menggunakan command ini.")
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

    @commands.command(name="setchlevel")
    async def setchlevel(self, ctx, channel: discord.TextChannel):
        if ctx.author.id != ctx.guild.owner_id and ctx.author.id != 416234104317804544:
            await ctx.send("❌ Hanya pemilik server yang bisa menggunakan command ini.")
            return

        guild_id = ctx.guild.id  # gunakan int
        channel_id = channel.id  # gunakan int

        # Perbaikan: urutan argumen sesuai fungsi set_channel_settings(db, guild_id, setting_type, channel_id)
        set_channel_settings(self.db, guild_id, "level", channel_id)
        await ctx.send(f"✅ Channel khusus level-up telah disetel ke {channel.mention}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.guild is None:
            return

        # Skip jika pesan dimulai dengan prefix bot
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
            # Cek role dari cache dulu
            role_id = None
            guild_roles = self.guild_level_roles.get(guild_id)
            if guild_roles:
                role_id = guild_roles.get(new_level)

            # Kalau belum ada, ambil dari DB lalu update cache
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
                    role = discord.utils.get(message.guild.roles, id=role_id_int)
                    if role and role not in user.roles:
                        bot_member = message.guild.me
                        if bot_member.top_role.position > role.position:
                            await user.add_roles(role)
                            message_content += f" Kamu juga mendapatkan role **{role.name}**!"
                except Exception as e:
                    print(f"[ERROR] Gagal memberi role: {e}")

            # Ambil channel khusus level dari DB
            channel_id_str = get_channel_settings(self.db, guild_id, setting_type="level")
            target_channel = None
            if channel_id_str:
                try:
                    channel_id_int = int(channel_id_str)
                    target_channel = message.guild.get_channel(channel_id_int)
                except Exception as e:
                    print(f"[ERROR] Gagal konversi channel_id: {e}")

            if not target_channel:
                target_channel = message.channel

            await target_channel.send(message_content)

async def setup(bot):
    await bot.add_cog(LevelCog(bot))
