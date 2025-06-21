import mysql.connector
from mysql.connector import Error
import os
import time
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

def add_timed_word(db, guild_id, title, content):
    cursor = db.cursor()
    cursor.execute("INSERT INTO timed_words (guild_id, title, content) VALUES (%s, %s, %s)", (guild_id, title, content))
    db.commit()

def get_timed_words(db, guild_id):
    cursor = db.cursor()
    cursor.execute("SELECT title, content FROM timed_words WHERE guild_id = %s", (guild_id,))
    return cursor.fetchall()


