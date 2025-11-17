import mysql.connector
from mysql.connector import Error
import os
import time
from datetime import datetime, timedelta, date
import json
from dotenv import load_dotenv
import logging

# Configure logging
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



def retry_database(retries=5, delay=3):
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except Error as e:
                    last_exception = e
                    logger.warning(f"[Attempt {attempt}] Database error: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
            logger.error(f"Failed after {retries} attempts")
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
        logger.error(f"Failed to create database: {e}")
        raise

@retry_database(retries=3, delay=3)
def connect_db():
    """Create and return a new database connection"""
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASS") or None,
        database=os.getenv("MYSQL_DB")
    )

class ChannelBlockManager:
    def __init__(self, db):
        self.db = db
        self.cache = {}  # {guild_id: set(channel_ids)}

    def load_all_guilds(self, guilds):
        cursor = self.db.cursor()
        for guild in guilds:
            gid = guild.id
            cursor.execute("SELECT channel_id FROM disabled_channels WHERE guild_id=%s", (gid,))
            rows = cursor.fetchall()
            self.cache[gid] = {row[0] for row in rows}

    def is_channel_disabled(self, guild_id, channel_id):
        return guild_id in self.cache and channel_id in self.cache[guild_id]

    def disable_channel(self, guild_id, channel_id):
        cursor = self.db.cursor()
        cursor.execute("""
            INSERT INTO disabled_channels (guild_id, channel_id)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE channel_id = channel_id;
        """, (guild_id, channel_id))
        self.db.commit()

        self.cache.setdefault(guild_id, set()).add(channel_id)

    def enable_channel(self, guild_id, channel_id):
        cursor = self.db.cursor()
        cursor.execute("""
            DELETE FROM disabled_channels
            WHERE guild_id = %s AND channel_id = %s
        """, (guild_id, channel_id))
        self.db.commit()

        if guild_id in self.cache:
            self.cache[guild_id].discard(channel_id)

    def get_disabled_channels(self, guild_id):
        return self.cache.get(guild_id, set())


class CommandManager:
    """Handles command disabling/enabling functionality"""
    
    @retry_database()
    def disable_command(self, guild_id: int, command_name: str, disabled_by: int = None) -> bool:
        """Disable a command for a specific guild"""
        try:
            conn = connect_db()
            cursor = conn.cursor()
            
            query = """
            INSERT INTO disabled_commands (guild_id, command_name, disabled_by)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE disabled_by = VALUES(disabled_by), disabled_at = CURRENT_TIMESTAMP
            """
            cursor.execute(query, (guild_id, command_name, disabled_by))
            conn.commit()
            return True
        except Error as e:
            logger.error(f"Failed to disable command '{command_name}' for guild {guild_id}: {e}")
            return False
        finally:
            close_connection(conn)

    @retry_database()
    def enable_command(self, guild_id: int, command_name: str) -> bool:
        """Enable a previously disabled command"""
        try:
            conn = connect_db()
            cursor = conn.cursor()
            
            cursor.execute(
                "DELETE FROM disabled_commands WHERE guild_id = %s AND command_name = %s",
                (guild_id, command_name)
            )
            conn.commit()
            return cursor.rowcount > 0
        except Error as e:
            logger.error(f"Failed to enable command '{command_name}' for guild {guild_id}: {e}")
            return False
        finally:
            close_connection(conn)

    @retry_database()
    def is_command_disabled(self, guild_id: int, command_name: str) -> bool:
        """Check if a command is disabled for a guild"""
        try:
            conn = connect_db()
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT 1 FROM disabled_commands WHERE guild_id = %s AND command_name = %s",
                (guild_id, command_name)
            )
            return cursor.fetchone() is not None
        except Error as e:
            logger.error(f"Failed to check if command '{command_name}' is disabled for guild {guild_id}: {e}")
            return False
        finally:
            close_connection(conn)

    @retry_database()
    def get_disabled_commands(self, guild_id: int) -> list:
        """Get all disabled commands for a guild"""
        try:
            conn = connect_db()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute(
                "SELECT command_name, disabled_by, disabled_at FROM disabled_commands WHERE guild_id = %s",
                (guild_id,)
            )
            return cursor.fetchall()
        except Error as e:
            logger.error(f"Failed to get disabled commands for guild {guild_id}: {e}")
            return []
        finally:
            close_connection(conn)
