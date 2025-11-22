import discord
from discord.ext import commands
from database import CommandManager, set_feature_status, get_feature_status, connect_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CommandStatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cmd_manager = CommandManager()

    async def cog_load(self):
        """Dipanggil otomatis ketika cog sudah siap"""
        await self._validate_existing_commands()

    async def _validate_existing_commands(self):
        """Memastikan semua command terdaftar dengan benar"""
        for cmd in self.bot.commands:
            cmd.add_check(self.global_command_check)

    async def global_command_check(self, ctx):
        if ctx.guild and self.cmd_manager.is_command_disabled(ctx.guild.id, ctx.command.name):
            logger.info(f"Blocked disabled command '{ctx.command.name}' in guild {ctx.guild.id}")
            raise commands.DisabledCommand(f"Command {ctx.command.name} dinonaktifkan")
        return True

    @commands.command(name="disablecmd", extras={"category": "Admin"})
    @commands.has_permissions(administrator=True)
    async def disable_command(self, ctx, command_name: str):
        command_name = command_name.lower()

        if not self.bot.get_command(command_name):
            return await ctx.send(f"⚠️ Command `{command_name}` tidak ditemukan!")

        if self.cmd_manager.disable_command(ctx.guild.id, command_name, ctx.author.id):
            logger.info(f"Command '{command_name}' dinonaktifkan oleh {ctx.author}")

            cmd = self.bot.get_command(command_name)
            if cmd:
                cmd.add_check(self.global_command_check)

            await ctx.send(f"✅ Command `{command_name}` berhasil dinonaktifkan!")
        else:
            await ctx.send("❌ Gagal menonaktifkan command.")

    @commands.command(name="enablecmd", extras={"category": "Admin"})
    @commands.has_permissions(administrator=True)
    async def enable_command(self, ctx, command_name: str):
        command_name = command_name.lower()

        if self.cmd_manager.enable_command(ctx.guild.id, command_name):
            logger.info(f"Command '{command_name}' diaktifkan kembali oleh {ctx.author}")

            cmd = self.bot.get_command(command_name)
            if cmd:
                cmd.remove_check(self.global_command_check)

            await ctx.send(f"✅ Command `{command_name}` berhasil diaktifkan kembali!")
        else:
            await ctx.send(f"⚠️ Command `{command_name}` tidak terdaftar sebagai dinonaktifkan.")

    @commands.command(name="toggle_welcome", extras={"category": "Admin"})
    @commands.has_permissions(administrator=True)
    async def toggle_welcome(self, ctx):
        db = connect_db()
        current_status = get_feature_status(db, ctx.guild.id, "welcome_message")
        new_status = not current_status
        set_feature_status(db, ctx.guild.id, "welcome_message", new_status)
        db.close()

        await ctx.send(f"✅ Fitur welcome message telah {'diaktifkan' if new_status else 'dinonaktifkan'}.")

    @commands.command(name="toggle_reply_words", extras={"category": "Admin"})
    @commands.has_permissions(administrator=True)
    async def toggle_reply_words(self, ctx):
        db = connect_db()
        current_status = get_feature_status(db, ctx.guild.id, "reply_words")
        new_status = not current_status
        set_feature_status(db, ctx.guild.id, "reply_words", new_status)
        db.close()

        await ctx.send(f"✅ Fitur reply words telah {'diaktifkan' if new_status else 'dinonaktifkan'}.")

    @commands.command(name="cmdstatus", extras={"category": "Admin"})
    async def command_status(self, ctx, command_name: str = None):
        if command_name:
            command_name = command_name.lower()
            if self.cmd_manager.is_command_disabled(ctx.guild.id, command_name):
                await ctx.send(f"🔴 Command `{command_name}` dinonaktifkan.")
            else:
                await ctx.send(f"🟢 Command `{command_name}` aktif.")
        else:
            disabled_commands = self.cmd_manager.get_disabled_commands(ctx.guild.id)
            if not disabled_commands:
                return await ctx.send("Tidak ada command yang dinonaktifkan.")

            commands_list = "\n".join(f"• `{cmd['command_name']}`" for cmd in disabled_commands)
            embed = discord.Embed(
                title="Daftar Command Dinonaktifkan",
                description=commands_list,
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Anda tidak memiliki izin!")
        elif isinstance(error, commands.CommandNotFound):
            await ctx.send("❌ Command tidak ditemukan!")
        elif isinstance(error, commands.DisabledCommand):
            await ctx.send(f"⛔ Command `{ctx.command.name}` dinonaktifkan!")
        else:
            await ctx.send(f"❌ Error: {str(error)}")
            raise error


async def setup(bot):
    await bot.add_cog(CommandStatusCog(bot))
