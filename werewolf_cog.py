import discord
from discord.ext import commands, tasks
import random
import asyncio
from datetime import datetime, timedelta

# Simulasi database (pakai modul database sesuai implementasimu)
from database import (
    create_new_game, update_game_status, get_active_game,
    add_player, get_alive_players, get_players_by_role,
    kill_player, reset_players, set_roles_config,
    save_vote, get_votes_for_round, log_event,
    update_leaderboard, get_game_logs
)

ROLE_POOL = {
    5: ["werewolf", "seer", "villager"],
    5: ["werewolf", "seer", "villager", "villager"],
    5: ["werewolf", "seer", "villager", "villager", "villager"],
    6: ["werewolf", "werewolf", "seer", "villager", "villager", "villager"],
    7: ["werewolf", "werewolf", "seer", "villager", "villager", "villager", "guardian"],
    8: ["werewolf", "werewolf", "seer", "guardian", "witch", "villager", "villager", "villager"]
}

MIN_PLAYERS = 3
MAX_PLAYERS = 8
TIMEOUT_DURATION = timedelta(days=2)

class TargetSelect(discord.ui.Select):
    def __init__(self, role, options, callback_func):
        self.role = role
        self.callback_func = callback_func
        super().__init__(placeholder="Pilih target...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        target_id = int(self.values[0])
        await self.callback_func(interaction, self.role, target_id)

class TargetView(discord.ui.View):
    def __init__(self, role, players, callback_func):
        super().__init__(timeout=60)
        seen_ids = set()
        options = []
        for p in players:
            if p['alive'] and p['user_id'] not in seen_ids:
                options.append(discord.SelectOption(label=p['username'], value=str(p['user_id'])))
                seen_ids.add(p['user_id'])
        self.add_item(TargetSelect(role, options, callback_func))

class WitchTargetSelect(discord.ui.Select):
    def __init__(self, game_id, user_id, cog, options):
        self.game_id = game_id
        self.user_id = user_id
        self.cog = cog
        super().__init__(
            placeholder="Pilih target untuk Heal/Kill",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction):
        target_id = int(self.values[0])
        view = WitchActionButtons(target_id, self.game_id, self.user_id, self.cog)
        await interaction.response.send_message(
            f"Kamu memilih <@{target_id}>. Sekarang pilih aksi:",
            view=view,
            ephemeral=True
        )


class WitchActionButtons(discord.ui.View):
    def __init__(self, target_id, game_id, user_id, cog):
        super().__init__()
        self.target_id = target_id
        self.game_id = game_id
        self.user_id = user_id
        self.cog = cog

    @discord.ui.button(label="Heal", style=discord.ButtonStyle.success, emoji="✨")
    async def heal_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Bukan giliranmu.", ephemeral=True)
            return

        witch_actions = self.cog.night_actions[self.game_id]['witch']
        
        if witch_actions.get('used_heal'):
            await interaction.response.send_message("Potion penyembuh sudah habis.", ephemeral=True)
            return

        if witch_actions['heal'] or witch_actions['kill']:
            await interaction.response.send_message("Kamu sudah memilih aksi malam ini.", ephemeral=True)
            return

        witch_actions['heal'] = self.target_id
        witch_actions['used_heal'] = True
        await interaction.response.send_message(f"✅ Kamu akan menyembuhkan <@{self.target_id}>.", ephemeral=True)


    @discord.ui.button(label="Kill", style=discord.ButtonStyle.danger, emoji="☠️")
    async def kill_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Bukan giliranmu.", ephemeral=True)
            return

        witch_actions = self.cog.night_actions[self.game_id]['witch']
        
        if witch_actions.get('used_kill'):
            await interaction.response.send_message("Potion racun sudah habis.", ephemeral=True)
            return

        if witch_actions['heal'] or witch_actions['kill']:
            await interaction.response.send_message("Kamu sudah memilih aksi malam ini.", ephemeral=True)
            return

        witch_actions['kill'] = self.target_id
        witch_actions['used_kill'] = True
        await interaction.response.send_message(f"☠️ Kamu akan membunuh <@{self.target_id}>.", ephemeral=True)



class Werewolf(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = {}  # guild_id: game_id
        self.night_actions = {}  # game_id: dict
        self.hosts = {}
        self.last_activity = {}  # game_id: datetime
        self.timeout_checker.start()

    def update_activity(self, game_id):
        self.last_activity[game_id] = datetime.utcnow()

    @tasks.loop(minutes=30)
    async def timeout_checker(self):
        now = datetime.utcnow()
        to_remove = []
        for guild_id, game_id in self.active_games.items():
            last = self.last_activity.get(game_id)
            if last and now - last > TIMEOUT_DURATION:
                print(f"[TIMEOUT] Game {game_id} dihentikan karena tidak ada aktivitas.")
                game = get_active_game(guild_id)
                if game:
                    update_game_status(game_id, 'ended')
                    reset_players(game_id)
                    to_remove.append(guild_id)
                    channel = self.bot.get_channel(game['channel_id'])
                    if channel:
                        await channel.send("⏰ Game dihentikan otomatis karena tidak ada aktivitas selama 2 hari.")
        for gid in to_remove:
            self.active_games.pop(gid, None)
            self.hosts.pop(gid, None)

    async def send_embed(self, ctx_or_channel, title, description, color=discord.Color.blurple()):
        embed = discord.Embed(title=title, description=description, color=color)
        try:
            if isinstance(ctx_or_channel, discord.Interaction):
                await ctx_or_channel.response.defer()
                return await ctx_or_channel.followup.send(embed=embed)
            elif isinstance(ctx_or_channel, discord.abc.Messageable):
                return await ctx_or_channel.send(embed=embed)
        except Exception as e:
            print(f"[ERROR] send_embed gagal: {e}")

    async def send_dm_with_dropdown(self, member, role, players, callback_func):
        try:
            await member.send(
                embed=discord.Embed(
                    title=f"{role.capitalize()} Phase",
                    description="Pilih targetmu dari daftar di bawah ini.",
                    color=discord.Color.purple()
                ),
                view=TargetView(role, players, callback_func)
            )
        except Exception as e:
            print(f"[DM ERROR] Gagal kirim DM ke {member.name}: {e}")

    async def handle_dm_selection(self, interaction, role, target_id):
        user_id = interaction.user.id
        guild_id = None
        game_id = None

        # Cari game_id berdasarkan active_games
        for g_id, g_game_id in self.active_games.items():
            game = get_active_game(g_id)
            if not game or game['status'] != 'night':
                continue
            players = get_alive_players(g_game_id)
            if any(p['user_id'] == user_id and p['role'] == role for p in players):
                guild_id = g_id
                game_id = g_game_id
                break

        if not game_id or not self.night_actions.get(game_id):
            await interaction.response.send_message("Terjadi kesalahan atau game tidak aktif.", ephemeral=True)
            return

        # Proses aksi berdasarkan role
        if role == 'werewolf':
            self.night_actions[game_id]['werewolf'][user_id] = target_id
            await interaction.response.send_message(f"Kamu memilih untuk menyerang <@{target_id}>.", ephemeral=True)

        elif role == 'seer':
            # Cegah jika sudah pernah memilih
            if self.night_actions[game_id]['seer'] is not None:
                await interaction.response.send_message("❌ Kamu sudah menggunakan kemampuanmu malam ini.", ephemeral=True)
                return

            players = get_alive_players(game_id)
            target_player = next((p for p in players if p['user_id'] == target_id), None)
            if target_player:
                self.night_actions[game_id]['seer'] = target_id
                await interaction.response.send_message(
                    f"🔍 Peran {target_player['username']} adalah: **{target_player['role'].upper()}**", ephemeral=True
                )

        elif role == 'guardian':
            self.night_actions[game_id]['guardian'] = target_id
            await interaction.response.send_message(f"Kamu memilih untuk melindungi <@{target_id}>.", ephemeral=True)

        elif role == 'witch':
            # Untuk witch, asumsikan default tombol hanya untuk 'heal'
            self.night_actions[game_id]['witch']['heal'] = target_id
            await interaction.response.send_message(f"Kamu memilih untuk menyembuhkan <@{target_id}>.", ephemeral=True)

    async def send_witch_dm(self, member, game_id):
        players = get_alive_players(game_id)

        seen_ids = set()
        options = []
        for p in players:
            if p['user_id'] != member.id and p['user_id'] not in seen_ids:
                options.append(discord.SelectOption(label=p['username'], value=str(p['user_id'])))
                seen_ids.add(p['user_id'])

        view = discord.ui.View()
        view.add_item(WitchTargetSelect(game_id, member.id, self, options))

        await member.send(
            embed=discord.Embed(
                title="Peranmu: Witch",
                description="Pilih target yang ingin kamu Heal atau Kill.",
                color=discord.Color.purple()
            ),
            view=view
        )


    @commands.command(name="startwerewolf")
    async def startwerewolf_cmd(self, ctx):
        game = get_active_game(ctx.guild.id)
        if game:
            await self.send_embed(ctx, "Game Aktif", "Sudah ada game aktif. Gunakan `mstopwerewolf` untuk mengakhiri.")
            return

        game_id = create_new_game(ctx.guild.id, ctx.channel.id)
        self.active_games[ctx.guild.id] = game_id
        self.hosts[ctx.guild.id] = ctx.author.id

        embed = discord.Embed(
            title="Werewolf Game Dibuat",
            description="Gunakan tombol di bawah untuk bergabung ke game. Setelah cukup pemain, host dapat memulai.",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Minimal {MIN_PLAYERS} pemain, maksimal {MAX_PLAYERS} pemain.")

        view = discord.ui.View()
        bot_self = self

        class JoinButton(discord.ui.Button):
            def __init__(self):
                super().__init__(label="Join Game", style=discord.ButtonStyle.primary)

            async def callback(self, interaction):
                players = get_alive_players(game_id)
                if any(p['user_id'] == interaction.user.id for p in players):
                    await interaction.response.send_message("Kamu sudah bergabung sebelumnya!", ephemeral=True)
                    return

                if len(players) >= MAX_PLAYERS:
                    await interaction.response.send_message("Jumlah pemain sudah mencapai batas maksimal!", ephemeral=True)
                    return

                add_player(game_id, interaction.user.id, str(interaction.user), role="pending")
                await interaction.response.send_message(f"{interaction.user.mention} bergabung ke permainan!", ephemeral=True)

                player_names = [p['username'] for p in get_alive_players(game_id)]
                embed.description = (
                    "Gunakan tombol di bawah untuk bergabung ke game. Setelah cukup pemain, host dapat memulai.\n\n"
                    "**Pemain yang sudah bergabung:**\n" +
                    "\n".join(f"- {name}" for name in player_names)
                )
                await interaction.message.edit(embed=embed, view=view)

        class StartButton(discord.ui.Button):
            def __init__(self):
                super().__init__(label="Start Game", style=discord.ButtonStyle.success)

            async def callback(self, interaction):
                if interaction.user.id != bot_self.hosts.get(ctx.guild.id) and interaction.user.id != 416234104317804544:
                    await interaction.response.send_message("Hanya host atau developer yang dapat memulai permainan.", ephemeral=True)
                    return
                await bot_self.startwerewolf_game(interaction)

        view.add_item(JoinButton())
        view.add_item(StartButton())

        await ctx.send(embed=embed, view=view)

    async def startwerewolf_game(self, interaction):
        await interaction.response.defer()

        guild_id = interaction.guild.id
        game = get_active_game(guild_id)
        if not game:
            await self.send_embed(interaction, "Gagal", "Tidak ada game aktif.")
            return

        # Ambil pemain yang sudah join (masih role "pending")
        players = get_alive_players(game['id'])
        if len(players) < MIN_PLAYERS:
            await self.send_embed(interaction, "Gagal", f"Minimal {MIN_PLAYERS} pemain untuk memulai game.")
            return

        # Ambil dan acak role & pemain
        roles = ROLE_POOL.get(len(players), ROLE_POOL[max(ROLE_POOL)])
        random.shuffle(roles)
        random.shuffle(players)

        # Simpan data user sebelum reset
        player_data = [{'user_id': p['user_id'], 'username': p['username']} for p in players]
        reset_players(game['id'])

        # Tetapkan role dan kirim DM
        for player, role in zip(player_data, roles):
            add_player(game['id'], player['user_id'], player['username'], role)
            member = interaction.guild.get_member(player['user_id'])
            if member:
                try:
                    await member.send(embed=discord.Embed(
                        title="Peranmu",
                        description=f"Peranmu di Werewolf adalah: **{role.upper()}**",
                        color=discord.Color.dark_green()
                    ))
                except Exception as e:
                    print(f"[DM ERROR] Gagal kirim DM ke {player['username']}: {e}")

        # Simpan konfigurasi role dan mulai malam
        set_roles_config(game['id'], {r: roles.count(r) for r in set(roles)})
        update_game_status(game['id'], 'night', 1)

        channel = interaction.channel
        await self.send_embed(channel, "Game Dimulai", "Malam pertama dimulai...")
        await self.handle_night_phase(channel, game['id'], 1)



    @commands.command(name="stopwerewolf")
    async def stopwerewolf_cmd(self, ctx):
        game = get_active_game(ctx.guild.id)
        if not game:
            await self.send_embed(ctx, "Tidak Ada Game", "Belum ada game yang dimulai.")
            return

        if ctx.author.id != self.hosts.get(ctx.guild.id) and ctx.author.id != 416234104317804544:
            await self.send_embed(ctx, "Bukan Host", "Hanya host atau developer yang dapat menghentikan game.")
            return

        update_game_status(game['id'], 'ended')
        reset_players(game['id'])
        del self.active_games[ctx.guild.id]
        del self.hosts[ctx.guild.id]
        await self.send_embed(ctx, "Game Dihentikan", "Game berhasil dihentikan dan semua data direset.")

    async def handle_night_phase(self, ctx, game_id, round_number):
        print(f"[NIGHT] Mulai malam {round_number} untuk game {game_id}")
        update_game_status(game_id, 'night', round_number)
        if game_id not in self.night_actions:
            self.night_actions[game_id] = {}

        # Reset aksi malam tapi simpan status potion Witch
        previous_witch = self.night_actions[game_id].get('witch', {})
        self.night_actions[game_id] = {
            'werewolf': {},
            'seer': None,
            'guardian': None,
            'witch': {
                'heal': None,
                'kill': None,
                'used_heal': previous_witch.get('used_heal', False),
                'used_kill': previous_witch.get('used_kill', False)
            }
        }

        try:
            await self.send_embed(ctx, f"\U0001F319 Malam {round_number}", "Semua peran khusus silakan DM bot sesuai kemampuan.")
        except Exception as e:
            print(f"[ERROR] Gagal kirim embed malam: {e}")

        guild = ctx.guild if hasattr(ctx, 'guild') else ctx.channel.guild

        roles = ["werewolf", "seer", "guardian", "witch"]
        for role in roles:
            players = get_players_by_role(game_id, role)
            for p in players:
                member = guild.get_member(p['user_id'])
                if not member or not p['alive']:
                    continue
                try:
                    if role == 'werewolf':
                        # Ambil semua werewolf (kecuali dia sendiri)
                        others = [w for w in players if w['user_id'] != p['user_id']]
                        others_text = "\n".join(f"- {w['username']}" for w in others) if others else "Hanya kamu."
                        await member.send(embed=discord.Embed(
                            title="Peranmu: Werewolf",
                            description=f"Silakan pilih target. Werewolf lain:\n{others_text}",
                            color=discord.Color.red()
                        ), view=TargetView(role, get_alive_players(game_id), self.handle_dm_selection))
                    elif role == 'witch':
                        await self.send_witch_dm(member, game_id)
                    else:
                        await self.send_dm_with_dropdown(member, role, get_alive_players(game_id), self.handle_dm_selection)
                    print(f"[NIGHT] DM ke {member.name} sebagai {role}")
                except Exception as e:
                    print(f"[NIGHT ERROR] Gagal kirim DM ke {member.name}: {e}")

        await asyncio.sleep(30)

        # ⛔ STOP jika game sudah dihentikan saat tidur
        game = get_active_game(ctx.guild.id)
        if not game or game['status'] == 'ended':
            print(f"[NIGHT] Game {game_id} sudah dihentikan, tidak lanjut evaluasi.")
            return

        print("[NIGHT] Waktu malam habis, evaluasi aksi.")
        actions = self.night_actions[game_id]
        target_to_kill = None

        # 1. Werewolf kill result
        votes = list(actions['werewolf'].values())
        if votes:
            target_to_kill = max(set(votes), key=votes.count)

        # 2. Witch heal cancels kill
        heal_target = actions['witch'].get('heal')
        if heal_target and heal_target == target_to_kill:
            print("[NIGHT] Witch menyembuhkan target werewolf.")
            target_to_kill = None

        # 3. Guardian protection
        if actions['guardian'] and actions['guardian'] == target_to_kill:
            print("[NIGHT] Guardian melindungi target.")
            target_to_kill = None

        # 4. Witch kill overrides all
        if actions['witch']['kill']:
            print("[NIGHT] Witch membunuh target override.")
            target_to_kill = actions['witch']['kill']

        if target_to_kill:
            kill_player(game_id, int(target_to_kill))
            log_event(game_id, round_number, "killed", int(target_to_kill))
            victim = ctx.guild.get_member(int(target_to_kill))
            if victim:
                await self.send_embed(ctx, "Pagi Hari", f"{victim.mention} ditemukan mati pagi ini.")
            else:
                await self.send_embed(ctx, "Pagi Hari", "Seseorang ditemukan mati pagi ini.")
        else:
            await self.send_embed(ctx, "Pagi Hari", "Malam tenang. Tidak ada korban.")

        await self.check_game_result(ctx, game_id)

        # ❗ Cek lagi apakah game dihentikan saat proses
        game = get_active_game(ctx.guild.id)
        if not game or game['status'] == 'ended':
            print(f"[NIGHT END] Game {game_id} dihentikan, tidak lanjut siang.")
            return

        update_game_status(game_id, 'day', round_number)
        await self.handle_day_phase(ctx, game_id, round_number)


    async def handle_day_phase(self, ctx, game_id, round_number):
        print(f"[DAY] Mulai siang {round_number} untuk game {game_id}")
        await self.send_embed(ctx, f"\u2600\ufe0f Siang {round_number}", "Diskusi dan voting dimulai. Kirim `mvote @user`.")
        await asyncio.sleep(30)

        # ⛔ STOP jika game dihentikan
        game = get_active_game(ctx.guild.id)
        if not game or game['status'] == 'ended':
            print(f"[DAY] Game {game_id} sudah dihentikan, tidak lanjut voting.")
            return

        print("[DAY] Waktu diskusi selesai, proses vote.")
        votes = get_votes_for_round(game_id, round_number, phase="day")
        if not votes:
            await self.send_embed(ctx, "Voting", "Tidak ada yang divote. Tidak ada yang mati.")
            print("[DAY] Tidak ada vote.")
        else:
            count = {}
            for v in votes:
                count[v['voted_id']] = count.get(v['voted_id'], 0) + 1
            target_id = max(count, key=count.get)
            kill_player(game_id, target_id)
            log_event(game_id, round_number, "voted", target_id)

            guild = ctx.guild if hasattr(ctx, 'guild') else ctx.channel.guild
            target = guild.get_member(target_id)
            await self.send_embed(ctx, "Voting Berhasil", f"{target.mention} telah digantung oleh warga!")
            print(f"[DAY] {target.name} digantung.")

        await self.check_game_result(ctx, game_id)

        # ❗ Cek lagi sebelum malam
        game = get_active_game(ctx.guild.id)
        if not game or game['status'] == 'ended':
            print(f"[DAY END] Game {game_id} dihentikan, tidak lanjut malam berikutnya.")
            return

        # ✅ Tambahan: hentikan jika tidak ada aksi malam DAN tidak ada vote siang
        last_night_actions = self.night_actions.get(game_id, {})
        no_night_action = (
            not last_night_actions.get('werewolf') and
            not last_night_actions.get('seer') and
            not last_night_actions.get('guardian') and
            not last_night_actions.get('witch', {}).get('heal') and
            not last_night_actions.get('witch', {}).get('kill')
        )

        if no_night_action and not votes:
            await self.send_embed(ctx, "Game Dihentikan", "🔕 Tidak ada aksi malam dan tidak ada voting siang.\nGame diberhentikan otomatis karena tidak ada partisipasi.")
            update_game_status(game_id, 'ended')
            reset_players(game_id)
            self.active_games.pop(ctx.guild.id, None)
            self.hosts.pop(ctx.guild.id, None)
            print(f"[AUTO-END] Game {game_id} dihentikan karena inaktivitas.")
            return

        update_game_status(game_id, 'night', round_number + 1)
        await self.handle_night_phase(ctx, game_id, round_number + 1)


    async def check_game_result(self, ctx, game_id):
        werewolves = [p for p in get_players_by_role(game_id, 'werewolf') if p['alive']]
        villagers = [p for p in get_alive_players(game_id) if p['role'] != 'werewolf']

        if not werewolves:
            await self.send_embed(ctx, "Warga Menang", "\U0001F389 Semua werewolf telah dieliminasi.")
            for p in get_alive_players(game_id):
                update_leaderboard(p['user_id'], ctx.guild.id, won=(p['role'] != 'werewolf'))
            update_game_status(game_id, 'ended')
            reset_players(game_id)
        elif len(werewolves) >= len(villagers):
            await self.send_embed(ctx, "Werewolf Menang", "\U0001F480 Mereka menguasai desa.")
            for p in get_alive_players(game_id):
                update_leaderboard(p['user_id'], ctx.guild.id, won=(p['role'] == 'werewolf'))
            update_game_status(game_id, 'ended')
            reset_players(game_id)

    @commands.command()
    async def vote(self, ctx, target: discord.Member):
        game = get_active_game(ctx.guild.id)
        if not game:
            await self.send_embed(ctx, "Gagal", "Tidak ada game aktif.")
            return

        if game['status'] != 'day':
            await self.send_embed(ctx, "Gagal", "Voting hanya bisa dilakukan saat siang.")
            return

        alive_ids = [p['user_id'] for p in get_alive_players(game['id'])]
        if ctx.author.id not in alive_ids or target.id not in alive_ids:
            await self.send_embed(ctx, "Gagal", "Hanya pemain yang masih hidup yang bisa voting.")
            return

        votes = get_votes_for_round(game['id'], game['current_round'], "day")
        if any(v['voter_id'] == ctx.author.id for v in votes):
            await self.send_embed(ctx, "Voting", "Kamu sudah melakukan voting hari ini.")
            return

        save_vote(game['id'], game['current_round'], ctx.author.id, target.id, "day")
        await self.send_embed(ctx, "Voting", f"{ctx.author.mention} memilih untuk menggantung {target.mention}.")

    @commands.command()
    async def werewolf_end(self, ctx):
        game = get_active_game(ctx.guild.id)
        if not game:
            await self.send_embed(ctx, "Gagal", "Tidak ada game aktif.")
            return

        logs = get_game_logs(game['id'])
        embed = discord.Embed(title="Ringkasan Game", color=discord.Color.gold())
        for log in logs:
            embed.add_field(
                name=f"Round {log['round']} - {log['event_type'].capitalize()}",
                value=f"Target: <@{log['target_id']}> | Info: {log.get('message', '-')}",
                inline=False
            )
        await ctx.send(embed=embed)

        update_game_status(game['id'], 'ended')
        reset_players(game['id'])

    @commands.Cog.listener()
    async def on_message(self, message):
        if not isinstance(message.channel, discord.DMChannel):
            return
        user_id = message.author.id

        for guild_id, game_id in self.active_games.items():
            game = get_active_game(guild_id)
            if not game or game['status'] != 'night':
                continue

            players = get_alive_players(game_id)
            player = next((p for p in players if p['user_id'] == user_id), None)
            if not player:
                continue

            role = player['role']
            content = message.content.strip()
            actions = self.night_actions.get(game_id)
            if not actions:
                continue

            try:
                if role == 'werewolf':
                    actions['werewolf'][user_id] = int(content)

                elif role == 'seer':
                    if actions['seer'] is not None:
                        await message.author.send("Kamu sudah menggunakan kemampuanmu malam ini.")
                        return

                    target_id = int(content)
                    target_player = next((p for p in players if p['user_id'] == target_id), None)
                    if target_player:
                        actions['seer'] = target_id
                        await message.author.send(
                            f"Peran mereka adalah: **{target_player['role'].upper()}**"
                        )

                elif role == 'guardian':
                    actions['guardian'] = int(content)

                elif role == 'witch':
                    parts = content.split()
                    if not parts or len(parts) < 2:
                        await message.author.send("Format salah. Gunakan `heal <user_id>` atau `kill <user_id>`.")
                        return

                    action = parts[0]
                    target_id = int(parts[1])
                    witch_actions = actions['witch']

                    if action == "heal":
                        if witch_actions.get('used_heal'):
                            await message.author.send("Potion penyembuh sudah habis.")
                            return
                        if witch_actions['heal'] or witch_actions['kill']:
                            await message.author.send("Kamu sudah melakukan aksi malam ini.")
                            return
                        witch_actions['heal'] = target_id
                        witch_actions['used_heal'] = True
                        await message.author.send(f"✅ Kamu akan menyembuhkan <@{target_id}>.")

                    elif action == "kill":
                        if witch_actions.get('used_kill'):
                            await message.author.send("Potion racun sudah habis.")
                            return
                        if witch_actions['heal'] or witch_actions['kill']:
                            await message.author.send("Kamu sudah melakukan aksi malam ini.")
                            return
                        witch_actions['kill'] = target_id
                        witch_actions['used_kill'] = True
                        await message.author.send(f"☠️ Kamu akan membunuh <@{target_id}>.")
            except:
                pass

async def setup(bot):
    await bot.add_cog(Werewolf(bot))