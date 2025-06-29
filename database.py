import mysql.connector
from mysql.connector import Error
import os
from contextlib import closing
import time
import json
from dotenv import load_dotenv

load_dotenv()

def retry_database(retries=5, delay=3):
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except Error as e:
                    last_exception = e
                    print(f"[Attempt {attempt}] Gagal koneksi ke database: {e}. Retry in {delay}s...")
                    time.sleep(delay)
            print(f"Gagal setelah {retries} percobaan.")
            raise last_exception
        return wrapper
    return decorator

@retry_database(retries=3, delay=3)
def ensure_database_exists():
    try:
        db = mysql.connector.connect(
            host=os.getenv("MYSQL_HOST"),
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASS") or None
        )
        cursor = db.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {os.getenv('MYSQL_DB')}")
        cursor.close()
        db.close()
    except Error as e:
        print(f"[DB INIT ERROR] Failed to create database: {e}")

@retry_database(retries=3, delay=3)
def connect_db():
    db = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASS") or None,
        database=os.getenv("MYSQL_DB")
    )
    return db

def get_user_xp(db, user_id, guild_id):
    if db is None:
        return 0
    cursor = db.cursor()
    cursor.execute(
        "SELECT xp FROM user_levels WHERE user_id=%s AND guild_id=%s",
        (user_id, guild_id)
    )
    result = cursor.fetchone()
    cursor.close()

    if result:
        return result[0]
    return 0

def set_user_xp(db, user_id, guild_id, xp):
    if db is None:
        return
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO user_levels (user_id, guild_id, xp) VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE xp=%s",
        (user_id, guild_id, xp, xp)
    )
    db.commit()
    cursor.close()


def insert_level_role(db, guild_id, level, role_id):
    if db is None:
        return
    cursor = db.cursor()
    # Pastikan tabel sudah ada
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS level_roles (
            guild_id VARCHAR(50) NOT NULL,
            level INT NOT NULL,
            role_id VARCHAR(50) NOT NULL,
            PRIMARY KEY (guild_id, level)
        )
    """)
    cursor.execute("""
        INSERT INTO level_roles (guild_id, level, role_id)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE role_id = VALUES(role_id)
    """, (str(guild_id), level, str(role_id)))
    db.commit()
    cursor.close()


def get_level_role(db, guild_id, level):
    if db is None:
        return None
    cursor = db.cursor()
    cursor.execute(
        "SELECT role_id FROM level_roles WHERE guild_id=%s AND level=%s",
        (str(guild_id), level)
    )
    result = cursor.fetchone()
    cursor.close()

    if result:
        return int(result[0])
    return None

def is_level_disabled(db, guild_id):
    cursor = db.cursor()
    cursor.execute("SELECT 1 FROM disabled_levels WHERE guild_id = %s", (guild_id,))
    result = cursor.fetchone()
    cursor.close()
    return result is not None

def disable_level(db, guild_id):
    cursor = db.cursor()
    cursor.execute("INSERT IGNORE INTO disabled_levels (guild_id) VALUES (%s)", (guild_id,))
    db.commit()
    cursor.close()

def enable_level(db, guild_id):
    cursor = db.cursor()
    cursor.execute("DELETE FROM disabled_levels WHERE guild_id = %s", (guild_id,))
    db.commit()
    cursor.close()

def get_no_xp_roles(db, guild_id):
    cursor = db.cursor()
    cursor.execute("SELECT role_id FROM no_xp_roles WHERE guild_id = %s", (guild_id,))
    roles = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return roles

def add_no_xp_role(db, guild_id, role_id):
    cursor = db.cursor()
    cursor.execute("INSERT IGNORE INTO no_xp_roles (guild_id, role_id) VALUES (%s, %s)", (guild_id, role_id))
    db.commit()
    cursor.close()

def remove_no_xp_role(db, guild_id, role_id):
    cursor = db.cursor()
    cursor.execute("DELETE FROM no_xp_roles WHERE guild_id = %s AND role_id = %s", (guild_id, role_id))
    db.commit()
    cursor.close()

def get_channel_settings(db, guild_id, setting_type):
    if db is None:
        return None
    cursor = db.cursor()
    cursor.execute("""
        SELECT channel_id FROM channel_settings
        WHERE guild_id=%s AND setting_type=%s
    """, (guild_id, setting_type))
    row = cursor.fetchone()
    cursor.close()
    if row:
        return str(row[0])
    return None

def set_channel_settings(db, guild_id, setting_type, channel_id):
    if db is None:
        return
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO channel_settings (guild_id, setting_type, channel_id)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE channel_id=VALUES(channel_id)
    """, (guild_id, setting_type, channel_id))
    db.commit()
    cursor.close()


