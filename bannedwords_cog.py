import discord
from discord.ext import commands
from database import connect_db, add_banned_word, get_all_banned_words

ALLOWED_USER_ID = 416234104317804544

class BannedWordsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="replywords", help="Tambah kata terlarang. Format: replywords <kata> | <respon>")
    async def add_banned_word_cmd(self, ctx, *, arg: str = None):
        if not arg or "|" not in arg:
            return await ctx.send("❗ Format salah. Contoh: `replywords doxxing | Jangan lakukan doxxing!`")

        if not (ctx.author.guild_permissions.administrator or ctx.author.id == ALLOWED_USER_ID):
            return await ctx.send("❌ Hanya admin atau user tertentu yang boleh menambahkan kata terlarang.")

        word, response = map(str.strip, arg.split("|", 1))
        if not word or not response:
            return await ctx.send("❗ Format tidak lengkap. Harus ada kata dan respon.")

        db = connect_db()
        add_banned_word(db, ctx.guild.id, word.lower(), response)
        db.close()

        await ctx.send(f"✅ Kata terlarang '**{word}**' telah ditambahkan dengan respon:\n> {response}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        # ⛔ Abaikan command (jangan diperiksa kata terlarang)
        if message.content.startswith(tuple(await self.bot.get_prefix(message))):
            return

        db = connect_db()
        banned_words = get_all_banned_words(db, message.guild.id)
        db.close()

        content_lower = message.content.lower()

        for word, response in banned_words:
            if word in content_lower:
                await message.channel.send(response, delete_after=10)
                break  # hanya satu pelanggaran diproses

        await self.bot.process_commands(message)
