import discord
from discord.ext import commands
import os, shutil, random
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

    import os
import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
IMGUR_CLIENT_ID = os.getenv("IMGUR_CLIENT_ID")

class image_cog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.download_folder = 'downloads'
        if not os.path.exists(self.download_folder):
            os.makedirs(self.download_folder)

    async def upload_to_imgur(self, image_path):
        headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}
        url = "https://api.imgur.com/3/image"

        with open(image_path, 'rb') as img:
            data = {'image': img.read()}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as resp:
                if resp.status == 200:
                    json_resp = await resp.json()
                    image_id = json_resp['data']['id']
                    image_type = json_resp['data']['type'].split('/')[-1]
                    return f"https://i.imgur.com/{image_id}.{image_type}"
                else:
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
        except:
            pass

        if link:
            await ctx.send(f"✅ Gambar berhasil diupload ke Imgur:\n{link}")
        else:
            await ctx.send("❌ Gagal mengupload gambar ke Imgur.")


    @commands.command(name="avatar", help="Menampilkan avatar dari user")
    async def avatar(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        avatar_url = member.display_avatar.url
        embed = discord.Embed(title=f"Avatar {member.display_name}")
        embed.set_image(url=avatar_url)
        await ctx.send(embed=embed)

    @commands.command(name="emoji", help="Download emoji sebagai gambar (custom atau unicode)")
    async def emoji(self, ctx, *, emoji_input: str):
        import re

        custom_emoji_match = re.match(r'<(a)?:\w+:(\d+)>', emoji_input)
        if custom_emoji_match:
            is_animated = custom_emoji_match.group(1) == 'a'
            emoji_id = custom_emoji_match.group(2)
            file_ext = 'gif' if is_animated else 'png'
            url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{file_ext}"
            filename = f"custom_{emoji_id}.{file_ext}"
        else:
            codepoints = '-'.join(f"{ord(c):x}" for c in emoji_input)
            url = f"https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/72x72/{codepoints}.png"
            filename = f"unicode_{codepoints}.png"

        path = os.path.join(self.download_folder, filename)

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    await ctx.send("Gagal mendownload emoji.")
                    return
                with open(path, 'wb') as f:
                    f.write(await resp.read())

        await ctx.send(file=discord.File(path))

    @commands.command(name="sticker", help="Download sticker dari pesan yang direply")
    async def sticker(self, ctx):
        if ctx.message.reference:
            replied = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            if replied.stickers:
                sticker = replied.stickers[0]
                filename = f"{sticker.name}.png"
                path = os.path.join(self.download_folder, filename)

                async with aiohttp.ClientSession() as session:
                    async with session.get(sticker.url) as resp:
                        if resp.status != 200:
                            await ctx.send("Gagal mendownload stiker.")
                            return
                        with open(path, 'wb') as f:
                            f.write(await resp.read())

                await ctx.send(file=discord.File(path))
            else:
                await ctx.send("Pesan yang direply tidak mengandung stiker.")
        else:
            await ctx.send("Reply pesan yang mengandung stiker untuk menggunakan perintah ini.")
