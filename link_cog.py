import discord
from discord.ext import commands
import yt_dlp
import os
import asyncio
import mimetypes
import glob
import instaloader
import shutil
import re
import requests
import logging


logger = logging.getLogger()

INSTAGRAM_POST_RE = re.compile(r"(https?://(?:www\.)?instagram\.com/(?:p|reel)/([A-Za-z0-9_-]+)/?)")

class link_cog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.media_folder = 'media'
        if not os.path.exists(self.media_folder):
            os.makedirs(self.media_folder)

        self.clean_media_folder()

        self.insta_user = os.getenv('INSTA_USER')
        self.insta_pass = os.getenv('INSTA_PASS')

        if not self.insta_user:
            self.L = None
            return

        self.L = instaloader.Instaloader(
            download_videos=True,
            download_pictures=True,
            save_metadata=False,
            quiet=True
        )

        session_folder = os.path.join(os.getcwd(), "insta_sessions")
        os.makedirs(session_folder, exist_ok=True)

        self.session_file = os.path.join(session_folder, f"{self.insta_user}.session")

        try:
            if os.path.exists(self.session_file):
                self.L.load_session_from_file(self.insta_user, self.session_file)
            elif self.insta_pass:
                self.L.login(self.insta_user, self.insta_pass)
                self.L.save_session_to_file(filename=self.session_file)
            else:
                self.L = None
        except Exception as e:
            self.L = None

    def clean_media_folder(self):
        files = glob.glob(os.path.join(self.media_folder, '*'))
        for f in files:
            try:
                if os.path.isfile(f):
                    os.remove(f)
                elif os.path.isdir(f):
                    shutil.rmtree(f)
            except Exception as e:
                logger.error(f"Gagal hapus {f}: {e}")

    def download_instagram_post(self, url):
        if not self.L:
            raise Exception("Instaloader belum terinisialisasi (gagal login).")

        match = INSTAGRAM_POST_RE.search(url)
        if not match:
            raise Exception("URL Instagram tidak valid atau shortcode tidak ditemukan.")
        shortcode = match.group(2)

        post = instaloader.Post.from_shortcode(self.L.context, shortcode)
        target_folder = os.path.join(self.media_folder, shortcode)
        if not os.path.exists(target_folder):
            os.makedirs(target_folder)

        if post.typename == 'GraphSidecar':
            nodes = list(post.get_sidecar_nodes())
            for idx, node in enumerate(nodes):
                if node.is_video:
                    media_url = node.video_url
                    ext = '.mp4'
                else:
                    media_url = node.display_url
                    ext = '.jpg'

                filename = os.path.join(target_folder, f"{shortcode}_{idx}{ext}")

                r = requests.get(media_url, stream=True)
                if r.status_code == 200:
                    with open(filename, 'wb') as f:
                        for chunk in r.iter_content(1024):
                            f.write(chunk)
                else:
                    logger.error(f"Gagal download media {idx} dari carousel, status code: {r.status_code}")
        else:
            if post.is_video:
                media_url = post.video_url
                ext = '.mp4'
            else:
                media_url = post.url
                ext = '.jpg'
            filename = os.path.join(target_folder, shortcode + ext)

            r = requests.get(media_url, stream=True)
            if r.status_code == 200:
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(1024):
                        f.write(chunk)
            else:
                raise Exception(f"Gagal download media, status code {r.status_code}")

        files = os.listdir(target_folder)
        if files:
            return os.path.join(target_folder, files[0])
        else:
            raise FileNotFoundError("Media tidak ditemukan setelah download.")

    def download_media_yt_dlp(self, url):
        self.clean_media_folder()
        ydl_opts = {
            'outtmpl': os.path.join(self.media_folder, '%(id)s.%(ext)s'),
            'format': 'best',
            'quiet': False,  # Tampilkan log yt_dlp di console VPS
            'noplaylist': True,
            'no_warnings': False,
            'ignoreerrors': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise FileNotFoundError("Info media tidak didapatkan.")

        files = glob.glob(os.path.join(self.media_folder, '*'))
        if not files:
            raise FileNotFoundError("File hasil download tidak ditemukan.")

        latest_file = max(files, key=os.path.getctime)
        return latest_file

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        content = message.content.lower()

        if "instagram.com/p/" in content or "instagram.com/reel/" in content:
            if not self.L:
                await message.channel.send("Instagram session belum siap, coba lagi nanti.")
                return

            match = INSTAGRAM_POST_RE.search(message.content)
            if not match:
                await message.channel.send("URL Instagram tidak valid atau tidak ditemukan.")
                return

            url = match.group(1)
            shortcode = match.group(2)

            await message.channel.typing()
            try:
                loop = asyncio.get_running_loop()
                file_path = await loop.run_in_executor(None, self.download_instagram_post, url)


                mime, _ = mimetypes.guess_type(file_path)
                if not mime or not mime.startswith(('image', 'video')):
                    await message.channel.send("Jenis file tidak dikenali.")
                    return

                size_mb = os.path.getsize(file_path) / (1024 * 1024)
                if size_mb > 8:
                    await message.channel.send(f"File terlalu besar untuk diupload ke Discord (max 8MB). Ukuran file: {size_mb:.2f} MB")
                    return

                await message.channel.send(file=discord.File(file_path))

                try:
                    os.remove(file_path)
                    os.rmdir(os.path.dirname(file_path))
                except Exception as e:
                    logger.error(f"Gagal hapus file/folder setelah upload: {e}")

            except Exception as e:
                await message.channel.send("Gagal mengambil media dari Instagram.")

        elif "tiktok.com" in content:
            await message.channel.typing()
            try:
                loop = asyncio.get_running_loop()
                file_path = await loop.run_in_executor(None, self.download_media_yt_dlp, message.content)


                mime, _ = mimetypes.guess_type(file_path)
                if not mime or not mime.startswith(('image', 'video')):
                    await message.channel.send("Jenis file tidak dikenali.")
                    return

                size_mb = os.path.getsize(file_path) / (1024 * 1024)
                if size_mb > 8:
                    await message.channel.send(f"File terlalu besar untuk diupload ke Discord (max 8MB). Ukuran file: {size_mb:.2f} MB")
                    return

                await message.channel.send(file=discord.File(file_path))
                os.remove(file_path)
            except Exception as e:
                await message.channel.send("Gagal mengambil media dari TikTok.")
                logger.error(f"Gagal download TikTok media: {e}")

async def setup(bot):
    await bot.add_cog(link_cog(bot))
