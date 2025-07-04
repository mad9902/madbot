import discord
import random
import asyncio

from discord.ext import commands
from discord import app_commands
from bot_state import DISABLED_GUILDS, OWNER_ID

class main_cog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.text_channel_list = []

    @commands.Cog.listener()
    async def on_ready(self):
        activity = discord.Game(name="mad help|md help|mhelp")
        await self.bot.change_presence(status=discord.Status.dnd, activity=activity)

        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                self.text_channel_list.append(channel)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if hasattr(self.bot, "on_message"):
            return
        await self.bot.process_commands(message)


    @commands.command(name="botoff")
    async def botoff(self, ctx):
        if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID):
            return await ctx.send("❌ Hanya admin atau pemilik bot yang bisa menggunakan command ini.")
        DISABLED_GUILDS.add(ctx.guild.id)
        await ctx.send("🛑 Bot dinonaktifkan di server ini. Tidak akan merespons command.")

    @commands.command(name="boton")
    async def boton(self, ctx):
        if not (ctx.author.guild_permissions.administrator or ctx.author.id == OWNER_ID):
            return await ctx.send("❌ Hanya admin atau pemilik bot yang bisa menggunakan command ini.")
        DISABLED_GUILDS.discard(ctx.guild.id)
        await ctx.send("✅ Bot diaktifkan kembali di server ini.")
                
    @app_commands.command(name="ping", description="Cek latensi bot.")
    async def slash_ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"[SLASH] Pong! 🏓 Latensi: {latency}ms")

    @commands.command(name="ping", help="Cek latensi bot.")
    async def prefix_ping(self, ctx):
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"Pong! 🏓 Latensi: {latency}ms")

    @commands.command(name="help", aliases=["h"], help="Displays all the available commands")
    async def help(self, ctx):
        embed = discord.Embed(
            title="📜 MAD BOT HELP",
            description="Daftar command yang tersedia:\nGunakan prefix `mad , md , m` sebelum command.\nContoh: `mad play | md play | mplay`",
            color=discord.Color.purple()
        )

        embed.add_field(
            name="💬 General Commands",
            value=(
                "`help`                       - Tampilkan semua command\n"
                "`clear / cl <amount>`        - Hapus pesan (owner only)\n"
                "`pick <opsi1, opsi2>`        - Pilih acak dari beberapa opsi\n"
                "`giveaway <hadiah> <durasi>` - Buat giveaway\n"
                "`poll <pertanyaan>`          - Buat polling ya/tidak\n"
                "`ping`                       - Cek Ping Bot\n"
                "`tts <teks>`                 - Ubah teks jadi text-to-speech\n"
            ),
            inline=False
        )

        embed.add_field(
            name="🖼️ Image Commands",
            value=(
                "`emoji <emoji or id>`   - Ambil emoji sebagai gambar\n"
                "`sticker <reply or id>` - Ambil stiker sebagai gambar\n"
                "`avatar <tag optional>` - Ambil avatar user\n"
                "`upload <image>`        - Upload gambar ke link\n"
                "`caption <reply image>` - add caption ke gambar (additional command --uppercase --lowercase --top --bottom)"
            ),
            inline=False
        )

        embed.add_field(
            name="🤖 AI",
            value=(
                "`ai (question)`  - generate ai berdasarkan pertanyaan\n"
                "`anomali (name)` - generate nama dan kisah anomali dari nama\n"
                "`truth`          - memberikan pertanyaan untuk game (truth) or dare\n"
                "`dare`           - memberikan pertanyaan untuk game truth or (dare)\n"
                "`rank <topik>`   - memberikan rank untuk topik tertentu"
            ),
            inline=False
        )

        embed.add_field(
            name="🕹️ Game",
            value=(
                "`sambungkata`    - game sambung kata multiplayer\n"
                "`stopgame`       - stop game yang sudah dimulai (host only)"
            ),
            inline=False
        )

        embed.add_field(
            name="🎵 Music Commands",
            value=(
                "`p / play <lagu>`          - Putar lagu dari YouTube\n"
                "`q / queue`                - Lihat antrian lagu\n"
                "`skip`                     - Lewati lagu saat ini\n"
                "`setchmusic <id_channel>`  - Set channel musik (owner only)\n"
                "`leave / disconnect / dc`  - Hentikan dan keluar voice\n"
                "`shuffle`                  - Acak antrian\n"
                "`loop current / queue`     - Loop lagu atau antrian\n"
                "`song <lyrics>`            - Cari lagu berdasarkan lyrics"
            ),
            inline=False
        )

        embed.add_field(
            name="📌 Role Reaction (owner only)",
            value=(
                "`rolemenu <emoji> <nama role>`\n"
                "Contoh: `mad rolemenu 🎮 Gamer, 🧱 Minecraft`"
            ),
            inline=False
        )

        embed.add_field(
            name="🆙 XP System",
            value=(
                "`level`                           - Lihat level XP kamu\n"
                "`leaderboard`                     - Lihat top 10 leaderboard XP\n"
                "`setchlevel <id channel>`         - Set Channel kirim leveling info (owner only)\n"
                "`setrolelvl <level> <id role>`    - Auto-role saat level tertentu\n"
                "`removerolelvl <level>`           - Hapus auto-role"
            ),
            inline=False
        )

        embed.add_field(
            name="🎂 Birthday",
            value=(
                "`setbirthday [@user|nama] <tanggal>` - Simpan ulang tahun kamu atau orang lain\n"
                "`mybirthday`                         - Lihat ulang tahun kamu\n"
                "`birthdaylist`                       - Daftar ulang tahun semua user\n"
                "`nearestbirthday`                    - Ulang tahun terdekat\n"
                "`deletebirthday [@user|nama]`        - Hapus ulang tahun (owner only)\n"
                "`setbirthdaych <channel>`            - Set channel ucapan ulang tahun"
            ),
            inline=False
        )

        embed.add_field(
            name="😴 AFK",
            value=(
                "`afk <alasan>` - Tandai kamu AFK\n"
                "AFK akan dihapus otomatis saat kamu kirim pesan"
            ),
            inline=False
        )

        embed.add_field(
            name="🌐 Translate",
            value=(
                "`translate <teks> <kode_bahasa>` - Terjemahkan teks ke bahasa tertentu\n"
                "Contoh: `mtranslate Aku suka kamu en`"
            ),
            inline=False
        )

        embed.add_field(
            name="📤 Download Video / Audio",
            value=(
                " Auto konversi link Instagram reels/video TikTok/Yt Shorts ke video saat kirim link\n"
                "`mp3 <video>/<link>`         - ambil audio dari video/link\n"
            ),
            inline=False
        )

        embed.add_field(
            name="ℹ️ Info",
            value=(
                "`serverinfo`     - Info server\n"
                "`userinfo <tag>` - Info user"
            ),
            inline=False
        )

        embed.set_footer(text="Gunakan command dengan bijak ✨")

        await ctx.send(embed=embed)



    @commands.command(name="clear", aliases=["cl"], help="Clears a specified amount of messages")
    async def clear(self, ctx, arg):
        # Cek apakah user adalah pemilik server atau user dengan ID tertentu
        if ctx.author.id != 416234104317804544 and ctx.author != ctx.guild.owner:
            await ctx.send("❌ Maaf, hanya pemilik server yang bisa menggunakan command ini.")
            return
        amount = 5
        try:
            amount = int(arg)
        except Exception:
            pass

        await ctx.channel.purge(limit=amount)
        await ctx.send(f"✅ Berhasil menghapus {amount} pesan.", delete_after=5)


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



    @commands.command(name="rolemenu", help="Buat menu role dengan emoji dan nama: mad rolemenu 🎮 DnD, 🧱 Minecraft")
    async def rolemenu(self, ctx, *, arg):
        if ctx.author.id != ctx.guild.owner_id and ctx.author.id != 416234104317804544:
            await ctx.send("❌ Hanya pemilik server yang bisa menggunakan command ini.")
            return

        try:
            # Parsing: pisahkan berdasarkan koma
            raw_pairs = [item.strip() for item in arg.split(",") if item.strip()]
            emoji_role_pairs = {}

            for pair in raw_pairs:
                parts = pair.strip().split(" ", 1)
                if len(parts) != 2:
                    await ctx.send(f"❌ Format salah untuk: `{pair}`. Gunakan: <emoji> <nama role>")
                    return
                emoji, role_name = parts
                emoji_role_pairs[emoji] = role_name.strip()

            # Buat embed menu
            desc_lines = [f"{emoji} - {name}" for emoji, name in emoji_role_pairs.items()]
            embed = discord.Embed(
                title="🎭 Pilih Role",
                description="Klik emoji di bawah untuk memilih role favoritmu!\n\n" + "\n".join(desc_lines) + "\n\nKlik lagi untuk menghapus role-nya.",
                color=discord.Color.blue()
            )
            msg = await ctx.send(embed=embed)

            self.role_emoji_map = emoji_role_pairs
            self.role_message_id = msg.id

            for emoji in emoji_role_pairs:
                await msg.add_reaction(emoji)

        except Exception as e:
            await ctx.send(f"⚠️ Gagal membuat menu role: {e}")


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


    @commands.command(name="pick", help="Pilih random dari daftar item dengan persentase opsional. Contoh: !pick ayam 5%, bakso, mie, nasi 10%")
    async def pick(self, ctx, *, items: str):
            entries = [x.strip() for x in items.split(',')]
            choices = []
            total_given_percent = 0.0
            unspecified = []

            for entry in entries:
                if '%' in entry:
                    try:
                        name, percent = entry.rsplit(' ', 1)
                        percent = float(percent.strip().replace('%', ''))
                        if percent < 0 or percent > 100:
                            await ctx.send(f"❌ Persentase untuk '{name.strip()}' harus antara 0 dan 100.")
                            return
                        choices.append((name.strip(), percent))
                        total_given_percent += percent
                    except Exception:
                        unspecified.append(entry)
                else:
                    unspecified.append(entry)

            if total_given_percent > 100:
                await ctx.send("❌ Total persentase yang diberikan melebihi 100%.")
                return

            remaining = 100 - total_given_percent
            count_unspecified = len(unspecified)

            if count_unspecified > 0:
                share = remaining / count_unspecified
                for name in unspecified:
                    choices.append((name.strip(), share))

            # Buat cumulative distribution
            cumulative = []
            current = 0
            for name, percent in choices:
                current += percent
                cumulative.append((name, current))

            # Pilih secara acak berdasarkan distribusi
            roll = random.uniform(0, 100)
            for name, threshold in cumulative:
                if roll <= threshold:
                    await ctx.send(f"🎲 Hasil random: **{name}**")
                    return



