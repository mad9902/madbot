# Bot Musik Discord ULTRA VERSION
# Fitur:
# ✔ Spotify → YouTube converter
# ✔ YouTube search auto extractor (anti SABR update 2025)
# ✔ Volume Control (FFmpeg filter)
# ✔ BassBoost (low/medium/high/insane)
# ✔ Auto Normalizer + Compressor
# ✔ Preload next track (low latency transition)
# ✔ Auto leave after idle 60s / empty VC 60s
# ✔ Queue / Loop / Skip / Shuffle
#
# Prefix mengikuti main bot (tidak ditentukan di sini)

import discord
import asyncio
import os
import re
import shutil
import random
import requests
from discord.ext import commands
from discord.ui import View, Button
from yt_dlp import YoutubeDL
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
from database import set_channel_settings, get_channel_settings

load_dotenv()

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    )
)

# ======================================================
# BUTTON CONTROL VIEW
# ======================================================

class PlayerControl(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    # Pause
    @discord.ui.button(emoji="⏸", style=discord.ButtonStyle.gray)
    async def pause(self, interaction: discord.Interaction, button: Button):
        vc = self.cog.vc
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸ Lagu dijeda.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠ Tidak ada lagu yang berjalan.", ephemeral=True)

    # Resume
    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.green)
    async def resume(self, interaction: discord.Interaction, button: Button):
        vc = self.cog.vc
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Dilanjutkan.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠ Tidak ada lagu yang dijeda.", ephemeral=True)

    # Skip
    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.blurple)
    async def skip(self, interaction: discord.Interaction, button: Button):
        vc = self.cog.vc
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("⏭️ Skip lagu.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠ Tidak ada lagu.", ephemeral=True)

    # Volume Down
    @discord.ui.button(emoji="🔉", style=discord.ButtonStyle.gray)
    async def vol_down(self, interaction: discord.Interaction, button: Button):
        self.cog.volume = max(0.1, self.cog.volume - 0.1)
        if self.cog.vc and (self.cog.vc.is_playing() or self.cog.vc.is_paused()):
            await self.cog.refresh_current()
        await interaction.response.send_message(
            f"🔉 Volume: {int(self.cog.volume*100)}%", ephemeral=True
        )
    # Volume Up
    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.gray)
    async def vol_up(self, interaction: discord.Interaction, button: Button):
        self.cog.volume = min(2.0, self.cog.volume + 0.1)
        if self.cog.vc and (self.cog.vc.is_playing() or self.cog.vc.is_paused()):
            await self.cog.refresh_current()
        await interaction.response.send_message(
            f"🔊 Volume: {int(self.cog.volume*100)}%", ephemeral=True
        )
    # Loop toggle
    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.gray)
    async def loop_toggle(self, interaction: discord.Interaction, button: Button):
        if self.cog.loop_mode is None:
            self.cog.loop_mode = "single"
            msg = "🔁 Loop ON (single)"
        elif self.cog.loop_mode == "single":
            self.cog.loop_mode = "queue"
            msg = "🔁 Loop ON (queue)"
        else:
            self.cog.loop_mode = None
            msg = "⏹ Loop OFF"

        await interaction.response.send_message(msg, ephemeral=True)


