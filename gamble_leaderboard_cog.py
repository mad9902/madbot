import discord
from discord.ext import commands
from discord.ui import View, Select, Button
from gamble_utils import comma


class LBPaginator(View):
    def __init__(self, pages):
        super().__init__(timeout=60)
        self.pages = pages
        self.index = 0

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: Button):
        if self.index > 0:
            self.index -= 1
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: Button):
        if self.index < len(self.pages) - 1:
            self.index += 1
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)


class LeaderboardView(View):
    def __init__(self, bot, ctx):
        super().__init__(timeout=60)
        self.bot = bot
        self.ctx = ctx
        self.db = bot.db

        self.select.placeholder = "Pilih kategori leaderboard…"

    @discord.ui.select(
        options=[
            discord.SelectOption(label="🪙 Global Cash", value="global_cash"),
            discord.SelectOption(label="🪙 Server Cash", value="server_cash"),
            discord.SelectOption(label="🎰 Server Gamble Wins", value="server_wins"),
            discord.SelectOption(label="🌍 Global Gamble Wins", value="global_wins"),
        ]
    )
    async def select(self, interaction: discord.Interaction, selector: Select):

        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(
                "❌ Itu bukan menu kamu.", ephemeral=True
            )

        lb_type = selector.values[0]
        rows = self.fetch(lb_type)
        pages = self.build_pages(rows, lb_type)

        paginator = LBPaginator(pages)
        await interaction.response.edit_message(
            embed=pages[0],
            view=paginator
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

        # User rank
        user_id = self.ctx.author.id
        user_rank = None
        user_value = None

        for i, row in enumerate(rows, start=1):
            if row["user_id"] == user_id:
                user_rank = i
                user_value = row.get("cash", row.get("total", 0))
                break

        if user_rank is None:
            user_rank = "Tidak masuk 50 besar"
            user_value = 0

        # Generate pages
        for i in range(0, len(rows), page_size):
            chunk = rows[i:i+page_size]
            desc = ""

            for idx, row in enumerate(chunk, start=i+1):
                user = self.ctx.guild.get_member(row["user_id"]) or f"<@{row['user_id']}>"
                val = comma(row.get("cash", row.get("total", 0)))
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

    @commands.command(name="mlb")
    async def mlb(self, ctx):
        view = LeaderboardView(self.bot, ctx)
        await ctx.send("📊 **MadBot Leaderboards** — pilih kategori:", view=view)


async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))
