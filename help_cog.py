import discord
from discord.ext import commands


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.remove_command("help")  # disable default help


    # ============================================================
    #  MAIN HELP COMMAND
    # ============================================================
    @commands.command(name="help")
    async def help(self, ctx, category: str = None):

        # No category → show index
        if not category:
            embed = discord.Embed(
                title="📘 MadBot Help Menu",
                description="""
Pilih kategori bantuan:

🟢 **Gamble Commands**
`help gamble`

🔵 **Daily System**
`help daily`

🟣 **Duel**
`help duel`

🔴 **Robbery System**
`help rob`

⚙️ **Admin Commands**
`help admin`
                """,
                color=discord.Color.blurple()
            )
            embed.set_footer(text="MadBot — Smart Economy System")
            return await ctx.send(embed=embed)

        category = category.lower()

        # ============================================================
        # GAMBLE HELP
        # ============================================================
        if category == "gamble":
            embed = discord.Embed(
                title="🟢 Gamble Commands",
                description="""
💰 **Earning Cash**
Cash bertambah otomatis dari chat (anti-spam + anti-duplicate).

🎲 **Coinflip**
`cf <jumlah>`
`cf all`
• Menang/kalah 50%

🎰 **Slots**
`slots <jumlah>`
`slots all`
• Payout: x2, x4, x5, x10

💼 **Balance**
`bal`
`balance`

🔒 **Set Max Bet (Admin)**
`setmaxbet <angka>`

📍 **Set Gamble Channel (Admin)**
`setgamblech #channel`
                """,
                color=discord.Color.green()
            )
            return await ctx.send(embed=embed)

        # ============================================================
        # DAILY HELP
        # ============================================================
        if category == "daily":
            embed = discord.Embed(
                title="🔵 Daily Reward System",
                description="""
🎁 **Daily**
`daily`
• Reset harian jam 14:00 WIB
• Streak meningkat tiap hari
• Reward bertambah sesuai streak:
  • Base 200 + (streak × 50)

💰 Contoh:
Hari 1 → 200  
Hari 10 → 650  
Hari 30 → 1700  
                """,
                color=discord.Color.blue()
            )
            return await ctx.send(embed=embed)

        # ============================================================
        # DUEL HELP
        # ============================================================
        if category == "duel":
            embed = discord.Embed(
                title="🟣 Duel System",
                description="""
🎲 **Duel**
`duel <jumlah> @user`
`duel all @user`

• User A menantang user B  
• User B harus accept/decline  
• Roll dadu 1–6  
• Jika seri → rematch otomatis  
• Pemenang mendapat jumlah taruhan  
• Tidak bisa duel diri sendiri atau bot  
• Anti-abuse: tidak bisa duel saat pending duel lain
                """,
                color=discord.Color.purple()
            )
            return await ctx.send(embed=embed)

        # ============================================================
        # ROB HELP
        # ============================================================
        if category == "rob":
            embed = discord.Embed(
                title="🔴 Robbery System",
                description="""
🔪 **Rob Target**
`rob @user`
→ Menampilkan preview:
• Berapa yang akan dicuri (5–10%)
• Risiko gagal (10% kehilangan sendiri)
• Chance sukses (dynamic 35–65%)

🔪 **Confirm Rob**
`rob @user confirm`
→ Eksekusi rob setelah preview

🛡 **Buy Protection**
`buyprotection`
• 500 cash
• Kebal rob selama 24 jam

🛡 **Anti-Rob 2 Jam**
• Korban sukses rob → otomatis aman 2 jam

📊 **Rob Status**
`robstatus`

🏆 **Rob Leaderboard**
`roblb`

🛑 **Disable/Enable Rob (Admin)**
`robdisable`
`robenable`
                """,
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # ============================================================
        # ADMIN HELP
        # ============================================================
        if category == "admin":
            embed = discord.Embed(
                title="⚙️ Admin Commands",
                description="""
📍 **Gamble Settings**
`setgamblech #channel`
`setmaxbet <angka>`

🛑 **Rob Toggle**
`robdisable`
`robenable`

(Owner server + User ID master)
                """,
                color=discord.Color.gold()
            )
            return await ctx.send(embed=embed)

        # ============================================================
        # UNKNOWN CATEGORY
        # ============================================================
        else:
            return await ctx.send("❌ Kategori tidak dikenal. Gunakan `help` untuk daftar kategori.")



async def setup(bot):
    await bot.add_cog(HelpCog(bot))
