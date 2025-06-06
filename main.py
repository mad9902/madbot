import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio

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

# Optional: Error handler global
@bot.event
async def on_command_error(ctx, error):
    print(f"[ERROR] Di command {ctx.command}: {error}")
    await ctx.send(f"❌ Terjadi error: {str(error)}")

# Fungsi utama
async def main():
    # Hapus default help command
    bot.remove_command('help')

    # @bot.event
    # async def on_command_error(ctx, error):
    #     print(f"Error di command {ctx.command}: {error}")
    #     await ctx.send(f"Terjadi error: {error}")


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
