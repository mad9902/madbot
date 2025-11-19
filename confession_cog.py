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
    get_channel_settings
)

CONFESSION_THREAD_MAP = {}
MAP_FILE = "confession_map.json"

# ======================================================
#  STORAGE
# ======================================================

def save_confession_map():
    with open(MAP_FILE, "w") as f:
        json.dump(CONFESSION_THREAD_MAP, f)


def load_confession_map():
    global CONFESSION_THREAD_MAP
    try:
        if not os.path.exists(MAP_FILE):
            print("[ConfessionMap] MAP_FILE tidak ada, pakai map kosong.")
            CONFESSION_THREAD_MAP = {}
            return

        size = os.path.getsize(MAP_FILE)
        print(f"[ConfessionMap] MAP_FILE ditemukan, size = {size} bytes")

        if size == 0:
            print("[ConfessionMap] MAP_FILE kosong, set map kosong.")
            CONFESSION_THREAD_MAP = {}
            return

        with open(MAP_FILE, "r") as f:
            raw = json.load(f)
            CONFESSION_THREAD_MAP = {}
            for k, v in raw.items():
                try:
                    ik = int(k)
                except ValueError:
                    print(f"[ConfessionMap] KEY bukan int: {k}, skip")
                    continue

                CONFESSION_THREAD_MAP[ik] = v

        print(f"[ConfessionMap] Loaded {len(CONFESSION_THREAD_MAP)} entries dari file.")
        # Optional: print beberapa contoh
        for i, (mid, data) in enumerate(CONFESSION_THREAD_MAP.items()):
            if i >= 5:
                break
            print(f"[ConfessionMap] Sample {i}: mid={mid}, data={data}")

    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[ConfessionMap] ERROR saat load file: {e}")
        CONFESSION_THREAD_MAP = {}


def cleanup_confession_map():
    valid = {}
    for mid, data in CONFESSION_THREAD_MAP.items():
        if isinstance(data, dict) and "channel_id" in data:
            valid[int(mid)] = data
    with open(MAP_FILE, "w") as f:
        json.dump(valid, f)


# ======================================================
#  BUTTON RESTORE
# ======================================================

