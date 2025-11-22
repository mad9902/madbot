import discord
from discord.ext import commands
import uuid
import asyncio
import json
import aiohttp
import os
from database import (
    save_confession,
    connect_db,
    set_channel_settings,
    get_channel_settings,
    save_confession_db,          # NEW
    get_all_confession_messages, # NEW
    get_confession_by_message
)
import time
IMAGE_SUBMIT_COOLDOWN = {}

# ======================================================
#  BUTTON RESTORE
# ======================================================

async def restore_reply_buttons(bot: commands.Bot):
    db = connect_db()
    rows = get_all_confession_messages(db)
    db.close()

    for row in rows:
        msg_id = row["id"]
        
        # Kalau parent → register view ConfessionView
        if row["is_parent"]:
            view = ConfessionView(bot)
            view.add_item(ReplyToConfessionButton(bot, msg_id))
            bot.add_view(view, message_id=msg_id)


        # Kalau reply → register ThreadReplyView
        else:
            view = ThreadReplyView()
            view.add_item(ReplyToConfessionButton(bot, msg_id))
            bot.add_view(view, message_id=msg_id)


# ======================================================
# BUTTON — SUBMIT CONFESSION
# ======================================================

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
                "❌ Tidak bisa membuat confession baru dari dalam thread.",
                ephemeral=True
            )
        await interaction.response.send_modal(
            ConfessionModal(self.bot)
        )


# ======================================================
# BUTTON — REPLY
# ======================================================

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
        mid = int(custom_id.split("_")[-1])
        return cls(bot, mid)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            ConfessionModal(
                self.bot,
                parent_message_id=self.message_id
            )
        )


# ======================================================
# BUTTON — IMAGE CONFESSION
# ======================================================

class SubmitImageConfessionButton(discord.ui.Button):
    def __init__(self, bot: commands.Bot):
        super().__init__(
            label="Submit with image / video",
            style=discord.ButtonStyle.green,
            custom_id="confess_image_submit"
        )
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        now = time.time()

        # ========== CEK COOLDOWN PER USER ==========
        last = IMAGE_SUBMIT_COOLDOWN.get(user_id, 0)
        COOLDOWN = 30  # detik

        if now - last < COOLDOWN:
            sisa = round(COOLDOWN - (now - last), 1)
            return await interaction.response.send_message(
                f"⏱️ Kamu terlalu cepat! Coba lagi dalam **{sisa}s**.",
                ephemeral=True
            )

        # set timestamp baru
        IMAGE_SUBMIT_COOLDOWN[user_id] = now

        # ========== LANJUT PROSES NORMAL ==========
        # OPEN DM
        try:
            dm = await interaction.user.create_dm()
            await dm.send("📸 Kirim gambar/video max 5MB + caption (opsional). Waktu kamu hanya 30 detik")
        except:
            return await interaction.response.send_message(
                "❌ Tidak dapat mengirim DM. Aktifkan DM dulu.",
                ephemeral=True
            )

        await interaction.response.send_message("📨 Cek DM kamu!", ephemeral=True)

        # WAIT ATTACHMENT
        def check(msg):
            return (
                msg.author.id == user_id
                and isinstance(msg.channel, discord.DMChannel)
                and len(msg.attachments) > 0
            )

        try:
            msg = await self.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            return await dm.send("⏱️ Waktu habis.")

        att = msg.attachments[0]

        if att.size > 5 * 1024 * 1024:
            return await dm.send("❌ File lebih dari 5MB.")

        # ========== LANJUTKAN PROSES ASLI ==========

        caption = msg.content or " "
        confession_id = str(uuid.uuid4())[:8]

        # SAVE TEMP
        tmp_dir = "/tmp" if os.name != "nt" else "temp"
        os.makedirs(tmp_dir, exist_ok=True)
        temp_path = os.path.join(tmp_dir, f"{uuid.uuid4().hex}_{att.filename}")

        # Download file
        async with aiohttp.ClientSession() as session:
            async with session.get(att.url) as resp:
                if resp.status != 200:
                    return await dm.send("❌ Gagal download file.")
                with open(temp_path, "wb") as f:
                    f.write(await resp.read())

        # GET TARGET CHANNEL
        db = connect_db()
        channel_id = get_channel_settings(db, interaction.guild_id, "confession")
        db.close()

        target_ch = interaction.guild.get_channel(int(channel_id))

        # BUILD EMBED
        embed = discord.Embed(
            title=f"Anonymous Confession (#{confession_id})",
            description=f'"{caption}"',
            color=discord.Color.dark_gray()
        )

        file = discord.File(temp_path, filename=att.filename)

        if att.filename.lower().endswith((".mp4", ".mov", ".webm", ".mkv", ".gif")):
            sent = await target_ch.send(embed=embed, file=file)
        else:
            embed.set_image(url=f"attachment://{att.filename}")
            sent = await target_ch.send(embed=embed, file=file)

        try:
            os.remove(temp_path)
        except:
            pass

        # SAVE DB
        db2 = connect_db()
        save_confession_db(
            db2,
            sent.id,
            interaction.guild_id,
            target_ch.id,
            None,
            None,
            confession_id,
            True
        )
        db2.close()

        # BUTTONS
        view = ConfessionView(self.bot)
        view.add_item(ReplyToConfessionButton(self.bot, sent.id))
        # await sent.edit(view=view)

        save_confession(
            self.bot.db,
            interaction.guild_id,
            interaction.user.id,
            confession_id,
            caption
        )


        await dm.send("✅ Confession berhasil dikirim!")



