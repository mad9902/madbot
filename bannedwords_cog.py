import discord
from discord.ext import commands
from database import connect_db, add_banned_word, get_all_banned_words, remove_banned_word, get_feature_status, set_feature_status
from discord import ui, Interaction
from streak_cog import BLOCKED_MESSAGES

ALLOWED_USER_ID = 416234104317804544
VALID_TYPES = {"female", "partnership", "pelanggaran"}

class PaginationView(ui.View):
    def __init__(self, embeds):
        super().__init__(timeout=60)
        self.embeds = embeds
        self.current = 0
        self.update_buttons()

    def update_buttons(self):
        self.previous.disabled = self.current == 0
        self.next.disabled = self.current == len(self.embeds) - 1

    @ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: Interaction, button: ui.Button):
        if self.current > 0:
            self.current -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)

    @ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: Interaction, button: ui.Button):
        if self.current < len(self.embeds) - 1:
            self.current += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)


class BannedWordsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="listreplywords", help="Menampilkan daftar kata yang disetel.")
    async def list_banned_words(self, ctx):
        db = connect_db()
        banned_words = get_all_banned_words(db, ctx.guild.id)
        db.close()

        if not banned_words:
            return await ctx.send("🚫 Belum ada kata yang disetel.")

        pages = []
        per_page = 5
        for i in range(0, len(banned_words), per_page):
            chunk = banned_words[i:i+per_page]
            desc = ""
            for word, response, word_type in chunk:
                type_label = f"`{word_type}`" if word_type else "`-`"
                desc += f"• **Kata:** `{word}`\n🏷️ **Tipe:** {type_label}\n💬 {response}\n\n"

            embed = discord.Embed(
                title=f"📋 Daftar Kata ({i+1}–{min(i+per_page, len(banned_words))} dari {len(banned_words)})",
                description=desc,
                color=discord.Color(int("C9DFEC", 16))
            )
            embed.set_footer(text="Gunakan tombol ⬅️ ➡️ untuk pindah halaman.")
            pages.append(embed)

        await ctx.send(embed=pages[0], view=PaginationView(pages))

    @commands.command(name="replywords", help="Tambah kata. Format: replywords <kata> | <respon> | <type (opsional)>")
    async def add_banned_word_cmd(self, ctx, *, arg: str = None):
        if not arg or "|" not in arg:
            return await ctx.send("❗ Format salah. Contoh: `replywords doxxing | Jangan lakukan doxxing! | pelanggaran`")

        if not (ctx.author.guild_permissions.administrator or ctx.author.id == ALLOWED_USER_ID):
            return await ctx.send("❌ Hanya admin atau user tertentu yang boleh menambahkan kata.")

        parts = [p.strip() for p in arg.split("|")]
        if len(parts) < 2:
            return await ctx.send("❗ Format tidak lengkap. Harus ada kata dan respon.")

        word = parts[0]
        response = parts[1]
        word_type = parts[2].lower() if len(parts) > 2 else None

        if word_type and word_type not in VALID_TYPES:
            return await ctx.send("❌ Jenis/type tidak valid. Gunakan: `female`, `partnership`, atau `pelanggaran`.")

        db = connect_db()
        add_banned_word(db, ctx.guild.id, word.lower(), response, word_type)
        db.close()

        embed = discord.Embed(
            title="✅ KATA DITAMBAHKAN",
            description=f"• **Kata**: `{word}`\n• **Respon**: {response}",
            color=discord.Color(int("C9DFEC", 16))
        )
        if word_type:
            embed.add_field(name="Tipe", value=word_type.capitalize(), inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="removereplywords", help="Hapus kata. Format: delword <kata>")
    async def delete_banned_word(self, ctx, *, word: str = None):
        if not word:
            return await ctx.send("❗ Format salah. Contoh: `delword spam`")

        if not (ctx.author.guild_permissions.administrator or ctx.author.id == ALLOWED_USER_ID):
            return await ctx.send("❌ Hanya admin atau user tertentu yang boleh menghapus kata.")

        db = connect_db()
        remove_banned_word(db, ctx.guild.id, word)
        db.close()

        await ctx.send(f"✅ Kata '**{word}**' telah dihapus dari database.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.id in BLOCKED_MESSAGES:
            return
        if message.author.bot or not message.guild:
            return
        
        if getattr(message, "_streak_block", False):
            return

        # ⛔ Cek jika fitur reply_words sedang dimatikan
        db = connect_db()
        if not get_feature_status(db, message.guild.id, 'reply_words'):
            db.close()
            return

        banned_words = get_all_banned_words(db, message.guild.id)
        db.close()

        prefixes = await self.bot.get_prefix(message)
        content = message.content

        is_valid_command = False

        for p in prefixes:
            if content.startswith(p):
                # ambil kata setelah prefix
                after = content[len(p):].strip().split(" ")[0].lower()

                # cek apakah kata setelah prefix memang nama command bot
                if after in self.bot.all_commands:
                    is_valid_command = True
                break

        if is_valid_command:
            return


        content_lower = message.content.lower()

        for word, response, word_type in banned_words:
            if word in content_lower:
                # ⬇️ Send embed seperti biasa
                word_upper = word.upper()

                if word_type == "female":
                    title = f"🔍 `{word_upper}`"
                    color = discord.Color.purple()
                    footer = "Pengguna ini mungkin perlu verifikasi cewek."
                elif word_type == "partnership":
                    title = f"🤝 `{word_upper}`"
                    color = discord.Color.blue()
                    footer = "Dilarang promosi server tanpa izin staff."
                elif word_type == "pelanggaran":
                    title = f"❗ `{word_upper}`"
                    color = discord.Color.red()
                    footer = "Pelanggaran terhadap peraturan server."
                else:
                    title = f"⚠️ `{word_upper}`"
                    color = discord.Color(int("C9DFEC", 16))
                    footer = "We hope you enjoy your time in this server!"

                embed = discord.Embed(
                    title=title,
                    description=response,
                    color=color
                )
                embed.set_footer(text=footer)

                await message.channel.send(embed=embed)
                break
            
        message._from_bannedwords = True

        await self.bot.process_commands(message)

    @commands.command(name="togglereplywords", help="Aktif/nonaktifkan fitur auto reply kata.")
    @commands.has_permissions(administrator=True)
    async def toggle_reply_words(self, ctx, status: str):
        status = status.lower()
        if status not in ["on", "off"]:
            return await ctx.send("❗ Gunakan `on` atau `off`. Contoh: `mtogglereplywords on`")

        db = connect_db()
        set_feature_status(db, ctx.guild.id, "reply_words", status == "on")
        db.close()

        await ctx.send(f"✅ Fitur reply_words telah {'diaktifkan' if status == 'on' else 'dinonaktifkan'}.")

        
    @commands.command(name="replywordstatus", help="Cek status fitur reply_words.")
    async def reply_words_status(self, ctx):
        db = connect_db()
        status = get_feature_status(db, ctx.guild.id, "reply_words")
        db.close()
        await ctx.send(f"💬 Fitur reply_words saat ini: {'Aktif ✅' if status else 'Nonaktif ❌'}")