def set_afk(db, user_id, guild_id, reason):
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO afk_status (user_id, guild_id, reason)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE reason=VALUES(reason), since=CURRENT_TIMESTAMP
    """, (user_id, guild_id, reason))
    db.commit()
    cursor.close()

def get_afk(db, user_id, guild_id):
    cursor = db.cursor()
    cursor.execute("SELECT reason FROM afk_status WHERE user_id=%s AND guild_id=%s", (user_id, guild_id))
    row = cursor.fetchone()
    cursor.close()
    return row[0] if row else None

def clear_afk(db, user_id, guild_id):
    cursor = db.cursor()
    cursor.execute("DELETE FROM afk_status WHERE user_id=%s AND guild_id=%s", (user_id, guild_id))
    db.commit()
    cursor.close()

def get_xp_leaderboard(db, guild_id, limit=10):
    cursor = db.cursor()
    cursor.execute("""
        SELECT user_id, xp FROM user_levels
        WHERE guild_id = %s
        ORDER BY xp DESC
        LIMIT %s
    """, (guild_id, limit))
    results = cursor.fetchall()
    cursor.close()
    return results

def set_birthday(db, user_id, guild_id, birthdate, display_name=None, wish=None):
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO birthdays (user_id, guild_id, birthdate, display_name, wish)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
            birthdate = VALUES(birthdate),
            display_name = VALUES(display_name),
            wish = VALUES(wish)
    """, (user_id, guild_id, birthdate, display_name, wish))
    db.commit()
    cursor.close()


def delete_birthday(db, user_id, guild_id):
    cursor = db.cursor()
    cursor.execute("DELETE FROM birthdays WHERE user_id=%s AND guild_id=%s", (user_id, guild_id))
    db.commit()
    cursor.close()


def get_birthday(db, user_id, guild_id):
    cursor = db.cursor()
    cursor.execute("""
        SELECT birthdate, display_name, wish FROM birthdays
        WHERE user_id = %s AND guild_id = %s
    """, (user_id, guild_id))
    result = cursor.fetchone()
    cursor.close()
    return result if result else None


def get_today_birthdays(db):
    cursor = db.cursor()
    cursor.execute("""
        SELECT user_id, guild_id, display_name, wish FROM birthdays
        WHERE DAY(birthdate) = DAY(CURDATE()) AND MONTH(birthdate) = MONTH(CURDATE())
    """)
    result = cursor.fetchall()
    cursor.close()
    return result


def get_all_birthdays(db, guild_id):
    cursor = db.cursor()
    cursor.execute("""
        SELECT user_id, birthdate, display_name, wish FROM birthdays
        WHERE guild_id = %s
        ORDER BY MONTH(birthdate), DAY(birthdate)
    """, (guild_id,))
    result = cursor.fetchall()
    cursor.close()
    return result

def add_banned_word(db, guild_id, word, response, word_type=None):
    cursor = db.cursor()
    if word_type:
        cursor.execute("""
            INSERT INTO banned_words (guild_id, word, response, type)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                response = VALUES(response),
                type = VALUES(type)
        """, (guild_id, word.lower(), response, word_type))
    else:
        cursor.execute("""
            INSERT INTO banned_words (guild_id, word, response)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE response = VALUES(response)
        """, (guild_id, word.lower(), response))
    db.commit()
    cursor.close()


def get_all_banned_words(db, guild_id):
    cursor = db.cursor()
    cursor.execute("SELECT word, response, type FROM banned_words WHERE guild_id = %s", (guild_id,))
    results = cursor.fetchall()
    cursor.close()
    return results  # list of tuples: (word, response, type)

def remove_banned_word(db, guild_id, word):
    cursor = db.cursor()
    cursor.execute("DELETE FROM banned_words WHERE guild_id = %s AND word = %s", (guild_id, word.lower()))
    db.commit()
    cursor.close()


def set_welcome_message(db, guild_id: int, message: str):
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO welcome_messages (guild_id, message)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE message = VALUES(message)
    """, (guild_id, message))
    db.commit()

def get_welcome_message(db, guild_id: int) -> str | None:
    cursor = db.cursor()
    cursor.execute("SELECT message FROM welcome_messages WHERE guild_id = %s", (guild_id,))
    result = cursor.fetchone()
    return result[0] if result else None

def add_timed_word(db, guild_id, title, content, interval=30):
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO timed_words (guild_id, title, content, interval_minutes) VALUES (%s, %s, %s, %s)",
        (guild_id, title, content, interval)
    )
    db.commit()

def get_timed_words(db, guild_id):
    cursor = db.cursor()
    cursor.execute("SELECT title, content, interval_minutes FROM timed_words WHERE guild_id = %s", (guild_id,))
    return cursor.fetchall() 

def remove_timed_word(db, guild_id, title):
    cursor = db.cursor()
    cursor.execute("SELECT title FROM timed_words WHERE guild_id = %s", (guild_id,))
    rows = cursor.fetchall()
    for row in rows:
        if row[0].lower() == title.lower():
            cursor.execute(
                "DELETE FROM timed_words WHERE guild_id = %s AND title = %s",
                (guild_id, row[0])
            )
            db.commit()
            break

def save_confession(db, guild_id, user_id, confession_id, content):
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO confessions (guild_id, user_id, confession_id, content)
        VALUES (%s, %s, %s, %s)
    """, (guild_id, user_id, confession_id, content))
    db.commit()

