import discord
from discord.ext import commands
import yt_dlp
import os
import asyncio
import mimetypes
import glob
import shutil
import re
import logging

logger = logging.getLogger('link_cog')
logger.setLevel(logging.DEBUG)  # atur sesuai kebutuhan
ch = logging.StreamHandler()
formatter = logging.Formatter('[%(levelname)s] %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

INSTAGRAM_RE = re.compile(r"(https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[A-Za-z0-9_-]+/?)+")
TIKTOK_RE = re.compile(r"(https?://(?:www\.)?tiktok\.com/[^\s]+)")

class link_cog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.media_folder = 'media'
        if not os.path.exists(self.media_folder):
            os.makedirs(self.media_folder)
            logger.info(f"Folder media dibuat: {self.media_folder}")

    def clean_media_folder(self):
        files = glob.glob(os.path.join(self.media_folder, '*'))
        for f in files:
            try:
                if os.path.isfile(f):
                    os.remove(f)
                    logger.debug(f"File dihapus: {f}")
                elif os.path.isdir(f):
                    shutil.rmtree(f)
                    logger.debug(f"Folder dihapus: {f}")
            except Exception as e:
                logger.error(f"Gagal hapus {f}: {e}")

    def download_media_yt_dlp(self, url):
        self.clean_media_folder()
        ydl_opts = {
            'outtmpl': os.path.join(self.media_folder, '%(id)s.%(ext)s'),
            'format': 'bestvideo+bestaudio/best',
            'quiet': True,
            'noplaylist': True,
            'no_warnings': True,
            'ignoreerrors': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise FileNotFoundError("Info media tidak didapatkan.")
            except yt_dlp.utils.DownloadError as e:
                err_msg = str(e)
                if "There is no video in this post" in err_msg:
                    logger.warning(f"Tidak ada video di post Instagram: {url}")
                    return None
                else:
                    raise
        # Cari file hasil download
        files = glob.glob(os.path.join(self.media_folder, '*'))
        if not files:
            raise FileNotFoundError("File hasil download tidak ditemukan.")

        latest_file = max(files, key=os.path.getctime)
        logger.info(f"File terbaru hasil download yt_dlp: {latest_file}")
        return latest_file

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        content = message.content.lower()

        if INSTAGRAM_RE.search(content) or TIKTOK_RE.search(content):
            await message.channel.typing()
            try:
                loop = asyncio.get_running_loop()
                file_path = await loop.run_in_executor(None, self.download_media_yt_dlp, message.content)

                if file_path is None:
                    logger.info("Media pada link tersebut bukan video, jadi tidak bisa dikirim.") 
                    return

                mime, _ = mimetypes.guess_type(file_path)
                if not mime or not mime.startswith('video'):
                    logger.info(f"File yang didownload bukan video, diabaikan: {file_path} dengan MIME {mime}")
                    os.remove(file_path)
                       
                    return

                size_mb = os.path.getsize(file_path) / (1024 * 1024)
                if size_mb > 8:
                    await message.channel.send(f"File terlalu besar untuk diupload ke Discord (max 8MB). Ukuran file: {size_mb:.2f} MB")
                    logger.error(f"File terlalu besar untuk upload: {file_path}, ukuran {size_mb:.2f} MB")
                    try:
                        os.remove(file_path)
                        logger.debug("File besar dihapus setelah dicek.")
                    except Exception as e:
                        logger.error(f"Gagal hapus file besar: {e}")
                    return

                await message.channel.send(file=discord.File(file_path))

                try:
                    os.remove(file_path)
                    logger.debug("File hasil download berhasil dihapus setelah upload.")
                except Exception as e:
                    logger.error(f"Gagal hapus file setelah upload: {e}")

            except Exception as e:
                await message.channel.send("Gagal mengambil media dari link.")
                logger.error(f"Gagal download media dengan yt_dlp: {e}")

async def setup(bot):
    await bot.add_cog(link_cog(bot))
