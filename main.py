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
from afk_cog import AFK
from birthday_cog import Birthday
from welcome_cog import WelcomeMessageConfig
from timedwords_cog import TimedWordsCog
from bannedwords_cog import BannedWordsCog
from bot_state import DISABLED_GUILDS, OWNER_ID

# Load .env
load_dotenv()

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

def get_prefix(bot, message):
    if message.guild and message.guild.id in DISABLED_GUILDS:
        if message.content.strip().lower().startswith(("mad boton", "md boton", "mboton")):
            return ['mad ', 'md ', 'm']
        return commands.when_mentioned(bot)
    return ['mad ', 'md ', 'm']

bot = commands.Bot(command_prefix=get_prefix, intents=intents)

@bot.check
async def block_disabled_guilds(ctx):
    if ctx.guild and ctx.guild.id in DISABLED_GUILDS:
        if ctx.command and ctx.command.name == "boton":
            return True
        return False
    return True

@bot.event
async def on_interaction(interaction):
    if interaction.guild and interaction.guild.id in DISABLED_GUILDS:
        await interaction.response.send_message("❌ Bot sedang nonaktif di server ini.", ephemeral=True)
        return
    await bot.process_application_commands(interaction)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        attempted = ctx.message.content[len(ctx.prefix):].split()[0]
        command_names = [command.name for command in bot.commands]
        result = process.extractOne(attempted, command_names, scorer=fuzz.ratio)
        if result is not None:
            match, score, _ = result
            if score >= 70:
                await ctx.reply(f"❓ Apakah maksudmu `m{match}`?", delete_after=5)
                return
    else:
        await ctx.send(f"❌ Terjadi error: {error}", delete_after=5)

async def main():
    bot.remove_command("help")
    ensure_database_exists()
    bot.db = connect_db()
    migrate(bot.db)

    await bot.add_cog(main_cog(bot))
    await bot.add_cog(image_cog(bot))
    await bot.add_cog(music_cog(bot))
    await bot.add_cog(link_cog(bot))
    await bot.add_cog(LevelCog(bot))
    await bot.add_cog(GeminiCog(bot))
    await bot.add_cog(SambungKataMultiplayer(bot))
    await bot.add_cog(AFK(bot))
    await bot.add_cog(Birthday(bot))
    await bot.add_cog(WelcomeMessageConfig(bot))
    await bot.add_cog(BannedWordsCog(bot))
    await bot.add_cog(TimedWordsCog(bot))

    await bot.start(os.getenv("TOKEN"))

asyncio.run(main())
