import discord
import random
import asyncio

from discord.ext import commands

class main_cog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.help_message = """
```
General commands:
mad help                   - displays all the available commands
mad clear / cl <amount>    - will delete the past messages with the amount specified

Image commands:
mad emoji <emoji>                  - will get the emoji
mad sticker <sticker               - will get the sticker
mad avatar <tag>                   - will get the avatar from the user

Music commands:
mad p or play <keywords>       - finds the song on youtube and plays 
                                 it in your current channel
mad q or queue                 - displays the current music queue
mad skip                       - skips the current song being played
mad setch <id channel>         - to set channel for music
mad leave or disconnect / dc
mad shuffle
mad loop current / queue


Polls & Voting:
mad poll <question>                    - create a yes/no poll

Giveaway:
mad giveaway <prize> <duration_seconds> - start a giveaway with prize and duration

Role Reaction:
mad rolemenu                        - create role selection menu with reactions

XP System:
mad level                           - check your current XP level
mad setrolelvl <level> <id role>
mad removerolelvl <level> <id role>

Auto Send:
Instagram or tiktok link

Info:
mad serverinfo
mad userinfo <tag>

```
"""
        self.text_channel_list = []
   
    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                self.text_channel_list.append(channel)
        

    @commands.command(name="help", aliases=["h"], help="Displays all the available commands")
    async def help(self, ctx):
        await ctx.send(self.help_message)

    async def send_to_all(self, msg):
        for text_channel in self.text_channel_list:
            await text_channel.send(msg)

    @commands.command(name="clear", aliases=["cl"], help="Clears a specified amount of messages")
    async def clear(self, ctx, arg):
        #extract the amount to clear
        amount = 5
        try:
            amount = int(arg)
        except Exception: pass

        await ctx.channel.purge(limit=amount)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        embed = discord.Embed(
            title="👋 Selamat Datang!",
            description=f"Selamat datang di server, {member.mention}!",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        channel = member.guild.system_channel
        if channel:
            await channel.send(embed=embed)

    @commands.command(name="serverinfo", help="Menampilkan info server.")
    async def serverinfo(self, ctx):
        guild = ctx.guild
        embed = discord.Embed(title=f"Server Info: {guild.name}", color=discord.Color.blurple())
        embed.add_field(name="👑 Owner", value=guild.owner, inline=True)
        embed.add_field(name="👥 Members", value=guild.member_count, inline=True)
        embed.add_field(name="📅 Dibuat pada", value=guild.created_at.strftime("%d %B %Y"), inline=False)
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        await ctx.send(embed=embed)

    @commands.command(name="userinfo", help="Tampilkan info pengguna.")
    async def userinfo(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=f"Info Pengguna: {member}", color=discord.Color.orange())
        embed.add_field(name="🆔 ID", value=member.id)
        embed.add_field(name="📛 Display Name", value=member.display_name)
        embed.add_field(name="📅 Bergabung pada", value=member.joined_at.strftime("%d %B %Y"))
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        await ctx.send(embed=embed)
    
    @commands.command(name="poll", help="Buat polling: mad poll <pertanyaan>")
    async def poll(self, ctx, *, question):
        embed = discord.Embed(title="📊 Poll", description=question, color=discord.Color.gold())
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        message = await ctx.send(embed=embed)
        await message.add_reaction("👍")
        await message.add_reaction("👎")


    @commands.command(name="giveaway", help="Mulai giveaway: mad giveaway <hadiah> <durasi detik>")
    async def giveaway(self, ctx, hadiah: str, durasi: int):
        embed = discord.Embed(
            title="🎉 Giveaway!",
            description=f"Hadiah: **{hadiah}**\nKlik 🎉 untuk ikut!",
            color=discord.Color.magenta()
        )
        message = await ctx.send(embed=embed)
        await message.add_reaction("🎉")

        await asyncio.sleep(durasi)

        # Refresh message dan reactions
        try:
            message = await ctx.channel.fetch_message(message.id)
            reaction = discord.utils.get(message.reactions, emoji="🎉")
            if reaction is None:
                await ctx.send("❌ Tidak ada yang ikut giveaway.")
                return

            users = []
            async for user in reaction.users():
                users.append(user)

            users = [user for user in users if not user.bot]

            if len(users) == 0:
                await ctx.send("❌ Tidak ada yang ikut giveaway.")
                return

            winner = random.choice(users)
            await ctx.send(f"🎉 Selamat {winner.mention}, kamu menang **{hadiah}**!")
        except Exception as e:
            await ctx.send(f"⚠️ Terjadi kesalahan saat menentukan pemenang: {e}")




    @commands.command(name="rolemenu", help="Buat menu role dengan emoji")
    async def rolemenu(self, ctx):
        embed = discord.Embed(
            title="🎭 Pilih Role",
            description = (
                "Klik emoji di bawah untuk memilih role game favoritmu!\n\n"
                "🎮 - Dungeon And Dragon\n"
                "🖌️ - Valorant\n"
                "🧱 - Minecraft\n"
                "🦁 - League Of Legend\n"
                "🔫 - Counter Strike 2\n"
                "🧒 - Roblox\n\n"
                "Klik lagi untuk menghapus role-nya."
            ),
            color=discord.Color.blue()
        )

        msg = await ctx.send(embed=embed)

        # Emoji unik untuk tiap role
        emoji_role_pairs = {
            "🎮": "Dungeon And Dragon",
            "🖌️": "Valorant",
            "🧱": "Minecraft",
            "🦁": "League Of Legend",
            "🔫": "Counter Strike 2",
            "🧒": "Roblox"
        }

        self.role_emoji_map = emoji_role_pairs
        self.role_message_id = msg.id

        for emoji in emoji_role_pairs:
            await msg.add_reaction(emoji)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.message_id != getattr(self, "role_message_id", None):
            return

        guild = self.bot.get_guild(payload.guild_id)
        role_name = self.role_emoji_map.get(str(payload.emoji))
        if role_name:
            role = discord.utils.get(guild.roles, name=role_name)
            if role is None:
                role = await guild.create_role(name=role_name)
                print(f"Role '{role_name}' dibuat di server {guild.name}")

            # Pastikan member diambil ulang via guild.fetch_member jika guild.get_member None
            member = guild.get_member(payload.user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(payload.user_id)
                except Exception as e:
                    print(f"Gagal mendapatkan member: {e}")
                    return

            if role and member:
                try:
                    await member.add_roles(role)
                    print(f"Role '{role_name}' berhasil diberikan ke {member}")
                except Exception as e:
                    print(f"Gagal menambahkan role ke member: {e}")


    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.message_id != getattr(self, "role_message_id", None):
            return

        guild = self.bot.get_guild(payload.guild_id)
        role_name = self.role_emoji_map.get(str(payload.emoji))
        if role_name:
            role = discord.utils.get(guild.roles, name=role_name)
            if role is None:
                return

            member = guild.get_member(payload.user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(payload.user_id)
                except Exception as e:
                    print(f"Gagal mendapatkan member saat reaction remove: {e}")
                    return

            if role and member:
                try:
                    await member.remove_roles(role)
                    print(f"Role '{role_name}' di-remove dari {member}")
                except Exception as e:
                    print(f"Gagal menghapus role dari member: {e}")



