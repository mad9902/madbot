import discord
from discord.ext import commands

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ghelp")
    async def help_category(self, ctx, category: str = None):

        if category is None:
            embed = discord.Embed(
                title="📘 Economy Help Menu",
                description="""
Pilih kategori:

🟢 `ghelp gamble`  
🔵 `ghelp daily`  
🟣 `ghelp duel`  
🔴 `ghelp rob`  
⚙️ `ghelp admin`
                """,
                color=discord.Color.blurple()
            )
            return await ctx.send(embed=embed)

        c = category.lower()

        # ======================================================
        # GAMBLE HELP (Blackjack ditambahkan)
        # ======================================================
        if c == "gamble":
            embed = discord.Embed(
                title="🟢 Gamble Commands",
                description="""
💰 **Earning Cash**
Cash bertambah otomatis dari chat.

🎲 **Coinflip**
`cf <jumlah>`
`cf all`

🎰 **Slots (Basic)**
`slots <jumlah>`
`slots all`

🃏 **Blackjack**
`blackjack <jumlah>`
• Animasi kartu delay 1-1  
• Dealer AI  
• React HIT / STAND  
• Auto-cancel kalau kamu left  
• Ada cooldown 5 detik  
• Blackjack bayar ×2.5

💼 **Balance**
`bal`, `balance`

🔒 **Max Bet (Admin)**
`setmaxbet <angka>`

📍 **Gamble Channel (Admin)**
`setgamblech #channel`
                """,
                color=discord.Color.green()
            )
            return await ctx.send(embed=embed)

        # ======================================================
        # DAILY
        # ======================================================
        if c == "daily":
            embed = discord.Embed(
                title="🔵 Daily Reward System",
                description="""
🎁 **Daily**
`daily`

• Reset jam 14:00 WIB
• Streak meningkat tiap hari
• Reward naik terus (200 + streak × 50)
                """,
                color=discord.Color.blue()
            )
            return await ctx.send(embed=embed)

        # ======================================================
        # DUEL
        # ======================================================
        if c == "duel":
            embed = discord.Embed(
                title="🟣 Duel System",
                description="""
🎲 **Duel**
`duel <jumlah> @user`
`duel all @user`

• Target harus accept
• Roll dadu 1–6
• Seri → rematch
• Pemenang ambil taruhan
                """,
                color=discord.Color.purple()
            )
            return await ctx.send(embed=embed)

        # ======================================================
        # ROB
        # ======================================================
        if c == "rob":
            embed = discord.Embed(
                title="🔴 Robbery System",
                description=""" 
🔪 `rob @user` → Preview curian  
🔪 `rob @user confirm` → Eksekusi

🛡 `buyprotection` → Shield 24 jam  
🛡 Anti-Rob 2 jam untuk korban sukses rob

📊 `robstatus`  
🏆 `roblb`

🛑 Admin:
`robdisable`
`robenable`
                """,
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # ======================================================
        # ADMIN
        # ======================================================
        if c == "admin":
            embed = discord.Embed(
                title="⚙️ Admin Commands (Economy)",
                description="""
📍 `setgamblech #channel`
📍 `setmaxbet <angka>`
📍 `robdisable`
📍 `robenable`
                """,
                color=discord.Color.gold()
            )
            return await ctx.send(embed=embed)

        # Fallback → help bawaan
        default_help = self.bot.get_command("help")
        if default_help:
            return await ctx.invoke(default_help)

        return await ctx.send("❌ Kategori tidak dikenal.")

async def setup(bot):
    await bot.add_cog(HelpCog(bot))