async def restore_reply_buttons(bot: commands.Bot):
    print("====================================================")
    print("[Restore] MULAI restore_reply_buttons")
    print(f"[Restore] Total entry di CONFESSION_THREAD_MAP: {len(CONFESSION_THREAD_MAP)}")
    print("====================================================")

    for message_id, data in CONFESSION_THREAD_MAP.items():
        print("----------------------------------------------------")
        print(f"[Restore] Proses message_id={message_id} | data={data}")

        try:
            # Validasi basic
            if not isinstance(data, dict):
                print(f"[Restore] SKIP message_id={message_id} karena data bukan dict: {type(data)}")
                continue

            channel_id = data.get("channel_id")
            thread_id = data.get("thread_id")

            print(f"[Restore] channel_id={channel_id}, thread_id={thread_id}")

            if not channel_id:
                print(f"[Restore] SKIP message_id={message_id} karena channel_id kosong / None")
                continue

            # ====== FETCH PARENT CHANNEL ======
            try:
                parent_ch = await bot.fetch_channel(channel_id)
                print(f"[Restore] parent_ch fetched: {parent_ch} (type={type(parent_ch)})")
            except Exception as e:
                print(f"[Restore] GAGAL fetch_channel({channel_id}) → {repr(e)}")
                continue

            if not isinstance(parent_ch, discord.TextChannel):
                print(f"[Restore] SKIP message_id={message_id} karena parent_ch bukan TextChannel (type={type(parent_ch)})")
                continue

            # ====== FETCH PARENT MESSAGE ======
            try:
                parent_msg = await parent_ch.fetch_message(int(message_id))
                print(f"[Restore] parent_msg fetched: id={parent_msg.id}, content={parent_msg.content!r}")
            except Exception as e:
                print(f"[Restore] GAGAL fetch_message di channel {channel_id} untuk mid={message_id} → {repr(e)}")
                continue

            # ====== BUILD & REGISTER VIEW UNTUK PARENT ======
            try:
                view = ConfessionView(bot)
                # pastikan pakai int(message_id)
                view.add_item(ReplyToConfessionButton(bot, int(message_id)))
                bot.add_view(view)
                print(f"[Restore] Berhasil add_view untuk parent message_id={message_id}")

                await parent_msg.edit(view=view)
                print(f"[Restore] Berhasil edit parent_msg id={message_id} (tambah view).")
            except Exception as e:
                print(f"[Restore] GAGAL set view pada parent_msg id={message_id} → {repr(e)}")

            # ====== RESTORE THREAD (JIKA ADA) ======
            if thread_id:
                print(f"[Restore] Coba restore thread dengan thread_id={thread_id}")
                try:
                    thread = await bot.fetch_channel(thread_id)
                    print(f"[Restore] Thread fetched: {thread} (type={type(thread)})")
                except Exception as e:
                    print(f"[Restore] GAGAL fetch thread {thread_id} → {repr(e)}")
                    continue

                try:
                    async for msg in thread.history(limit=None):
                        if msg.author.id != bot.user.id:
                            continue
                        print(f"[Restore] Tambah view ke thread msg id={msg.id}")

                        v = ThreadReplyView(bot, msg.id)
                        bot.add_view(v)
                        try:
                            await msg.edit(view=v)
                            print(f"[Restore] Berhasil edit thread msg {msg.id}")
                        except Exception as e_msg:
                            print(f"[Restore] GAGAL edit thread msg {msg.id} → {repr(e_msg)}")
                except Exception as e_hist:
                    print(f"[Restore] ERROR saat iterasi history thread {thread_id} → {repr(e_hist)}")

        except Exception as e:
            # Ini last-resort kalau ada error di luar yang lain
            print("[Restore Error] Exception tak terduga:", repr(e))

    print("====================================================")
    print("[Restore] SELESAI restore_reply_buttons")
    print("====================================================")

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

        # OPEN DM
        try:
            dm = await interaction.user.create_dm()
            await dm.send("📸 Kirim gambar/video max 5MB + caption (opsional).")
        except:
            await interaction.followup.send(
                "❌ Tidak dapat mengirim DM. Aktifkan DM dulu.",
                ephemeral=True
            )

        await interaction.response.send_message("📨 Cek DM kamu!", ephemeral=True)

        # WAIT FOR ATTACHMENT
        def check(msg):
            return (
                msg.author.id == interaction.user.id
                and isinstance(msg.channel, discord.DMChannel)
                and len(msg.attachments) > 0
            )

        try:
            msg = await self.bot.wait_for("message", timeout=120, check=check)
        except asyncio.TimeoutError:
            return await dm.send("⏱️ Waktu habis.")

        att = msg.attachments[0]

        if att.size > 5 * 1024 * 1024:
            return await dm.send("❌ File lebih dari 5MB.")

        caption = msg.content or " "
        confession_id = str(uuid.uuid4())[:8]

        # SAVE TEMP
        tmp_dir = "/tmp" if os.name != "nt" else "temp"
        os.makedirs(tmp_dir, exist_ok=True)

        temp_path = os.path.join(tmp_dir, f"{uuid.uuid4().hex}_{att.filename}")

        # Download RAW BYTES — anti-corrupt
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

        # Video or animated GIF
        if att.filename.lower().endswith((".mp4", ".mov", ".webm", ".mkv", ".gif")):
            # Embed TETAP ADA
            embed.description = f'"{caption}"'
            # Jangan set_image untuk video/gif
            sent = await target_ch.send(embed=embed, file=file)

        # Image
        else:
            embed.set_image(url=f"attachment://{att.filename}")
            sent = await target_ch.send(embed=embed, file=file)

        try:
            os.remove(temp_path)
        except:
            pass

        # SAVE MAP
        CONFESSION_THREAD_MAP[sent.id] = {
            "thread_id": None,
            "channel_id": target_ch.id,
            "is_parent": True,
            "confession_id": confession_id
        }
        save_confession_map()

        # BUTTONS
        view = discord.ui.View(timeout=None)
        view.add_item(SubmitConfessionButton(self.bot))
        view.add_item(SubmitImageConfessionButton(self.bot))
        view.add_item(ReplyToConfessionButton(self.bot, sent.id))
        await sent.edit(view=view)

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
    def __init__(self, bot: commands.Bot, message_id: int):
        super().__init__(timeout=None)
        self.add_item(ReplyToConfessionButton(bot, message_id))


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
            raw = CONFESSION_THREAD_MAP.get(self.parent_message_id)

            if raw:
                # Jika ini reply ke reply → ambil parent direct-nya
                parent_id = self.parent_message_id
                parent_data = CONFESSION_THREAD_MAP.get(parent_id)


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

            if not parent_id or not parent_data:
                await interaction.followup.send(
                    "❌ Confession yang kamu reply tidak ditemukan.",
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

                # simpan thread id
                CONFESSION_THREAD_MAP[parent_id]["thread_id"] = thread.id
                save_confession_map()

                # Reply pertama → TIDAK PAKAI reference
                sent = await thread.send(
                    embed=embed,
                    mention_author=False
                )

            # simpan mapping reply
            CONFESSION_THREAD_MAP[sent.id] = {
                "thread_id": thread.id,
                "channel_id": parent_data["channel_id"],
                "is_parent": False,
                "confession_id": confession_id,
                "parent_id": parent_id
            }
            save_confession_map()

            await sent.edit(view=ThreadReplyView(self.bot, sent.id))

            return await interaction.followup.send(
                "✅ Balasan kamu sudah dikirim!",
                ephemeral=True
            )



            # # ============================
            # # BUILD JUMP LINK
            # # ============================
            # guild_id = interaction.guild.id
            # channel_id = parent_data["channel_id"] if parent_data.get("is_parent", False) \
            #             else parent_data["thread_id"]
            # msg_link = f"https://discord.com/channels/{guild_id}/{channel_id}/{parent_id}"

            # embed.description = f'"{content}"'

            # # ===================================================
            # # Thread handling
            # # ===================================================
            # thread = None

            # # Thread belum ada
            # if parent_data.get("thread_id") is None:
            #     thread = await parent_msg.create_thread(
            #         name=f"Confession #{parent_confess_id}"
            #     )
            #     CONFESSION_THREAD_MAP[parent_id]["thread_id"] = thread.id
            #     save_confession_map()

            #     # ❗ Reply pertama TIDAK BOLEH pakai reference
            #     sent = await thread.send(
            #         embed=embed,
            #         reference=parent_msg,
            #         mention_author=False
            #     )

            # else:
            #     # Thread sudah ada

            #     thread = await self.bot.fetch_channel(parent_data["thread_id"])
            #     # Selalu kirim reply TANPA reference (Discord melarang cross-channel reference)
            #     sent = await thread.send(
            #         embed=embed,
            #         reference=parent_msg,
            #         mention_author=False
            #     )




            # # SAVE mapping reply
            # CONFESSION_THREAD_MAP[sent.id] = {
            #     "thread_id": thread.id,
            #     "channel_id": parent_data["channel_id"],
            #     "is_parent": False,
            #     "confession_id": confession_id,
            #     "parent_id": parent_id
            # }
            # save_confession_map()

            # await sent.edit(view=ThreadReplyView(self.bot, sent.id))

            # await interaction.followup.send(
            #     "✅ Balasan kamu sudah dikirim!",
            #     ephemeral=True
            # )

        # ===================================================
        # =============== NEW CONFESSION ====================
        # ===================================================
        db = connect_db()
        channel_id = get_channel_settings(db, interaction.guild_id, "confession")
        db.close()

        target_channel = interaction.guild.get_channel(int(channel_id)) if channel_id else interaction.channel

        sent = await target_channel.send(embed=embed)

        CONFESSION_THREAD_MAP[sent.id] = {
            "message_id": sent.id,
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
        load_confession_map()

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
    print("[ConfessionCog] setup() dipanggil, mulai init cog + views + restore")

    await bot.add_cog(ConfessionCog(bot))
    print("[ConfessionCog] Cog ditambahkan")

    bot.add_view(ConfessionView(bot))
    print("[ConfessionCog] ConfessionView global terdaftar (persistent)")

    bot.add_dynamic_items(
        "confess_reply_",
        lambda cid: ReplyToConfessionButton.from_custom_id(bot, cid)
    )
    print("[ConfessionCog] dynamic_items untuk confess_reply_ terdaftar")

    print("[ConfessionCog] Panggil restore_reply_buttons...")
    await restore_reply_buttons(bot)

    print("[ConfessionCog] Panggil cleanup_confession_map...")
    cleanup_confession_map()
    print("[ConfessionCog] setup() selesai")

