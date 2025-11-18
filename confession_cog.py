import discord
from discord.ext import commands
import uuid
import asyncio
import json
import os
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
                view = ConfessionView(bot)
                view.add_item(ReplyToConfessionButton(bot, message_id))

                await parent_message.edit(view=view)

                # ===========================
                #  RESTORE BUTTONS INSIDE THREAD
                # ===========================
                if thread_id:
                    try:
                        thread = await bot.fetch_channel(thread_id)

                        # Loop semua pesan di thread
                        async for msg in thread.history(limit=None):
                            if msg.author.id != bot.user.id:
                                continue

                            view = ThreadReplyView(bot, msg.id)
                            await msg.edit(view=view)

                            # FIX: simpan mapping yang BENAR
                            CONFESSION_THREAD_MAP[msg.id] = {
                                "thread_id": thread.id,
                                "channel_id": parent_channel.id,   # parent text channel
                                "is_parent": False
                            }

                        save_confession_map()

                    except Exception as e:
                        print(f"[Restore] Thread restore error for thread {thread_id}: {e}")



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
        tmp_dir = "/tmp" if os.name != "nt" else "temp"

        os.makedirs(tmp_dir, exist_ok=True)

        temp_path = os.path.join(tmp_dir, f"{uuid.uuid4().hex}_{orig_filename}")
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
            os.remove(temp_path)
        except:
            pass


        # Tidak membuat thread sekarang
        CONFESSION_THREAD_MAP[sent.id] = {
            "thread_id": None,
            "channel_id": target_channel.id,
            "is_parent": True
        }
        save_confession_map()

        # Add buttons under confession
        view = discord.ui.View(timeout=None)
        view.add_item(SubmitConfessionButton(self.bot))
        view.add_item(SubmitImageConfessionButton(self.bot))
        view.add_item(ReplyToConfessionButton(self.bot, sent.id))
        await sent.edit(view=view)

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

    def __init__(self, bot: commands.Bot, reply_thread: discord.Thread = None, parent_message_id: int = None):
        super().__init__()
        self.bot = bot
        self.reply_thread = reply_thread
        self.parent_message_id = parent_message_id

    async def on_submit(self, interaction: discord.Interaction):
        confession_id = str(uuid.uuid4())[:8]
        content = self.confession_input.value

        embed = discord.Embed(
            title="Balasan Anonim" if self.parent_message_id else f"Anonymous Confession (#{confession_id})",
            description=f'"{content}"',
            color=discord.Color.dark_gray()
        )

        try:
            # ============================================================
            # REPLY MODE
            # ============================================================
            if self.parent_message_id:

                pressed_message = interaction.message
                data = CONFESSION_THREAD_MAP.get(self.parent_message_id)

                if not data:
                    return await interaction.response.send_message(
                        "❌ Data mapping hilang atau rusak.",
                        ephemeral=True
                    )

                # FETCH / CREATE THREAD
                if data.get("thread_id") is None:
                    parent_channel = interaction.guild.get_channel(int(data["channel_id"]))
                    parent_msg = await parent_channel.fetch_message(int(self.parent_message_id))

                    thread = await parent_msg.create_thread(
                        name=f"Confession Thread #{self.parent_message_id}"
                    )

                    CONFESSION_THREAD_MAP[self.parent_message_id]["thread_id"] = thread.id
                    save_confession_map()

                    # BALASAN PERTAMA → TIDAK BOLEH ADA reference !!!
                    sent = await thread.send(embed=embed)

                else:
                    # Thread sudah ada → fetch
                    thread = await self.bot.fetch_channel(int(data["thread_id"]))

                    # PILIH TARGET REFERENCE:
                    if isinstance(pressed_message.channel, discord.Thread):
                        # reply di dalam thread → valid
                        reference_target = pressed_message
                    else:
                        # reply dari luar → reference ke parent
                        parent_channel = interaction.guild.get_channel(int(data["channel_id"]))
                        reference_target = await parent_channel.fetch_message(self.parent_message_id)

                    # KIRIM PESAN DENGAN APPLICATION REPLY
                    sent = await thread.send(
                        embed=embed,
                        reference=reference_target,
                        mention_author=False
                    )

                # SAVE MAPPING
                CONFESSION_THREAD_MAP[sent.id] = {
                    "thread_id": thread.id,
                    "channel_id": data["channel_id"],
                    "is_parent": False
                }
                save_confession_map()

                # ADD REPLY BUTTON
                await sent.edit(view=ThreadReplyView(self.bot, sent.id))

                return await interaction.response.send_message(
                    "✅ Balasan kamu sudah dikirim!",
                    ephemeral=True
                )

            # ============================================================
            # CONFESSION BARU (bukan reply)
            # ============================================================
            db = connect_db()
            channel_id = get_channel_settings(db, interaction.guild_id, "confession")
            db.close()

            target_channel = (
                interaction.guild.get_channel(int(channel_id))
                if channel_id else interaction.channel
            )

            sent = await target_channel.send(embed=embed)

            # Simpan mapping
            CONFESSION_THREAD_MAP[sent.id] = {
                "thread_id": None,
                "channel_id": target_channel.id,
                "is_parent": True
            }
            save_confession_map()

            # Tombol
            view = discord.ui.View(timeout=None)
            view.add_item(SubmitConfessionButton(self.bot))
            view.add_item(SubmitImageConfessionButton(self.bot))
            view.add_item(ReplyToConfessionButton(self.bot, sent.id))
            await sent.edit(view=view)

            # Simpan DB
            save_confession(
                self.bot.db,
                interaction.guild_id,
                interaction.user.id,
                confession_id,
                content
            )

            await interaction.response.send_message(
                "✅ Confession kamu telah dikirim!",
                ephemeral=True
            )

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

    @classmethod
    def from_custom_id(cls, bot, custom_id: str):
        # custom_id example: confess_reply_12345678901234
        message_id = int(custom_id.split("_")[-1])
        return cls(bot, message_id)


    async def callback(self, interaction: discord.Interaction):
     # Tombol Reply TIDAK MEMBUAT THREAD
        # Hanya buka modal dan kasih parent_message_id
        await interaction.response.send_modal(
            ConfessionModal(
                self.bot,
                reply_thread=None,
                parent_message_id=self.message_id
            )
        )

# ==============================
# VIEW
# ==============================

class ConfessionView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.add_item(SubmitConfessionButton(bot))
        self.add_item(SubmitImageConfessionButton(bot))

class ThreadReplyView(discord.ui.View):
    def __init__(self, bot: commands.Bot, message_id: int):
        super().__init__(timeout=None)
        self.add_item(ReplyToConfessionButton(bot, message_id))

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
    bot.add_dynamic_items("confess_reply_", lambda custom_id: ReplyToConfessionButton.from_custom_id(bot, custom_id))
    await restore_reply_buttons(bot)   # restore old messages
    cleanup_confession_map()
