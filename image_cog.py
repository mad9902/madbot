import discord
from discord.ext import commands
from PIL import Image, ImageOps
import io
import aiohttp
import os
import shutil
import aiohttp
from dotenv import load_dotenv

load_dotenv()
IMGUR_CLIENT_ID = os.getenv("IMGUR_CLIENT_ID")


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

    @commands.command(name="avatar", help="Menampilkan avatar user dengan background")
    async def avatar(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        avatar_url = member.display_avatar.with_size(256).with_static_format('png').url

        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as resp:
                if resp.status != 200:
                    await ctx.send("Gagal mengambil avatar.")
                    return
                avatar_bytes = await resp.read()

        avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")

        bg = Image.open("background.png").convert("RGBA")

        avatar_img = ImageOps.fit(avatar_img, (128, 128), method=Image.LANCZOS)

        bg_w, bg_h = bg.size
        avatar_pos = ((bg_w - 128) // 2, (bg_h - 128) // 2)
        bg.paste(avatar_img, avatar_pos, avatar_img)

        with io.BytesIO() as image_binary:
            bg.save(image_binary, "PNG")
            image_binary.seek(0)
            await ctx.send(file=discord.File(fp=image_binary, filename="avatar.png"))


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



    @commands.command(name="sticker", help="Download sticker dari ID")
    async def sticker(self, ctx, sticker_id: int):
        url_png = f"https://cdn.discordapp.com/stickers/{sticker_id}.png"
        url_gif = f"https://cdn.discordapp.com/stickers/{sticker_id}.gif"

        path = None
        async with aiohttp.ClientSession() as session:
            for url in [url_gif, url_png]:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        ext = url.split('.')[-1]
                        filename = f"sticker_{sticker_id}.{ext}"
                        path = os.path.join(self.download_folder, filename)
                        data = await resp.read()
                        with open(path, 'wb') as f:
                            f.write(data)
                        break

        if path:
            await ctx.send(file=discord.File(path))
        else:
            await ctx.send("Gagal mendownload sticker dengan ID tersebut.")


