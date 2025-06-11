import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
from rapidfuzz import process, fuzz


# Database dan migrasi
from database import connect_db, ensure_database_exists
from migration import migrate

# Import semua cog
from main_cog import main_cog
from image_cog import image_cog
from music_cog import music_cog
from link_cog import link_cog
from ai_cog import GeminiCog
from level_cog import LevelCog
from game_cog import SambungKataMultiplayer


# Load env
load_dotenv()

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # diperlukan untuk akses member dan role

# Prefix
def get_prefix(bot, message):
    return ['mad ', 'md ', 'm']

# Inisialisasi bot
bot = commands.Bot(command_prefix=get_prefix, intents=intents)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        attempted = ctx.message.content[len(ctx.prefix):].split()[0]
        command_names = [command.name for command in bot.commands]

        result = process.extractOne(
            attempted,
            command_names,
            scorer=fuzz.ratio
        )

        if result is not None:
            match, score, _ = result
            if score >= 70:
                await ctx.reply(f"❓ Apakah maksudmu `m{match}`?", delete_after=5)
                return
    else:
        await ctx.send(f"❌ Terjadi error: {error}", delete_after=5)

# Fungsi utama
async def main():
    # Hapus default help command
    bot.remove_command('help')

    # Setup database
    ensure_database_exists()
    bot.db = connect_db()
    migrate(bot.db)

    # Tambahkan semua cog
    await bot.add_cog(main_cog(bot))
    await bot.add_cog(image_cog(bot))
    await bot.add_cog(music_cog(bot))
    await bot.add_cog(link_cog(bot))
    await bot.add_cog(LevelCog(bot))
    await bot.add_cog(GeminiCog(bot))
    await bot.add_cog(SambungKataMultiplayer(bot))  # ✅ harus pakai await!

    # Jalankan bot
    await bot.start(os.getenv("TOKEN"))

# Jalankan event loop utama
asyncio.run(main())