### CHARACTER UTILITY ###

RARITY_LEVELS = ('common', 'uncommon', 'rare', 'epic', 'legendary')

def character_exists(user_id):
    with connect_db() as db, closing(db.cursor()) as cursor:
        cursor.execute("SELECT id FROM user_characters WHERE user_id = %s", (user_id,))
        return cursor.fetchone() is not None

def character_name_exists(name):
    with connect_db() as db, closing(db.cursor()) as cursor:
        cursor.execute("SELECT id FROM user_characters WHERE character_name = %s", (name,))
        return cursor.fetchone() is not None

def create_character(user_id, name):
    if character_exists(user_id):
        raise ValueError("Kamu sudah memiliki karakter!")
    if character_name_exists(name):
        raise ValueError("Nama karakter sudah dipakai!")
    if not name or not name.strip() or len(name.strip()) > 50:
        raise ValueError("Nama karakter tidak valid.")

    with connect_db() as db, closing(db.cursor()) as cursor:
        cursor.execute("""
            INSERT INTO user_characters (
                user_id, character_name,
                level, exp, exp_to_next,
                base_hp, base_atk, base_def, base_spd,
                win_streak, train_level, last_checkpoint
            ) VALUES (%s, %s, 1, 0, 100, 100, 20, 10, 10, 0, 1, 1)
        """, (user_id, name))
        db.commit()

def get_user_character_by_id(user_id):
    with connect_db() as db, closing(db.cursor(dictionary=True)) as cursor:
        cursor.execute("SELECT * FROM user_characters WHERE user_id = %s", (user_id,))
        return cursor.fetchone()

def level_up_character(character_id, exp_gain):
    with connect_db() as db, closing(db.cursor(dictionary=True)) as cursor:
        cursor.execute("SELECT id, level, exp, exp_to_next FROM user_characters WHERE id = %s", (character_id,))
        char = cursor.fetchone()
        if not char:
            raise ValueError("Karakter tidak ditemukan.")

        level = char["level"]
        exp = char["exp"] + exp_gain
        exp_to_next = char["exp_to_next"]
        new_skills = []
        level_ups = 0

        while exp >= exp_to_next:
            exp -= exp_to_next
            level += 1
            level_ups += 1
            exp_to_next = round(exp_to_next * 1.2)

            cursor.execute("SELECT * FROM skills WHERE unlock_level = %s", (level,))
            unlocked = cursor.fetchall()
            for skill in unlocked:
                cursor.execute("""
                    INSERT IGNORE INTO character_skills (character_id, skill_id)
                    VALUES (%s, %s)
                """, (character_id, skill["id"]))
                new_skills.append(skill["name"])

                cursor.execute("""
                    INSERT INTO system_logs (character_id, log_type, description, metadata_json)
                    VALUES (%s, 'skill_unlock', %s, %s)
                """, (
                    character_id,
                    f"Unlocked skill: {skill['name']}",
                    json.dumps({"skill_id": skill["id"]})
                ))

        cursor.execute("""
            UPDATE user_characters
            SET level = %s, exp = %s, exp_to_next = %s
            WHERE id = %s
        """, (level, exp, exp_to_next, character_id))

        if level_ups > 0:
            cursor.execute("""
                INSERT INTO system_logs (character_id, log_type, description, metadata_json)
                VALUES (%s, 'level_up', %s, %s)
            """, (
                character_id,
                f"Naik level ke {level}",
                json.dumps({"level_ups": level_ups, "new_level": level})
            ))

        db.commit()
        return {
            "new_level": level,
            "unlocked_skills": new_skills
        }

def get_enemy_by_level(train_level):
    with connect_db() as db, closing(db.cursor(dictionary=True)) as cursor:
        cursor.execute("""
            SELECT * FROM enemy_pool
            WHERE min_level <= %s AND max_level >= %s
            ORDER BY RAND() LIMIT 1
        """, (train_level, train_level))
        return cursor.fetchone()