# ======================================================
# VIEWS
# ======================================================

class ConfessionView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.add_item(SubmitConfessionButton(bot))
        self.add_item(SubmitImageConfessionButton(bot))


class ThreadReplyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        # no manual buttons


# ======================================================
# MODAL (HEADER SAJA — tanpa on_submit)
# ======================================================

class ConfessionModal(discord.ui.Modal, title=f"Anonymous Confession"):

    confession_input = discord.ui.TextInput(
        label="Confession",
        style=discord.TextStyle.paragraph,
        placeholder="Tulis pesanmu secara anonim...",
        max_length=1000,
        required=True
    )

    def __init__(self, bot, parent_message_id=None):
        super().__init__()
        self.bot = bot
        self.parent_message_id = parent_message_id

    async def on_submit(self, interaction: discord.Interaction):
        confession_id = str(uuid.uuid4())[:8]
        content = self.confession_input.value
        is_reply = self.parent_message_id is not None

        # ===================================================
        # NORMALISASI PARENT ID (fix reply dari dalam thread)
        # ===================================================
        parent_id = None
        parent_data = None

        await interaction.response.defer(ephemeral=True, thinking=False)


        if is_reply:
            parent_id = self.parent_message_id

            db = connect_db()
            parent_data = get_confession_by_message(db, parent_id)
            db.close()

        # ===================================================
        # Base embed
        # ===================================================
        embed = discord.Embed(
            title=f"Anonymous Confession (#{confession_id})" if not is_reply else f"Balasan Anonim (#{confession_id})",
            description=f'"{content}"',
            color=discord.Color.dark_gray()
        )

        # ===================================================
        # =============== REPLY MODE ========================
        # ===================================================
        if is_reply:

            if parent_data is None:
                return await interaction.followup.send(
                    "❌ Data confession yang kamu balas tidak ditemukan.",
                    ephemeral=True
                )


            thread = None
            parent_msg_in_thread = None

            # =========== CASE A: PARENT SUDAH PUNYA THREAD ===========
            if parent_data.get("thread_id"):
                thread = await self.bot.fetch_channel(parent_data["thread_id"])

                # coba fetch parent
                try:
                    parent_msg_in_thread = await thread.fetch_message(parent_id)
                except:
                    parent_msg_in_thread = None

                # parent ketemu → pakai reference
                if parent_msg_in_thread:
                    sent = await thread.send(
                        embed=embed,
                        reference=parent_msg_in_thread,
                        mention_author=False
                    )
                else:
                    # fallback aman
                    sent = await thread.send(
                        embed=embed,
                        mention_author=False
                    )
                    
            else:
                # =========== CASE B: PARENT BELUM PUNYA THREAD ===========
                try:
                    parent_msg_main = await interaction.guild.get_channel(
                        parent_data["channel_id"]
                    ).fetch_message(parent_id)
                except:
                    await interaction.followup.send(
                        "❌ Parent hilang.",
                        ephemeral=True
                    )

                # Buat thread
                parent_confess_id = parent_data.get("confession_id", "?")
                thread = await parent_msg_main.create_thread(
                    name=f"Confession #{parent_confess_id}"
                )
                # update thread_id di DB
                db2 = connect_db()
                save_confession_db(
                    db2,
                    parent_id,                 # update parent record
                    interaction.guild_id,
                    parent_data["channel_id"],
                    thread.id,                 # thread baru
                    None,
                    parent_data["confession_id"],
                    True                       # tetap parent
                )
                db2.close()

                # Reply pertama → TIDAK PAKAI reference
                sent = await thread.send(
                    embed=embed,
                    mention_author=False
                )


            db2 = connect_db()
            save_confession_db(
                db2,
                sent.id,
                interaction.guild_id,
                parent_data["channel_id"],
                thread.id,
                parent_id,
                confession_id,
                False   # reply, bukan parent
            )
            db2.close()

            view = ThreadReplyView()
            view.add_item(ReplyToConfessionButton(self.bot, sent.id))
            # await sent.edit(view=view)



            save_confession(
                self.bot.db,
                interaction.guild_id,
                interaction.user.id,
                confession_id,
                content
            )

            return await interaction.followup.send(
                "✅ Balasan kamu sudah dikirim!",
                ephemeral=True
            )

        # ===================================================
        # =============== NEW CONFESSION ====================
        # ===================================================
        db = connect_db()
        channel_id = get_channel_settings(db, interaction.guild_id, "confession")
        db.close()

        target_channel = interaction.guild.get_channel(int(channel_id)) if channel_id else interaction.channel

        sent = await target_channel.send(embed=embed)

      
        db2 = connect_db()
        save_confession_db(
            db2,
            sent.id,
            interaction.guild_id,
            target_channel.id,  # channel utama
            None,               # no thread
            None,               # no parent
            confession_id,
            True                # is_parent
        )
        db2.close()



        view = ConfessionView(self.bot)
        view.add_item(ReplyToConfessionButton(self.bot, sent.id))
        # await sent.edit(view=view)



        save_confession(self.bot.db, interaction.guild_id, interaction.user.id, confession_id, content)

        await interaction.followup.send(
            "✅ Confession kamu telah dikirim!",
            ephemeral=True
        )

