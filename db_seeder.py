import json
from database import connect_db  # pastikan file ini berada di folder yang sama

def seed_data():
    with connect_db() as db:
        cursor = db.cursor()

        # Seed enemy_pool
        enemies = [
            ('Slime', 50, 8, 3, 5, 1, 3),
            ('Goblin', 80, 12, 5, 7, 2, 5),
            ('Orc', 120, 18, 10, 6, 4, 8),
            ('Dark Knight', 180, 25, 15, 10, 6, 10),
        ]
        cursor.executemany("""
            INSERT INTO enemy_pool (name, base_hp, base_atk, base_def, base_spd, min_level, max_level)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, enemies)

        # Seed skills
        skills = [
            ('Power Strike', 'active', 2, {"multiplier": 1.5, "cooldown": 3}),
            ('Shield Wall', 'active', 4, {"def_boost": 5, "duration": 2}),
            ('Quick Reflexes', 'passive', 3, {"spd_bonus": 2}),
            ('Berserker', 'passive', 6, {"atk_bonus": 4, "hp_threshold": 0.5}),
        ]
        cursor.executemany("""
            INSERT INTO skills (name, type, unlock_level, effect_json)
            VALUES (%s, %s, %s, %s)
        """, [(n, t, l, json.dumps(e)) for n, t, l, e in skills])

        # Seed items
        items = [
            ('Iron Sword', 'weapon', 'common', {"atk": 5}),
            ('Steel Shield', 'armor', 'uncommon', {"def": 3}),
            ('Boots of Swiftness', 'accessory', 'rare', {"spd": 2}),
            ('Amulet of Vitality', 'accessory', 'epic', {"hp": 20}),
            ('Blade of Destiny', 'weapon', 'legendary', {"atk": 12, "crit_chance": 0.15}),
        ]
        cursor.executemany("""
            INSERT INTO items (name, type, rarity, stat_bonus_json)
            VALUES (%s, %s, %s, %s)
        """, [(n, t, r, json.dumps(e)) for n, t, r, e in items])


        db.commit()
        print("✅ Seeder selesai dijalankan.")

if __name__ == "__main__":
    seed_data()
