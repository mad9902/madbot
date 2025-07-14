import mysql.connector
from mysql.connector import Error
import os
import time
from datetime import datetime, timedelta
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

def close_connection(conn):
    if conn and conn.is_connected():
        conn.close()


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
        try:
            return int(row[0])
        except ValueError:
            return None
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
# ==================== GAME CORE ====================
def create_new_game(guild_id, channel_id):
    conn = connect_db()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO werewolf_games (guild_id, channel_id)
            VALUES (%s, %s)
        """, (guild_id, channel_id))
        conn.commit()
        return cursor.lastrowid
    except Error as e:
        print(f"[DB] create_new_game: {e}")
        return None
    finally:
        close_connection(conn)

def update_game_status(game_id, status, round_number=None):
    conn = connect_db()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        if round_number is not None:
            cursor.execute("""
                UPDATE werewolf_games SET status = %s, current_round = %s WHERE id = %s
            """, (status, round_number, game_id))
        else:
            cursor.execute("""
                UPDATE werewolf_games SET status = %s WHERE id = %s
            """, (status, game_id))
        conn.commit()
    except Error as e:
        print(f"[DB] update_game_status: {e}")
    finally:
        close_connection(conn)

def get_active_game(guild_id):
    conn = connect_db()
    if not conn:
        return None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM werewolf_games
            WHERE guild_id = %s AND status != 'ended'
            ORDER BY id DESC LIMIT 1
        """, (guild_id,))
        return cursor.fetchone()
    except Error as e:
        print(f"[DB] get_active_game: {e}")
        return None
    finally:
        close_connection(conn)

# ==================== PLAYERS ====================
def add_player(game_id, user_id, username, role):
    conn = connect_db()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO werewolf_players (game_id, user_id, username, role)
            VALUES (%s, %s, %s, %s)
        """, (game_id, user_id, username, role))
        conn.commit()
    except Error as e:
        print(f"[DB] add_player: {e}")
    finally:
        close_connection(conn)

def get_alive_players(game_id):
    conn = connect_db()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM werewolf_players WHERE game_id = %s AND alive = TRUE
        """, (game_id,))
        return cursor.fetchall()
    except Error as e:
        print(f"[DB] get_alive_players: {e}")
        return []
    finally:
        close_connection(conn)

def get_players_by_game(game_id):
    conn = connect_db()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id, username, role, alive FROM werewolf_players WHERE game_id = %s", (game_id,))
        return cursor.fetchall()
    except Error as e:
        print(f"[DB] get_players_by_game: {e}")
        return []
    finally:
        close_connection(conn)

def get_player(game_id, user_id):
    players = get_players_by_game(game_id)
    for p in players:
        if int(p['user_id']) == int(user_id):
            return p
    return None

def get_players_by_role(game_id, role):
    conn = connect_db()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM werewolf_players WHERE game_id = %s AND role = %s
        """, (game_id, role))
        return cursor.fetchall()
    except Error as e:
        print(f"[DB] get_players_by_role: {e}")
        return []
    finally:
        close_connection(conn)

def kill_player(game_id, user_id):
    conn = connect_db()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE werewolf_players SET alive = FALSE WHERE game_id = %s AND user_id = %s
        """, (game_id, user_id))
        conn.commit()
    except Error as e:
        print(f"[DB] kill_player: {e}")
    finally:
        close_connection(conn)

def reset_players(game_id):
    conn = connect_db()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM werewolf_players WHERE game_id = %s", (game_id,))
        conn.commit()
    except Error as e:
        print(f"[DB] reset_players: {e}")
    finally:
        close_connection(conn)

# ==================== ROLES CONFIG ====================
def set_roles_config(game_id, roles_dict):
    conn = connect_db()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        for role, count in roles_dict.items():
            cursor.execute("""
                INSERT INTO werewolf_roles_config (game_id, role, count)
                VALUES (%s, %s, %s)
            """, (game_id, role, count))
        conn.commit()
    except Error as e:
        print(f"[DB] set_roles_config: {e}")
    finally:
        close_connection(conn)

# ==================== VOTES ====================
def save_vote(game_id, round_number, voter_id, voted_id, phase):
    conn = connect_db()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO werewolf_votes (game_id, round, voter_id, voted_id, phase)
            VALUES (%s, %s, %s, %s, %s)
        """, (game_id, round_number, voter_id, voted_id, phase))
        conn.commit()
    except Error as e:
        print(f"[DB] save_vote: {e}")
    finally:
        close_connection(conn)

def get_votes_for_round(game_id, round_number, phase):
    conn = connect_db()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM werewolf_votes
            WHERE game_id = %s AND round = %s AND phase = %s
        """, (game_id, round_number, phase))
        return cursor.fetchall()
    except Error as e:
        print(f"[DB] get_votes_for_round: {e}")
        return []
    finally:
        close_connection(conn)

