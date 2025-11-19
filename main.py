import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv
from rapidfuzz import process, fuzz

# Database dan migrasi
from database import connect_db, ensure_database_exists, CommandManager, ChannelBlockManager
from migration import migrate

# Import semua cog
from main_cog import main_cog
from image_cog import image_cog
from music_cog import music_cog
from streak_cog import StreakCog
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
from commandstatus_cog import CommandStatusCog
from logs_cog import LogCog
from gamble_cog import GambleCog
from daily_cog import DailyCog
from duel_cog import DuelCog
from rob_cog import RobCog
from help_cog import HelpCog
from channelcontrol_cog import ChannelControl
from admin_cog import AdminCog
from confession_cog import ConfessionCog, ConfessionView, restore_reply_buttons
from bot_state import DISABLED_GUILDS, OWNER_ID

# Load env
load_dotenv()

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guild_reactions = True
intents.reactions = True

# Prefix logic
def get_prefix(bot, message):
    if message.guild and message.guild.id in DISABLED_GUILDS:
        if message.content.strip().lower().startswith(("mad boton", "md boton", "mboton")):
            return ['mad', 'm', 'k', 'kos ']
        return commands.when_mentioned(bot)

    # Prioritas prefix panjang → pendek
    return ['kos ', 'kos', 'mad ', 'mad', 'm', 'k']


# ======================================================
# BOT CLASS
# ======================================================

class MadBot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db = None
        self.command_manager = None
        self.channel_manager = None

    async def setup_hook(self):
        self.remove_command("help")

        # siapkan DB
        ensure_database_exists()
        self.db = connect_db()

        # migration
        migrate(self.db)

        # manager per-command
        self.command_manager = CommandManager()

        # manager per-channel (NEW)
        self.channel_manager = ChannelBlockManager(self.db)

        # Load semua COG
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

        await self.add_cog(WelcomeMessageConfig(self))
        await self.add_cog(BannedWordsCog(self))
        await self.add_cog(TimedWordsCog(self))
        await self.add_cog(ConfessionCog(self))
        await self.add_cog(MassDM(self))
        await self.add_cog(Werewolf(self))
        await self.add_cog(LogCog(self))
        await self.add_cog(CommandStatusCog(self))
        await self.add_cog(StreakCog(self))
        await self.add_cog(ChannelControl(self))
        await self.add_cog(AdminCog(self))
        await self.add_cog(GambleCog(self))
        await self.add_cog(DailyCog(self))
        await self.add_cog(DuelCog(self))
        await self.add_cog(RobCog(self))
        await self.add_cog(HelpCog(self))

        # Load cache semua guild


        # tombol global tetap hidup
        self.add_view(ConfessionView(self))
        self.channel_manager.load_all_guilds(self.guilds)
        await restore_reply_buttons(self)


# BOT INSTANCE
bot = MadBot(command_prefix=get_prefix, intents=intents)


# ======================================================
# CHECK 1: Block entire guild
# ======================================================

@bot.check
async def block_disabled_guilds(ctx):
    if ctx.guild and ctx.guild.id in DISABLED_GUILDS:
        if ctx.command and ctx.command.name == "boton":
            return True
        return False
    return True


# ======================================================
# CHECK 2: Block entire CHANNEL (NEW FEATURE)
# ======================================================

@bot.check
async def block_disabled_channels(ctx):
    if not ctx.guild:
        return True

    # whitelist admin & owner
    if ctx.author.id == OWNER_ID:
        return True
    if ctx.author.guild_permissions.administrator:
        return True

    # block normal user
    return not bot.channel_manager.is_channel_disabled(ctx.guild.id, ctx.channel.id)



# ======================================================
# CHECK 3: Block individual disabled command
# ======================================================

@bot.check
async def check_command_disabled(ctx):
    if not ctx.guild or not ctx.command:
        return True

    return not bot.command_manager.is_command_disabled(ctx.guild.id, ctx.command.name)


# ======================================================
# BLOCK INTERACTION (slash/button) jika guild/channel disabled
# ======================================================

@bot.event
async def on_interaction(interaction: discord.Interaction):

    # block whole guild
    if interaction.guild and interaction.guild.id in DISABLED_GUILDS:
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Bot sedang nonaktif di server ini.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Bot sedang nonaktif di server ini.", ephemeral=True)
        except:
            pass
        return

    # block channel
    if interaction.guild and bot.channel_manager.is_channel_disabled(interaction.guild.id, interaction.channel.id):
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Bot nonaktif di channel ini.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Bot nonaktif di channel ini.", ephemeral=True)
        except:
            pass
        return

    # biarkan interaction lanjut normal
    return


# ======================================================
# SAFE RESPOND UTILITY
# ======================================================

async def safe_respond(inter: discord.Interaction, **kwargs):
    try:
        if inter.response.is_done():
            await inter.followup.send(**kwargs)
        else:
            await inter.response.send_message(**kwargs)
    except discord.HTTPException:
        pass


# ======================================================
# ERROR HANDLER
# ======================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        attempted = ctx.message.content[len(ctx.prefix):].split()[0]
        command_names = [c.name for c in bot.commands]

        result = process.extractOne(attempted, command_names, scorer=fuzz.ratio)

        if result:
            match, score, _ = result
            if score >= 70:
                await ctx.reply(f"❓ Apakah maksudmu `{ctx.prefix}{match}`?", delete_after=5)
                return

    elif isinstance(error, commands.CheckFailure):
        # biasanya karena channel disabled — jangan spam
        return

    else:
        await ctx.send(f"❌ Error: {error}", delete_after=5)


# ======================================================
# BOT RUNNER
# ======================================================

async def main():
    await bot.start(os.getenv("TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())