def set_feature_status(db, guild_id, feature_name, status):
    """Set status fitur untuk guild tertentu."""
    cursor = db.cursor()
    cursor.execute("INSERT INTO feature_status (guild_id, feature_name, status) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE status = %s", (guild_id, feature_name, status, status))
    db.commit()

def get_feature_status(db, guild_id, feature_name):
    """Get status fitur untuk guild tertentu."""
    cursor = db.cursor()
    cursor.execute("SELECT status FROM feature_status WHERE guild_id = %s AND feature_name = %s", (guild_id, feature_name))
    result = cursor.fetchone()
    return result[0] if result else True  # Default ke True jika tidak ada entri

def close_connection(conn):
    """Properly close database connection"""
    if conn and conn.is_connected():
        conn.close()
# Initialize database when module loads
ensure_database_exists()


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

def log_event_discord(db, guild_id, user_id, event_type, event_data):
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

def delete_old_logs(older_than_days=5):
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

def _normalize_pair_users(user1_id, user2_id):
    """
    Biar pasangan streak unik & konsisten:
    selalu simpan user1_id < user2_id.
    """
    return (user1_id, user2_id) if user1_id <= user2_id else (user2_id, user1_id)

def get_streak_pair(guild_id, user1_id, user2_id):
    """
    Ambil data pasangan streak (kalau ada).
    """
    db = connect_db()
    cursor = db.cursor(dictionary=True)

    u1, u2 = _normalize_pair_users(user1_id, user2_id)
    cursor.execute("""
        SELECT *
        FROM streak_pairs
        WHERE guild_id = %s AND user1_id = %s AND user2_id = %s
    """, (guild_id, u1, u2))

    row = cursor.fetchone()
    cursor.close()
    db.close()
    return row

def create_streak_pair(guild_id, user1_id, user2_id, initiator_id):
    """
    Buat pasangan streak baru.
    - Jika belum ada → buat baru (status PENDING)
    - Jika sudah ada & status BROKEN → reset dan set ke PENDING
    - Jika sudah ada dengan status lain → balikin existing row
    """
    existing = get_streak_pair(guild_id, user1_id, user2_id)

    if existing:
        # 🔥 Jika sudah BROKEN → reset total dan jadikan PENDING ulang
        if existing["status"] == "BROKEN":
            db = connect_db()
            cursor = db.cursor(dictionary=True)

            cursor.execute("""
                UPDATE streak_pairs
                SET 
                    status = 'PENDING',
                    initiator_id = %s,
                    current_streak = 0,
                    max_streak = 0,
                    needs_restore = 0,
                    restore_deadline = NULL,
                    restore_used_this_cycle = 0,
                    restore_month = NULL,
                    restore_year = NULL,
                    last_update_date = NULL
                WHERE id = %s
            """, (initiator_id, existing["id"]))

            db.commit()

            cursor.execute("SELECT * FROM streak_pairs WHERE id = %s", (existing["id"],))
            row = cursor.fetchone()

            cursor.close()
            db.close()
            return row

        # Kalau bukan BROKEN, cukup return existing
        return existing

    # 🔥 Kalau belum ada → buat baru
    db = connect_db()
    cursor = db.cursor(dictionary=True)

    u1, u2 = _normalize_pair_users(user1_id, user2_id)
    cursor.execute("""
        INSERT INTO streak_pairs (guild_id, user1_id, user2_id, initiator_id, status)
        VALUES (%s, %s, %s, %s, 'PENDING')
    """, (guild_id, u1, u2, initiator_id))
    db.commit()

    pair_id = cursor.lastrowid
    cursor.execute("SELECT * FROM streak_pairs WHERE id = %s", (pair_id,))
    row = cursor.fetchone()

    cursor.close()
    db.close()
    return row