# ======================================================
# COG
# ======================================================

class ConfessionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # load_confession_map()

    @commands.command(name="sendconfessbutton")
    async def send_confess_button(self, ctx):
        if not ctx.author.guild_permissions.manage_guild \
           and ctx.author.id != 416234104317804544:
            return await ctx.send("❌ Kamu tidak boleh menggunakan command ini.")

        view = ConfessionView(self.bot)
        embed = discord.Embed(
            title="Confessions",
            description="Klik tombol di bawah untuk mengirim confession anonim!",
            color=discord.Color.green()
        )

        await ctx.send(embed=embed, view=view)

    @commands.command(name="setconfessch")
    async def set_confession_channel(self, ctx, channel: discord.TextChannel):
        if ctx.author.id != ctx.guild.owner_id \
           and ctx.author.id != 416234104317804544:
            return await ctx.send("❌ Hanya owner server yang bisa mengatur ini.")

        db = connect_db()
        set_channel_settings(db, ctx.guild.id, "confession", channel.id)
        db.close()

        await ctx.send(f"✅ Channel confession di-set ke {channel.mention}")


# ======================================================
# SETUP
# ======================================================

async def setup(bot):

    await bot.add_cog(ConfessionCog(bot))

    bot.add_view(ConfessionView(bot))

    bot.add_dynamic_items(
        "confess_reply_",
        lambda cid: ReplyToConfessionButton.from_custom_id(bot, cid)
    )

    await restore_reply_buttons(bot)

