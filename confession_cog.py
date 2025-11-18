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

                        async for msg in thread.history(limit=None):
                            if msg.author.id != bot.user.id:
                                continue

                            view = ThreadReplyView(bot, msg.id)
                            await msg.edit(view=view)

                            CONFESSION_THREAD_MAP[msg.id] = {
                                "thread_id": thread.id,
                                "channel_id": parent_channel.id,
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

        if attachment.size > 5 * 1024 * 1024:
            return await dm.send("❌ File lebih dari 5MB.")

        content_type = attachment.content_type or ""
        is_image = content_type.startswith("image/")
        is_video = content_type.startswith("video/")

        if not (is_image or is_video):
            return await dm.send("❌ Hanya gambar / GIF / video yang diterima.")

        caption = msg.content or " "
        confession_id = str(uuid.uuid4())[:8]

        orig_filename = attachment.filename
        tmp_dir = "/tmp" if os.name != "nt" else "temp"

        os.makedirs(tmp_dir, exist_ok=True)

        temp_path = os.path.join(tmp_dir, f"{uuid.uuid4().hex}_{orig_filename}")
        await attachment.save(temp_path)

        db = connect_db()
        channel_id = get_channel_settings(db, interaction.guild_id, "confession")
        db.close()
        target_channel = interaction.guild.get_channel(int(channel_id))

        embed = discord.Embed(
            title=f"Anonymous Confession (#{confession_id})",
            description=f'"{caption}"',
            color=discord.Color.dark_gray()
        )

        if is_image:
            embed.set_image(url=f"attachment://{orig_filename}")

        file = discord.File(temp_path, filename=orig_filename)
        sent = await target_channel.send(embed=embed, file=file)

        try:
            os.remove(temp_path)
        except:
            pass

        CONFESSION_THREAD_MAP[sent.id] = {
            "thread_id": None,
            "channel_id": target_channel.id,
            "is_parent": True,
            "confession_id": confession_id    # PATCH A1
        }
        save_confession_map()

        view = discord.ui.View(timeout=None)
        view.add_item(SubmitConfessionButton(self.bot))
        view.add_item(SubmitImageConfessionButton(self.bot))
        view.add_item(ReplyToConfessionButton(self.bot, sent.id))
        await sent.edit(view=view)

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

        # ========================================================
        # INIT EMBED
        # ========================================================
        embed = discord.Embed(
            title="Balasan Anonim" if self.parent_message_id else f"Anonymous Confession (#{confession_id})",
            description=f'"{content}"',
            color=discord.Color.dark_gray()
        )

        # ========================================================
        # REPLY MODE → RESOLVE ROOT PARENT (ANTI RECURSIVE)
        # ========================================================
        is_reply = self.parent_message_id is not None

        if is_reply:
            root_id = self.parent_message_id
            parent_data = CONFESSION_THREAD_MAP.get(root_id)

            # If reply-to-reply → climb to actual root
            if parent_data and not parent_data.get("is_parent", False):
                root_id = parent_data.get("root_parent_id", root_id)
                parent_data = CONFESSION_THREAD_MAP.get(root_id)

            if not parent_data:
                return await interaction.response.send_message(
                    "❌ Confession parent hilang atau rusak.",
                    ephemeral=True
                )

            # =====================================================
            # FETCH ORIGINAL ROOT MESSAGE (bukan reply)
            # =====================================================
            try:
                parent_channel = interaction.guild.get_channel(int(parent_data["channel_id"]))
                root_msg = await parent_channel.fetch_message(int(root_id))

                root_embed = root_msg.embeds[0] if root_msg.embeds else None
                root_desc = root_embed.description or ""

                # Ambil hanya konten ASLI (tanpa breadcrumb)
                import re
                cleaned = re.findall(r'"(.*?)"', root_desc)
                root_content = cleaned[-1] if cleaned else root_desc.strip('"')

                root_cid = parent_data.get("confession_id", "?")

                # =================================================
                # APPLY BREADCRUMB (NON-RECURSIVE)
                # =================================================
                breadcrumb = (
                    f"**🧵 Reply to: #{root_cid}**\n"
                    f"⤷ *\"{root_content}\"*\n\n"
                )

                embed.description = breadcrumb + f'"{content}"'
                embed.title = f"Balasan Anonim (#{root_cid})"

            except Exception as e:
                print("Breadcrumb error:", e)

        # ========================================================
        # MAIN EXECUTION
        # ========================================================
        try:

            # ----------------------------------------------------
            # ================ REPLY MODE ========================
            # ----------------------------------------------------
            if is_reply:

                data = parent_data
                root_id = root_id
                parent_confession_id = data.get("confession_id", "unknown")

                # ================================================
                # THREAD BELUM ADA → CREATE
                # ================================================
                if data.get("thread_id") is None:
                    parent_channel = interaction.guild.get_channel(int(data["channel_id"]))
                    parent_msg = await parent_channel.fetch_message(int(root_id))

                    thread = await parent_msg.create_thread(
                        name=f"Confession #{parent_confession_id}"
                    )

                    CONFESSION_THREAD_MAP[root_id]["thread_id"] = thread.id
                    save_confession_map()

                    sent = await thread.send(embed=embed)

                # ================================================
                # THREAD SUDAH ADA
                # ================================================
                else:
                    thread = await self.bot.fetch_channel(int(data["thread_id"]))

                    # Semua reply selalu reference ke ROOT
                    try:
                        parent_channel = interaction.guild.get_channel(int(data["channel_id"]))
                        reference_target = await parent_channel.fetch_message(int(root_id))
                    except:
                        reference_target = None

                    sent = await thread.send(
                        embed=embed,
                        reference=reference_target,
                        mention_author=False
                    )

                # ================================================
                # SAVE REPLY MAPPING
                # ================================================
                CONFESSION_THREAD_MAP[sent.id] = {
                    "thread_id": thread.id,
                    "channel_id": data["channel_id"],
                    "is_parent": False,
                    "confession_id": parent_confession_id,
                    "root_parent_id": root_id
                }
                save_confession_map()

                await sent.edit(view=ThreadReplyView(self.bot, sent.id))

                return await interaction.response.send_message(
                    "✅ Balasan kamu sudah dikirim!",
                    ephemeral=True
                )

            # ----------------------------------------------------
            # ================ NEW CONFESSION ====================
            # ----------------------------------------------------
            db = connect_db()
            channel_id = get_channel_settings(db, interaction.guild_id, "confession")
            db.close()

            target_channel = (
                interaction.guild.get_channel(int(channel_id))
                if channel_id else interaction.channel
            )

            sent = await target_channel.send(embed=embed)

            CONFESSION_THREAD_MAP[sent.id] = {
                "thread_id": None,
                "channel_id": target_channel.id,
                "is_parent": True,
                "confession_id": confession_id
            }
            save_confession_map()

            view = discord.ui.View(timeout=None)
            view.add_item(SubmitConfessionButton(self.bot))
            view.add_item(SubmitImageConfessionButton(self.bot))
            view.add_item(ReplyToConfessionButton(self.bot, sent.id))
            await sent.edit(view=view)

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

        # ========================================================
        # ERROR FALLBACK
        # ========================================================
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
        message_id = int(custom_id.split("_")[-1])
        return cls(bot, message_id)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            ConfessionModal(
                self.bot,
                reply_thread=None,
                parent_message_id=self.message_id
            )
        )


# ==============================
# VIEWS
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

    # Persist view utama
    bot.add_view(ConfessionView(bot))

    # Dynamic reply button restore
    bot.add_dynamic_items("confess_reply_", lambda custom_id: ReplyToConfessionButton.from_custom_id(bot, custom_id))

    # Restore semua tombol dari file
    await restore_reply_buttons(bot)

    # Cleanup mapping invalid
    cleanup_confession_map()
