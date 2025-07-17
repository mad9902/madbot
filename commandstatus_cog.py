import discord
from discord.ext import commands
from database import CommandManager, set_feature_status, get_feature_status, connect_db
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CommandStatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cmd_manager = CommandManager()
        
        # Validasi semua command saat cog dimuat
        self._validate_existing_commands()

    async def _validate_existing_commands(self):
        """Memastikan semua command terdaftar dengan benar"""
        for cmd in self.bot.commands:
            cmd.add_check(self.global_command_check)

    async def global_command_check(self, ctx):
        """Global check untuk semua command"""
        if ctx.guild and self.cmd_manager.is_command_disabled(ctx.guild.id, ctx.command.name):
            logger.info(f"Blocked disabled command '{ctx.command.name}' in guild {ctx.guild.id}")
            raise commands.DisabledCommand(f"Command {ctx.command.name} dinonaktifkan")
        return True

    @commands.command(name="disablecmd")
    @commands.has_permissions(administrator=True)
    async def disable_command(self, ctx, command_name: str):
        """Menonaktifkan sebuah command di server ini"""
        command_name = command_name.lower()
        
        if not self.bot.get_command(command_name):
            return await ctx.send(f"⚠️ Command `{command_name}` tidak ditemukan!")

        if self.cmd_manager.disable_command(ctx.guild.id, command_name, ctx.author.id):
            logger.info(f"Command '{command_name}' dinonaktifkan oleh {ctx.author} di guild {ctx.guild.name}.")
            # Update command check secara real-time
            cmd = self.bot.get_command(command_name)
            if cmd:
                cmd.add_check(self.global_command_check)
            await ctx.send(f"✅ Command `{command_name}` berhasil dinonaktifkan di server ini!")
        else:
            await ctx.send("❌ Gagal menonaktifkan command. Coba lagi nanti.")

    @commands.command(name="enablecmd")
    @commands.has_permissions(administrator=True)
    async def enable_command(self, ctx, command_name: str):
        """Mengaktifkan kembali sebuah command di server ini"""
        command_name = command_name.lower()

        if self.cmd_manager.enable_command(ctx.guild.id, command_name):
            logger.info(f"Command '{command_name}' diaktifkan kembali oleh {ctx.author} di guild {ctx.guild.name}.")
            # Update command check secara real-time
            cmd = self.bot.get_command(command_name)
            if cmd:
                cmd.remove_check(self.global_command_check)
            await ctx.send(f"✅ Command `{command_name}` berhasil diaktifkan kembali!")
        else:
            await ctx.send(f"⚠️ Command `{command_name}` tidak terdaftar sebagai dinonaktifkan.")

    @commands.command(name="toggle_welcome", help="Aktifkan atau nonaktifkan welcome message.")
    @commands.has_permissions(administrator=True)
    async def toggle_welcome(self, ctx):
        """Toggle welcome message feature"""
        db = connect_db()
        current_status = get_feature_status(db, ctx.guild.id, "welcome_message")
        new_status = not current_status
        set_feature_status(db, ctx.guild.id, "welcome_message", new_status)
        db.close()

        status_message = "diaktifkan" if new_status else "dinonaktifkan"
        await ctx.send(f"✅ Fitur welcome message telah {status_message}.")

    @commands.command(name="toggle_reply_words", help="Aktifkan atau nonaktifkan fitur reply words.")
    @commands.has_permissions(administrator=True)
    async def toggle_reply_words(self, ctx):
        """Toggle reply words feature"""
        db = connect_db()
        current_status = get_feature_status(db, ctx.guild.id, "reply_words")
        new_status = not current_status
        set_feature_status(db, ctx.guild.id, "reply_words", new_status)
        db.close()

        status_message = "diaktifkan" if new_status else "dinonaktifkan"
        await ctx.send(f"✅ Fitur reply words telah {status_message}.")

    @commands.command(name="cmdstatus")
    async def command_status(self, ctx, command_name: str = None):
        """Memeriksa status sebuah command atau list semua command yang dinonaktifkan"""
        if command_name:
            command_name = command_name.lower()
            if self.cmd_manager.is_command_disabled(ctx.guild.id, command_name):
                await ctx.send(f"🔴 Command `{command_name}` sedang **dinonaktifkan** di server ini.")
            else:
                await ctx.send(f"🟢 Command `{command_name}` **aktif** di server ini.")
        else:
            disabled_commands = self.cmd_manager.get_disabled_commands(ctx.guild.id)
            if not disabled_commands:
                await ctx.send("Tidak ada command yang dinonaktifkan di server ini.")
            else:
                commands_list = "\n".join(f"• `{cmd['command_name']}`" for cmd in disabled_commands)
                embed = discord.Embed(
                    title="Daftar Command Dinonaktifkan",
                    description=commands_list,
                    color=discord.Color.orange()
                )
                await ctx.send(embed=embed)

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Anda tidak memiliki izin untuk menggunakan command ini!")
        elif isinstance(error, commands.CommandNotFound):
            await ctx.send("❌ Command tidak ditemukan!")
        elif isinstance(error, commands.DisabledCommand):
            await ctx.send(f"⛔ Command `{ctx.command.name}` dinonaktifkan di server ini!")
        else:
            await ctx.send(f"❌ Tidak Dapat Merespon Command karena: {str(error)}")
            raise error

def setup(bot):
    bot.add_cog(CommandStatusCog(bot))
