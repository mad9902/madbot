import discord
from discord.ext import commands
from database import connect_db, set_afk, get_afk, clear_afk

class AFK(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="afk", help="Menandai kamu sedang AFK")
    async def afk(self, ctx, *, reason="Tidak ada alasan"):
        db = connect_db()
        set_afk(db, ctx.author.id, ctx.guild.id, reason)
        db.close()

        try:
            # Gunakan nick jika ada, jika tidak fallback ke name
            new_nick = f"[AFK] {ctx.author.nick or ctx.author.name}"
            await ctx.author.edit(nick=new_nick)
        except discord.Forbidden:
            pass  # Bot tidak punya izin ubah nickname

        await ctx.send(f"💤 {ctx.author.mention} sekarang AFK: `{reason}`")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        # ⛔ Abaikan jika pesan adalah command
        if message.content.startswith(tuple(await self.bot.get_prefix(message))):
            return

        db = connect_db()

        # ➤ Hapus status AFK dari pengirim
        afk_status = get_afk(db, message.author.id, message.guild.id)
        if afk_status:
            clear_afk(db, message.author.id, message.guild.id)
            try:
                if message.author.nick and message.author.nick.startswith("[AFK] "):
                    new_nick = message.author.nick.replace("[AFK] ", "", 1)
                    await message.author.edit(nick=new_nick)
            except discord.Forbidden:
                pass
            await message.channel.send(f"✅ Selamat datang kembali, {message.author.mention}! Status AFK kamu telah dihapus.")

        # ➤ Cek user yang di-mention
        afk_mentions = []
        notified = set()
        for user in message.mentions:
            if user.id in notified:
                continue
            reason = get_afk(db, user.id, message.guild.id)
            if reason:
                afk_mentions.append(f"🔕 {user.display_name} sedang AFK: `{reason}`")
                notified.add(user.id)

        if afk_mentions:
            await message.channel.send("\n".join(afk_mentions))

        db.close()

async def setup(bot):
    await bot.add_cog(AFK(bot))
