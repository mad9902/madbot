import discord
from discord.ext import commands
from database import connect_db, add_banned_word, get_all_banned_words
from discord import ui, Interaction


ALLOWED_USER_ID = 416234104317804544
VALID_TYPES = {"female", "partnership", "pelanggaran"}

class PaginationView(ui.View):
    def __init__(self, embeds):
        super().__init__(timeout=60)
        self.embeds = embeds
        self.current = 0

    @ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: Interaction, button: ui.Button):
        if self.current > 0:
            self.current -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)

    @ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: Interaction, button: ui.Button):
        if self.current < len(self.embeds) - 1:
            self.current += 1
            await interaction.response.edit_message(embed=self.embeds[self.current], view=self)


class BannedWordsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    @commands.command(name="listreplywords", help="Menampilkan daftar kata terlarang yang disetel.")
    async def list_banned_words(self, ctx):
        db = connect_db()
        banned_words = get_all_banned_words(db, ctx.guild.id)
        db.close()

        if not banned_words:
            return await ctx.send("🚫 Belum ada kata terlarang yang disetel.")

        # Bagi jadi beberapa halaman (misal 5 per embed)
        pages = []
        per_page = 5
        for i in range(0, len(banned_words), per_page):
            chunk = banned_words[i:i+per_page]
            desc = ""
            for word, response, word_type in chunk:
                type_label = f"`{word_type}`" if word_type else "`-`"
                desc += f"• **Kata:** `{word}`\n  🏷️ **Tipe:** {type_label}\n  💬 {response}\n\n"

            embed = discord.Embed(
                title=f"📋 Daftar Kata Terlarang ({i+1}–{min(i+per_page, len(banned_words))} dari {len(banned_words)})",
                description=desc,
                color=discord.Color(int("C9DFEC", 16))
            )
            embed.set_footer(text="Gunakan tombol ⬅️ ➡️ untuk pindah halaman.")
            pages.append(embed)

        # Jika hanya 1 halaman, langsung kirim
        if len(pages) == 1:
            return await ctx.send(embed=pages[0])

        # Kalau >1 halaman → pakai UI Button
        await ctx.send(embed=pages[0], view=PaginationView(pages))


    @commands.command(name="replywords", help="Tambah kata. Format: replywords <kata> | <respon> | <type (opsional)>")
    async def add_banned_word_cmd(self, ctx, *, arg: str = None):
        if not arg or "|" not in arg:
            return await ctx.send("❗ Format salah. Contoh: `replywords doxxing | Jangan lakukan doxxing! | pelanggaran`")

        if not (ctx.author.guild_permissions.administrator or ctx.author.id == ALLOWED_USER_ID):
            return await ctx.send("❌ Hanya admin atau user tertentu yang boleh menambahkan kata terlarang.")

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
    
    @commands.command(name="removereplywords", help="Hapus kata terlarang. Format: delword <kata>")
    async def delete_banned_word(self, ctx, *, word: str = None):
        if not word:
            return await ctx.send("❗ Format salah. Contoh: `delword spam`")

        if not (ctx.author.guild_permissions.administrator or ctx.author.id == ALLOWED_USER_ID):
            return await ctx.send("❌ Hanya admin atau user tertentu yang boleh menghapus kata terlarang.")

        db = connect_db()
        from database import remove_banned_word
        remove_banned_word(db, ctx.guild.id, word)
        db.close()

        await ctx.send(f"✅ Kata terlarang '**{word}**' telah dihapus dari database.")


    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        if message.content.startswith(tuple(await self.bot.get_prefix(message))):
            return

        db = connect_db()
        banned_words = get_all_banned_words(db, message.guild.id)  # returns (word, response, type)
        db.close()

        content_lower = message.content.lower()

        for word, response, word_type in banned_words:
            if word in content_lower:
                word_upper = word.upper()

                # 🎨 Embed style per type
                if word_type == "female":
                    title = f"🔍`{word_upper}`"
                    color = discord.Color.purple()
                    footer = "Pengguna ini mungkin perlu verifikasi cewek."
                elif word_type == "partnership":
                    title = f"🤝`{word_upper}`"
                    color = discord.Color.blue()
                    footer = "Dilarang promosi server tanpa izin staff."
                elif word_type == "pelanggaran":
                    title = f"❗`{word_upper}`"
                    color = discord.Color.red()
                    footer = "Pelanggaran terhadap peraturan server."
                else:
                    title = f"⚠️ `{word_upper}`"
                    color = discord.Color(int("C9DFEC", 16))
                    footer = "Harap berhati-hati menggunakan kata ini."

                embed = discord.Embed(
                    title=title,
                    description=f"{response}",
                    color=color
                )
                embed.set_footer(text=footer)

                await message.channel.send(embed=embed)
                break

        await self.bot.process_commands(message)
