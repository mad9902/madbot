import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

load_dotenv()

def connect_db():
    try:
        db = mysql.connector.connect(
            host=os.getenv("MYSQL_HOST"),
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASS") or None,
            database=os.getenv("MYSQL_DB")
        )
        return db
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def get_user_xp(user_id, guild_id):
    db = connect_db()
    if db is None:
        return 0
    cursor = db.cursor()
    cursor.execute(
        "SELECT xp FROM user_levels WHERE user_id=%s AND guild_id=%s",
        (user_id, guild_id)
    )
    result = cursor.fetchone()
    cursor.close()
    db.close()
    if result:
        return result[0]
    return 0

def set_user_xp(user_id, guild_id, xp):
    db = connect_db()
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
    db.close()

def insert_level_role(guild_id, level, role_id):
    db = connect_db()
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
    db.close()

def get_level_role(guild_id, level):
    db = connect_db()
    if db is None:
        return None
    cursor = db.cursor()
    cursor.execute(
        "SELECT role_id FROM level_roles WHERE guild_id=%s AND level=%s",
        (str(guild_id), level)
    )
    result = cursor.fetchone()
    cursor.close()
    db.close()
    if result:
        return int(result[0])
    return None
