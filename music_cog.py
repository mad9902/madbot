
# Bot Musik Discord dengan Spotify, Shuffle, dan Loop
# File ini menggantikan music_cog.py kamu sebelumnya
# Pastikan kamu sudah install: discord.py, yt_dlp, spotipy

import discord
import asyncio
import json
import os
import re
import random
import requests
from discord.ui import View, Button
import spotipy
from discord.ext import commands
from yt_dlp import YoutubeDL
from spotipy.oauth2 import SpotifyClientCredentials
from discord.ui import View, Button
from dotenv import load_dotenv
from database import set_channel_settings, get_channel_settings
load_dotenv()

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

class music_cog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.is_playing = False
        self.disconnect_task = None
        self.current_song = None
        self.previous_song = None
        self.music_queue = []
        self.db = bot.db
        self.loop_mode = None
        self.channel_settings = {}
        self.YDL_OPTIONS = {'format': 'bestaudio/best', 'noplaylist': 'True'}
        self.FFMPEG_OPTIONS = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -hide_banner',
            'options': '-vn -loglevel warning'
        }
        self.vc = None
        self.ffmpeg_executable = "/usr/bin/ffmpeg" if not os.name == "nt" else r"C:\\ffmpeg\\bin\\ffmpeg.exe"

    async def load_channel_settings(self, guild_id, setting_type):
        settings = get_channel_settings(self.bot.db, guild_id, setting_type)
        self.channel_settings[(guild_id, setting_type)] = settings or {}


    async def save_channel_setting(self, guild_id, setting_type, channel_id, key, value):
        set_channel_settings(self.bot.db, guild_id, setting_type, channel_id)
        if (guild_id, setting_type) not in self.channel_settings:
            self.channel_settings[(guild_id, setting_type)] = {}
        self.channel_settings[(guild_id, setting_type)][key] = value


    async def send_to_music_channel(self, guild: discord.Guild, embed: discord.Embed):
        guild_id = str(guild.id)
        channel_id = self.channel_settings.get((guild_id, "music"))

        if channel_id is None:
            channel_id = get_channel_settings(self.bot.db, guild_id, "music")
            if channel_id:
                self.channel_settings[(guild_id, "music")] = channel_id

        target_channel = guild.get_channel(int(channel_id)) if channel_id else None

        if not target_channel:
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    target_channel = ch
                    break

        if target_channel:
            await target_channel.send(embed=embed)


    def search_yt(self, item):
        with YoutubeDL(self.YDL_OPTIONS) as ydl:
            try:
                info = ydl.extract_info(item if item.startswith("http") else f"ytsearch:{item}", download=False)
                if not item.startswith("http"):
                    info = info['entries'][0]
            except Exception as e:
                print(f"❌ Error saat mencari lagu: {e}")
                return False
            audio_url = None
            best_bitrate = 0
            for f in info.get('formats', []):
                if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                    abr = f.get('abr') or 0
                    if abr > best_bitrate:
                        best_bitrate = abr
                        audio_url = f['url']
            if audio_url is None:
                audio_url = info.get('url')
        return {
            'source': audio_url,
            'title': info['title'],
            'duration': info.get('duration_string') or f"{info.get('duration', 0) // 60}:{info.get('duration', 0) % 60:02}",
            'thumbnail': info.get('thumbnail')
        }

    def extract_spotify_id(self, url, type_):
        pattern = rf"open.spotify.com/{type_}/([a-zA-Z0-9]+)"
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        return None

    async def handle_spotify(self, query):
        results = []

        if "open.spotify.com/track" in query:
            track_id = self.extract_spotify_id(query, "track")
            if not track_id:
                return []
            track = sp.track(track_id)
            results.append(f"{track['name']} {track['artists'][0]['name']}")

        elif "open.spotify.com/album" in query:
            album_id = self.extract_spotify_id(query, "album")
            if not album_id:
                return []
            album = sp.album(album_id)
            for track in album['tracks']['items']:
                results.append(f"{track['name']} {track['artists'][0]['name']}")

        elif "open.spotify.com/playlist" in query:
            playlist_id = self.extract_spotify_id(query, "playlist")
            if not playlist_id:
                return []
            playlist = sp.playlist(playlist_id)
            for item in playlist['tracks']['items']:
                track = item['track']
                results.append(f"{track['name']} {track['artists'][0]['name']}")

        return results

    async def play_music(self):
        if len(self.music_queue) == 0:
            self.is_playing = False
            return

        song_data, voice_channel = self.music_queue.pop(0)
        self.current_song = song_data
        m_url = song_data['source']

        try:
            if self.vc is None or not self.vc.is_connected():
                self.vc = await voice_channel.connect()
            elif self.vc.channel != voice_channel:
                await self.vc.move_to(voice_channel)
        except Exception as e:
            print(f"❌ Voice connect error: {e}")
            self.is_playing = False
            return

        if self.vc.is_playing():
            self.vc.stop()

        try:
            self.vc.play(
                discord.FFmpegPCMAudio(m_url, executable=self.ffmpeg_executable, **self.FFMPEG_OPTIONS),
                after=lambda e: self.play_next(e)
            )
            self.is_playing = True
            embed = discord.Embed(
                title="🎶 Now Playing",
                description=f"**{self.current_song['title']}**",
                color=discord.Color.green()
            )
            embed.add_field(name="Track Length", value=self.current_song.get('duration', 'N/A'), inline=True)
            embed.set_image(url=self.current_song.get('thumbnail', ''))
            await self.send_to_music_channel(self.vc.guild, embed)
        except Exception as e:
            print(f"❌ Error saat memutar lagu di play_music: {e}")
            self.is_playing = False


    def play_next(self, error=None):
        if error:
            print(f"❌ Error saat play_next: {error}")

        if self.loop_mode == "single" and self.current_song:
            self.music_queue.insert(0, [self.current_song, self.vc.channel])
        elif self.loop_mode == "queue" and self.previous_song:
            self.music_queue.append(self.previous_song)

        if len(self.music_queue) > 0:
            self.is_playing = True
            next_song_data = self.music_queue.pop(0)
            self.current_song = next_song_data[0]
            m_url = self.current_song['source']
            self.previous_song = [self.current_song, self.vc.channel]

            # Kirim embed Now Playing
            embed = discord.Embed(
                title="🎶 Now Playing",
                description=f"**{self.current_song['title']}**",
                color=discord.Color.green()
            )
            embed.add_field(name="Track Length", value=self.current_song.get('duration', 'N/A'), inline=True)
            embed.set_image(url=self.current_song.get('thumbnail', ''))
            self.bot.loop.create_task(self.send_to_music_channel(self.vc.guild, embed))

            try:
                self.vc.play(
                    discord.FFmpegPCMAudio(m_url, executable=self.ffmpeg_executable, **self.FFMPEG_OPTIONS),
                    after=lambda e: self.play_next(e)
                )
            except Exception as e:
                print(f"❌ Error saat memutar lagu di play_next: {e}")
                self.is_playing = False
        else:
            self.is_playing = False
            if self.vc and self.vc.is_connected():
                if self.disconnect_task is None:
                    self.disconnect_task = self.bot.loop.create_task(
                        self.disconnect_after_timeout(self.vc.channel)
                    )


    @commands.command(name="queue", aliases=["q"], help="Show the current queue")
    async def queue(self, ctx):
        if not self.music_queue and not self.current_song:
            await ctx.send("📭 Antrian kosong!")
            return

        items_per_page = 10
        pages = [self.music_queue[i:i+items_per_page] for i in range(0, len(self.music_queue), items_per_page)]

        current_page = 0

        def create_embed(page):
            embed = discord.Embed(
                title="🎵 Daftar Antrian Lagu",
                description="Berikut lagu-lagu yang akan diputar:",
                color=discord.Color.blue()
            )

            if self.current_song:
                embed.add_field(name="🎧 Sedang Diputar", value=self.current_song['title'], inline=False)

            if not pages:
                embed.add_field(name="📋 Antrian Selanjutnya", value="Tidak ada", inline=False)
            else:
                queue_text = ""
                for i, song in enumerate(pages[page]):
                    index = page * items_per_page + i + 1
                    queue_text += f"**{index}.** {song[0]['title']}\n"
                embed.add_field(name="📋 Antrian Selanjutnya", value=queue_text or "Tidak ada", inline=False)
                embed.set_footer(text=f"Halaman {page+1} dari {len(pages)}")

            return embed

        class QueueView(View):
            def __init__(self):
                super().__init__(timeout=60)
                self.page = current_page

            @discord.ui.button(label="⬅️ Sebelumnya", style=discord.ButtonStyle.blurple)
            async def previous(self, interaction: discord.Interaction, button: Button):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("❌ Hanya yang memanggil command yang bisa navigasi.", ephemeral=True)
                    return
                if self.page > 0:
                    self.page -= 1
                    await interaction.response.edit_message(embed=create_embed(self.page), view=self)

            @discord.ui.button(label="➡️ Berikutnya", style=discord.ButtonStyle.blurple)
            async def next(self, interaction: discord.Interaction, button: Button):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("❌ Hanya yang memanggil command yang bisa navigasi.", ephemeral=True)
                    return
                if self.page < len(pages) - 1:
                    self.page += 1
                    await interaction.response.edit_message(embed=create_embed(self.page), view=self)

        await ctx.send(embed=create_embed(current_page), view=QueueView())

    @commands.command(name="play", aliases=["p"])
    async def p(self, ctx, *, query):
        if ctx.author.voice is None:
            await ctx.send("🎤 Kamu harus join voice channel dulu.")
            return
        voice_channel = ctx.author.voice.channel

        if "open.spotify.com" in query:
            tracks = await self.handle_spotify(query)
            if not tracks:
                await ctx.send("❌ Tidak bisa mengambil lagu dari Spotify.")
                return
            first_song_added = False  # flag
            for q in tracks:
                song = self.search_yt(q)
                if song:
                    self.music_queue.append([song, voice_channel])
                    if not self.is_playing and not first_song_added:
                        await self.play_music()
                        first_song_added = True  # hanya panggil sekali saat lagu pertama
                    # Kirim embed untuk setiap lagu
                    embed = discord.Embed(
                        title="🎵 Lagu Ditambahkan ke Antrian",
                        description=f"**{song['title']}**",
                        color=discord.Color.orange()
                    )
                    embed.add_field(name="Durasi", value=song.get('duration', 'N/A'), inline=True)
                    embed.set_image(url=song.get('thumbnail', ''))
                    embed.set_footer(text=f"Ditambahkan oleh {ctx.author.display_name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
                    await self.send_to_music_channel(ctx.guild, embed)

            await ctx.send(f"✅ Menambahkan {len(tracks)} lagu dari Spotify ke antrian.")
        else:
            song = self.search_yt(query)
            if not song:
                await ctx.send("❌ Tidak bisa menemukan lagu.")
                return
            self.music_queue.append([song, voice_channel])
            # Kirim embed untuk satu lagu
            embed = discord.Embed(
                title="🎵 Lagu Ditambahkan ke Antrian",
                description=f"**{song['title']}**",
                color=discord.Color.orange()
            )
            embed.add_field(name="Durasi", value=song.get('duration', 'N/A'), inline=True)
            embed.set_image(url=song.get('thumbnail', ''))
            embed.set_footer(text=f"Ditambahkan oleh {ctx.author.display_name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
            await self.send_to_music_channel(ctx.guild, embed)

        if not self.is_playing:
            await self.play_music()


    @commands.command(name="shuffle")
    async def shuffle(self, ctx):
        if len(self.music_queue) < 2:
            await ctx.send("❗ Tidak cukup lagu untuk diacak.")
            return
        random.shuffle(self.music_queue)
        await ctx.send("🔀 Antrian telah diacak.")

    @commands.command(name="loop")
    async def loop(self, ctx, mode: str = None):
        if mode == "current":
            self.loop_mode = "single"
            await ctx.send("🔁 Mode loop: Lagu saat ini.")
        elif mode == "queue":
            self.loop_mode = "queue"
            await ctx.send("🔁 Mode loop: Seluruh antrian.")
        elif mode == "off":
            self.loop_mode = None
            await ctx.send("⏹️ Loop dimatikan.")
        else:
            await ctx.send("❗ Gunakan `loop current`, `loop queue`, atau `loop off`.")

    @commands.command(name="setchmusic", aliases=["setchannel"], help="Set channel khusus untuk kirim info musik")
    async def setch(self, ctx, channel: discord.TextChannel):
        if ctx.author.id != ctx.guild.owner_id and ctx.author.id != 416234104317804544:
            await ctx.send("❌ Hanya pemilik server yang bisa menggunakan command ini.")
            return

        guild_id = str(ctx.guild.id)
        channel_id = str(channel.id)

        # Simpan ke DB dengan setting_type 'music'
        set_channel_settings(self.db, guild_id, "music", channel_id)

        # Update cache dengan struktur nested dict per setting_type
        if guild_id not in self.channel_settings:
            self.channel_settings[guild_id] = {}
        self.channel_settings[guild_id]['music'] = channel_id

        print(guild_id, channel_id)
        await ctx.send(f"✅ Channel khusus musik telah disetel ke {channel.mention}")



    @commands.command(name="disconnect", aliases=["stop", "dc", "leave"], help="Disconnect the bot from voice channel")
    async def dc(self, ctx):
        # Cek apakah bot sedang terhubung ke voice channel
        if self.vc and self.vc.is_connected():
            author_vc = ctx.author.voice.channel if ctx.author.voice else None

            # Cek apakah user berada di voice channel yang sama dengan bot
            if author_vc != self.vc.channel:
                await ctx.send("🚫 Kamu harus berada di voice channel yang sama dengan bot untuk menggunakan perintah ini.")
                return

            await self.vc.disconnect()
            self.is_playing = False
            self.music_queue.clear()
            self.vc = None
            await ctx.send("🔌 Bot keluar dari voice channel.")
        else:
            await ctx.send("❗ Bot belum join ke voice channel.")

    # Event handler yang pantau user masuk/keluar voice channel
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not self.vc or not self.vc.channel:
            return  # Bot belum connect voice

        voice_channel = self.vc.channel

        # Cek apakah event terkait voice channel bot
        # Misal user pindah dari atau ke voice_channel bot
        if before.channel == voice_channel or after.channel == voice_channel:
            # Cek jumlah user (non-bot) di voice_channel bot sekarang
            members = [m for m in voice_channel.members if not m.bot]

            if len(members) == 0:
                # Kalau kosong, mulai countdown disconnect kalau belum jalan
                if self.disconnect_task is None:
                    print("Voice channel kosong, mulai countdown disconnect 180 detik")
                    self.disconnect_task = self.bot.loop.create_task(
                        self.disconnect_after_timeout(voice_channel, timeout=180)
                    )
            else:
                # Kalau ada user, cancel countdown disconnect kalau ada
                if self.disconnect_task:
                    print("User masuk kembali, cancel countdown disconnect")
                    self.disconnect_task.cancel()
                    self.disconnect_task = None

    async def disconnect_after_timeout(self, voice_channel, timeout=180):
        try:
            await asyncio.sleep(timeout)

            # Cek lagi sebelum disconnect
            if not self.vc or self.vc.channel != voice_channel:
                return

            members = [m for m in voice_channel.members if not m.bot]

            if len(members) == 0:
                print(f"Timeout {timeout}s selesai, disconnecting bot...")
                await self.vc.disconnect()
                self.vc = None
                self.is_playing = False

                embed = discord.Embed(
                    title="👋 Bot Keluar",
                    description="Bot keluar karena tidak ada user di voice channel dalam waktu lama.",
                    color=discord.Color.red()
                )
                # Kirim pesan ke channel musik atau lainya (implementasi sesuai kamu)
                await self.send_to_music_channel(voice_channel.guild, embed)

            self.disconnect_task = None

        except asyncio.CancelledError:
            # Task dibatalkan karena user masuk lagi
            print("Countdown disconnect dibatalkan.")
            self.disconnect_task = None

    @commands.command(name="skip", aliases=["s", "next"], help="Skip the current song")
    async def skip(self, ctx):
        if self.vc and self.vc.is_playing():
            # Cek apakah ada lagu berikutnya di antrian
            if len(self.music_queue) > 0:
                next_song = self.music_queue[0][0]  # Ambil lagu berikutnya (tanpa pop)
                
                embed = discord.Embed(
                    title="🎶 Next Up",
                    description=f"**{next_song['title']}**",
                    color=discord.Color.green()
                )
                embed.add_field(name="Track Length", value=next_song.get('duration', 'N/A'), inline=True)
                embed.set_image(url=next_song.get('thumbnail', ''))
                embed.set_footer(
                    text=f"Requested by {ctx.author.display_name}",
                    icon_url=ctx.author.avatar.url if ctx.author.avatar else None
                )

                await ctx.send(embed=embed)
            else:
                await ctx.send("📭 Tidak ada lagu berikutnya dalam antrian.")

            self.vc.stop()
        else:
            await ctx.send("❗ Tidak ada lagu yang sedang diputar.")


    @commands.command(name="song", help="Cari lagu berdasarkan lirik. Gunakan argumen atau reply.")
    async def msong_command(self, ctx, *, lyric_snippet: str = None):
        # Ambil isi dari reply jika tidak ada argumen
        if not lyric_snippet and ctx.message.reference:
            try:
                replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if replied_message.content:
                    text = replied_message.content
                elif replied_message.embeds:
                    text = replied_message.embeds[0].description or ""
                else:
                    text = ""
                # Bersihkan teks
                text = re.sub(r"<@!?[0-9]+>", "", text)
                text = re.sub(r"\s+", " ", text)
                lyric_snippet = text.strip()
            except Exception as e:
                print(f"[msong ERROR] gagal ambil reply: {e}")
                lyric_snippet = None

        # Validasi input
        if not lyric_snippet or len(lyric_snippet.split()) < 4:
            return await ctx.send("❗ Berikan potongan lirik yang cukup melalui argumen atau reply.")

        # Kirim pesan proses dan simpan referensinya untuk dihapus nanti
        loading_msg = await ctx.send("🔎 Mencari lagu berdasarkan lirik...")

        # Siapkan permintaan ke AudD API
        api_key = os.getenv("AUDD_API_KEY")
        params = {
            "q": lyric_snippet,
            "api_token": api_key
        }

        try:
            res = requests.get("https://api.audd.io/findLyrics/", params=params)
            data = res.json()

            if data.get("status") != "success" or not data.get("result"):
                await loading_msg.delete()
                return await ctx.send("❌ Lagu tidak ditemukan.")

            song = data["result"][0]
            title = song.get("title", "Unknown")
            artist = song.get("artist", "Unknown")

            await loading_msg.delete()
            await ctx.send(f"🎵 Dugaan lagu berdasarkan lirik:\n**{title} - {artist}**")

        except Exception as e:
            print(f"[msong ERROR] {e}")
            await loading_msg.delete()
            await ctx.send("❌ Terjadi error saat menghubungi AudD API.")