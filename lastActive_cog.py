import discord
from discord.ext import commands
from datetime import datetime
import pytz

from database import (
    update_last_active,
    get_last_active,
    add_tracked_user,
    get_all_tracked_users,
)

class LastActive(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tracked_users = set()
        self.last_known_status = {}  # Cache status terakhir

    async def load_tracked_users(self):
        try:
            self.tracked_users = set(get_all_tracked_users())
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_tracked_users()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.author.id not in self.tracked_users:
            return

        current_status = message.author.status
        last_status = self.last_known_status.get(message.author.id)

        if last_status != current_status:
            self.last_known_status[message.author.id] = current_status
            update_last_active(message.author.id, current_status)

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        if after.bot or after.id not in self.tracked_users:
            return

        current_status = after.status
        last_status = self.last_known_status.get(after.id)

        if last_status != current_status:
            self.last_known_status[after.id] = current_status
            update_last_active(after.id, current_status)

    @commands.command(name='lastactive')
    async def lastactive(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        last_seen = get_last_active(member.id)

        if last_seen:
            last_time, last_status = last_seen
            if isinstance(last_time, datetime):
                jakarta = pytz.timezone("Asia/Jakarta")
                local_time = last_time.replace(tzinfo=pytz.utc).astimezone(jakarta)
                formatted = local_time.strftime('%Y-%m-%d %H:%M:%S WIB')
            else:
                formatted = str(last_time)

            await ctx.send(
                f"📅 **{member.display_name}** terakhir aktif: `{formatted}`\n"
                f"📶 Status terakhir: `{last_status}`"
            )
        else:
            await ctx.send(f"❌ Belum ada data aktivitas untuk {member.display_name}")

    @commands.command(name='activatelastseen')
    @commands.has_permissions(administrator=True)
    async def activatelastseen(self, ctx, member: discord.Member):
        try:
            await ctx.guild.fetch_member(member.id)
        except:
            pass
        add_tracked_user(member.id)
        self.tracked_users.add(member.id)
        self.last_known_status[member.id] = member.status
        await ctx.send(f"✅ Sekarang melacak aktivitas: **{member.display_name}**")

async def setup(bot):
    cog = LastActive(bot)
    await bot.add_cog(cog)
    await cog.load_tracked_users()