def save_battle_result(user_id, character_id, enemy_id, result, exp_gain, coin_gain, skill_point_gain, turn_log):
    with connect_db() as db, closing(db.cursor()) as cursor:
        cursor.execute("""
            INSERT INTO train_battle_log (
                user_id, character_id, enemy_id, result,
                exp_gain, coin_gain, skill_point_gain, turn_log_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id, character_id, enemy_id, result,
            exp_gain, coin_gain, skill_point_gain,
            json.dumps(turn_log)
        ))

        cursor.execute("""
            SELECT level, exp, exp_to_next, win_streak, train_level, skill_point
            FROM user_characters WHERE id = %s
        """, (character_id,))
        row = cursor.fetchone()
        if not row:
            db.rollback()
            raise ValueError("Karakter tidak ditemukan.")

        level, exp, exp_to_next, win_streak, train_level, skill_point = row

        if result == "win":
            exp += exp_gain
            while exp >= exp_to_next:
                exp -= exp_to_next
                level += 1
                exp_to_next = round(exp_to_next * 1.2)

            win_streak += 1
            train_level += 1
            skill_point += skill_point_gain  # Tambah poin skill jika menang
        else:
            win_streak = 0

        cursor.execute("""
            UPDATE user_characters
            SET level = %s, exp = %s, exp_to_next = %s,
                win_streak = %s, train_level = %s, skill_point = %s
            WHERE id = %s
        """, (level, exp, exp_to_next, win_streak, train_level, skill_point, character_id))
        db.commit()

def get_recent_battle_logs(user_id, limit=5):
    with connect_db() as db, closing(db.cursor(dictionary=True)) as cursor:
        cursor.execute("""
            SELECT t.created_at, t.result, t.exp_gain, t.coin_gain, e.name AS enemy_name
            FROM train_battle_log t
            JOIN enemy_pool e ON t.enemy_id = e.id
            WHERE t.user_id = %s
            ORDER BY t.created_at DESC
            LIMIT %s
        """, (user_id, limit))
        return cursor.fetchall()

def get_available_skills(level):
    with connect_db() as db, closing(db.cursor(dictionary=True)) as cursor:
        cursor.execute("SELECT * FROM skills WHERE unlock_level <= %s", (level,))
        return cursor.fetchall()

def assign_skill_to_character(character_id, skill_id):
    with connect_db() as db, closing(db.cursor()) as cursor:
        # Cek skill point
        cursor.execute("SELECT skill_point FROM user_characters WHERE id = %s", (character_id,))
        row = cursor.fetchone()
        if not row or row[0] < 1:
            raise ValueError("Skill point tidak cukup.")

        # Cek apakah skill sudah dimiliki
        cursor.execute("""
            SELECT 1 FROM character_skills
            WHERE character_id = %s AND skill_id = %s
        """, (character_id, skill_id))
        if cursor.fetchone():
            raise ValueError("Skill sudah dimiliki.")

        # Assign dan kurangi skill point
        cursor.execute("""
            INSERT INTO character_skills (character_id, skill_id)
            VALUES (%s, %s)
        """, (character_id, skill_id))
        cursor.execute("""
            UPDATE user_characters
            SET skill_point = skill_point - 1
            WHERE id = %s
        """, (character_id,))
        db.commit()


def get_character_skills(character_id):
    with connect_db() as db, closing(db.cursor(dictionary=True)) as cursor:
        cursor.execute("""
            SELECT s.* FROM character_skills cs
            JOIN skills s ON cs.skill_id = s.id
            WHERE cs.character_id = %s
        """, (character_id,))
        return cursor.fetchall()

def get_items_by_rarity(rarity):
    with connect_db() as db, closing(db.cursor(dictionary=True)) as cursor:
        cursor.execute("SELECT * FROM items WHERE rarity = %s", (rarity,))
        return cursor.fetchall()

def assign_item_to_character(character_id, item_id):
    with connect_db() as db, closing(db.cursor()) as cursor:
        cursor.execute("""
            INSERT INTO character_items (character_id, item_id)
            VALUES (%s, %s)
        """, (character_id, item_id))
        db.commit()

def get_character_items(character_id):
    with connect_db() as db, closing(db.cursor(dictionary=True)) as cursor:
        cursor.execute("""
            SELECT i.*, ci.is_equipped
            FROM character_items ci
            JOIN items i ON ci.item_id = i.id
            WHERE ci.character_id = %s
        """, (character_id,))
        return cursor.fetchall()

def get_leaderboard(top_n=10):
    with connect_db() as db, closing(db.cursor(dictionary=True)) as cursor:
        cursor.execute("""
            SELECT character_name, level, exp, win_streak
            FROM user_characters
            ORDER BY level DESC, exp DESC, win_streak DESC
            LIMIT %s
        """, (top_n,))
        return cursor.fetchall()

def log_system_event(character_id, log_type, description, metadata=None):
    with connect_db() as db, closing(db.cursor()) as cursor:
        cursor.execute("""
            INSERT INTO system_logs (character_id, log_type, description, metadata_json)
            VALUES (%s, %s, %s, %s)
        """, (
            character_id, log_type, description,
            json.dumps(metadata) if metadata else None
        ))
        db.commit()

