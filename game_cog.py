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

    # cek cache
    if kata in CACHE_KATA:
        return CACHE_KATA[kata]

    url = "https://x-labs.my.id/api/kbbi"
    try:
        r = requests.get(url, params={"search": kata}, timeout=5)
        # kalau status code bukan 200 langsung dianggap tidak valid
        if r.status_code != 200:
            CACHE_KATA[kata] = False
            return False

        data = r.json()

        # success bisa True / "true"
        success = data.get("success", False)
        success_bool = (success is True) or (str(success).lower() == "true")

        # pastikan ada data & tidak kosong
        data_list = data.get("data", [])
        valid = success_bool and bool(data_list)

        CACHE_KATA[kata] = valid
        return valid

    except Exception:
        # kalau error (timeout, parse, dsb) jangan bikin bot crash
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

        self.players = {}      # user_id -> discord.User
        self.skip_counts = {}  # user_id -> jumlah skip
        self.miss_counts = {}  # user_id -> jumlah tidak merespon (max 2)
        self.message = None
        self.game_active = False

    # =============================
    # JOIN GAME
    # =============================
    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success)
    async def join_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id in self.players:
            await interaction.response.send_message("❗ Kamu sudah join!", ephemeral=True)
            return

        uid = interaction.user.id
        self.players[uid] = interaction.user
        self.skip_counts[uid] = 0
        self.miss_counts[uid] = 0

        await interaction.response.send_message(
            f"✅ {interaction.user.name} telah bergabung!", ephemeral=True
        )
        await self.update_embed()

        if len(self.players) >= 2:
            # enable Start
            self.children[1].disabled = False
            await self.message.edit(view=self)

    # =============================
    # START GAME
    # =============================
    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.primary, disabled=True)
    async def start_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message(
                "❌ Hanya host yang bisa memulai!", ephemeral=True
            )
            return

        # disable UI join & start
        self.children[0].disabled = True
        self.children[1].disabled = True
        await self.message.edit(view=self)

        await interaction.response.defer()
        await self.start_game(interaction)

    async def update_embed(self):
        desc = "\n".join(f"- {u.name}" for u in self.players.values()) or "Belum ada pemain."
        embed = discord.Embed(
            title="🔤 Game Sambung Kata Multiplayer",
            description=f"Pemain:\n{desc}",
            color=discord.Color.blurple()
        )
        await self.message.edit(embed=embed, view=self)

    # =============================
    # GAME LOGIC
    # =============================
    async def start_game(self, interaction: discord.Interaction):
        self.game_active = True

        players = list(self.players.values())
        random.shuffle(players)

        poin = {p.id: 0 for p in players}

        kata_awal = random.choice(["jalan", "nasi", "baca", "main", "lari", "tulis", "apel", "besar"])
        kata_terakhir = kata_awal
        used_words = {kata_awal}

        index = 0

        def potong(k: str) -> str:
            return k[-2:]

        await interaction.followup.send(f"🎮 Game dimulai!\nKata pertama: **{kata_awal}**")

        # ==================================================
        #                    MAIN GAME LOOP
        # ==================================================
        while self.game_active and len(players) > 1:
            ronde_miss = 0  # jumlah player yg TIDAK merespon sama sekali di ronde ini

            for _ in range(len(players)):
                if not self.game_active or len(players) <= 1:
                    break

                player = players[index]
                uid = player.id
                awalan = potong(kata_terakhir)

                # skor sementara tiap awal putaran 1
                if index == 0:
                    sorted_players = sorted(players, key=lambda p: poin[p.id], reverse=True)
                    score_embed = discord.Embed(
                        title="📊 Skor Sementara",
                        description="\n".join(f"**{p.name}**: {poin[p.id]} poin" for p in sorted_players),
                        color=discord.Color.green()
                    )
                    await interaction.followup.send(embed=score_embed)

                await interaction.followup.send(
                    f"{player.mention}, giliranmu!\n"
                    f"Kata harus diawali **'{awalan}'**\n"
                    f"⏳ Waktu: **15 detik** (tidak reset saat salah)\n"
                    f"⏭ Skip tersisa: {3 - self.skip_counts[uid]}"
                )

                def check(m: discord.Message):
                    return (m.channel == interaction.channel) and (m.author.id == uid)

                start_time = asyncio.get_event_loop().time()
                kata_valid = False
                responded = False  # apakah player mengirim pesan apapun di turn ini

                # =======================================================
                #           HARD 15 SECOND TIMER - MULTI TRY
                # =======================================================
                while True:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    remaining = 15 - elapsed
                    if remaining <= 0:
                        break

                    try:
                        msg = await self.bot.wait_for("message", check=check, timeout=remaining)
                        kata = msg.content.lower().strip()
                        responded = True

                        # ---------- STOPGAME ----------
                        if kata == "stopgame":
                            if uid == self.host_id:
                                await interaction.followup.send("🛑 Game dihentikan oleh host.")
                                self.game_active = False
                                break
                            else:
                                await interaction.followup.send("❌ Kamu bukan host.")
                                # masih boleh coba kata lain, waktu tetap jalan
                                continue

                        # ---------- SKIP ----------
                        if kata == "skip":
                            if self.skip_counts[uid] >= 3:
                                await interaction.followup.send("❌ Skip kamu sudah habis.")
                                # boleh coba kata lagi, waktu tetap jalan
                                continue

                            self.skip_counts[uid] += 1

                            # ganti kata, tapi giliran tetap di player ini
                            base_choices = ["jalan", "nasi", "baca", "main", "lari", "tulis", "apel", "besar"]
                            new_candidates = [w for w in base_choices if w not in used_words]
                            if not new_candidates:
                                new_candidates = base_choices

                            kata_terakhir = random.choice(new_candidates)
                            used_words.add(kata_terakhir)

                            await interaction.followup.send(
                                f"⏭ {player.mention} melakukan skip!\n"
                                f"Kata baru: **{kata_terakhir}**"
                            )

                            # reset timer 15 detik lagi untuk kata baru
                            start_time = asyncio.get_event_loop().time()
                            awalan = potong(kata_terakhir)
                            await interaction.followup.send(
                                f"{player.mention}, giliranmu lagi!\n"
                                f"Kata harus diawali **'{awalan}'**\n"
                                f"⏳ Waktu: **15 detik**\n"
                                f"⏭ Skip tersisa: {3 - self.skip_counts[uid]}"
                            )
                            continue

                        # ---------- VALIDASI AWALAN ----------
                        if not kata.startswith(awalan):
                            await interaction.followup.send("❌ Kata tidak sesuai awalan.")
                            # boleh coba lagi selama waktu masih ada
                            continue

                        # ---------- SUDAH TERPAKAI ----------
                        if kata in used_words:
                            await interaction.followup.send("⚠️ Kata sudah pernah dipakai.")
                            # boleh coba lagi
                            continue

                        # ---------- CEK API KBBI ----------
                        if not cek_kata(kata):
                            await interaction.followup.send("❌ Kata tidak valid menurut KBBI.")
                            # boleh coba lagi
                            continue

                        # ---------- KATA VALID ----------
                        kata_valid = True
                        used_words.add(kata)
                        poin[uid] += len(kata)
                        kata_terakhir = kata

                        await interaction.followup.send(
                            f"✅ {player.mention} mendapat **{len(kata)} poin!** "
                            f"Total: **{poin[uid]}**"
                        )

                        if poin[uid] >= 100:
                            await interaction.followup.send(
                                f"🏆 {player.mention} mencapai 100 poin! Kamu menang!"
                            )
                            self.game_active = False
                        break

                    except asyncio.TimeoutError:
                        # tidak ada pesan sampai waktu habis
                        break

                # keluar dari while (timer) karena:
                # - waktu habis, atau
                # - kata valid, atau
                # - host stopgame

                if not self.game_active:
                    break

                # =========================
                #  SELESAI GILIRAN PLAYER
                # =========================
                if not responded:
                    # benar2 tidak kirim pesan → miss
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
                            await interaction.followup.send(
                                f"🏆 {players[0].mention} menang otomatis!"
                            )
                            self.game_active = False
                        # jangan update index di sini karena panjang list berubah
                        continue
                    else:
                        await interaction.followup.send(
                            f"⚠️ {player.mention} tidak merespon. Peringatan {self.miss_counts[uid]}/2."
                        )
                else:
                    # player sempat merespon (apapun), tapi:
                    # - kalau kata_valid False → turn lewat tanpa poin, TIDAK dihitung miss
                    # - kalau kata_valid True → sudah handle di atas
                    pass

                # pindah ke player berikutnya kalau game masih jalan dan pemain > 1
                if self.game_active and len(players) > 1:
                    index = (index + 1) % len(players)

            # ==================================================
            # STOP GAME JIKA 1 RONDE SEMUA DIAM
            # ==================================================
            if self.game_active and len(players) > 1 and ronde_miss >= len(players):
                await interaction.followup.send(
                    "🛑 Semua pemain **tidak merespon sama sekali** di ronde ini.\n"
                    "Game dihentikan otomatis."
                )
                self.game_active = False
                break

        # cleanup
        if self.guild_id in self.game_dict:
            self.game_dict.pop(self.guild_id, None)

        self.stop()
