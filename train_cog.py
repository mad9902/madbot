import discord
from discord.ext import commands
import random
import asyncio
from contextlib import closing
from database import connect_db
from database import (
    get_user_character_by_id,
    create_character,
    get_enemy_by_level,
    save_battle_result,
    character_exists,
    get_recent_battle_logs,
    character_name_exists,
    get_leaderboard,
    get_character_skills, get_available_skills,assign_skill_to_character,
    get_recent_battle_logs, get_character_items, get_items_by_rarity, assign_item_to_character

)

class TrainCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="unlockskill")
    async def unlock_skill(self, ctx, *, skill_name):
        char = get_user_character_by_id(ctx.author.id)
        if not char:
            return await ctx.send("❌ Kamu belum punya karakter.")

        if char['skill_point'] <= 0:
            return await ctx.send("❌ Kamu tidak punya Skill Point.")

        available = get_available_skills(char["level"])
        skill = next((s for s in available if s["name"].lower() == skill_name.lower()), None)
        if not skill:
            return await ctx.send("❌ Skill tidak tersedia atau belum terbuka.")

        current_skills = get_character_skills(char["id"])
        if any(s["id"] == skill["id"] for s in current_skills):
            return await ctx.send("❌ Skill ini sudah kamu miliki.")

        assign_skill_to_character(char["id"], skill["id"])
        with connect_db() as db, closing(db.cursor()) as cursor:
            cursor.execute("""
                UPDATE user_characters
                SET skill_point = skill_point - 1
                WHERE id = %s AND skill_point > 0
            """, (char["id"],))
            db.commit()

        await ctx.send(f"✅ Skill '{skill['name']}' berhasil di-unlock!")


    @commands.command(name="items")
    async def show_items(self, ctx):
        user_id = ctx.author.id
        char = get_user_character_by_id(user_id)
        if not char:
            return await ctx.send("❌ Kamu belum punya karakter.")

        items = get_character_items(char["id"])
        if not items:
            return await ctx.send("📭 Belum ada item.")

        embed = discord.Embed(title="🎒 Item yang Dimiliki", color=discord.Color.blurple())
        for item in items:
            status = "✅ Equipped" if item["is_equipped"] else "❌"
            embed.add_field(
                name=f'{item["name"]} [{item["rarity"].capitalize()}] ({status})',
                value=item["description"] or "Tidak ada deskripsi.",
                inline=False
            )
        await ctx.send(embed=embed)

    @commands.command(name="equip")
    async def equip_item(self, ctx, *, item_name: str):
        user_id = ctx.author.id
        char = get_user_character_by_id(user_id)
        if not char:
            return await ctx.send("❌ Kamu belum punya karakter.")

        items = get_character_items(char["id"])
        selected = next(
            (i for i in items if i["name"].lower() == item_name.lower()), None
        )

        if not selected:
            return await ctx.send("❌ Item tidak ditemukan atau tidak dimiliki.")

        with connect_db() as db, closing(db.cursor()) as cursor:
            # Unequip semua item dengan slot yang sama
            cursor.execute("""
                UPDATE character_items
                SET is_equipped = FALSE
                WHERE character_id = %s AND item_id IN (
                    SELECT id FROM items WHERE slot = %s
                )
            """, (char["id"], selected["slot"]))

            # Equip item yang dipilih
            cursor.execute("""
                UPDATE character_items
                SET is_equipped = TRUE
                WHERE character_id = %s AND item_id = %s
            """, (char["id"], selected["id"]))
            db.commit()

        await ctx.send(f"✅ {selected['name']} telah di-*equip*.")


    @commands.command(name="skillassign")
    async def assign_skill(self, ctx, *, skill_name):
        char = get_user_character_by_id(ctx.author.id)
        if not char:
            return await ctx.send("❌ Kamu belum punya karakter.")

        level = char["level"]
        available_skills = get_available_skills(level)

        # Cari skill dengan nama (case insensitive)
        match = next((s for s in available_skills if s["name"].lower() == skill_name.lower()), None)
        if not match:
            return await ctx.send("❌ Skill tidak ditemukan atau belum terbuka.")

        try:
            assign_skill_to_character(char["id"], match["id"])
            await ctx.send(f"✅ Skill '{match['name']}' berhasil diassign!")
        except ValueError as e:
            await ctx.send(f"❌ {str(e)}")


    @commands.command(name="availableskills")
    async def available_skills(self, ctx):
        char = get_user_character_by_id(ctx.author.id)
        if not char:
            await ctx.send("❌ Kamu belum punya karakter.")
            return

        skills = get_available_skills(char["level"])
        if not skills:
            await ctx.send("Belum ada skill yang tersedia untuk level ini.")
            return

        msg = "**Skill yang tersedia:**\n"
        for skill in skills:
            msg += f"🌀 {skill['name']} - Level {skill['unlock_level']}\n"
        await ctx.send(msg)


    @commands.command(name="battlelogs")
    async def battle_logs(self, ctx):
        logs = get_recent_battle_logs(ctx.author.id)
        if not logs:
            await ctx.send("📭 Belum ada pertarungan.")
            return

        msg = "**📜 Riwayat Pertarungan Terakhir:**\n"
        for l in logs:
            status = "🏆" if l["result"] == "win" else "💀"
            msg += f"{status} vs {l['enemy_name']} | EXP: {l['exp_gain']} | Coin: {l['coin_gain']} | {l['created_at']}\n"
        await ctx.send(msg)

    @commands.command(name="top")
    async def top_characters(self, ctx):
        top = get_leaderboard()
        if not top:
            await ctx.send("📉 Belum ada karakter.")
            return

        msg = "**🏆 Leaderboard:**\n"
        for i, row in enumerate(top, start=1):
            msg += f"{i}. {row['character_name']} (Lv {row['level']} | WS: {row['win_streak']})\n"
        await ctx.send(msg)

    @commands.command(name="myskills")
    async def my_skills(self, ctx):
        char = get_user_character_by_id(ctx.author.id)
        if not char:
            await ctx.send("❌ Kamu belum punya karakter.")
            return

        skills = get_character_skills(char["id"])
        if not skills:
            await ctx.send("📭 Belum ada skill yang dimiliki.")
            return

        msg = "**🧠 Skill yang dimiliki:**\n"
        for s in skills:
            msg += f"- {s['name']} ({s['type']}): {s['effect']}\n"
        await ctx.send(msg)

    @commands.command(name="createchar")
    async def create_character_cmd(self, ctx, *, name: str = None):
        if not name:
            await ctx.send("❗ Gunakan: `!createchar <nama>`")
            return

        if character_exists(ctx.author.id):
            await ctx.send("❌ Kamu sudah punya karakter.")
            return

        if character_name_exists(name):
            await ctx.send("❌ Nama karakter sudah digunakan.")
            return

        try:
            create_character(ctx.author.id, name)
            await ctx.send(f"✅ Karakter `{name}` berhasil dibuat!")
        except Exception as e:
            await ctx.send(f"❌ Gagal membuat karakter: {e}")

    @commands.command(name="gamehelp", aliases=["helpgame", "ghelp"])
    async def game_help(self, ctx):
        embed = discord.Embed(
            title="🎮 Sistem Game MadBot — Petunjuk Lengkap",
            description="Latih karaktermu, lawan musuh, dan kuasai arena virtual!",
            color=discord.Color.purple()
        )
        embed.add_field(name="🧱 Karakter", value="Gunakan `!createchar <nama>` untuk memulai.", inline=False)
        embed.add_field(name="🧪 Latihan", value="Gunakan `!train` untuk bertarung dan naik level.", inline=False)
        embed.add_field(name="📊 Statistik", value="Gunakan `!trainstats` untuk cek progres kamu.", inline=False)
        embed.add_field(name="📜 Log Latihan", value="Gunakan `!trainlog` untuk melihat histori pertarungan kamu.", inline=False)
        embed.set_footer(text="Fitur akan terus bertambah.")
        await ctx.send(embed=embed)

    @commands.command(name="train")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def train_command(self, ctx):
        user_id = ctx.author.id
        db_character = get_user_character_by_id(user_id)
        if not db_character:
            await ctx.send("❌ Kamu belum punya karakter!")
            return

        enemy = get_enemy_by_level(db_character["train_level"])
        if not enemy:
            await ctx.send("❌ Musuh tidak ditemukan.")
            return

        char = {
            "name": db_character["character_name"],
            "hp": db_character["base_hp"] + db_character["level"] * 10,
            "atk": db_character["base_atk"] + db_character["level"] * 1.5,
            "def": db_character["base_def"],
            "spd": db_character["base_spd"],
        }
        enemy_stat = {
            "name": enemy["name"],
            "hp": enemy["base_hp"] + db_character["train_level"] * 5,
            "atk": enemy["base_atk"] + db_character["train_level"] * 1.2,
            "def": enemy["base_def"],
            "spd": enemy["base_spd"],
        }

        await ctx.send(f"🧪 {char['name']} melawan **{enemy_stat['name']}**!")
        log = []
        turn = 1

        while char["hp"] > 0 and enemy_stat["hp"] > 0:
            log.append(f"\n🔁 **Turn {turn}**")
            first, second = (char, enemy_stat) if char["spd"] >= enemy_stat["spd"] else (enemy_stat, char)
            for attacker, defender in [(first, second), (second, first)]:
                if defender["hp"] <= 0:
                    break
                dmg = max(1, int(attacker["atk"] - defender["def"] + random.randint(-3, 3)))
                defender["hp"] -= dmg
                log.append(f"🔪 {attacker['name']} menyerang {defender['name']} -{dmg} HP (tersisa {max(0, defender['hp'])})")
            turn += 1
            await asyncio.sleep(1)

        result = "win" if char["hp"] > 0 else "lose"
        exp_gain = random.randint(20, 35) if result == "win" else 0
        coin_gain = random.randint(5, 10) if result == "win" else 0
        skill_gain = 1 if result == "win" and random.random() < 0.3 else 0

        embed = discord.Embed(title="📜 Hasil Pertarungan", color=discord.Color.green() if result == "win" else discord.Color.red())
        embed.add_field(name="Status", value="🏆 Menang!" if result == "win" else "💀 Kalah.")
        embed.add_field(name="EXP", value=f"+{exp_gain}")
        embed.add_field(name="Coin", value=f"+{coin_gain}")
        if skill_gain:
            embed.add_field(name="Skill Point", value="+1")

        if result == "win":
            # Only roll item drop if player wins
            roll = random.random()
            rarity = None
            if roll < 0.5:
                rarity = "common"
            elif roll < 0.75:
                rarity = "uncommon"
            elif roll < 0.9:
                rarity = "rare"
            elif roll < 0.995:
                rarity = "epic"
            elif roll < 0.9991:
                rarity = "legendary"

            if rarity:
                items = get_items_by_rarity(rarity)
                if items:
                    dropped_item = random.choice(items)
                    assign_item_to_character(db_character["id"], dropped_item["id"])
                    embed.add_field(
                        name="Item Drop",
                        value=f"🎁 {dropped_item['name']} ({dropped_item['rarity'].capitalize()})",
                        inline=False
                    )

        embed.set_footer(text=f"{char['name']} vs {enemy_stat['name']}")
        await ctx.send(embed=embed)

        save_battle_result(user_id, db_character["id"], enemy["id"], result, exp_gain, coin_gain, skill_gain, log)


    @commands.command(name="trainstats")
    async def train_stats(self, ctx):
        db_character = get_user_character_by_id(ctx.author.id)
        if not db_character:
            await ctx.send("❌ Karakter belum ada.")
            return

        embed = discord.Embed(title=f"📊 Stats {db_character['character_name']}", color=discord.Color.blue())
        embed.add_field(name="Level", value=str(db_character["level"]))
        embed.add_field(name="EXP", value=f"{db_character['exp']} / {db_character['exp_to_next']}")
        embed.add_field(name="Train Level", value=str(db_character["train_level"]))
        embed.add_field(name="Win Streak", value=str(db_character["win_streak"]))
        await ctx.send(embed=embed)

    @commands.command(name="trainlog")
    async def train_log(self, ctx):
        logs = get_recent_battle_logs(ctx.author.id, limit=5)
        if not logs:
            await ctx.send("📝 Belum ada histori latihan.")
            return

        embed = discord.Embed(title="📖 Log Latihan Terakhir", color=discord.Color.orange())
        for log in logs:
            embed.add_field(
                name=f"{log['created_at'].strftime('%d %b %Y %H:%M')}",
                value=f"🆚 {log['enemy_name']} — **{log['result'].upper()}** | +{log['exp_gain']} EXP, +{log['coin_gain']}💰",
                inline=False
            )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(TrainCog(bot))
