import discord
from discord.ext import commands
import uuid
import asyncio
import json
from database import (
    save_confession,
    connect_db,
    set_channel_settings,
    get_channel_settings
)

CONFESSION_THREAD_MAP = {}
MAP_FILE = "confession_map.json"


# ==============================
# MAP STORAGE
# ==============================

def save_confession_map():
    with open(MAP_FILE, "w") as f:
        json.dump(CONFESSION_THREAD_MAP, f)


def load_confession_map():
    global CONFESSION_THREAD_MAP
    try:
        with open(MAP_FILE, "r") as f:
            raw = json.load(f)
            CONFESSION_THREAD_MAP = {}
            for k, v in raw.items():
                k = int(k)
                if isinstance(v, dict):
                    CONFESSION_THREAD_MAP[k] = v
                else:
                    CONFESSION_THREAD_MAP[k] = {
                        "thread_id": v,
                        "channel_id": None
                    }
    except FileNotFoundError:
        CONFESSION_THREAD_MAP = {}


def cleanup_confession_map():
    valid_map = {}
    for mid, data in CONFESSION_THREAD_MAP.items():
        if (
            isinstance(data, dict)
            and "thread_id" in data
            and "channel_id" in data
        ):
            valid_map[int(mid)] = data

    with open(MAP_FILE, "w") as f:
        json.dump(valid_map, f)


async def restore_reply_buttons(bot: commands.Bot):
    for message_id, data in CONFESSION_THREAD_MAP.items():
        try:
            if (
                not isinstance(data, dict)
                or "thread_id" not in data
                or "channel_id" not in data
            ):
                print(f"[Restore] Data incomplete for {message_id}")
                continue

            thread_id = data["thread_id"]
            channel_id = data["channel_id"]

            # Fetch parent channel
            try:
                parent_channel = await bot.fetch_channel(channel_id)
                if not isinstance(parent_channel, discord.TextChannel):
                    print(f"[Restore] {channel_id} bukan text channel.")
                    continue

                # Fetch original message
                parent_message = await parent_channel.fetch_message(int(message_id))

                # Create view
                view = discord.ui.View(timeout=None)
                view.add_item(SubmitConfessionButton(bot))
                view.add_item(SubmitImageConfessionButton(bot))
                view.add_item(ReplyToConfessionButton(bot, int(message_id)))

                await parent_message.edit(view=view)

            except discord.NotFound:
                print(f"[Restore] Pesan {message_id} hilang.")
            except Exception as e:
                print(f"[Restore] Error restore {message_id}: {e}")

        except Exception as e:
            print(f"[Restore] Processing error {message_id}: {e}")


# ==============================
# BUTTON — IMAGE CONFESSION
# ==============================

