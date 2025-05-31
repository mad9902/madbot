import discord
from discord.ext import commands
from PIL import Image, ImageOps
import subprocess
from bs4 import BeautifulSoup
import io
import aiohttp
import os
import shutil
import re
import aiohttp
from dotenv import load_dotenv

load_dotenv()
IMGUR_CLIENT_ID = os.getenv("IMGUR_CLIENT_ID")

def guess_ext_from_bytes(data: bytes) -> str:
        if data.startswith(b'GIF87a') or data.startswith(b'GIF89a'):
            return "gif"
        if data.startswith(b'RIFF') and data[8:12] == b'WEBP':
            return "webp"
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            return "png"
        return "bin"

def sanitize_filename(name: str) -> str:
    # Ganti karakter ilegal Windows dengan underscore
    return re.sub(r'[<>:"/\\|?*]', '_', name)

class image_cog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.download_folder = 'downloads'

        if not os.path.exists(self.download_folder):
            os.makedirs(self.download_folder)

        self.clear_folder()

    def clear_folder(self):
        for filename in os.listdir(self.download_folder):
            file_path = os.path.join(self.download_folder, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'Gagal hapus {file_path}. Alasan: {e}')

    async def upload_to_imgur(self, image_path):
        headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}
        url = "https://api.imgur.com/3/image"

        # baca file sebagai bytes untuk upload multipart/form-data
        with open(image_path, 'rb') as img:
            img_bytes = img.read()

        # untuk aiohttp harus dikirim dalam data sebagai dict dengan key 'image'
        data = aiohttp.FormData()
        data.add_field('image', img_bytes)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as resp:
                if resp.status == 200:
                    json_resp = await resp.json()
                    image_id = json_resp['data']['id']
                    image_type = json_resp['data']['type'].split('/')[-1]
                    return f"https://i.imgur.com/{image_id}.{image_type}"
                else:
                    print(f"Imgur upload gagal, status: {resp.status}")
                    return None

    @commands.command(name="upload", help="Upload gambar dari attachment atau reply ke Imgur")
    async def upload(self, ctx):
        image = None

        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.content_type and "image" in attachment.content_type:
                image = attachment
        elif ctx.message.reference:
            replied = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if replied.attachments:
                attachment = replied.attachments[0]
                if attachment.content_type and "image" in attachment.content_type:
                    image = attachment

        if image is None:
            await ctx.send("❌ Tidak ada gambar yang bisa diupload. Kirim gambar atau reply ke gambar.")
            return

        filename = os.path.join(self.download_folder, image.filename)
        await image.save(fp=filename)

        link = await self.upload_to_imgur(filename)

        try:
            os.remove(filename)
        except Exception as e:
            print(f"Gagal hapus file sementara: {e}")

        if link:
            await ctx.send(f"✅ Gambar berhasil diupload ke Imgur:\n{link}")
        else:
            await ctx.send("❌ Gagal mengupload gambar ke Imgur.")

    @commands.command(name="avatar", help="Menampilkan avatar dan banner user (jika ada) dalam gaya profil Discord")
    async def avatar(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        user_id = member.id
        token = ctx.bot.http.token

        avatar_url = member.display_avatar.url
        username = f"{member.name}#{member.discriminator}"

        # Ambil banner user dari Discord API
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bot {token}"}
            async with session.get(f"https://discord.com/api/v10/users/{user_id}", headers=headers) as resp:
                if resp.status != 200:
                    await ctx.send("Gagal mengambil data user.")
                    return
                data = await resp.json()

        banner_hash = data.get("banner")

        embed = discord.Embed(
            title=username,
            description=f"ID: `{user_id}`\n\n\u200b",  # tambahkan newline + zero width space supaya ada spasi bawah
            color=discord.Color.blurple()
        )


        if banner_hash:
            ext = "gif" if banner_hash.startswith("a_") else "png"
            banner_url = f"https://cdn.discordapp.com/banners/{user_id}/{banner_hash}.{ext}?size=1024"
            embed.set_image(url=banner_url)
            embed.set_thumbnail(url=avatar_url)
        else:
            # Jika tidak ada banner, avatar jadi gambar utama
            embed.set_image(url=avatar_url)

        await ctx.send(embed=embed)


    @commands.command(name="emoji", help="Download emoji custom dengan ID atau mention")
    async def emoji(self, ctx, emoji_input: str):
        import re

        custom_emoji_match = re.match(r'<(a)?:\w+:(\d+)>', emoji_input)
        if custom_emoji_match:
            is_animated = custom_emoji_match.group(1) == 'a'
            emoji_id = custom_emoji_match.group(2)
        else:
            emoji_id = emoji_input
            is_animated = False 

        ext = 'gif' if is_animated else 'png'

        urls_to_try = [
            f"https://cdn.discordapp.com/emojis/{emoji_id}.gif",
            f"https://cdn.discordapp.com/emojis/{emoji_id}.png"
        ]

        path = None
        async with aiohttp.ClientSession() as session:
            for url in urls_to_try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        ext = url.split('.')[-1]
                        filename = f"emoji_{emoji_id}.{ext}"
                        path = os.path.join(self.download_folder, filename)
                        data = await resp.read()
                        with open(path, 'wb') as f:
                            f.write(data)
                        break

        if path:
            await ctx.send(file=discord.File(path))
        else:
            await ctx.send("Gagal mendownload emoji dengan ID tersebut.")


    @commands.command(name="sticker", help="Download sticker dari ID atau dari pesan yang di-reply")
    async def sticker(self, ctx, sticker_id: int = None):
        try:
            if sticker_id is None:
                if ctx.message.reference is None:
                    await ctx.send("❌ Mohon reply pesan yang ada sticker atau sertakan ID sticker.")
                    return
                replied_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                if not replied_msg.stickers:
                    await ctx.send("❌ Pesan yang direply tidak mengandung sticker.")
                    return
                sticker = replied_msg.stickers[0]  # ambil sticker pertama
                sticker_id = sticker.id

            await ctx.send(f"🔍 Mengambil data stiker untuk ID `{sticker_id}`...")

            token = self.bot.http.token
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bot {token}"}
                async with session.get(f"https://discord.com/api/v10/stickers/{sticker_id}", headers=headers) as resp:
                    print(f"[DEBUG] API sticker status: {resp.status}")
                    if resp.status != 200:
                        await ctx.send("❌ Gagal mengambil data stiker.")
                        return
                    data = await resp.json()
                    print(f"[DEBUG] Sticker API data: {data}")

                format_type = data.get("format_type")
                name = data.get("name", f"sticker_{sticker_id}")
                name = sanitize_filename(name)
                print(f"[DEBUG] format_type={format_type}, name={name}")

                if format_type == 3:
                    await ctx.send(
                        f"⚠️ Sticker **{name}** adalah animasi Lottie dan tidak bisa diunduh langsung.\n"
                        f"Lihat preview: https://discord.com/stickers/{sticker_id}"
                    )
                    return

                if format_type in [1, 2]:
                    ext = "png" if format_type == 1 else "apng"
                elif format_type == 4:
                    ext = "webp"
                else:
                    await ctx.send("❌ Format sticker tidak dikenali atau tidak didukung.")
                    return

                url = f"https://cdn.discordapp.com/stickers/{sticker_id}.{ext}"
                filename = f"{name}.{ext}"
                path = os.path.join(self.download_folder, filename)
                print(f"[DEBUG] Downloading sticker file from URL: {url}")

                async with session.get(url) as resp:
                    print(f"[DEBUG] CDN sticker file status: {resp.status}")
                    if resp.status == 200:
                        content = await resp.read()
                        with open(path, "wb") as f:
                            f.write(content)

                        print(f"[DEBUG] Sticker file saved to {path}")
                        await ctx.send(file=discord.File(path, filename=filename))
                        return
                    else:
                        preview_url = f"https://discord.com/stickers/{sticker_id}"
                        print(f"[DEBUG] CDN sticker file failed, trying preview page: {preview_url}")
                        async with session.get(preview_url) as preview_resp:
                            print(f"[DEBUG] Preview page status: {preview_resp.status}")

                            if preview_resp.status == 404:
                                await ctx.send("⚠️ Stiker APNG ini tidak tersedia untuk diunduh karena keterbatasan akses CDN Discord.")
                                return

                            elif preview_resp.status != 200:
                                await ctx.send("❌ Gagal mengambil halaman preview sticker.")
                                return

                            content_type = preview_resp.headers.get("content-type", "")
                            print(f"[DEBUG] Preview page content-type: {content_type}")

                            if content_type.startswith("text/html"):
                                html = await preview_resp.text()
                                soup = BeautifulSoup(html, "html.parser")
                                video_tag = soup.find("video")
                                if video_tag and video_tag.has_attr("src"):
                                    video_url = video_tag["src"]
                                    print(f"[DEBUG] Found video URL in preview page: {video_url}")
                                    ext_video = "gif" if video_url.lower().endswith(".gif") else "mp4"
                                    filename_video = f"{name}.{ext_video}"
                                    path_video = os.path.join(self.download_folder, filename_video)

                                    async with session.get(video_url) as video_resp:
                                        print(f"[DEBUG] Video file status: {video_resp.status}")
                                        if video_resp.status != 200:
                                            await ctx.send("❌ Gagal mengunduh file animasi dari preview.")
                                            return
                                        content = await video_resp.read()
                                        with open(path_video, "wb") as f:
                                            f.write(content)
                                    print(f"[DEBUG] Video file saved to {path_video}")
                                    await ctx.send(file=discord.File(path_video, filename=filename_video))
                                    return
                                else:
                                    await ctx.send(
                                        f"⚠️ Sticker **{name}** adalah animasi dan preview video tidak ditemukan.\n"
                                        f"Lihat preview: {preview_url}"
                                    )
                                    return
                            else:
                                content_bytes = await preview_resp.read()
                                print(f"[DEBUG] Preview non-HTML content bytes snippet: {content_bytes[:100]}")

                                # Fungsi ini harus kamu buat sendiri atau langsung pakai ekstensi default:
                                def guess_ext_from_bytes(data: bytes) -> str:
                                    # Contoh sederhana, kamu bisa kembangkan sesuai kebutuhan
                                    if data.startswith(b"\x89PNG"):
                                        return "png"
                                    elif data.startswith(b"GIF"):
                                        return "gif"
                                    elif data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
                                        return "webp"
                                    else:
                                        return "png"  # fallback

                                ext_real = guess_ext_from_bytes(content_bytes)
                                filename_real = f"{name}.{ext_real}"
                                path_real = os.path.join(self.download_folder, filename_real)
                                with open(path_real, "wb") as f:
                                    f.write(content_bytes)
                                print(f"[DEBUG] Non-HTML preview content saved to {path_real}")
                                await ctx.send(file=discord.File(path_real, filename=filename_real))
                                return

        except Exception as e:
            print(f"[ERROR] {e}")
            await ctx.send(f"❌ Terjadi kesalahan: `{e}`")






