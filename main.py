import discord
from discord.ext import commands
import atexit
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
from broadcast_cog import MassDM
from werewolf_cog import Werewolf
from lastActive_cog import LastActive
from logs_cog import LogCog
from confession_cog import ConfessionCog, ConfessionView, restore_reply_buttons  
from bot_state import DISABLED_GUILDS, OWNER_ID

# Load .env
load_dotenv()

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

# Prefix logic
def get_prefix(bot, message):
    if message.guild and message.guild.id in DISABLED_GUILDS:
        if message.content.strip().lower().startswith(("mad boton", "md boton", "mboton")):
            return ['mad ', 'md ', 'm']
        return commands.when_mentioned(bot)
    return ['mad ', 'md ', 'm']

# Subclass Bot
class MadBot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db = None

    async def setup_hook(self):
        self.remove_command("help")
        ensure_database_exists()
        self.db = connect_db()
        migrate(self.db)

        # Load semua cog
        await self.add_cog(main_cog(self))
        await self.add_cog(image_cog(self))
        await self.add_cog(music_cog(self))
        await self.add_cog(link_cog(self))
        await self.add_cog(LevelCog(self))
        await self.add_cog(GeminiCog(self))
        await self.add_cog(LastActive(self))
        await self.add_cog(SambungKataMultiplayer(self))
        await self.add_cog(AFK(self))

        birthday_cog = Birthday(self)
        await self.add_cog(birthday_cog)
        self.loop.create_task(birthday_cog.start_birthday_loop())

        await self.add_cog(WelcomeMessageConfig(self))
        await self.add_cog(BannedWordsCog(self))
        await self.add_cog(TimedWordsCog(self))
        await self.add_cog(ConfessionCog(self))
        await self.add_cog(MassDM(self))
        await self.add_cog(Werewolf(self))
        await self.add_cog(LogCog(self))

        # Tambahkan view global untuk tombol confession agar tetap hidup setelah restart
        self.add_view(ConfessionView(self))  # PENTING
        await restore_reply_buttons(self)


# Buat bot instance
bot = MadBot(command_prefix=get_prefix, intents=intents)

# Cek disable per guild
@bot.check
async def block_disabled_guilds(ctx):
    if ctx.guild and ctx.guild.id in DISABLED_GUILDS:
        if ctx.command and ctx.command.name == "boton":
            return True
        return False
    return True

# Blok interaksi juga kalau dinonaktifkan
@bot.event
async def on_interaction(interaction):
    if interaction.guild and interaction.guild.id in DISABLED_GUILDS:
        try:
            await interaction.response.send_message("❌ Bot sedang nonaktif di server ini.", ephemeral=True)
        except discord.InteractionResponded:
            pass
        return
    await bot.process_interaction(interaction)

# Fitur typo autocorrect
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

# Jalankan bot
async def main():
    await bot.start(os.getenv("TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())
