import discord
from discord.ext import commands

# ============================================================
# CATEGORY CONFIG
# ============================================================

HELP_CATEGORIES = [
    "General",
    "Image",
    "AI",
    "Games",
    "Economy",
    "XP",
    "Birthday",
    "AFK",
    "Translate",
    "Downloader",
    "Info",
    "Welcome",
    "Role",
    "TimedWords",
    "ReplyWords",
    # "Werewolf",
    "Admin",
    "Streak",
    "Music",
    "Confession",
]

CATEGORY_EMOJIS = {
    "General": "📘",
    "Image": "🖼️",
    "AI": "🤖",
    "Games": "🎮",
    "Economy": "💰",
    "XP": "🆙",
    "Birthday": "🎂",
    "AFK": "😴",
    "Translate": "🌐",
    "Downloader": "📥",
    "Info": "ℹ️",
    "Welcome": "👋",
    "Role": "🎭",
    "TimedWords": "⏱️",
    "ReplyWords": "💬",
    # "Werewolf": "🐺",
    "Confession": "💌",
    "Admin": "⚙️",
    "Streak": "🔥",
    "Music": "🎵",
}

CATEGORY_DESCRIPTIONS = {
    "General": """
• `ping`
• `pick`
• `poll`
• `giveaway`
• `serverinfo`
• `userinfo`
➡ Gunakan `mhelpgeneral` untuk detail.
""",

    "Image": """
• Emoji Steal  
• Sticker Save  
• Avatar Tools  
• Upload Image  
• Caption Editor  
➡ Gunakan `mhelpimage`.
""",

    "AI": """
• AI QnA  
• Truth / Dare  
• Rank generator  
• Anomali lore  
➡ Gunakan `mhelpai`.
""",

    "Games": """
• Sambung Kata  
• Stop Game  
➡ Gunakan `mhelpgame`.
""",

    "Economy": """
• `cash`, `bal`  
• `daily`    
• `gamble` → `mghelp gamble`  
• `duel` → `mghelp duel`  
• `rob` → `mghelp rob`  
➡ Gunakan `mghelp` untuk full economy.
""",

    "XP": """
• Level  
• Leaderboard  
• Autorole Level  
• Level Announcement  
➡ Gunakan `mhelpxp`.
""",

    "Birthday": """
• Set Birthday  
• Birthday List  
• Nearest Birthday  
• Birthday Channel  
➡ Gunakan `mhelpbirthday`.
""",

    "AFK": """
• Set AFK  
• Auto Remove AFK  
➡ Gunakan `mhelpafk`.
""",

"Translate": """
• Translate text  
➡ Gunakan `mtranslate <kode_bahasa> <text>`  
Contoh: `mtranslate id i need you`
""",


    "Downloader": """
• Auto IG/Tiktok/Shorts download  
• `mp3 <link>`  
➡ Gunakan `mhelpdl`.
""",

    "Info": """
• Server Info  
• User Info  
➡ Gunakan `mhelpinfo`.
""",

    "Welcome": """
• Welcome Message  
• Goodbye Message  
• Join/Leave Log  
➡ Gunakan `mhelpwelcome`.
""",

    "Role": """
• `selectrole <kategori>`  
   Kirim katalog role dengan dropdown select menu.

• `rolemenu <kategori>`  
   Membuat role menu dengan tombol / reaction.

➡ Gunakan `mhelprole` untuk detail.
""",


    "TimedWords": """
• Pesan Otomatis Berkala  
➡ Gunakan `mhelptimedwords`.
""",

    "ReplyWords": """
• Pesan Balasan Otomatis  
➡ Gunakan `mhelpreplywords`.
""",

#     "Werewolf": """
# • Start  
# • Join  
# • Vote  
# • Night Actions  
# ➡ Gunakan `mhelpww`.
# """,

    "Admin": """
• Bot ON/OFF  
• Clear Messages  
• Set Channels  
• Economy Admin Tools  
➡ Gunakan `mhelpadmin`.
""",

    "Streak": """
• Daily Streak Pair  
• Couple streak  
• Restore streak  
• Give streak  

➡ Gunakan `mhelpstreak` untuk melihat command lengkap.
""",

    "Music": """
• Play lagu  
• Pause / Resume  
• Skip  
• Stop  
• Queue list  
• Join/Leave VC  
➡ Gunakan `mhelpmusic`.
""",

    "Confession": """
• Kirim konfesi anonim  
• Kirim konfesi dengan gambar/video  
• Auto-thread system  
• Reply button  
• Anti-spam cooldown  
➡ Gunakan `mhelpconfession`.
""",



}


# ============================================================
# HELP MASTER COG
# ============================================================

