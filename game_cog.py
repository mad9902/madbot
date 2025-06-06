import discord
from discord.ext import commands
from discord.ui import Button, View
import random
import asyncio
from kbbi import KBBI  # Pastikan module kbbi sudah terinstall dan bisa dipanggil

def cek_kata(kata: str) -> bool:
    try:
        kbbi_obj = KBBI(kata)
        if not kbbi_obj.entri:
            return False
        for entri in kbbi_obj.entri:
            if hasattr(entri, 'baku') and entri.baku:
                return True
            else:
                deskripsi = str(entri)
                if "bentuk tidak baku" not in deskripsi.lower():
                    return True
        return False
    except Exception:
        return False

class SambungKataMultiplayer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}  # guild_id: JoinSambungKata instance

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
            description="Klik tombol **Join Game** di bawah untuk bergabung!\n\nBelum ada pemain yang bergabung.",
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
        self.players = {}  # user.id: discord.User
        self.message = None
        self.current_player = None
        self.skip_event = asyncio.Event()
        self.stop_event = asyncio.Event()
        self.game_dict = game_dict
        self.game_active = False
        self.skip_counts = {}  # user.id: jumlah skip yang sudah dipakai

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success)
    async def join_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id in self.players:
            await interaction.response.send_message("❗ Kamu sudah join!", ephemeral=True)
            return

        self.players[interaction.user.id] = interaction.user
        self.skip_counts[interaction.user.id] = 0
        await interaction.response.send_message(f"✅ {interaction.user.name} telah bergabung!", ephemeral=True)
        await self.update_embed()

        if len(self.players) >= 2:
            self.children[1].disabled = False  # Enable Start Game
            await self.message.edit(view=self)

    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.primary, disabled=True)
    async def start_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("❌ Hanya host yang bisa memulai game!", ephemeral=True)
            return

        self.children[0].disabled = True  # Join
        self.children[1].disabled = True  # Start
        await self.message.edit(view=self)
        await interaction.response.defer()
        await self.start_game(interaction)

    async def update_embed(self):
        desc = "\n".join(f"- {user.name}" for user in self.players.values()) or "Belum ada pemain."
        embed = discord.Embed(
            title="🔤 Game Sambung Kata Multiplayer",
            description=f"Klik tombol **Join Game** untuk bergabung!\n\nPemain:\n{desc}",
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

        skip_round_counter = 0  # hitung berapa pemain melewatkan giliran di satu putaran
        total_players = len(players)

        def potong_suku(kata):
            return kata[-2:]

        await interaction.followup.send(f"🎮 Game dimulai!\nKata pertama: **{kata_terakhir}**")

        while self.game_active and len(players) > 1:
            player = players[index]
            self.current_player = player
            akhir = potong_suku(kata_terakhir)

            if index == 0:
                # Cek dulu apakah game masih aktif
                if not self.game_active:
                    break
                sorted_players = sorted(players, key=lambda p: poin[p.id], reverse=True)
                poin_embed = discord.Embed(
                    title="📊 Skor Sementara",
                    description="\n".join(f"**{p.name}**: {poin[p.id]} poin" for p in sorted_players),
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=poin_embed)

            if not self.game_active:
                break

            await interaction.followup.send(
                f"{player.mention}, giliranmu! Kata harus diawali dengan **'{akhir}'**. (15 detik)\n"
                f"Skip tersisa: {3 - self.skip_counts.get(player.id, 0)}\n"
                f"Ketik kata baru, atau ketik **skip** untuk melewatkan giliran jika masih ada skip. mstopgame untuk stop game (hanya host yang bisa)"
            )

            def check(m):
                return m.channel == interaction.channel and m.author.id == player.id

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=15.0)
                kata = msg.content.lower().strip()

                if not self.game_active:
                    break  # Tambahan pengecekan disini

                if kata == "stopgame":
                    if player.id == self.host_id:
                        if not interaction.response.is_done():
                            await interaction.response.send_message("🛑 Game dihentikan oleh host.")
                        else:
                            await interaction.followup.send("🛑 Game dihentikan oleh host.")
                        self.game_active = False
                        break
                    else:
                        if not interaction.response.is_done():
                            await interaction.response.send_message("❌ Hanya host yang bisa menghentikan game.")
                        else:
                            await interaction.followup.send("❌ Hanya host yang bisa menghentikan game.")
                        continue

                if kata == "skip":
                    if self.skip_counts.get(player.id, 0) >= 3:
                        await interaction.followup.send(f"❌ {player.mention}, skip kamu sudah habis. Kamu harus jawab kata atau tunggu timeout dan kamu akan kalah.")
                        continue
                    self.skip_counts[player.id] += 1

                    new_candidates = [w for w in ["jalan", "nasi", "baca", "main", "lari", "tulis", "apel", "besar"] if w not in used_words]
                    if not new_candidates:
                        new_candidates = ["jalan", "nasi", "baca", "main", "lari", "tulis", "apel", "besar"]
                    kata_terakhir = random.choice(new_candidates)
                    used_words.add(kata_terakhir)

                    skip_round_counter += 1
                    if skip_round_counter >= total_players:
                        await interaction.followup.send("🛑 Semua pemain melewatkan giliran. Game dihentikan otomatis.")
                        self.game_active = False
                        break

                    await interaction.followup.send(f"⏩ {player.mention} skip! Kata baru diganti: **{kata_terakhir}**")
                    continue

                # cek validitas kata
                if not kata.startswith(akhir):
                    await interaction.followup.send("❌ Kata tidak sesuai awalan.")
                    continue
                elif kata in used_words:
                    await interaction.followup.send("⚠️ Kata sudah pernah dipakai.")
                    continue
                elif not cek_kata(kata):
                    await interaction.followup.send("❌ Kata tidak valid menurut KBBI.")
                    continue
                else:
                    used_words.add(kata)
                    poin[player.id] += len(kata)
                    kata_terakhir = kata
                    skip_round_counter = 0
                    await interaction.followup.send(
                        f"✅ {player.mention} dapat **{len(kata)} poin!** Total: **{poin[player.id]}**"
                    )
                    if poin[player.id] >= 100:
                        await interaction.followup.send(f"🏆 {player.mention} menang dengan 100 poin!")
                        self.game_active = False
                        break
                    index = (index + 1) % len(players)

            except asyncio.TimeoutError:
                if not self.game_active:
                    break

                if self.skip_counts.get(player.id, 0) >= 3:
                    await interaction.followup.send(f"⏰ {player.mention} tidak merespon dan sudah tidak punya skip tersisa. Kamu kalah dan dikeluarkan dari game.")
                    poin.pop(player.id, None)
                    players.remove(player)
                    self.players.pop(player.id, None)
                    self.skip_counts.pop(player.id, None)

                    if len(players) == 1:
                        await interaction.followup.send(f"🏆 {players[0].mention} menang karena semua pemain lain kalah!")
                        self.game_active = False
                        break

                    if index >= len(players):
                        index = 0
                else:
                    new_candidates = [w for w in ["jalan", "nasi", "baca", "main", "lari", "tulis", "apel", "besar"] if w not in used_words]
                    if not new_candidates:
                        new_candidates = ["jalan", "nasi", "baca", "main", "lari", "tulis", "apel", "besar"]
                    kata_terakhir = random.choice(new_candidates)
                    used_words.add(kata_terakhir)

                    skip_round_counter += 1
                    if skip_round_counter >= total_players:
                        await interaction.followup.send("🛑 Semua pemain melewatkan giliran. Game dihentikan otomatis.")
                        self.game_active = False
                        break

                    await interaction.followup.send(
                        f"⏰ {player.mention} tidak merespon. Kata diganti menjadi **{kata_terakhir}**.\n➡️ Giliran berpindah ke pemain berikutnya."
                    )
                    index = (index + 1) % len(players)


            except asyncio.TimeoutError:
                if self.skip_counts.get(player.id, 0) >= 3:
                    await interaction.followup.send(f"⏰ {player.mention} tidak merespon dan sudah tidak punya skip tersisa. Kamu kalah dan dikeluarkan dari game.")
                    poin.pop(player.id, None)
                    players.remove(player)
                    self.players.pop(player.id, None)
                    self.skip_counts.pop(player.id, None)

                    if len(players) == 1:
                        await interaction.followup.send(f"🏆 {players[0].mention} menang karena semua pemain lain kalah!")
                        self.game_active = False
                        break

                    if index >= len(players):
                        index = 0
                else:
                    new_candidates = [w for w in ["jalan", "nasi", "baca", "main", "lari", "tulis", "apel", "besar"] if w not in used_words]
                    if not new_candidates:
                        new_candidates = ["jalan", "nasi", "baca", "main", "lari", "tulis", "apel", "besar"]
                    kata_terakhir = random.choice(new_candidates)
                    used_words.add(kata_terakhir)

                    skip_round_counter += 1  # tambah hitungan pemain skip karena timeout
                    if skip_round_counter >= total_players:
                        await interaction.followup.send("🛑 Semua pemain melewatkan giliran. Game dihentikan otomatis.")
                        self.game_active = False
                        break

                    await interaction.followup.send(
                        f"⏰ {player.mention} tidak merespon. Kata diganti menjadi **{kata_terakhir}**.\n➡️ Giliran berpindah ke pemain berikutnya."
                    )
                    index = (index + 1) % len(players)

        if self.guild_id in self.game_dict:
            self.game_dict.pop(self.guild_id)
        self.stop()
