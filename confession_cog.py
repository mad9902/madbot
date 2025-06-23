import discord
from discord.ext import commands
import uuid
from database import (
    save_confession,
    connect_db,
    set_channel_settings,
)

CONFESSION_THREAD_MAP = {}

class ConfessionModal(discord.ui.Modal, title="Anonymous Confession"):
    confession_input = discord.ui.TextInput(
        label="Confession",
        style=discord.TextStyle.paragraph,
        placeholder="Tulis pesan kamu secara anonim...",
        max_length=1000,
        required=True,
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        confession_id = str(uuid.uuid4())[:8]
        content = self.confession_input.value

        embed = discord.Embed(
            title=f"Anonymous Confession (#{confession_id})",
            description=f'"{content}"',
            color=discord.Color.dark_gray()
        )

        try:
            sent = await interaction.channel.send(
                embed=embed,
                view=ConfessionView(self.bot, interaction.channel, is_thread=False)
            )

            if isinstance(interaction.channel, discord.TextChannel):
                thread = await sent.create_thread(name=f"Confession #{confession_id}")
                CONFESSION_THREAD_MAP[sent.id] = thread.id

                await thread.send(
                    "Gunakan tombol di bawah ini untuk membalas confession ini secara anonim:",
                    view=ConfessionView(self.bot, thread, is_thread=True)
                )

            guild_id = interaction.guild_id or getattr(interaction.channel, "guild", None).id
            save_confession(self.bot.db, guild_id, interaction.user.id, confession_id, content)

            await interaction.response.send_message("✅ Confession kamu telah dikirim!", ephemeral=True)

        except Exception as e:
            print("Error sending confession:", e)
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Gagal mengirim confession. Coba lagi.", ephemeral=True)



class ConfessionView(discord.ui.View):
    def __init__(self, bot: commands.Bot, target_channel: discord.abc.Messageable = None, is_thread=False):
        super().__init__(timeout=None)
        self.bot = bot
        self.channel = target_channel
        self.is_thread = is_thread

        if self.is_thread:
            self.add_item(ReplyButton(bot))
        else:
            self.add_item(SubmitButton(bot))

    def is_persistent(self) -> bool:
        return True


class SubmitButton(discord.ui.Button):
    def __init__(self, bot):
        super().__init__(
            label="Submit a confession!",
            style=discord.ButtonStyle.blurple,
            custom_id="confess_submit"
        )
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ConfessionModal(self.bot))


class ReplyButton(discord.ui.Button):
    def __init__(self, bot):
        super().__init__(
            label="Reply",
            style=discord.ButtonStyle.gray,
            custom_id="confess_reply"
        )
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        if isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_modal(ConfessionModal(self.bot))
            return

        message = interaction.message
        thread_id = CONFESSION_THREAD_MAP.get(message.id)

        if not thread_id:
            await interaction.response.send_message("❌ Tidak ditemukan thread untuk confession ini.", ephemeral=True)
            return

        thread = await self.bot.fetch_channel(thread_id)
        if not isinstance(thread, discord.Thread):
            await interaction.response.send_message("❌ Gagal menemukan thread target.", ephemeral=True)
            return

        await interaction.response.send_modal(ConfessionModal(self.bot))


class ConfessionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sendconfessbutton")
    async def send_confess_button(self, ctx):
        if not ctx.author.guild_permissions.manage_guild and ctx.author.id != 416234104317804544:
            return await ctx.send("❌ Hanya admin server yang bisa menggunakan command ini.")

        view = ConfessionView(self.bot, ctx.channel, is_thread=False)
        embed = discord.Embed(
            title="Confessions",
            description="Klik tombol di bawah untuk mengirim confession secara anonim!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed, view=view)

    @commands.command(name="setconfessch", help="Set channel khusus untuk tombol confession")
    async def set_confession_channel(self, ctx, channel: discord.TextChannel):
        if ctx.author.id != ctx.guild.owner_id and ctx.author.id != 416234104317804544:
            return await ctx.send("❌ Hanya pemilik server yang bisa menggunakan command ini.")

        db = connect_db()
        set_channel_settings(db, ctx.guild.id, "confession", channel.id)
        db.close()

        await ctx.send(f"✅ Channel confession disetel ke {channel.mention}")


async def setup(bot):
    await bot.add_cog(ConfessionCog(bot))