def set_streak_status(pair_id, status):
    """
    Ubah status streak_pairs: PENDING / ACTIVE / DENIED / BROKEN.
    """
    db = connect_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE streak_pairs
        SET status = %s
        WHERE id = %s
    """, (status, pair_id))
    db.commit()
    cursor.close()
    db.close()

def get_pending_streak_requests(guild_id, target_user_id=None, limit=20, offset=0):
    """
    Ambil daftar request PENDING di satu guild.
    - Kalau target_user_id = None -> semua pending di guild.
    - Kalau target_user_id diisi -> hanya yang melibatkan user tsb.
    """
    db = connect_db()
    cursor = db.cursor(dictionary=True)

    if target_user_id is None:
        cursor.execute("""
            SELECT *
            FROM streak_pairs
            WHERE guild_id = %s
              AND status = 'PENDING'
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (guild_id, limit, offset))
    else:
        cursor.execute("""
            SELECT *
            FROM streak_pairs
            WHERE guild_id = %s
              AND status = 'PENDING'
              AND (user1_id = %s OR user2_id = %s)
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (guild_id, target_user_id, target_user_id, limit, offset))

    rows = cursor.fetchall()
    cursor.close()
    db.close()
    return rows

def get_active_streaks(guild_id, limit=20, offset=0, order_by="current"):
    """
    Ambil list pasangan streak aktif untuk command /topstreak.
    order_by: 'current' atau 'max'
    """
    db = connect_db()
    cursor = db.cursor(dictionary=True)

    if order_by == "max":
        order_sql = "max_streak DESC"
    else:
        order_sql = "current_streak DESC"

    query = f"""
        SELECT *
        FROM streak_pairs
        WHERE guild_id = %s AND status = 'ACTIVE'
        ORDER BY {order_sql}, updated_at DESC
        LIMIT %s OFFSET %s
    """
    cursor.execute(query, (guild_id, limit, offset))
    rows = cursor.fetchall()

    cursor.close()
    db.close()
    return rows

def get_streak_settings(guild_id):
    """
    Ambil pengaturan streak per guild.
    """
    db = connect_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM streak_settings
        WHERE guild_id = %s
    """, (guild_id,))
    row = cursor.fetchone()

    cursor.close()
    db.close()
    return row

