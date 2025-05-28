import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
from database import connect_db, ensure_database_exists  
from migration import migrate  # import fungsi migration

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # perlu untuk assign role

from main_cog import main_cog
from image_cog import image_cog
from music_cog import music_cog
from link_cog import link_cog
from level_cog import LevelCog

def get_prefix(bot, message):
    return ['mad ', 'md ', 'm']

bot = commands.Bot(command_prefix=get_prefix, intents=intents)


async def main():
    bot.remove_command('help')
    ensure_database_exists()
    bot.db = connect_db()

    # Panggil migration supaya tabel dibuat jika belum ada
    migrate(bot.db)

    await bot.add_cog(main_cog(bot))
    await bot.add_cog(image_cog(bot))
    await bot.add_cog(music_cog(bot))
    await bot.add_cog(link_cog(bot))
    await bot.add_cog(LevelCog(bot))

    await bot.start(os.getenv("TOKEN"))

asyncio.run(main())
