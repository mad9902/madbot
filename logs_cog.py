import discord
from discord.ext import commands, tasks
from discord.ui import View, Select, Button
from database import connect_db, set_channel_settings, get_channel_settings, get_logs_by_type, delete_old_logs, log_event_discord, delete_old_voice_logs  
import json
from pytz import timezone
from datetime import timezone as dt_timezone

class LogSelect(Select):
    def __init__(self, bot, guild_id, user):
        self.bot = bot
        self.guild_id = guild_id
        self.user = user
        options = [
            discord.SelectOption(label="Pesan Dihapus", value="message_delete"),
            discord.SelectOption(label="Pesan Diedit", value="message_edit"),
            discord.SelectOption(label="Voice Update", value="voice_update"),
            discord.SelectOption(label="Ganti Username", value="username_change"),
            discord.SelectOption(label="Ganti Nickname", value="nickname_change"),
        ]
        super().__init__(placeholder="Pilih tipe log", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("❌ Bukan kamu yang membuka menu ini.", ephemeral=True)
            return
        self.view.event_type = self.values[0]
        self.view.page = 0
        await self.view.update_embed(interaction)

class LogView(View):
    def __init__(self, bot, guild_id, user):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.user = user
        self.page = 0
        self.event_type = None  # defaultnya belum ada pilihan

        self.select = LogSelect(bot, guild_id, user)
        self.prev_button = Button(label="⏮", style=discord.ButtonStyle.grey)
        self.next_button = Button(label="⏭", style=discord.ButtonStyle.grey)

        self.prev_button.callback = self.previous
        self.next_button.callback = self.next

        self.add_item(self.select)
        self.add_item(self.prev_button)
        self.add_item(self.next_button)

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user == self.user

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

    async def update_embed(self, interaction):
        # Tampilkan embed loading dulu biar responsif
        loading_embed = discord.Embed(
            title="⏳ Memuat...",
            description="Log sedang dimuat, mohon tunggu sebentar.",
            color=discord.Color.greyple()
        )
        await interaction.response.edit_message(embed=loading_embed, view=self)

        await discord.utils.sleep_until(discord.utils.utcnow())  # give time for UI to update

        # Setelah loading, proses embed utama
        embed = discord.Embed(color=discord.Color.blue())

        if not self.event_type:
            embed.title = "📋 Log Viewer"
            embed.description = "ℹ️ Silakan pilih kategori log terlebih dahulu."
            self.prev_button.disabled = True
            self.next_button.disabled = True
            await interaction.edit_original_response(embed=embed, view=self)
            return

        logs = get_logs_by_type(self.guild_id, self.event_type, limit=5, offset=self.page * 5)
        event_name = self.event_type.replace('_', ' ').title()
        embed.title = f"📋 Log: {event_name} (Halaman {self.page + 1})"

        if not logs:
            embed.description = "❌ Belum ada log yang tercatat."
        else:
            for log in logs:
                user_mention = f"<@{log['user_id']}>"
                wib = timezone("Asia/Jakarta")
                created_at_utc = log['created_at'].replace(tzinfo=dt_timezone.utc)
                created_at_wib = created_at_utc.astimezone(wib)
                waktu = created_at_wib.strftime('%Y-%m-%d %H:%M:%S')
                data = log['event_data']

                if self.event_type == "message_delete":
                    isi = f"🗑️ Pesan: `{data.get('content', '[kosong]')}`\n📍 Channel: `{data.get('channel')}`"
                elif self.event_type == "message_edit":
                    isi = (
                        f"✏️ **Sebelum:** `{data.get('before', '[kosong]')}`\n"
                        f"🆕 **Sesudah:** `{data.get('after', '[kosong]')}`\n"
                        f"📍 Channel: `{data.get('channel')}`"
                    )
                elif self.event_type == "voice_update":
                    isi = (
                        f"🔇 **Dari:** `{data.get('before_channel', 'None')}`\n"
                        f"🔊 **Ke:** `{data.get('after_channel', 'None')}`"
                    )
                elif self.event_type == "username_change":
                    isi = f"👤 **Dari:** `{data.get('before')}` ➜ `{data.get('after')}`"
                elif self.event_type == "nickname_change":
                    isi = f"🏷️ **Dari:** `{data.get('before')}` ➜ `{data.get('after')}`"
                else:
                    isi = f"📄 Data tidak dikenal: `{str(data)}`"

                embed.add_field(
                    name=f"{user_mention} • {waktu}",
                    value=isi,
                    inline=False
                )

        # Atur tombol prev & next
        self.select.disabled = False
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = len(logs) < 5

        # Edit kembali dengan data yang sudah siap
        await interaction.edit_original_response(embed=embed, view=self)

    async def previous(self, interaction: discord.Interaction):
        if self.page > 0:
            self.page -= 1
        await self.update_embed(interaction)

    async def next(self, interaction: discord.Interaction):
        self.page += 1
        await self.update_embed(interaction)

class LogCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.delete_old_logs.start()

    def cog_unload(self):
        self.delete_old_logs.cancel()

    @tasks.loop(hours=24)
    async def delete_old_logs(self):
        delete_old_logs(older_than_days=5)

    @tasks.loop(hours=24)
    async def delete_old_voice_logs(self):
        delete_old_voice_logs(older_than_days=1)

    @commands.command(name="setchlog")
    async def set_log_channel(self, ctx, channel: discord.TextChannel):
        is_owner = ctx.author.id == ctx.guild.owner_id or ctx.author.id == 416234104317804544
        if not is_owner:
            return await ctx.send("❌ Hanya pemilik server atau developer yang bisa menggunakan command ini.")
        db = connect_db()
        set_channel_settings(db, ctx.guild.id, "log", channel.id)
        db.close()
        await ctx.send(f"✅ Channel log telah disetel ke {channel.mention}")

    @commands.command(name="log")
    async def show_logs(self, ctx):
        view = LogView(self.bot, ctx.guild.id, ctx.author)
        await ctx.send(embed=discord.Embed(title="Silahkan Pilih Category Log", color=discord.Color.blurple()), view=view)

    # =============================
    # ==== EVENT LISTENERS ========
    # =============================

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild or message.author.bot:
            return
        db = connect_db()
        log_event_discord(db, message.guild.id, message.author.id, "message_delete", {
            "content": message.content,
            "channel": message.channel.name
        })
        db.close()

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.guild or before.author.bot:
            return
        db = connect_db()
        log_event_discord(db, before.guild.id, before.author.id, "message_edit", {
            "before": before.content,
            "after": after.content,
            "channel": before.channel.name
        })
        db.close()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.guild:
            return
        db = connect_db()
        log_event_discord(db, member.guild.id, member.id, "voice_update", {
            "before_channel": before.channel.name if before.channel else None,
            "after_channel": after.channel.name if after.channel else None
        })
        db.close()

    @commands.Cog.listener()
    async def on_user_update(self, before, after):
        # Bisa terjadi di DM, skip yang bukan di guild
        for guild in self.bot.guilds:
            member = guild.get_member(after.id)
            if member:
                db = connect_db()
                if before.name != after.name:
                    log_event_discord(db, guild.id, after.id, "username_change", {
                        "before": before.name,
                        "after": after.name
                    })
                if before.discriminator != after.discriminator:
                    log_event_discord(db, guild.id, after.id, "discriminator_change", {
                        "before": before.discriminator,
                        "after": after.discriminator
                    })
                db.close()

async def setup(bot):
    await bot.add_cog(LogCog(bot))