def upsert_streak_settings(guild_id, command_channel_id=None, log_channel_id=None, auto_update=True):
    """
    Simpan / update pengaturan streak.
    """
    db = connect_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO streak_settings (guild_id, command_channel_id, log_channel_id, auto_update)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            command_channel_id = VALUES(command_channel_id),
            log_channel_id = VALUES(log_channel_id),
            auto_update = VALUES(auto_update),
            updated_at = CURRENT_TIMESTAMP
    """, (guild_id, command_channel_id, log_channel_id, auto_update))

    db.commit()
    cursor.close()
    db.close()

def apply_streak_update(guild_id, user1_id, user2_id, channel_id, message_id, author_id,
                        is_restore=False, today=None):
    """
    Core logic update streak (+ restore):

    - Kalau belum pernah nyala -> current_streak = 1
    - Kalau beda 1 hari  (delta=1) -> current_streak + 1
    - Kalau beda 2 hari  (delta=2):
        - kalau is_restore=True dan kuota bulan ini < 5 -> current_streak + 1 (RESTORE)
        - kalau is_restore=False atau kuota habis -> reset ke 1 (PUTUS)
    - Kalau beda >=3 hari -> reset ke 1 (PUTUS)
    - Kalau delta <= 0 (hari sama/ mundur) -> tidak ubah streak

    Return dict:
    {
      "ok": bool,
      "reason": str | None,
      "pair": row_pair (dict) setelah update,
      "before": int,
      "after": int,
      "action_type": "UPDATE"|"RESTORE"|None,
      "broken": bool,
      "delta_days": int|None
    }
    """
    if today is None:
        today = date.today()

    db = connect_db()
    cursor = db.cursor(dictionary=True)

    u1, u2 = _normalize_pair_users(user1_id, user2_id)
    # Lock baris ini secara halus (MySQL default nggak terlalu strict,
    # tapi at least kita ambil data paling baru)
    cursor.execute("""
        SELECT *
        FROM streak_pairs
        WHERE guild_id = %s AND user1_id = %s AND user2_id = %s
        LIMIT 1
    """, (guild_id, u1, u2))

    pair = cursor.fetchone()
    if not pair:
        cursor.close()
        db.close()
        return {
            "ok": False,
            "reason": "pair_not_found",
            "pair": None,
            "before": 0,
            "after": 0,
            "action_type": None,
            "broken": False,
            "delta_days": None,
        }

    if pair["status"] != "ACTIVE":
        cursor.close()
        db.close()
        return {
            "ok": False,
            "reason": "pair_not_active",
            "pair": pair,
            "before": pair.get("current_streak", 0),
            "after": pair.get("current_streak", 0),
            "action_type": None,
            "broken": False,
            "delta_days": None,
        }

    last_date = pair["last_update_date"]
    current = pair["current_streak"] or 0
    before = current
    broken = False
    action_type = "UPDATE"
    delta_days = None

    if last_date is None:
        # pertama kali nyala
        current = 1
    else:
        if isinstance(last_date, datetime):
            last_date = last_date.date()

        delta_days = (today - last_date).days

        if delta_days <= 0:
            # hari ini sudah pernah dihitung atau waktu mundur → abaikan
            cursor.close()
            db.close()
            return {
                "ok": False,
                "reason": "already_updated_today",
                "pair": pair,
                "before": before,
                "after": before,
                "action_type": None,
                "broken": False,
                "delta_days": delta_days,
            }

        elif delta_days == 1:
            # normal naik
            current = before + 1

            cursor.execute("""
                UPDATE streak_pairs
                SET needs_restore = 0,
                    restore_deadline = NULL
                WHERE id = %s
            """, (pair["id"],))

        elif delta_days == 2:
            if is_restore:
                cursor2 = db.cursor()
                cursor2.execute("""
                    UPDATE streak_pairs
                    SET needs_restore = 0,
                        restore_deadline = NULL
                    WHERE id = %s
                """, (pair["id"],))
                db.commit()

                # --- Reset restore cycle jika perlu ---
                pair = ensure_restore_cycle(pair)

                # batas restore 5x / bulan
                if pair["restore_used_this_cycle"] >= 5:
                    cursor.close()
                    db.close()
                    return {
                        "ok": False,
                        "reason": "restore_quota_reached",
                        "pair": pair,
                        "before": before,
                        "after": before,
                        "action_type": None,
                        "broken": True,
                        "delta_days": delta_days,
                    }

                current = before + 1
                action_type = "RESTORE"

                # increment restore count
                cursor2 = db.cursor()
                cursor2.execute("""
                    UPDATE streak_pairs
                    SET restore_used_this_cycle = restore_used_this_cycle + 1
                    WHERE id = %s
                """, (pair["id"],))
                db.commit()
                cursor2.close()

            else:
                current = 1
                broken = True

        else:  # delta_days >= 3
            # sudah lewat 2 hari → tidak bisa restore, mulai dari 1 lagi
            current = 1
            broken = True

    # update streak_pairs
    new_max = max(pair.get("max_streak", 0) or 0, current)

    cursor.execute("""
        UPDATE streak_pairs
        SET current_streak = %s,
            max_streak = %s,
            last_update_date = %s
        WHERE id = %s
    """, (current, new_max, today, pair["id"]))

    # insert log
    cursor.execute("""
        INSERT INTO streak_logs (
            guild_id, pair_id, channel_id, message_id,
            author_id, before_streak, after_streak, action_type
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        guild_id,
        pair["id"],
        channel_id,
        message_id,
        author_id,
        before,
        current,
        action_type,
    ))

    db.commit()

    # ambil pair terbaru
    cursor.execute("SELECT * FROM streak_pairs WHERE id = %s", (pair["id"],))
    updated_pair = cursor.fetchone()

    cursor.close()
    db.close()

    return {
        "ok": True,
        "reason": None,
        "pair": updated_pair,
        "before": before,
        "after": current,
        "action_type": action_type,
        "broken": broken,
        "delta_days": delta_days,
    }