# ==================== LOGS ====================
def log_event(game_id, round_number, event_type, target_id, actor_id=None, message=None):
    conn = connect_db()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO werewolf_logs (game_id, round, event_type, target_id, actor_id, message)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (game_id, round_number, event_type, target_id, actor_id, message))
        conn.commit()
    except Error as e:
        print(f"[DB] log_event: {e}")
    finally:
        close_connection(conn)

def get_game_logs(game_id):
    conn = connect_db()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM werewolf_logs
            WHERE game_id = %s
            ORDER BY round ASC, id ASC
        """, (game_id,))
        return cursor.fetchall()
    except Error as e:
        print(f"[DB] get_game_logs: {e}")
        return []
    finally:
        close_connection(conn)

# ==================== LEADERBOARD ====================
def update_leaderboard(user_id, guild_id, won):
    conn = connect_db()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        if won:
            cursor.execute("""
                INSERT INTO werewolf_leaderboards (user_id, guild_id, win_count, lose_count)
                VALUES (%s, %s, 1, 0)
                ON DUPLICATE KEY UPDATE win_count = win_count + 1, last_played = CURRENT_TIMESTAMP
            """, (user_id, guild_id))
        else:
            cursor.execute("""
                INSERT INTO werewolf_leaderboards (user_id, guild_id, win_count, lose_count)
                VALUES (%s, %s, 0, 1)
                ON DUPLICATE KEY UPDATE lose_count = lose_count + 1, last_played = CURRENT_TIMESTAMP
            """, (user_id, guild_id))
        conn.commit()
    except Error as e:
        print(f"[DB] update_leaderboard: {e}")
    finally:
        close_connection(conn)

def get_leaderboard(guild_id, limit=10):
    conn = connect_db()
    if not conn:
        return []
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM werewolf_leaderboards
            WHERE guild_id = %s
            ORDER BY win_count DESC, last_played DESC
            LIMIT %s
        """, (guild_id, limit))
        return cursor.fetchall()
    except Error as e:
        print(f"[DB] get_leaderboard: {e}")
        return []
    finally:
        close_connection(conn)

def update_last_active(user_id, status):
    conn = connect_db()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_last_active (user_id, last_seen, last_status)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                last_seen = VALUES(last_seen),
                last_status = VALUES(last_status)
        """, (user_id, datetime.utcnow(), str(status)))
        conn.commit()
    except Exception as e:
        print(f"[DB] update_last_active: {e}")
    finally:
        close_connection(conn)

def get_last_active(user_id):
    conn = connect_db()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT last_seen, last_status FROM user_last_active
            WHERE user_id = %s
        """, (user_id,))
        result = cursor.fetchone()
        return result if result else None
    except Exception as e:
        print(f"[DB] get_last_active: {e}")
        return None
    finally:
        close_connection(conn)

def is_tracked(user_id):
    conn = connect_db()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM tracked_users WHERE user_id = %s", (user_id,))
        return cursor.fetchone() is not None
    except Exception as e:
        print(f"[DB] is_tracked: {e}")
        return False
    finally:
        close_connection(conn)

def add_tracked_user(user_id):
    conn = connect_db()
    if not conn:
        return
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT IGNORE INTO tracked_users (user_id) VALUES (%s)
        """, (user_id,))
        conn.commit()
    except Exception as e:
        print(f"[DB] add_tracked_user: {e}")
    finally:
        close_connection(conn)

def get_all_tracked_users():
    conn = connect_db()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM tracked_users")
        return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"[DB] get_all_tracked_users: {e}")
        return []
    finally:
        close_connection(conn)

def log_event(db, guild_id, user_id, event_type, event_data):
    cursor = db.cursor()
    query = """
        INSERT INTO discord_logs (guild_id, user_id, event_type, event_data)
        VALUES (%s, %s, %s, %s)
    """
    cursor.execute(query, (
        guild_id,
        user_id,
        event_type,
        json.dumps(event_data)
    ))
    db.commit()
    cursor.close()

def delete_old_logs(older_than_days=10):
    db = connect_db()
    cursor = db.cursor()
    threshold = datetime.now() - timedelta(days=older_than_days)
    query = "DELETE FROM discord_logs WHERE created_at < %s"
    cursor.execute(query, (threshold,))
    db.commit()
    cursor.close()
    db.close()

def delete_old_voice_logs(older_than_days=1):
    db = connect_db()
    cursor = db.cursor()

    query = """
        DELETE FROM discord_logs
        WHERE event_type = 'voice_update' AND created_at < %s
    """
    from datetime import datetime, timedelta
    threshold = datetime.now() - timedelta(days=older_than_days)
    cursor.execute(query, (threshold,))

    db.commit()
    cursor.close()
    db.close()


def get_logs_by_type(guild_id, event_type, limit=10, offset=0):
    db = connect_db()
    cursor = db.cursor(dictionary=True)
    query = """
        SELECT * FROM discord_logs
        WHERE guild_id = %s AND event_type = %s
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """
    cursor.execute(query, (guild_id, event_type, limit, offset))
    results_raw = cursor.fetchall()
    for row in results_raw:
        row['event_data'] = json.loads(row['event_data'])  # JSON to dict
    cursor.close()
    db.close()
    return results_raw