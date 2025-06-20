import discord
from discord.ext import commands
from database import connect_db, set_afk, get_afk, clear_afk

class AFK(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Command untuk mengaktifkan AFK
    @commands.command(name="afk", help="Menandai kamu sedang AFK")
    async def afk(self, ctx, *, reason="Tidak ada alasan"):
        db = connect_db()
        set_afk(db, ctx.author.id, ctx.guild.id, reason)
        db.close()

        try:
            await ctx.author.edit(nick=f"[AFK] {ctx.author.display_name}")
        except discord.Forbidden:
            pass  # Bot tidak punya izin untuk ubah nickname

        await ctx.send(f"💤 {ctx.author.mention} sekarang AFK: `{reason}`")

    # Event listener untuk menghapus status AFK saat user kirim pesan
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        # ⛔ Abaikan jika pesan adalah command
        if message.content.startswith(tuple(await self.bot.get_prefix(message))):
            return

        db = connect_db()
        
        # ➤ Cek dan hapus status AFK si pengirim
        afk_status = get_afk(db, message.author.id, message.guild.id)
        if afk_status:
            clear_afk(db, message.author.id, message.guild.id)
            try:
                if message.author.display_name.startswith("[AFK] "):
                    new_nick = message.author.display_name.replace("[AFK] ", "", 1)
                    await message.author.edit(nick=new_nick)
            except discord.Forbidden:
                pass
            await message.channel.send(f"✅ Selamat datang kembali, {message.author.mention}! Status AFK kamu telah dihapus.")

        # ➤ Cek apakah ada user yang disebut dan sedang AFK
        afk_mentions = []
        for user in message.mentions:
            reason = get_afk(db, user.id, message.guild.id)
            if reason:
                afk_mentions.append(f"🔕 {user.display_name} sedang AFK: `{reason}`")

        if afk_mentions:
            await message.channel.send("\n".join(afk_mentions))

        db.close()


async def setup(bot):
    await bot.add_cog(AFK(bot))