def mark_needs_restore(pair_id, deadline_date):
    """
    Tandai bahwa pair ini butuh restore (hari kedua tidak api).
    """
    db = connect_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE streak_pairs
        SET needs_restore = 1,
            restore_deadline = %s
        WHERE id = %s
    """, (deadline_date, pair_id))
    db.commit()
    cursor.close()
    db.close()

def clear_restore_flags(pair_id):
    """
    Hanya reset flag restore, JANGAN reset kuota.
    """
    db = connect_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE streak_pairs
        SET needs_restore = 0,
            restore_deadline = NULL
        WHERE id = %s
    """, (pair_id,))
    db.commit()
    cursor.close()
    db.close()

def kill_streak_due_to_deadline(pair_id):
    db = connect_db()
    cursor = db.cursor()
    cursor.execute("""
        UPDATE streak_pairs
        SET current_streak = 0,
            needs_restore = 0,
            restore_deadline = NULL,
            restore_used_this_cycle = 0,
            restore_month = NULL,
            restore_year = NULL,
            status = 'BROKEN'
        WHERE id = %s
    """, (pair_id,))
    db.commit()
    cursor.close()
    db.close()

def auto_process_gap(pair):
    """
    Evaluasi gap hari dan tentukan apakah perlu restore,
    keluar dari restore mode, atau langsung BROKEN.

    LOGIC:
    - delta 0  → aman
    - delta 1  → aman (belum bolong)
    - delta 2  → bolong 1 hari → NEED RESTORE
    - delta >=3:
        - kalau sudah lewat deadline → BROKEN
        - kalau belum restore → langsung BROKEN
    """

    if not pair:
        return pair

    pair = ensure_restore_cycle(pair)

    last = pair["last_update_date"]
    needs_restore = pair.get("needs_restore", 0)
    deadline = pair.get("restore_deadline")
    today = date.today()

    if last is None:
        return pair

    # Convert last date
    if isinstance(last, str):
        try:
            last = datetime.strptime(last, "%Y-%m-%d").date()
        except:
            last = today

    # Convert deadline
    if isinstance(deadline, str):
        try:
            deadline = datetime.strptime(deadline, "%Y-%m-%d").date()
        except:
            deadline = None

    delta = (today - last).days

    # CASE A — sama / mundur
    if delta <= 0:
        return pair

    # =====================================================
    # CASE B — SUDAH MODE RESTORE
    # =====================================================
    if needs_restore == 1:

        # 1️⃣ Kalau sudah LEWAT DEADLINE → auto BROKEN
        if deadline and today > deadline:
            kill_streak_due_to_deadline(pair["id"])
            return get_streak_pair(pair["guild_id"], pair["user1_id"], pair["user2_id"])

        # 2️⃣ Kalau ternyata last update sudah kembali normal
        # (hari ini ATAU kemarin), artinya streak sudah "on track" lagi → keluar restore mode
        if last == today or last == (today - timedelta(days=1)):
            clear_restore_flags(pair["id"])
            pair["needs_restore"] = 0
            pair["restore_deadline"] = None
            return pair

        # 3️⃣ Belum restore, belum lewat deadline → tetap butuh restore
        return pair

    # =====================================================
    # CASE C — DELTA 1 → NORMAL
    # =====================================================
    if delta == 1:
        return pair

    # =====================================================
    # CASE D — DELTA 2 → BUTUH RESTORE
    # =====================================================
    if delta == 2:
        deadline = today  # HARUS restore hari ini

        mark_needs_restore(pair["id"], deadline.strftime("%Y-%m-%d"))

        pair["needs_restore"] = 1
        pair["restore_deadline"] = deadline.strftime("%Y-%m-%d")

        return pair

    # =====================================================
    # CASE E — DELTA >= 3 → AUTO BROKEN
    # =====================================================
    if delta >= 3:
        kill_streak_due_to_deadline(pair["id"])
        return get_streak_pair(pair["guild_id"], pair["user1_id"], pair["user2_id"])

    return pair

