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