class music_cog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # autoplay state
        self.autoplay = False

        # skip after-callback kalau restart manual (volume/bass, dsb)
        self.skip_after = False

        # state untuk Now Playing / progress
        self.now_playing_message = None
        self.started_at = None          # datetime mulai lagu
        self.current_duration = None    # durasi dalam detik
        self.progress_task = None       # background task updater progress

        # playback state
        self.vc = None
        self.current_song = None
        self.previous_song = None
        self.music_queue = []
        self.is_playing = False
        self.after_lock = asyncio.Lock()

        # auto leave timers
        self.idle_disconnect_task = None
        self.empty_vc_disconnect_task = None

        # preload next track holder
        self.preloaded_source = None

        # loop mode: None, "single", "queue"
        self.loop_mode = None

        # channels where embed will be sent
        self.channel_settings = {}

        # database
        self.db = bot.db

        try:
            self.channel_settings = get_channel_settings(self.db) or {}
        except Exception as e:
            print(f"[MUSIC_COG] Gagal load channel_settings dari DB: {e}")
            self.channel_settings = {}

        # FFmpeg executable (Windows)
        self.ffmpeg_executable = shutil.which("ffmpeg")

        # Default volume
        self.volume = 1.0

        # BassBoost level (None / low / medium / high / insane)
        self.bassboost_level = None

        # normalize + compressor always on (from your selection)
        self.auto_normalize = True

    # ======================================================
    # FFmpeg FILTER BUILDER
    # ======================================================

    def build_ffmpeg_filters(self):
        """
        Build dynamic FFmpeg filter string based on:
        - volume
        - bassboost
        - normalize/compander
        """
        filters = []

        # Volume
        filters.append(f"volume={self.volume}")

        # BassBoost
        if self.bassboost_level == "low":
            filters.append("bass=g=3")
        elif self.bassboost_level == "medium":
            filters.append("bass=g=6")
        elif self.bassboost_level == "high":
            filters.append("bass=g=9")
        elif self.bassboost_level == "insane":
            filters.append("bass=g=12")

        # Auto normalize+compressor
        if self.auto_normalize:
            filters.append(
                "acompressor=threshold=-20dB:ratio=3:attack=10:release=100"
            )

        return ",".join(filters)


    # ======================================================
    # DURATION / PROGRESS HELPER
    # ======================================================

    def parse_duration_seconds(self, dur):
        """
        Ubah berbagai format durasi jadi detik (int).
        Support:
        - int / float → langsung
        - "215" → 215
        - "3:45" / "01:02:03" → konversi hh:mm:ss
        """
        if dur is None:
            return None

        if isinstance(dur, (int, float)):
            return int(dur)

        if isinstance(dur, str):
            dur = dur.strip()
            if dur.isdigit():
                return int(dur)

            parts = dur.split(":")
            try:
                parts = list(map(int, parts))
            except ValueError:
                return None

            total = 0
            for p in parts:
                total = total * 60 + p
            return total

        return None

    def format_mmss(self, t):
        if t is None:
            return "?:??"
        t = int(t)
        m = t // 60
        s = t % 60
        return f"{m}:{s:02d}"

    def build_progress_bar(self):
        """
        Bangun progress bar teks, misal:
        ▰▰▰▰▰▱▱▱▱▱ `1:23 / 3:45`
        """
        if not self.current_duration or not self.started_at:
            return "▱▱▱▱▱▱▱▱▱▱ `0:00 / ??:??`"

        now = discord.utils.utcnow()
        elapsed = (now - self.started_at).total_seconds()
        elapsed = max(0, min(self.current_duration, int(elapsed)))

        ratio = elapsed / self.current_duration if self.current_duration else 0
        total_blocks = 10
        filled = int(total_blocks * ratio)

        bar = "▰" * filled + "▱" * (total_blocks - filled)
        return f"{bar} `{self.format_mmss(elapsed)} / {self.format_mmss(self.current_duration)}`"

    def build_now_playing_embed(self):
        """
        Build embed Now Playing dengan icon mode + progress bar.
        """
        if not self.current_song:
            return None

        # ICON MODE
        base_icon = "🎶"
        if self.loop_mode == "single":
            base_icon = "🔂"
        elif self.loop_mode == "queue":
            base_icon = "🔁"

        if self.autoplay:
            base_icon += "✨"

        title = f"{base_icon} Now Playing"

        embed = discord.Embed(
            title=title,
            description=f"**{self.current_song['title']}**",
            color=discord.Color.green()
        )

        if self.current_song.get("thumbnail"):
            embed.set_image(url=self.current_song["thumbnail"])

        embed.add_field(
            name="Duration",
            value=self.current_song.get("duration", "N/A"),
            inline=True
        )

        # status mode di field terpisah
        loop_status = self.loop_mode or "off"
        autoplay_status = "on" if self.autoplay else "off"
        embed.add_field(
            name="Mode",
            value=f"Loop: **{loop_status}**\nAutoplay: **{autoplay_status}**",
            inline=True
        )

        # progress bar
        embed.add_field(
            name="Progress",
            value=self.build_progress_bar(),
            inline=False
        )

        return embed

    # ======================================================
    # YOUTUBE SEARCH & EXTRACT — Anti SABR 2025
    # ======================================================

    def search_yt(self, query):
        """
        Return dict:
        {
            "source": direct_audio_url,
            "title": "...",
            "thumbnail": "...",
            "duration": "..."
        }
        """

        YDL_OPTIONS = {
            "format": "bestaudio/best",
            "quiet": True,
            "noplaylist": True,
            "default_search": "auto",
            "extract_flat": False,
            "ignoreerrors": True,
            "no_warnings": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "cachedir": False,
        }

        with YoutubeDL(YDL_OPTIONS) as ydl:
            try:
                info = ydl.extract_info(query, download=False)
            except Exception as e:
                print(f"[YT ERROR] {e}")
                return None

        if not info:
            return None

        # If search results
        if "entries" in info:
            info = info["entries"][0]

        if not info or "url" not in info:
            return None

        # Fallback for SABR HLS streams
        stream_url = info.get("url")

        return {
            "source": stream_url,
            "title": info.get("title", "Unknown title"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration_string") or info.get("duration"),
        }


    def yt_search_filtered(self, query):

        YDL_OPTIONS = {
            "format": "bestaudio/best",
            "quiet": True,
            "noplaylist": True,
            "default_search": "ytsearch10",
            "ignoreerrors": True,
            "extractor_args": {"youtube": {"player_client": ["default"]}},
        }

        with YoutubeDL(YDL_OPTIONS) as ydl:
            try:
                info = ydl.extract_info(query, download=False)
            except:
                return None

        if not info or "entries" not in info:
            return None

        def pick_audio(entry):
            if "formats" not in entry:
                return None
            for f in entry["formats"]:
                if f.get("acodec") != "none" and f.get("vcodec") == "none":
                    return f.get("url")
            return None

        for entry in info["entries"]:
            if not entry:
                continue

            dur = entry.get("duration")
            title = entry.get("title", "").lower()

            if any(x in title for x in [
                "mix", "playlist", "hour", "extended", "full album"
            ]):
                continue

            if not dur or dur < 120 or dur > 360:
                continue

            audio_url = pick_audio(entry)
            if not audio_url:
                continue

            return {
                "source": audio_url,
                "title": entry.get("title"),
                "thumbnail": entry.get("thumbnail"),
                "duration": entry.get("duration"),
            }

        return None


    # ======================================================
    # SPOTIFY HANDLING
    # ======================================================

    def extract_spotify_id(self, url, type_):
        pattern = rf"open\.spotify\.com/{type_}/([a-zA-Z0-9]+)"
        m = re.search(pattern, url)
        return m.group(1) if m else None

    async def handle_spotify(self, query):
        """
        Convert Spotify → list of search keywords for YouTube
        """
        results = []

        if "open.spotify.com/track" in query:
            tid = self.extract_spotify_id(query, "track")
            if tid:
                track = sp.track(tid)
                results.append(f"{track['name']} {track['artists'][0]['name']}")

        elif "open.spotify.com/album" in query:
            aid = self.extract_spotify_id(query, "album")
            if aid:
                album = sp.album(aid)
                for t in album["tracks"]["items"]:
                    results.append(f"{t['name']} {t['artists'][0]['name']}")

        elif "open.spotify.com/playlist" in query:
            pid = self.extract_spotify_id(query, "playlist")
            if pid:
                playlist = sp.playlist(pid)
                for item in playlist["tracks"]["items"]:
                    t = item["track"]
                    results.append(f"{t['name']} {t['artists'][0]['name']}")

        return results

    # ======================================================
    # PRELOAD NEXT TRACK
    # ======================================================

    async def preload_next(self):
        """
        Pre-fetch next track source for low-latency transition.
        """
        if len(self.music_queue) == 0:
            self.preloaded_source = None
            return

        song_data, _ = self.music_queue[0]
        self.preloaded_source = song_data["source"]
        print(f"[PRELOAD] next source ready: {song_data['title']}")

    # ======================================================
    # PLAY MUSIC (MAIN EXECUTION)
    # ======================================================

    async def play_music(self):
        """
        Pop song from queue, connect VC if needed, play song with filters.
        """
        if len(self.music_queue) == 0:
            self.is_playing = False
            self.current_song = None
            self.started_at = None
            self.current_duration = None

            # stop updater progress kalau masih jalan
            if self.progress_task:
                self.progress_task.cancel()
                self.progress_task = None

            # optional: jangan lupa referensi message-nya dihapus
            self.now_playing_message = None

            await self.start_idle_timer()
            return

        song_data, voice_channel = self.music_queue.pop(0)
        self.current_song = song_data

        # set waktu mulai & durasi
        self.started_at = discord.utils.utcnow()
        self.current_duration = self.parse_duration_seconds(
            self.current_song.get("duration")
        )

        # Preload next track
        await self.preload_next()

        # Connect VC
        try:
            if self.vc is None or not self.vc.is_connected():
                self.vc = await voice_channel.connect()
            elif self.vc.channel != voice_channel:
                await self.vc.move_to(voice_channel)
        except Exception as e:
            print(f"[VC ERROR] {e}")
            self.is_playing = False
            return

        if self.vc.is_playing():
            self.vc.stop()

        # Build FFmpeg filters dynamically
        filter_chain = self.build_ffmpeg_filters()

        before_opt = (
            "-nostdin "
            "-reconnect 1 "
            "-reconnect_streamed 1 "
            "-reconnect_on_network_error 1 "
            "-reconnect_delay_max 5 "
            "-reconnect_at_eof 1 "
            "-protocol_whitelist file,http,https,tcp,tls,crypto"
        )

        options_str = (
            f'-vn -af "{filter_chain}" '
            "-threads 1 "
            "-flags +low_delay "
            "-ignore_unknown "
            "-nostats -hide_banner -loglevel error"
        )

        # Start playing
        try:
            # gunakan Hasil preload jika ada (lebih cepat karena sudah resolve)
            source = self.preloaded_source or self.current_song["source"]

            self.vc.play(
                discord.FFmpegPCMAudio(
                    source,
                    executable=self.ffmpeg_executable,
                    before_options=before_opt,
                    options=options_str
                ),
                after=lambda e: self.bot.loop.call_soon_threadsafe(
                    asyncio.create_task, self._continue_next(e)
                )
            )
            self.preloaded_source = None
            self.is_playing = True

            embed = self.build_now_playing_embed()
            controls = PlayerControl(self)
            # simpan message Now Playing biar bisa diedit progress-nya
            self.now_playing_message = await self.send_to_music_channel(
                self.vc.guild, embed, view=controls
            )

            # mulai updater progress
            await self.start_progress_updater()

        except Exception as e:
            print(f"[PLAY ERROR] {e}")
            self.is_playing = False

    async def refresh_current(self):
        """
        Restart ulang lagu yg sedang diputar dengan filter FFmpeg terbaru
        tanpa ngutik-ngutik queue.
        """
        if not self.current_song or not self.vc:
            return

        # tandai biar _continue_next tidak jalan ketika stop ini
        self.skip_after = True

        if self.vc.is_playing() or self.vc.is_paused():
            self.vc.stop()

        filter_chain = self.build_ffmpeg_filters()

        before_opt = (
            "-nostdin "
            "-reconnect 1 "
            "-reconnect_streamed 1 "
            "-reconnect_on_network_error 1 "
            "-reconnect_delay_max 5 "
            "-reconnect_at_eof 1 "
            "-protocol_whitelist file,http,https,tcp,tls,crypto"
        )

        options_str = (
            f'-vn -af "{filter_chain}" '
            "-threads 1 "
            "-flags +low_delay "
            "-ignore_unknown "
            "-nostats -hide_banner -loglevel error"
        )

        source = self.preloaded_source or self.current_song["source"]
        self.preloaded_source = None  # clear setelah dipakai


        self.vc.play(
            discord.FFmpegPCMAudio(
                source,
                executable=self.ffmpeg_executable,
                before_options=before_opt,
                options=options_str
            ),
            after=lambda e: self.bot.loop.call_soon_threadsafe(
                asyncio.create_task, self._continue_next(e)
            )
        )
        self.is_playing = True
        # reset start time & progress ketika refresh
        self.started_at = discord.utils.utcnow()

    async def start_progress_updater(self):
        """
        Background task untuk update field progress setiap beberapa detik.
        """
        if not self.now_playing_message or not self.current_duration:
            return

        # stop task lama kalau ada
        if self.progress_task:
            self.progress_task.cancel()
            self.progress_task = None

        async def runner():
            try:
                while self.is_playing and self.vc and self.vc.is_connected():
                    await asyncio.sleep(5)
                    await self.update_progress_embed()
            except asyncio.CancelledError:
                pass

        self.progress_task = asyncio.create_task(runner())

    async def update_progress_embed(self):
        """
        Edit embed Now Playing dengan progress bar terbaru.
        """
        if not self.now_playing_message:
            return

        try:
            embed = self.build_now_playing_embed()
            if not embed:
                return
            await self.now_playing_message.edit(embed=embed)
        except Exception:
            # kalau message hilang / tidak bisa diedit, diamkan saja
            pass



    # ======================================================
    # AFTER FINISH SONG
    # ======================================================

    async def _continue_next(self, error=None):

        async with self.after_lock:  # <--- ANTI DUPLIKASI
            # jika stop dipicu refresh_current
            if self.skip_after:
                self.skip_after = False
                return

            last_song = self.current_song

            if self.autoplay:
                self.loop_mode = None

            # Hentikan progress task
            if self.progress_task:
                self.progress_task.cancel()
                self.progress_task = None

            if error:
                print(f"[AFTER ERROR] {error}")

            # ===== LOOP SINGLE =====
            if self.loop_mode == "single" and last_song:
                self.music_queue.insert(0, [last_song, self.vc.channel])

            # ===== LOOP QUEUE ===== (autoplay OFF)
            elif self.loop_mode == "queue" and not self.autoplay and last_song:
                self.music_queue.append([last_song, self.vc.channel])

            # ===== QUEUE HABIS =====
            if len(self.music_queue) == 0:

                # ===== AUTOPLAY =====
                if self.autoplay and last_song:

                    base = last_song["title"].split("-")[0].strip()
                    q = f"{base} official audio"

                    auto = self.yt_search_filtered(q)

                    if auto:
                        print("[AUTOPLAY] Next filtered:", auto["title"])
                        self.music_queue.append([auto, self.vc.channel])
                        return await self.play_music()

                    # fallback
                    fallback = self.yt_search_filtered("popular songs official audio")
                    if fallback:
                        print("[AUTOPLAY] Fallback:", fallback["title"])
                        self.music_queue.append([fallback, self.vc.channel])
                        return await self.play_music()

                    print("[AUTOPLAY] Tidak ada rekomendasi valid.")

                self.is_playing = False
                await self.start_idle_timer()
                return

            # ===== LANJUT =====
            await self.play_music()





    # ======================================================
    # AUTO PLAY MUSIC
    # ======================================================

    @commands.command(name="autoplay", aliases=["ap"])
    async def autoplay_cmd(self, ctx, mode=None):
        if mode not in ["on", "off"]:
            return await ctx.send("🔁 Autoplay:\n`autoplay on`\n`autoplay off`")

        if mode == "on":
            self.autoplay = True
            await ctx.send("🔁 **Autoplay diaktifkan.** Bot akan memutar lagu rekomendasi ketika queue habis.")
        else:
            self.autoplay = False
            await ctx.send("⏹ Autoplay dimatikan.")


    # ======================================================
    # AUTO LEAVE (IDLE & EMPTY VC)
    # ======================================================

    async def start_idle_timer(self):
        """
        Leave VC if no song is playing for 60 seconds.
        """
        if self.idle_disconnect_task:
            self.idle_disconnect_task.cancel()

        async def idle_task():
            try:
                await asyncio.sleep(60)
                if not self.is_playing and self.vc and self.vc.is_connected():
                    await self.vc.disconnect()
                    self.vc = None
            except asyncio.CancelledError:
                pass

        self.idle_disconnect_task = asyncio.create_task(idle_task())

    async def start_empty_vc_timer(self, voice_channel):
        """
        Leave VC if 60s no users inside VC.
        """
        if self.empty_vc_disconnect_task:
            self.empty_vc_disconnect_task.cancel()

        async def empty_task():
            try:
                await asyncio.sleep(60)
                members = [m for m in voice_channel.members if not m.bot]
                if len(members) == 0 and self.vc and self.vc.is_connected():
                    await self.vc.disconnect()
                    self.vc = None
                    self.is_playing = False
            except asyncio.CancelledError:
                pass

        self.empty_vc_disconnect_task = asyncio.create_task(empty_task())

    # ======================================================
    # VOICE STATE LISTENER (DETECT EMPTY VC)
    # ======================================================

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not self.vc or not self.vc.channel:
            return

        vc = self.vc.channel

        if before.channel == vc or after.channel == vc:
            members = [m for m in vc.members if not m.bot]
            if len(members) == 0:
                await self.start_empty_vc_timer(vc)
            else:
                if self.empty_vc_disconnect_task:
                    self.empty_vc_disconnect_task.cancel()
                    self.empty_vc_disconnect_task = None

    # ======================================================
    # COMMAND: PLAY
    # ======================================================

    @commands.command(name="play", aliases=["p"])
    async def play_cmd(self, ctx, *, query):
        if ctx.author.voice is None:
            return await ctx.send("🔊 Join VC dulu.")

        vc = ctx.author.voice.channel

        # Spotify link
        if "open.spotify.com" in query:
            tracks = await self.handle_spotify(query)
            if not tracks:
                return await ctx.send("❌ Tidak bisa ambil lagu dari Spotify.")

            first_play = False
            for t in tracks:
                song = self.search_yt(t)
                if song:
                    self.music_queue.append([song, vc])
                    if not self.is_playing and not first_play:
                        await self.play_music()
                        first_play = True
            return await ctx.send(f"🎧 Menambahkan **{len(tracks)}** lagu ke queue.")

        # YouTube search
        song = self.search_yt(query)
        if not song:
            return await ctx.send("❌ Lagu tidak ditemukan.")

        self.music_queue.append([song, vc])
        # Jika user tambah lagu, autoplay dimatikan agar tidak bentrok
        if self.autoplay:
            self.autoplay = False
            await ctx.send("⏹ Autoplay dimatikan karena kamu menambahkan lagu manual.")

        if not self.is_playing:
            await self.play_music()

        await ctx.send(f"🎵 Ditambahkan: **{song['title']}**")

    # ======================================================
    # COMMAND: SKIP
    # ======================================================

    @commands.command(name="skip", aliases=["s", "next"])
    async def skip_cmd(self, ctx):
        if not self.vc or not self.vc.is_playing():
            return await ctx.send("❌ Tidak ada lagu.")

        self.vc.stop()
        await ctx.send("⏭️ Skip.")

    # ======================================================
    # COMMAND: QUEUE AND LOOP
    # ======================================================

    @commands.command(name="queue", aliases=["q"])
    async def queue_cmd(self, ctx):
        if not self.current_song and len(self.music_queue)==0:
            return await ctx.send("📭 Queue kosong.")

        embed = discord.Embed(
            title="🎶 Music Queue",
            color=discord.Color.blurple()
        )

        if self.current_song:
            embed.add_field(
                name="▶️ Now Playing",
                value=f"**{self.current_song['title']}**",
                inline=False
            )

        if len(self.music_queue) > 0:
            desc = ""
            for i,(song,_) in enumerate(self.music_queue[:15], start=1):
                desc += f"**{i}.** {song['title']}\n"
            embed.add_field(
                name="🎵 Next Up",
                value=desc,
                inline=False
            )

        loop_status = self.loop_mode or "off"
        autoplay_status = "on" if self.autoplay else "off"
        embed.set_footer(
            text=f"Total: {len(self.music_queue)} songs • Loop: {loop_status} • Autoplay: {autoplay_status}"
        )


        await ctx.send(embed=embed)

    @commands.command(name="loop")
    async def loop_cmd(self, ctx, mode=None):
        valid_modes = ["single", "queue", "off"]

        if mode not in valid_modes:
            embed = discord.Embed(
                title="🔁 Pengaturan Loop",
                description="Pilih mode loop:",
                color=discord.Color.orange()
            )
            embed.add_field(
                name="`loop single`",
                value="Ulangi lagu yang **sedang diputar** terus-menerus.",
                inline=False
            )
            embed.add_field(
                name="`loop queue`",
                value="Ulangi **seluruh queue** dari awal lagi setelah selesai.",
                inline=False
            )
            embed.add_field(
                name="`loop off`",
                value="Matikan semua loop.",
                inline=False
            )

            current = self.loop_mode or "off"
            embed.set_footer(text=f"Current loop mode: {current}")
            return await ctx.send(embed=embed)

        # Set mode
        if mode == "off":
            self.loop_mode = None
            status = "off"
        else:
            self.loop_mode = mode
            status = mode

        embed = discord.Embed(
            title="🔁 Loop Updated",
            description=f"Loop mode sekarang: **{status}**",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)


    # ======================================================
    # COMMAND: SHUFFLE
    # ======================================================
    @commands.command(name="shuffle")
    async def shuffle_cmd(self, ctx):
        if len(self.music_queue) < 2:
            return await ctx.send("🔀 Queue kurang dari 2 lagu.")

        random.shuffle(self.music_queue)
        await ctx.send("🔀 Queue di-shuffle!")


    # ======================================================
    # COMMAND: VOLUME
    # ======================================================

    @commands.command(name="volume", aliases=["vol"])
    async def volume_cmd(self, ctx, vol: int = None):
        if vol is None:
            return await ctx.send(f"🔊 Volume sekarang: **{int(self.volume * 100)}%**")

        if vol < 1 or vol > 200:
            return await ctx.send("❌ Volume harus 1–200%")

        self.volume = vol / 100

        await ctx.send(f"🔊 Volume diubah ke **{vol}%**")

        # Refresh audio jika sedang bermain / dijeda
        if self.vc and (self.vc.is_playing() or self.vc.is_paused()):
            await self.refresh_current()

    # ======================================================
    # COMMAND: BASSBOOST
    # ======================================================

    @commands.command(name="bass", aliases=["bassboost"])
    async def bass_cmd(self, ctx, level=None):
        valid = ["off", "low", "medium", "high", "insane"]

        if level not in valid:
            return await ctx.send(
                "🎚 BassBoost:\n"
                "`bass off`\n"
                "`bass low`\n"
                "`bass medium`\n"
                "`bass high`\n"
                "`bass insane`"
            )

        if level == "off":
            self.bassboost_level = None
            msg = "BassBoost dimatikan."
        else:
            self.bassboost_level = level
            msg = f"BassBoost diatur ke **{level.upper()}**"

        await ctx.send(msg)

        # sama seperti volume: refresh lagu yg lagi diputar
        if self.vc and (self.vc.is_playing() or self.vc.is_paused()):
            await self.refresh_current()

    # ======================================================
    # COMMAND: DISCONNECT
    # ======================================================

    @commands.command(name="disconnect", aliases=["dc", "stop", "leave"])
    async def dc_cmd(self, ctx):
        if not self.vc or not self.vc.is_connected():
            return await ctx.send("❌ Bot tidak sedang di VC.")

        await self.vc.disconnect()
        self.vc = None
        self.is_playing = False
        self.music_queue.clear()

        await ctx.send("👋 Bot keluar dari VC.")

    # ======================================================
    # COMMAND: SONG (FIND BY LYRICS)
    # ======================================================

    @commands.command(name="song")
    async def song_cmd(self, ctx, *, lyrics: str = None):
        if not lyrics:
            return await ctx.send("❗ Berikan potongan liriknya.")

        await ctx.send("🔎 Mencari lagu...")

        api_key = os.getenv("AUDD_API_KEY")
        params = {"q": lyrics, "api_token": api_key}

        try:
            res = requests.get("https://api.audd.io/findLyrics/", params=params)
            data = res.json()
        except Exception:
            return await ctx.send("❌ Error memanggil API.")

        if not data.get("result"):
            return await ctx.send("❌ Lagu tidak ditemukan.")

        first = data["result"][0]
        title = first.get("title", "Unknown")
        artist = first.get("artist", "Unknown")

        await ctx.send(f"🎵 Dugaan lagu:\n**{title} – {artist}**")

    # ======================================================
    # COMMAND: LYRICS
    # ======================================================

    @commands.command(name="lyrics")
    async def lyrics_cmd(self, ctx, *, title=None):
        if not title:
            return await ctx.send("❗ Berikan judul lagu.")

        await ctx.send("🔎 Mengambil lirik...")

        params = {"q": title, "api_token": os.getenv("AUDD_API_KEY")}

        try:
            res = requests.get("https://api.audd.io/lyrics/", params=params)
            data = res.json()
        except:
            return await ctx.send("❌ API error.")

        if not data.get("result"):
            return await ctx.send("❌ Lirik tidak ditemukan.")

        lyrics = data["result"].get("lyrics", "Tidak tersedia.")

        if len(lyrics) > 1800:
            lyrics = lyrics[:1800] + "\n...(terpotong)"

        await ctx.send(f"🎶 **{title}**\n\n{lyrics}")

    # ======================================================
    # COMMAND: SET MUSIC CHANNEL
    # ======================================================

    @commands.command(name="setchmusic", aliases=["setchannel"])
    async def setch_cmd(self, ctx, channel: discord.TextChannel):
        guild_id = str(ctx.guild.id)
        channel_id = str(channel.id)

        set_channel_settings(self.db, guild_id, "music", channel_id)

        if guild_id not in self.channel_settings:
            self.channel_settings[guild_id] = {}

        self.channel_settings[guild_id]["music"] = channel_id

        await ctx.send(f"✅ Channel musik diatur ke {channel.mention}")

    # ======================================================
    # SEND EMBED TO MUSIC CHANNEL
    # ======================================================

    async def send_to_music_channel(self, guild, embed, view=None):
        gid = str(guild.id)
        print("[DEBUG SEND]", self.channel_settings)
        ch_id = self.channel_settings.get(gid, {}).get("music")

        # fallback jika belum diset
        if not ch_id:
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).send_messages:
                    return await ch.send(embed=embed, view=view)
            return

        target = guild.get_channel(int(ch_id))
        if target:
            try:
                return await target.send(embed=embed, view=view)
            except:
                pass


    # ======================================================
    # COG SETUP
    # ======================================================

def setup(bot):
    bot.add_cog(music_cog(bot))