def force_new_day(pair_id):
    """
    Jangan pernah mengubah last_update_date.
    Fungsi ini hanya membersihkan restore flags
    agar perhitungan gap berjalan normal.
    """
    db = connect_db()
    cursor = db.cursor()

    cursor.execute("""
        UPDATE streak_pairs
        SET 
            needs_restore = 0,
            restore_deadline = NULL
        WHERE id = %s
    """, (pair_id,))

    db.commit()
    cursor.close()
    db.close()

def ensure_restore_cycle(pair):
    """
    Pastikan bahwa restore_used_this_cycle selaras dengan bulan & tahun saat ini.
    Jika bulan atau tahun sudah berubah → reset counter ke 0.
    """
    if not pair:
        return pair

    today = date.today()
    cur_month = today.month
    cur_year = today.year

    stored_month = pair.get("restore_month")
    stored_year = pair.get("restore_year")

    # Jika belum pernah diset → set sekarang
    if stored_month is None or stored_year is None:
        db = connect_db()
        cursor = db.cursor()
        cursor.execute("""
            UPDATE streak_pairs
            SET restore_month = %s,
                restore_year = %s,
                restore_used_this_cycle = 0
            WHERE id = %s
        """, (cur_month, cur_year, pair["id"]))
        db.commit()
        cursor.close()
        db.close()

        pair["restore_month"] = cur_month
        pair["restore_year"] = cur_year
        pair["restore_used_this_cycle"] = 0
        return pair

    # Jika bulan berbeda → reset counter
    if stored_month != cur_month or stored_year != cur_year:
        db = connect_db()
        cursor = db.cursor()
        cursor.execute("""
            UPDATE streak_pairs
            SET restore_month = %s,
                restore_year = %s,
                restore_used_this_cycle = 0
            WHERE id = %s
        """, (cur_month, cur_year, pair["id"]))
        db.commit()
        cursor.close()
        db.close()

        pair["restore_month"] = cur_month
        pair["restore_year"] = cur_year
        pair["restore_used_this_cycle"] = 0

    return pair

def set_tier_emoji(guild_id, min_streak, emoji_id):
    """
    Simpan atau update emoji untuk tier tertentu.
    UNIQUE per (guild_id, min_streak).
    """
    db = connect_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO streak_emoji_map (guild_id, min_streak, emoji_id)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            emoji_id = VALUES(emoji_id),
            created_at = CURRENT_TIMESTAMP
    """, (guild_id, min_streak, emoji_id))

    db.commit()
    cursor.close()
    db.close()

def get_tier_emojis(guild_id):
    """
    Ambil semua tier emoji untuk guild,
    diurutkan dari min_streak kecil ke besar.
    """
    db = connect_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM streak_emoji_map
        WHERE guild_id = %s
        ORDER BY min_streak ASC
    """, (guild_id,))

    rows = cursor.fetchall()
    cursor.close()
    db.close()
    return rows

def delete_tier_emoji(guild_id, min_streak):
    """
    Hapus emoji tier tertentu.
    """
    db = connect_db()
    cursor = db.cursor()

    cursor.execute("""
        DELETE FROM streak_emoji_map
        WHERE guild_id = %s AND min_streak = %s
    """, (guild_id, min_streak))

    db.commit()
    cursor.close()
    db.close()

def get_emoji_for_streak(guild_id, streak):
    """
    Ambil emoji ID yang cocok untuk streak tertentu.
    Pilih min_streak terbesar yang <= streak.

    Return:
        emoji_id atau None
    """
    db = connect_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT emoji_id
        FROM streak_emoji_map
        WHERE guild_id = %s AND min_streak <= %s
        ORDER BY min_streak DESC
        LIMIT 1
    """, (guild_id, streak))

    row = cursor.fetchone()
    cursor.close()
    db.close()

    if row:
        return row["emoji_id"]

    return None
