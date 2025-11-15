import discord
from discord.ext import commands
from discord.ui import Button, View
import random
import asyncio
import requests

# ================================
#  VALIDASI KATA MENGGUNAKAN API KATEGLO
# ================================

CACHE_KATA = {}

def cek_kata(kata: str) -> bool:
    kata = kata.lower().strip()

    if kata in CACHE_KATA:
        return CACHE_KATA[kata]

    url = f"https://kateglo.com/api.php?format=json&phrase={kata}"

    try:
        r = requests.get(url, timeout=5)
        data = r.json()

        if data.get("definition"):
            CACHE_KATA[kata] = True
            return True

        CACHE_KATA[kata] = False
        return False

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
            description="Klik tombol **Join Game** untuk bergabung!\n\nBelum ada pemain yang bergabung.",
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
            await ctx.send("❌ Tidak ada game yang berjalan atau kamu bukan host.")


class JoinSambungKata(View):
    def __init__(self, bot, host_id, guild_id, game_dict):
        super().__init__(timeout=None)
        self.bot = bot
        self.host_id = host_id
        self.guild_id = guild_id
        self.players = {}
        self.message = None
        self.game_dict = game_dict
        self.game_active = False
        self.skip_counts = {}
        self.miss_counts = {}  # ✨ baru: hitung miss per player

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success)
    async def join_button(self, interaction, button):
        if interaction.user.id in self.players:
            await interaction.response.send_message("❗ Kamu sudah join!", ephemeral=True)
            return

        self.players[interaction.user.id] = interaction.user
        self.skip_counts[interaction.user.id] = 0
        self.miss_counts[interaction.user.id] = 0  # ✨ reset miss count player baru

        await interaction.response.send_message(f"✅ {interaction.user.name} telah bergabung!", ephemeral=True)
        await self.update_embed()

        if len(self.players) >= 2:
            self.children[1].disabled = False
            await self.message.edit(view=self)

    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.primary, disabled=True)
    async def start_button(self, interaction, button):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("❌ Hanya host yang bisa memulai game!", ephemeral=True)
            return

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

    async def start_game(self, interaction):
        self.game_active = True
        players = list(self.players.values())

        random.shuffle(players)
        poin = {p.id: 0 for p in players}

        kata_awal = random.choice(["jalan", "nasi", "baca", "main", "lari", "tulis", "apel", "besar"])
        used_words = {kata_awal}
        kata_terakhir = kata_awal
        index = 0

        def potong(k): return k[-2:]

        await interaction.followup.send(f"🎮 Game dimulai!\nKata pertama: **{kata_terakhir}**")

        # ==========================
        #  GAME LOOP
        # ==========================

        while self.game_active and len(players) > 1:
            round_miss = 0  # ✨ reset miss untuk ronde ini

            for _ in range(len(players)):  # iterate ronde
                if not self.game_active: 
                    break

                player = players[index]
                akhir = potong(kata_terakhir)

                await interaction.followup.send(
                    f"{player.mention}, giliranmu! Kata harus diawali dengan **'{akhir}'**.\n"
                    f"Skip tersisa: {3 - self.skip_counts[player.id]}"
                )

                def check(m):
                    return m.channel == interaction.channel and m.author.id == player.id

                start = asyncio.get_event_loop().time()
                kata = None

                while (asyncio.get_event_loop().time() - start) < 20:
                    try:
                        timeout = 20 - (asyncio.get_event_loop().time() - start)
                        msg = await self.bot.wait_for("message", check=check, timeout=timeout)
                        kata = msg.content.lower().strip()
                        break
                    except asyncio.TimeoutError:
                        kata = None
                        break

                # ========== TIMEOUT HANDLING ==========
                if kata is None:
                    self.miss_counts[player.id] += 1
                    round_miss += 1

                    # Diskualifikasi jika miss 2x
                    if self.miss_counts[player.id] >= 2:
                        await interaction.followup.send(
                            f"⏰ {player.mention} tidak merespon **2 kali**, kamu **didiskualifikasi!**"
                        )
                        players.remove(player)
                        self.players.pop(player.id, None)
                        self.skip_counts.pop(player.id, None)
                        self.miss_counts.pop(player.id, None)

                        if len(players) == 1:
                            await interaction.followup.send(f"🏆 {players[0].mention} menang otomatis!")
                            self.game_active = False
                        break

                    await interaction.followup.send(
                        f"⚠️ {player.mention} tidak merespon. Peringatan {self.miss_counts[player.id]}/2."
                    )

                    index = (index + 1) % len(players)
                    continue

                # ========== KATA VALIDASI ==========
                if kata == "stopgame" and player.id == self.host_id:
                    await interaction.followup.send("🛑 Game dihentikan oleh host.")
                    self.game_active = False
                    break

                if kata == "skip":
                    if self.skip_counts[player.id] >= 3:
                        await interaction.followup.send("❌ Skip sudah habis.")
                    else:
                        self.skip_counts[player.id] += 1
                        await interaction.followup.send(f"⏩ {player.mention} skip!")
                    index = (index + 1) % len(players)
                    continue

                if not kata.startswith(akhir):
                    await interaction.followup.send("❌ Kata tidak sesuai awalan.")
                    continue

                if kata in used_words:
                    await interaction.followup.send("⚠️ Kata sudah pernah dipakai.")
                    continue

                if not cek_kata(kata):
                    await interaction.followup.send("❌ Kata tidak valid menurut Kateglo/KBBI.")
                    continue

                # Kata valid
                used_words.add(kata)
                poin[player.id] += len(kata)
                kata_terakhir = kata

                await interaction.followup.send(
                    f"✅ {player.mention} mendapat **{len(kata)} poin!** Total: **{poin[player.id]}**"
                )

                if poin[player.id] >= 100:
                    await interaction.followup.send(f"🏆 {player.mention} mencapai 100 poin! Menang!")
                    self.game_active = False
                    break

                index = (index + 1) % len(players)

            # ========== CEK RONDE TIDAK ADA PEMAIN RESPON ==========
            if self.game_active and round_miss >= len(players):
                await interaction.followup.send(
                    "🛑 **Semua pemain tidak merespon di ronde ini. Game otomatis dihentikan.**"
                )
                self.game_active = False
                break

        if self.guild_id in self.game_dict:
            self.game_dict.pop(self.guild_id)

        self.stop()
