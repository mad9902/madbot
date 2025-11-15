import discord
from discord.ext import commands
from discord.ui import Button, View
import random
import asyncio
import requests

# ================================
#  VALIDASI KATA MENGGUNAKAN API X-LABS
# ================================

CACHE_KATA = {}

def cek_kata(kata: str) -> bool:
    kata = kata.lower().strip()

    if kata in CACHE_KATA:
        return CACHE_KATA[kata]

    url = f"https://x-labs.my.id/api/kbbi/search/{kata}"

    try:
        r = requests.get(url, timeout=5)
        data = r.json()

        valid = data.get("status", False)
        CACHE_KATA[kata] = valid
        return valid

    except:
        CACHE_KATA[kata] = False
        return False


# ==================================================
#  COG GAME SAMBUNG KATA MULTIPLAYER
# ==================================================

class SambungKataMultiplayer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}

    def cog_unload(self):
        for view in self.active_games.values():
            view.stop()

    @commands.command(name="sambungkata")
    async def sambungkata_mp(self, ctx):
        if ctx.guild.id in self.active_games:
            await ctx.send("❌ Sudah ada game yang berjalan di server ini!")
            return

        view = JoinSambungKata(self.bot, ctx.author.id, ctx.guild.id, self.active_games)
        embed = discord.Embed(
            title="🔤 Game Sambung Kata Multiplayer",
            description="Klik tombol **Join Game** untuk ikut bermain!",
            color=discord.Color.blurple()
        )
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

        self.active_games[ctx.guild.id] = view

        async def wait_finish():
            await view.wait()
            self.active_games.pop(ctx.guild.id, None)

        self.bot.loop.create_task(wait_finish())

    @commands.command(name="stopgame")
    async def stop(self, ctx):
        view = self.active_games.get(ctx.guild.id)
        if view and ctx.author.id == view.host_id:
            await ctx.send("🛑 Game dihentikan oleh host.")
            view.game_active = False
            view.stop()
        else:
            await ctx.send("❌ Tidak ada game berjalan atau kamu bukan host.")

# ====================================================
#                    GAME VIEW
# ====================================================

