import discord
from discord.ext import commands

ALLOWED_ROLE_ID = 416234104317804544  # ID rolenya kamu

class MassDM(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_allowed_user(self, ctx):
        return (
            ctx.author.id == ctx.guild.owner_id or
            ctx.author.guild_permissions.administrator or
            discord.utils.get(ctx.author.roles, id=ALLOWED_ROLE_ID) is not None
        )

    @commands.command(name="bc", help="DM semua member dengan role tertentu. Contoh: mbc @Role Pesan penting")
    async def mbc_command(self, ctx, role: discord.Role, *, message: str = None):
        if not self.is_allowed_user(ctx):
            return await ctx.send("❌ Kamu tidak diizinkan menggunakan perintah ini.")

        if not message:
            return await ctx.send("❗ Harap berikan pesan yang ingin dikirim ke pengguna dengan role tersebut.")

        members = [member for member in role.members if not member.bot]
        if not members:
            return await ctx.send(f"❌ Tidak ada member dengan role {role.mention}.")

        await ctx.send(f"📬 Mengirim DM ke {len(members)} member dengan role {role.mention}...")

        success = 0
        fail = 0

        for member in members:
            try:
                await member.send(f"📢 Pesan dari server **{ctx.guild.name}**:\n{message}")
                success += 1
            except Exception as e:
                print(f"[mbc ERROR] Gagal kirim ke {member}: {e}")
                fail += 1

        await ctx.send(f"✅ DM berhasil dikirim ke {success} member. Gagal: {fail}")

    @mbc_command.error
    async def mbc_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❗ Format salah. Gunakan: `bc @Role Pesan kamu`.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❗ Tidak dapat mengenali role. Mention role seperti ini: `@Role`.")
        else:
            print(f"[mbc_command ERROR] {error}")
            await ctx.send("❌ Terjadi error saat menjalankan perintah.")

async def setup(bot):
    await bot.add_cog(MassDM(bot))