class SubmitImageConfessionButton(discord.ui.Button):
    def __init__(self, bot: commands.Bot):
        super().__init__(
            label="Submit confession with image",
            style=discord.ButtonStyle.green,
            custom_id="confess_image_submit"
        )
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):

        # Try DM user
        try:
            dm = await interaction.user.create_dm()
            await dm.send(
                "📸 Kirim gambar / GIF / video (max 5MB) + caption (optional).\n"
                "Setelah itu akan diposting sebagai confession anonim."
            )
        except:
            return await interaction.response.send_message(
                "❌ Tidak bisa kirim DM. Aktifkan DM terlebih dahulu.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "📨 Cek DM-ku ya!",
            ephemeral=True
        )

        # Wait for file
        def check(msg: discord.Message):
            return (
                msg.author.id == interaction.user.id
                and isinstance(msg.channel, discord.DMChannel)
                and len(msg.attachments) > 0
            )

        try:
            msg = await self.bot.wait_for("message", timeout=120.0, check=check)
        except asyncio.TimeoutError:
            return await dm.send("⏱️ Waktu habis. Confession dibatalkan.")

        attachment = msg.attachments[0]

        # File size validation
        if attachment.size > 5 * 1024 * 1024:
            return await dm.send("❌ File lebih dari 5MB.")

        content_type = attachment.content_type or ""
        is_image = content_type.startswith("image/")
        is_video = content_type.startswith("video/")

        if not (is_image or is_video):
            return await dm.send("❌ Hanya gambar / GIF / video yang diterima.")

        caption = msg.content or " "
        confession_id = str(uuid.uuid4())[:8]

        # Download with real filename
        orig_filename = attachment.filename
        temp_path = f"/tmp/{uuid.uuid4().hex}_{orig_filename}"
        await attachment.save(temp_path)

        # Target channel
        db = connect_db()
        channel_id = get_channel_settings(db, interaction.guild_id, "confession")
        db.close()
        target_channel = interaction.guild.get_channel(int(channel_id))

        # Prepare embed
        embed = discord.Embed(
            title=f"Anonymous Confession (#{confession_id})",
            description=f'"{caption}"',
            color=discord.Color.dark_gray()
        )

        # Prepare file
        file = discord.File(temp_path, filename=orig_filename)

        # If image, embed it
        if is_image:
            embed.set_image(url=f"attachment://{orig_filename}")

        # Send
        sent = await target_channel.send(embed=embed, file=file)

        # Remove temp file
        try:
            import os
            os.remove(temp_path)
        except:
            pass

        # Create thread
        thread = await sent.create_thread(name=f"Confession #{confession_id}")

        # Save mapping
        CONFESSION_THREAD_MAP[sent.id] = {
            "thread_id": thread.id,
            "channel_id": target_channel.id
        }
        save_confession_map()

        # Add buttons under confession
        view = discord.ui.View(timeout=None)
        view.add_item(SubmitConfessionButton(self.bot))
        view.add_item(SubmitImageConfessionButton(self.bot))
        view.add_item(ReplyToConfessionButton(self.bot, sent.id))
        await sent.edit(view=view)

        # Thread reply buttons
        thread_view = discord.ui.View(timeout=None)
        thread_view.add_item(ReplyToConfessionButton(self.bot, sent.id))
        await thread.send(
            "Balas confession ini secara anonim dengan tombol di bawah:",
            view=thread_view
        )

        # Save to DB
        save_confession(self.bot.db, interaction.guild_id, interaction.user.id, confession_id, caption)

        await dm.send("✅ Confession kamu sudah berhasil diposting!")


# ==============================
# MODAL — TEXT CONFESSION
# ==============================

class ConfessionModal(discord.ui.Modal, title="Anonymous Confession"):
    confession_input = discord.ui.TextInput(
        label="Confession",
        style=discord.TextStyle.paragraph,
        placeholder="Tulis pesan kamu secara anonim...",
        max_length=1000,
        required=True,
    )

    def __init__(self, bot: commands.Bot, reply_thread: discord.Thread = None):
        super().__init__()
        self.bot = bot
        self.reply_thread = reply_thread

    async def on_submit(self, interaction: discord.Interaction):
        confession_id = str(uuid.uuid4())[:8]
        content = self.confession_input.value

        embed = discord.Embed(
            title=f"Anonymous Confession (#{confession_id})" if not self.reply_thread else "Balasan Anonim",
            description=f'"{content}"',
            color=discord.Color.dark_gray()
        )

        try:
            # ---------- Reply IN_THREAD ----------
            if self.reply_thread:
                sent = await self.reply_thread.send(embed=embed)

                CONFESSION_THREAD_MAP[sent.id] = {
                    "thread_id": self.reply_thread.id,
                    "channel_id": self.reply_thread.parent_id
                }
                save_confession_map()

                view = discord.ui.View(timeout=None)
                view.add_item(SubmitConfessionButton(self.bot))
                view.add_item(SubmitImageConfessionButton(self.bot))
                view.add_item(ReplyToConfessionButton(self.bot, sent.id))

                await sent.edit(view=view)

                await interaction.response.send_message("✅ Balasan kamu telah dikirim secara anonim!", ephemeral=True)
                return

            # ---------- Not allowed in thread ----------
            if isinstance(interaction.channel, discord.Thread):
                return await interaction.response.send_message(
                    "❌ Tidak bisa mengirim confession dari dalam thread.",
                    ephemeral=True
                )

            # Ambil target channel
            db = connect_db()
            channel_id = get_channel_settings(db, interaction.guild_id, "confession")
            db.close()

            target_channel = (
                interaction.guild.get_channel(int(channel_id))
                if channel_id else interaction.channel
            )

            sent = await target_channel.send(embed=embed)
            thread = await sent.create_thread(name=f"Confession #{confession_id}")

            CONFESSION_THREAD_MAP[sent.id] = {
                "thread_id": thread.id,
                "channel_id": target_channel.id
            }
            save_confession_map()

            # Add buttons
            view = discord.ui.View(timeout=None)
            view.add_item(SubmitConfessionButton(self.bot))
            view.add_item(SubmitImageConfessionButton(self.bot))
            view.add_item(ReplyToConfessionButton(self.bot, sent.id))
            await sent.edit(view=view)

            # Thread buttons
            thread_view = discord.ui.View(timeout=None)
            thread_view.add_item(ReplyToConfessionButton(self.bot, sent.id))
            await thread.send(
                "Gunakan tombol di bawah ini untuk membalas confession ini secara anonim:",
                view=thread_view
            )

            # Save DB
            save_confession(self.bot.db, interaction.guild_id, interaction.user.id, confession_id, content)

            await interaction.response.send_message("✅ Confession kamu telah dikirim!", ephemeral=True)

        except Exception as e:
            print("❌ Error saat mengirim confession:", e)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Gagal mengirim confession. Coba lagi.",
                    ephemeral=True
                )