class HelpMaster(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ============================================================
    # DETAIL EMBED
    # ============================================================

    def make_detail_embed(self, category: str):
        embed = discord.Embed(
            title=f"{CATEGORY_EMOJIS[category]} {category} Commands",
            color=discord.Color.blurple()
        )

        # GET AUTO COMMAND LIST
        commands_list = self.scan_commands(category)
        embed.description = commands_list
        embed.set_footer(text="Prefix: m, mad, kos, k")
        return embed
    
    def scan_commands(self, category_name: str):
        result = []
        for cmd in self.bot.commands:
            cat = cmd.extras.get("category") if hasattr(cmd, "extras") else None
            if cat == category_name:
                # Prioritas 1: custom usage
                if cmd.usage:
                    usage = f"{cmd.qualified_name} {cmd.usage}"

                # fallback: signature default
                elif cmd.signature:
                    usage = f"{cmd.qualified_name} {cmd.signature}"

                else:
                    usage = cmd.qualified_name

                result.append(f"`{usage}`")
        return "\n".join(result) if result else "`(Tidak ada command ditemukan)`"

    # ------------------------------
    # VIEW
    # ------------------------------
    class HelpView(discord.ui.View):
        def __init__(self, master, pages):
            super().__init__(timeout=180)
            self.master = master       # <--- Wajib
            self.pages = pages
            self.index = 0
            self.add_item(HelpMaster.CategoryDropdown(self))

        async def update(self, interaction):
            await interaction.response.edit_message(
                embed=self.pages[self.index],
                view=self
            )

        @discord.ui.button(label="⬅ Prev", style=discord.ButtonStyle.secondary)
        async def prev(self, interaction, btn):
            if self.index > 0:
                self.index -= 1
                await self.update(interaction)

        @discord.ui.button(label="Next ➡", style=discord.ButtonStyle.secondary)
        async def next(self, interaction, btn):
            if self.index < len(self.pages) - 1:
                self.index += 1
                await self.update(interaction)

    # ------------------------------
    # DROPDOWN
    # ------------------------------
    class CategoryDropdown(discord.ui.Select):
        def __init__(self, parent_view):
            self.parent_view = parent_view

            options = [
                discord.SelectOption(
                    label=cat,
                    emoji=CATEGORY_EMOJIS[cat],
                    description=f"Help kategori {cat}"
                )
                for cat in HELP_CATEGORIES
            ]

            super().__init__(
                placeholder="Pilih kategori…",
                options=options,
                min_values=1,
                max_values=1,
            )

        async def callback(self, interaction):
            chosen = self.values[0]

            # AUTO-SCAN BERDASARKAN CATEGORY
            embed = self.parent_view.master.make_detail_embed(chosen)

            await interaction.response.edit_message(
                embed=embed,
                view=self.parent_view
            )


        async def callback(self, interaction):
            chosen = self.values[0]
            self.parent_view.index = HELP_CATEGORIES.index(chosen)
            # Rebuild embed agar ISI DETAIL CATEGORY muncul
            new_embed = self.parent_view.master.make_detail_embed(chosen)

            await interaction.response.edit_message(
                embed=new_embed,
                view=self.parent_view
            )




    # ------------------------------
    # MASTER HELP (mhelp)
    # ------------------------------
    @commands.command(name="help")
    async def open_master(self, ctx):
        pages = []

        for cat in HELP_CATEGORIES:
            em = discord.Embed(
                title=f"{CATEGORY_EMOJIS[cat]} {cat} Help",
                description=CATEGORY_DESCRIPTIONS[cat],
                color=discord.Color.blurple()
            )
            em.set_footer(text="Prefix: m, mad, kos, k")
            pages.append(em)

        # <<< PENTING!
        view = HelpMaster.HelpView(self, pages)

        await ctx.send(embed=pages[0], view=view)


    # ------------------------------
    # SUBHELP COMMANDS
    # ------------------------------

    @commands.command(name="helpgeneral")
    async def _1(self, ctx):
        await ctx.send(embed=self.make_detail_embed("General"))

    @commands.command(name="helpimage")
    async def _2(self, ctx):
        await ctx.send(embed=self.make_detail_embed("Image"))

    @commands.command(name="helpai")
    async def _3(self, ctx):
        await ctx.send(embed=self.make_detail_embed("AI"))

    @commands.command(name="helpgame")
    async def _4(self, ctx):
        await ctx.send(embed=self.make_detail_embed("Games"))

    @commands.command(name="helpeconomy")
    async def _5(self, ctx):
        await ctx.send(embed=self.make_detail_embed("Economy"))

    @commands.command(name="helpxp")
    async def _6(self, ctx):
        await ctx.send(embed=self.make_detail_embed("XP"))

    @commands.command(name="helpbirthday")
    async def _7(self, ctx):
        await ctx.send(embed=self.make_detail_embed("Birthday"))

    @commands.command(name="helpafk")
    async def _8(self, ctx):
        await ctx.send(embed=self.make_detail_embed("AFK"))

    @commands.command(name="helptranslate")
    async def _9(self, ctx):
        await ctx.send(embed=self.make_detail_embed("Translate"))

    @commands.command(name="helpdl")
    async def _10(self, ctx):
        await ctx.send(embed=self.make_detail_embed("Downloader"))

    @commands.command(name="helpinfo")
    async def _11(self, ctx):
        await ctx.send(embed=self.make_detail_embed("Info"))

    @commands.command(name="helpwelcome")
    async def _12(self, ctx):
        await ctx.send(embed=self.make_detail_embed("Welcome"))

    @commands.command(name="helprole")
    async def _13(self, ctx):
        await ctx.send(embed=self.make_detail_embed("Role"))

    @commands.command(name="helptimedwords")
    async def _14(self, ctx):
        await ctx.send(embed=self.make_detail_embed("TimedWords"))

    @commands.command(name="helpreplywords")
    async def _14(self, ctx):
        await ctx.send(embed=self.make_detail_embed("ReplyWords"))

    # @commands.command(name="helpww")
    # async def _15(self, ctx):
    #     await ctx.send(embed=self.make_detail_embed("Werewolf"))

    @commands.command(name="helpmusic")
    async def _15(self, ctx):
        await ctx.send(embed=self.make_detail_embed("Music"))

    @commands.command(name="helpadmin")
    async def _16(self, ctx):
        await ctx.send(embed=self.make_detail_embed("Admin"))

    @commands.command(name="helpconfession")
    async def _confession(self, ctx):
        await ctx.send(embed=self.make_detail_embed("Confession"))


async def setup(bot):
    await bot.add_cog(HelpMaster(bot))
