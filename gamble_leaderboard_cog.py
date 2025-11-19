import discord
from discord.ext import commands
from discord.ui import View, Select, Button
from gamble_utils import comma


class LeaderboardView(View):
    def __init__(self, bot, ctx):
        super().__init__(timeout=60)
        self.bot = bot
        self.ctx = ctx
        self.db = bot.db

        # state untuk pagination
        self.pages: list[discord.Embed] = []
        self.index: int = 0
        self.current_lb_type: str | None = None

        # set placeholder select
        self.select.placeholder = "Pilih kategori leaderboard…"

    # ===============================
    # SELECT KATEGORI
    # ===============================
    @discord.ui.select(
        options=[
            discord.SelectOption(label="🪙 Global Cash", value="global_cash", description="Top cash tertinggi (global)"),
            discord.SelectOption(label="🪙 Server Cash", value="server_cash", description="Top cash khusus server ini"),
            discord.SelectOption(label="🎰 Server Gamble Wins", value="server_wins", description="Top menang judi server ini"),
            discord.SelectOption(label="🌍 Global Gamble Wins", value="global_wins", description="Top menang judi (global)"),
        ]
    )
    async def select(self, interaction: discord.Interaction, selector: Select):

        # Biar cuma si pemanggil command yang bisa pakai menu ini
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(
                "❌ Itu bukan menu kamu.", ephemeral=True
            )

        lb_type = selector.values[0]
        self.current_lb_type = lb_type

        rows = self.fetch(lb_type)
        self.pages = self.build_pages(rows, lb_type)
        self.index = 0

        # Aman: selalu minimal 1 page (kosong) dari build_pages
        await interaction.response.edit_message(
            embed=self.pages[self.index],
            view=self
        )

    # ===============================
    # BUTTON PAGINATION
    # ===============================
    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(
                "❌ Itu bukan menu kamu.", ephemeral=True
            )

        if not self.pages:
            return await interaction.response.send_message(
                "Belum ada leaderboard yang bisa dipaginate.", ephemeral=True
            )

        if self.index > 0:
            self.index -= 1

        await interaction.response.edit_message(
            embed=self.pages[self.index],
            view=self
        )

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(
                "❌ Itu bukan menu kamu.", ephemeral=True
            )

        if not self.pages:
            return await interaction.response.send_message(
                "Belum ada leaderboard yang bisa dipaginate.", ephemeral=True
            )

        if self.index < len(self.pages) - 1:
            self.index += 1

        await interaction.response.edit_message(
            embed=self.pages[self.index],
            view=self
        )

    # ===============================
    # Fetch leaderboard
    # ===============================
    def fetch(self, lb_type):
        cursor = self.db.cursor(dictionary=True)

        if lb_type == "global_cash":
            cursor.execute("""
                SELECT user_id, cash
                FROM user_cash
                ORDER BY cash DESC
                LIMIT 50
            """)

        elif lb_type == "server_cash":
            cursor.execute("""
                SELECT user_id, cash
                FROM user_cash
                WHERE user_id IN (
                    SELECT DISTINCT user_id FROM gamble_log WHERE guild_id=%s
                )
                ORDER BY cash DESC
                LIMIT 50
            """, (self.ctx.guild.id,))

        elif lb_type == "server_wins":
            cursor.execute("""
                SELECT user_id, SUM(amount) AS total
                FROM gamble_log
                WHERE guild_id=%s AND result='WIN'
                GROUP BY user_id
                ORDER BY total DESC
                LIMIT 50
            """, (self.ctx.guild.id,))

        elif lb_type == "global_wins":
            cursor.execute("""
                SELECT user_id, SUM(amount) AS total
                FROM gamble_log
                WHERE result='WIN'
                GROUP BY user_id
                ORDER BY total DESC
                LIMIT 50
            """)

        rows = cursor.fetchall()
        cursor.close()
        return rows

    # ===============================
    # Build embed pages (pagination)
    # ===============================
    def build_pages(self, rows, lb_type):
        page_size = 10
        pages = []

        title_map = {
            "global_cash": "🪙 Global Cash Leaderboard",
            "server_cash": "🪙 Server Cash Leaderboard",
            "server_wins": "🎰 Server Gamble Wins",
            "global_wins": "🌍 Global Gamble Wins",
        }

        user_id = self.ctx.author.id
        user_rank = None
        user_value = None

        # Hitung rank user kalau ada di top 50
        for i, row in enumerate(rows, start=1):
            if row["user_id"] == user_id:
                user_rank = i
                user_value = row.get("cash", row.get("total", 0))
                break

        if user_rank is None:
            user_rank = "Tidak masuk 50 besar"
            user_value = 0

        # Kalau tidak ada data sama sekali → bikin 1 page kosong tapi rapi
        if not rows:
            desc = "Belum ada data untuk leaderboard ini."
            embed = discord.Embed(
                title=title_map[lb_type],
                description=f"""
👤 **Rank kamu:** **{user_rank}**  
💰 **Nilai kamu:** **{comma(user_value)}**

**TOP LIST:**  
{desc}
""",
                color=discord.Color.gold()
            )
            pages.append(embed)
            return pages

        # Generate pages dari data yang ada
        for i in range(0, len(rows), page_size):
            chunk = rows[i:i+page_size]
            desc = ""

            for idx, row in enumerate(chunk, start=i+1):
                member = self.ctx.guild.get_member(row["user_id"])
                user = member.mention if member else f"<@{row['user_id']}>"
                val = comma(row.get("cash", row.get("total", 0)) or 0)

                desc += f"**#{idx}** {user} — **{val}**\n"

            embed = discord.Embed(
                title=title_map[lb_type],
                description=f"""
👤 **Rank kamu:** **{user_rank}**  
💰 **Nilai kamu:** **{comma(user_value)}**

**TOP LIST:**  
{desc}
""",
                color=discord.Color.gold()
            )

            pages.append(embed)

        return pages


class LeaderboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    @commands.command(name="lb")
    async def mlb(self, ctx):
        view = LeaderboardView(self.bot, ctx)
        await ctx.send("📊 **MadBot Leaderboards** — pilih kategori:", view=view)


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
