import discord
from discord.ext import commands
from discord.ui import Button, View
import random
import asyncio

from kbbi_loader import load_kbbi

# ================================
#          LOAD KBBI OFFLINE
# ================================

print("[KBBI] Loading offline KBBI...")
KBBI_SET = load_kbbi()
print("[KBBI] READY — Offline dictionary aktif.")

def cek_kata(kata: str) -> bool:
    kata = kata.lower().strip()
    valid = kata in KBBI_SET
    print(f"[KBBI CHECK] '{kata}' => {valid}")
    return valid


# ==================================================
#             COG SAMBUNG KATA
# ==================================================

class SambungKataMultiplayer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}

    @commands.command(name="cek")
    async def cek_cmd(self, ctx, *, word: str):
        if word.lower() in KBBI_SET:
            await ctx.send(f"✅ **'{word}' valid menurut KBBI offline.**")
        else:
            await ctx.send(f"❌ **'{word}' tidak ditemukan.**")

    @commands.command(name="sambungkata")
    async def sambungkata_mp(self, ctx):
        if ctx.guild.id in self.active_games:
            await ctx.send("❌ Sudah ada game yang berjalan!")
            return

        view = JoinSambungKata(self.bot, ctx.author.id, ctx.guild.id, self.active_games)

        embed = discord.Embed(
            title="🔤 Sambung Kata Multiplayer",
            description="Klik **Join Game** untuk ikut bermain!",
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
            await ctx.send("❌ Kamu bukan host atau tidak ada game.")



# ====================================================
#                       GAME VIEW
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
        self.miss_counts = {}
        self.message = None
        self.game_active = False


    # ==================================================
    #                     JOIN GAME
    # ==================================================
    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.success)
    async def join_button(self, interaction, button):
        uid = interaction.user.id

        if uid in self.players:
            await interaction.response.send_message("❗ Kamu sudah join!", ephemeral=True)
            return

        self.players[uid] = interaction.user
        self.skip_counts[uid] = 0
        self.miss_counts[uid] = 0

        await interaction.response.send_message(
            f"✅ {interaction.user.name} bergabung!", ephemeral=True
        )
        await self.update_embed()

        if len(self.players) >= 2:
            self.children[1].disabled = False
            await self.message.edit(view=self)



    # ==================================================
    #                     START GAME
    # ==================================================
    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.primary, disabled=True)
    async def start_button(self, interaction, button):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("❌ Kamu bukan host!", ephemeral=True)
            return

        # disable UI
        for c in self.children:
            c.disabled = True
        await self.message.edit(view=self)

        await interaction.response.edit_message(view=self)
        await self.start_game(interaction)



    async def update_embed(self):
        desc = "\n".join(f"- {u.name}" for u in self.players.values()) or "Belum ada pemain."

        embed = discord.Embed(
            title="🔤 Sambung Kata Multiplayer",
            description=f"**Pemain terdaftar:**\n{desc}",
            color=discord.Color.blurple(),
        )
        await self.message.edit(embed=embed, view=self)


    # ==================================================
    #              ULTRA GAMEBOARD EMBED
    # ==================================================
    def build_ultra_embed(
        self, player, awalan, poin, used_words,
        skips_left, kata_terakhir, miss_counts
    ):
        embed = discord.Embed(
            title=f"🎮 GILIRAN — {player.name}",
            color=discord.Color.gold()
        )

        embed.add_field(name="🔡 Awalan", value=f"`{awalan}`", inline=True)
        embed.add_field(name="⏳ Timer", value="`15 detik`", inline=True)
        embed.add_field(name="⏭ Skip", value=f"`{skips_left}/3`", inline=True)

        embed.add_field(
            name="📜 Kata Terakhir",
            value=f"**{kata_terakhir}**",
            inline=False
        )

        # kata terpakai
        used_preview = ", ".join(list(used_words)[-15:]) or "-"
        embed.add_field(
            name=f"🗂 Kata Terpakai ({len(used_words)})",
            value=used_preview,
            inline=False
        )

        # scoreboard
        sorted_scores = sorted(poin.items(), key=lambda x: x[1], reverse=True)
        skor_text = "\n".join(f"**{self.players[uid].name}** — {score}" for uid, score in sorted_scores)
        embed.add_field(name="📊 Skor Sementara", value=skor_text, inline=False)

        # status pemain
        status_lines = []
        for uid, u in self.players.items():
            if uid not in miss_counts:
                continue
            if miss_counts[uid] == 0:
                status_lines.append(f"{u.name} — ✔ aman")
            elif miss_counts[uid] == 1:
                status_lines.append(f"{u.name} — ⚠ 1/2 miss")
            elif miss_counts[uid] >= 2:
                status_lines.append(f"{u.name} — ❌ eliminated")

        embed.add_field(
            name="⚠ Status Pemain",
            value="\n".join(status_lines) if status_lines else "-",
            inline=False
        )

        return embed



    # ==================================================
    #                    GAME LOOP
    # ==================================================
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

        # ===============================
        #        MAIN LOOP
        # ===============================
        while self.game_active and len(players) > 1:
            ronde_miss = 0

            for _ in range(len(players)):
                if not self.game_active or len(players) <= 1:
                    break

                player = players[index]
                uid = player.id
                awalan = potong(kata_terakhir)

                # ===============================
                #     SEND ULTRA GAMEBOARD
                # ===============================
                embed = self.build_ultra_embed(
                    player=player,
                    awalan=awalan,
                    poin=poin,
                    used_words=used_words,
                    skips_left=3 - self.skip_counts[uid],
                    kata_terakhir=kata_terakhir,
                    miss_counts=self.miss_counts
                )
                await interaction.followup.send(embed=embed)

                # WAIT FOR INPUT
                def check(m):
                    return m.channel == interaction.channel and m.author.id == uid

                start_time = asyncio.get_event_loop().time()
                responded = False

                while True:
                    remaining = 15 - (asyncio.get_event_loop().time() - start_time)
                    if remaining <= 0:
                        break

                    try:
                        msg = await self.bot.wait_for("message", check=check, timeout=remaining)
                        kata = msg.content.lower().strip()
                        responded = True

                        # STOPGAME
                        if kata == "stopgame" and uid == self.host_id:
                            await interaction.followup.send("🛑 Game dihentikan oleh host.")
                            self.game_active = False
                            break

                        # SKIP
                        if kata == "skip":
                            if self.skip_counts[uid] >= 3:
                                await interaction.followup.send("❌ Skip kamu habis.")
                                continue

                            self.skip_counts[uid] += 1

                            base_words = ["jalan", "nasi", "baca", "main", "lari", "tulis", "apel", "besar"]
                            candidates = [w for w in base_words if w not in used_words] or base_words

                            kata_terakhir = random.choice(candidates)
                            used_words.add(kata_terakhir)

                            await interaction.followup.send(
                                f"⏭ {player.mention} skip! Kata baru: **{kata_terakhir}**"
                            )

                            start_time = asyncio.get_event_loop().time()
                            awalan = potong(kata_terakhir)
                            continue

                        # INVALID AWALAN
                        if not kata.startswith(awalan):
                            await interaction.followup.send("❌ Kata tidak sesuai awalan.")
                            continue

                        if kata in used_words:
                            await interaction.followup.send("⚠️ Kata sudah dipakai.")
                            continue

                        if not cek_kata(kata):
                            await interaction.followup.send("❌ Kata tidak valid menurut KBBI.")
                            continue

                        # VALID WORD
                        used_words.add(kata)
                        poin[uid] += len(kata)
                        kata_terakhir = kata

                        await interaction.followup.send(
                            f"✅ {player.mention} mendapat **{len(kata)} poin!** Total: **{poin[uid]}**"
                        )

                        if poin[uid] >= 100:
                            await interaction.followup.send(
                                f"🏆 {player.mention} mencapai 100 poin! Menang!"
                            )
                            self.game_active = False
                        break

                    except asyncio.TimeoutError:
                        break

                # END INPUT

                # MISS
                if not responded:
                    self.miss_counts[uid] += 1
                    ronde_miss += 1

                    if self.miss_counts[uid] >= 2:
                        await interaction.followup.send(
                            f"⛔ {player.mention} tidak merespon **2 kali** → Diskualifikasi!"
                        )
                        players.remove(player)
                        continue
                    else:
                        await interaction.followup.send(
                            f"⚠️ {player.mention} tidak merespon. Peringatan {self.miss_counts[uid]}/2"
                        )

                if self.game_active and len(players) > 1:
                    index = (index + 1) % len(players)

            # Semua pemain diam 1 ronde
            if ronde_miss >= len(players):
                await interaction.followup.send("🛑 Semua pemain diam 1 ronde → Game dihentikan.")
                self.game_active = False
                break

        # END GAME
        if self.guild_id in self.game_dict:
            self.game_dict.pop(self.guild_id, None)

        self.stop()