# ==============================
# BUTTONS
# ==============================

class SubmitConfessionButton(discord.ui.Button):
    def __init__(self, bot: commands.Bot):
        super().__init__(
            label="Submit a confession!",
            style=discord.ButtonStyle.blurple,
            custom_id="confess_submit"
        )
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        if isinstance(interaction.channel, discord.Thread):
            return await interaction.response.send_message(
                "❌ Tidak bisa mengirim confession baru dari dalam thread.",
                ephemeral=True
            )
        await interaction.response.send_modal(ConfessionModal(self.bot))


class ReplyToConfessionButton(discord.ui.Button):
    def __init__(self, bot: commands.Bot, message_id: int):
        super().__init__(
            label="Reply",
            style=discord.ButtonStyle.gray,
            custom_id=f"confess_reply_{message_id}"
        )
        self.bot = bot
        self.message_id = message_id

    async def callback(self, interaction: discord.Interaction):
        data = CONFESSION_THREAD_MAP.get(self.message_id)
        if not data:
            return await interaction.response.send_message("❌ Thread tidak ditemukan.", ephemeral=True)

        thread_id = data["thread_id"]
        thread = await self.bot.fetch_channel(thread_id)

        if not isinstance(thread, discord.Thread):
            return await interaction.response.send_message("❌ Thread sudah tidak ada.", ephemeral=True)

        await interaction.response.send_modal(ConfessionModal(self.bot, reply_thread=thread))


# ==============================
# VIEW
# ==============================

class ConfessionView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.add_item(SubmitConfessionButton(bot))
        self.add_item(SubmitImageConfessionButton(bot))


# ==============================
# COG
# ==============================

class ConfessionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        load_confession_map()

    @commands.command(name="sendconfessbutton")
    async def send_confess_button(self, ctx):
        if not ctx.author.guild_permissions.manage_guild and ctx.author.id != 416234104317804544:
            return await ctx.send("❌ Kamu tidak boleh menggunakan command ini.")

        view = ConfessionView(self.bot)

        embed = discord.Embed(
            title="Confessions",
            description="Klik tombol di bawah untuk mengirim confession secara anonim!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed, view=view)

    @commands.command(name="setconfessch")
    async def set_confession_channel(self, ctx, channel: discord.TextChannel):
        if ctx.author.id != ctx.guild.owner_id and ctx.author.id != 416234104317804544:
            return await ctx.send("❌ Hanya owner server yang bisa mengatur ini.")

        db = connect_db()
        set_channel_settings(db, ctx.guild.id, "confession", channel.id)
        db.close()

        await ctx.send(f"✅ Channel confession disetel ke {channel.mention}")


# ==============================
# SETUP
# ==============================

async def setup(bot):
    await bot.add_cog(ConfessionCog(bot))
    bot.add_view(ConfessionView(bot))  # persist view buttons
    await restore_reply_buttons(bot)   # restore old messages
    cleanup_confession_map()