class JoinSambungKata(View):
    def __init__(self, bot, host_id, guild_id, game_dict):
        super().__init__(timeout=None)
        self.bot = bot
        self.host_id = host_id
        self.guild_id = guild_id
        self.game_dict = game_dict

        self.players = {}
        self.skip_counts = {}
        self.miss_counts = {}  # timeout tracking (max 2)
        self.message = None
        self.game_active = False

    # =============================
    # JOIN GAME
    # =============================
    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success)
    async def join_button(self, interaction, button):
        if interaction.user.id in self.players:
            await interaction.response.send_message("❗ Kamu sudah join!", ephemeral=True)
            return

        uid = interaction.user.id
        self.players[uid] = interaction.user
        self.skip_counts[uid] = 0
        self.miss_counts[uid] = 0

        await interaction.response.send_message(f"✅ {interaction.user.name} telah bergabung!", ephemeral=True)
        await self.update_embed()

        if len(self.players) >= 2:
            self.children[1].disabled = False
            await self.message.edit(view=self)

    # =============================
    # START GAME
    # =============================
    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.primary, disabled=True)
    async def start_button(self, interaction, button):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("❌ Hanya host yang bisa memulai!", ephemeral=True)
            return

        # disable UI
        self.children[0].disabled = True
        self.children[1].disabled = True
        await self.message.edit(view=self)

        await interaction.response.defer()
        await self.start_game(interaction)

    async def update_embed(self):
        desc = "\n".join(f"- {u.name}" for u in self.players.values())
        embed = discord.Embed(
            title="🔤 Game Sambung Kata Multiplayer",
            description=f"Pemain:\n{desc}",
            color=discord.Color.blurple()
        )
        await self.message.edit(embed=embed, view=self)

    # =============================
    # GAME LOGIC
    # =============================
    async def start_game(self, interaction):
        self.game_active = True

        players = list(self.players.values())
        random.shuffle(players)

        poin = {p.id: 0 for p in players}

        kata_awal = random.choice(["jalan", "nasi", "baca", "main", "lari", "tulis", "apel", "besar"])
        kata_terakhir = kata_awal
        used_words = {kata_awal}

        index = 0

        def potong(k): 
            return k[-2:]

        await interaction.followup.send(f"🎮 Game dimulai!\nKata pertama: **{kata_awal}**")

        # ==================================================
        #                    MAIN GAME LOOP
        # ==================================================
        while self.game_active and len(players) > 1:
            ronde_miss = 0

            for _ in range(len(players)):
                if not self.game_active:
                    break

                player = players[index]
                uid = player.id
                awalan = potong(kata_terakhir)

                await interaction.followup.send(
                    f"{player.mention}, giliranmu!\n"
                    f"Kata harus diawali **'{awalan}'**\n"
                    f"⏳ Waktu: **15 detik** (tidak reset)\n"
                    f"⏭ Skip tersisa: {3 - self.skip_counts[uid]}"
                )

                def check(m):
                    return m.channel == interaction.channel and m.author.id == uid

                start = asyncio.get_event_loop().time()
                kata = None

                # =======================================================
                #           **HARD 15 SECOND TIMER - NO RESET**
                # =======================================================
                while asyncio.get_event_loop().time() - start < 15:
                    try:
                        msg = await self.bot.wait_for("message", check=check, timeout=15 - (asyncio.get_event_loop().time() - start))
                        kata = msg.content.lower().strip()
                        break  # input diterima, tapi waktu tetap tidak reset
                    except asyncio.TimeoutError:
                        kata = None
                        break

                # =======================================================
                #          TIMEOUT HANDLING (TIDAK JAWAB 15 DETIK)
                # =======================================================
                if kata is None:
                    self.miss_counts[uid] += 1
                    ronde_miss += 1

                    if self.miss_counts[uid] >= 2:
                        await interaction.followup.send(
                            f"⛔ {player.mention} tidak merespon **2 kali**, kamu didiskualifikasi!"
                        )

                        players.remove(player)
                        self.players.pop(uid, None)
                        self.skip_counts.pop(uid, None)
                        self.miss_counts.pop(uid, None)

                        if len(players) == 1:
                            await interaction.followup.send(f"🏆 {players[0].mention} menang otomatis!")
                            self.game_active = False

                        break

                    await interaction.followup.send(
                        f"⚠️ {player.mention} tidak merespon. Peringatan {self.miss_counts[uid]}/2."
                    )

                    index = (index + 1) % len(players)
                    continue

                # =======================================================
                #                  INPUT VALIDATION
                # =======================================================

                # Host stop game
                if kata == "stopgame" and uid == self.host_id:
                    await interaction.followup.send("🛑 Game dihentikan oleh host.")
                    self.game_active = False
                    break

                # skip
                if kata == "skip":
                    if self.skip_counts[uid] >= 3:
                        await interaction.followup.send("❌ Skip sudah habis.")
                    else:
                        self.skip_counts[uid] += 1
                        await interaction.followup.send(f"⏭ {player.mention} melakukan skip.")

                    index = (index + 1) % len(players)
                    continue

                if not kata.startswith(awalan):
                    await interaction.followup.send("❌ Kata tidak sesuai awalan.")
                    continue

                if kata in used_words:
                    await interaction.followup.send("⚠️ Kata sudah pernah dipakai.")
                    continue

                if not cek_kata(kata):
                    await interaction.followup.send("❌ Kata tidak valid menurut KBBI.")
                    continue

                # ====================================================
                #                VALID WORD
                # ====================================================
                used_words.add(kata)
                poin[uid] += len(kata)
                kata_terakhir = kata

                await interaction.followup.send(
                    f"✅ {player.mention} mendapat **{len(kata)} poin!** Total: **{poin[uid]}**"
                )

                if poin[uid] >= 100:
                    await interaction.followup.send(
                        f"🏆 {player.mention} mencapai 100 poin! Kamu menang!"
                    )
                    self.game_active = False
                    break

                index = (index + 1) % len(players)

            # ==================================================
            # STOP GAME JIKA 1 RONDE SEMUA DIAM
            # ==================================================
            if self.game_active and ronde_miss >= len(players):
                await interaction.followup.send(
                    "🛑 Semua pemain tidak merespon di ronde ini. Game dihentikan!"
                )
                self.game_active = False
                break

        if self.guild_id in self.game_dict:
            self.game_dict.pop(self.guild_id)

        self.stop()
