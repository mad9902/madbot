import discord
from discord.ext import commands
import yt_dlp
import os
import asyncio
import mimetypes
import glob
import shutil
import requests
import re
import logging
import subprocess
import uuid

logger = logging.getLogger('link_cog')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
formatter = logging.Formatter('[%(levelname)s] %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

INSTAGRAM_RE = re.compile(r"https?://(?:www\.)?(?:instagram\.com|instagr\.am|l\.instagram\.com)/\S+")
TIKTOK_RE = re.compile(r"https?://(?:www\.)?(?:tiktok\.com|vt\.tiktok\.com)/\S+")
YOUTUBE_SHORTS_RE = re.compile(r"https?://(?:www\.)?youtube\.com/shorts/\S+")

class link_cog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Folder khusus file sampah (download, attachment, convert)
        self.temp_folder = 'temp_files'
        os.makedirs(self.temp_folder, exist_ok=True)

        # Bersihkan temp setiap start
        for f in os.listdir(self.temp_folder):
            try:
                os.remove(os.path.join(self.temp_folder, f))
            except:
                pass

        logger.info(f"Temp folder tersedia: {self.temp_folder}")

    # ============================================================
    # Utility: Clear temp folder
    # ============================================================
    def clear_temp(self):
        for f in glob.glob(os.path.join(self.temp_folder, '*')):
            try:
                os.remove(f)
            except Exception as e:
                logger.error(f"Gagal hapus {f}: {e}")

    # Alias lama agar tetap backward compatible
    def clean_media_folder(self):
        return self.clear_temp()


    def convert_to_mp3(self, video_path):
        mp3_path = os.path.join(self.temp_folder, f"{uuid.uuid4().hex}.mp3")
        try:
            subprocess.run([
                'ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-ab', '192k', '-ar', '44100', mp3_path
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return mp3_path
        except Exception as e:
            logger.error(f"Gagal konversi ke MP3: {e}")
            return None

    def compress_video(self, input_path):
        output_path = os.path.join(self.temp_folder, f"{uuid.uuid4().hex}.mp4")
        try:
            subprocess.run([
                'ffmpeg', '-i', input_path, '-vcodec', 'libx264', '-crf', '28', '-preset', 'fast', output_path
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return output_path
        except Exception as e:
            logger.error(f"Gagal kompres video: {e}")
            return None

    # ============================================================
    # Download via yt-dlp
    # ============================================================
    def download_media_yt_dlp(self, url, audio_only=False):
        self.clear_temp()

        if url.startswith("mmp3 "):
            url = url.replace("mmp3 ", "", 1).strip()

        ydl_opts = {
            'outtmpl': os.path.join(self.temp_folder, '%(id)s.%(ext)s'),
            'quiet': True,
            'noplaylist': True,
            'no_warnings': True,
            'ignoreerrors': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
            }
        }

        if audio_only:
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        else:
            ydl_opts['format'] = 'bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4][vcodec^=avc1]/best'
            ydl_opts['merge_output_format'] = 'mp4'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return None
            except Exception as e:
                logger.error(f"DownloadError: {e}")
                return None

        files = glob.glob(os.path.join(self.temp_folder, '*'))
        if not files:
            return None

        latest_file = max(files, key=os.path.getctime)
        logger.info(f"File hasil download: {latest_file}")
        return latest_file

    # ============================================================
    # Event Listener
    # ============================================================
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if message.content.startswith("m"):
            return

        content = message.content.lower()

        if INSTAGRAM_RE.search(content) or TIKTOK_RE.search(content) or YOUTUBE_SHORTS_RE.search(content):
            await message.channel.typing()
            try:
                loop = asyncio.get_running_loop()
                file_path = await loop.run_in_executor(None, self.download_media_yt_dlp, message.content, False)

                if not file_path:
                    await message.channel.send("Gagal mengunduh video.")
                    return

                if not file_path.lower().endswith(('.mp4', '.mov', '.webm', '.mkv')):
                    os.remove(file_path)
                    await message.channel.send("File yang didownload bukan video.")
                    return

                size_mb = os.path.getsize(file_path) / (1024 * 1024)
                if size_mb > 8:
                    compressed = self.compress_video(file_path)
                    if compressed and os.path.getsize(compressed) < 8 * 1024 * 1024:
                        await message.channel.send(file=discord.File(compressed, filename="video_compressed.mp4"))
                        os.remove(compressed)
                    else:
                        await message.channel.send(f"File terlalu besar ({size_mb:.2f} MB)")
                    os.remove(file_path)
                    return

                await message.channel.send(file=discord.File(file_path, filename="video.mp4"))
                os.remove(file_path)

            except Exception as e:
                logger.error(f"Error saat proses video: {e}")
                await message.channel.send("Gagal memproses video.")

    # ============================================================
    # GIF Command
    # ============================================================
    @commands.command(name="gif")
    async def gif_command(self, ctx, *, url: str = None):
        await ctx.typing()
        try:
            video_path = None

            if url and (url.startswith("http://") or url.startswith("https://")):
                loop = asyncio.get_running_loop()
                video_path = await loop.run_in_executor(None, self.download_media_yt_dlp, url, False)

            elif ctx.message.reference:
                try:
                    replied = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                    for attachment in replied.attachments:
                        if attachment.filename.lower().endswith(('.mp4', '.mov', '.webm', '.mkv')):
                            unique_name = f"{uuid.uuid4().hex}_{attachment.filename}"
                            video_path = os.path.join('temp_files', unique_name)
                            await attachment.save(video_path)
                            break
                except Exception as e:
                    logger.warning(f"Gagal ambil pesan reply: {e}")

            if not video_path or not os.path.exists(video_path):
                await ctx.send("Video tidak ditemukan atau format tidak didukung.", delete_after=5)
                return

            gif_path = self.convert_to_gif(video_path)
            if gif_path and os.path.getsize(gif_path) < 8 * 1024 * 1024:
                await ctx.send(file=discord.File(gif_path, filename="output.gif"))
                self.clear_temp()
            else:
                await ctx.send("Gagal membuat GIF atau ukuran terlalu besar.", delete_after=5)

            os.remove(video_path)
            if gif_path and os.path.exists(gif_path):
                os.remove(gif_path)
                self.clear_temp()

        except Exception as e:
            logger.error(f"Gagal proses GIF: {e}")
            await ctx.send("Terjadi kesalahan saat membuat GIF.", delete_after=5)



    @commands.command(name="mp3")
    async def mp3_command(self, ctx, *, url: str = None):
        if url and url.startswith("mmp3 "):
            url = url.replace("mmp3 ", "", 1).strip()

        await ctx.send("Mengambil audio...", delete_after=5)
        await ctx.typing()

        try:
            if url:
                if not url.startswith("http://") and not url.startswith("https://"):
                    await ctx.send("Link tidak valid. Harap mulai dengan http:// atau https://", delete_after=5)
                    return

                loop = asyncio.get_running_loop()
                file_path = await loop.run_in_executor(None, self.download_media_yt_dlp, url, True)

                if not file_path or not os.path.exists(file_path) or os.path.getsize(file_path) < 1024:
                    await ctx.send("Gagal mengambil audio dari link.", delete_after=5)
                    return

                if not file_path.endswith(".mp3"):
                    new_path = file_path + ".mp3"
                    os.rename(file_path, new_path)
                    file_path = new_path

                await ctx.send(file=discord.File(file_path, filename="audio.mp3"))
                os.remove(file_path)
                self.clear_temp()

            elif ctx.message.attachments:
                for attachment in ctx.message.attachments:
                    if attachment.filename.lower().endswith(('.mp4', '.mov', '.webm', '.mkv')):
                        unique_name = f"{uuid.uuid4().hex}_{attachment.filename}"
                        video_path = os.path.join(self.temp_folder, unique_name)
                        await attachment.save(video_path)
                        mp3_path = self.convert_to_mp3(video_path)
                        if mp3_path:
                            await ctx.send(file=discord.File(mp3_path, filename="audio.mp3"))
                            os.remove(mp3_path)
                            self.clear_temp()
                        os.remove(video_path)
                        return

                await ctx.send("Tidak ada video yang dilampirkan.", delete_after=5)
            else:
                await ctx.send("Berikan link atau lampiran video untuk dikonversi.", delete_after=5)

        except Exception as e:
            logger.error(f"Gagal proses audio: {e}")
            await ctx.send("Gagal memproses audio.", delete_after=5)

    @commands.command(name="tts")
    async def voice_command(self, ctx, *, text: str):
        await ctx.typing()

        api_key = os.getenv("ELEVEN_API_KEY")
        if not api_key:
            await ctx.send("API key ElevenLabs belum disetel di environment.", delete_after=5)
            return

        voice_id = "TxGEqnHWrfWFTfGW9XjX"  # Antoni
        output_path = os.path.join('temp_files', f"{uuid.uuid4().hex}.mp3")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }

        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }

        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(response.content)

            await ctx.send(file=discord.File(output_path, filename="tts.mp3"))
            os.remove(output_path)
            self.clear_temp()

        except Exception as e:
            logger.error(f"Gagal buat TTS ElevenLabs: {e}")
            await ctx.send("Gagal membuat suara dari ElevenLabs.", delete_after=5)

async def setup(bot):
    await bot.add_cog(link_cog(bot))
