def migrate(db):

    cursor = db.cursor()

    # Buat tabel user_levels jika belum ada
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_levels (
        user_id BIGINT NOT NULL,
        guild_id BIGINT NOT NULL,
        xp INT NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, guild_id)
    );
    """)

    # Buat tabel level_roles jika belum ada
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS level_roles (
        guild_id BIGINT NOT NULL,
        level INT NOT NULL,
        role_id BIGINT NOT NULL,
        PRIMARY KEY (guild_id, level)
    );
    """)

    # Cek apakah tabel channel_settings ada
    cursor.execute("""
    SELECT COUNT(*)
    FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = 'channel_settings'
    """)
    table_exists = cursor.fetchone()[0] == 1

    if table_exists:
        # Kalau ada, cek kolom setting_type
        cursor.execute("SHOW COLUMNS FROM channel_settings LIKE 'setting_type'")
        column_exists = cursor.fetchone() is not None

        if not column_exists:
            # Rename tabel lama
            cursor.execute("RENAME TABLE channel_settings TO channel_settings_old")

            # Buat tabel baru channel_settings dengan kolom setting_type
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS channel_settings (
                guild_id BIGINT NOT NULL,
                setting_type VARCHAR(50) NOT NULL,
                channel_id BIGINT NOT NULL,
                PRIMARY KEY (guild_id, setting_type)
            );
            """)

            # Migrasi data lama
            cursor.execute("""
            INSERT INTO channel_settings (guild_id, setting_type, channel_id)
            SELECT guild_id, 'music', channel_id FROM channel_settings_old;
            """)

            # Hapus tabel lama
            cursor.execute("DROP TABLE channel_settings_old")
    else:
        # Kalau tabel channel_settings belum ada, buat baru langsung
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS channel_settings (
            guild_id BIGINT NOT NULL,
            setting_type VARCHAR(50) NOT NULL,
            channel_id BIGINT NOT NULL,
            PRIMARY KEY (guild_id, setting_type)
        );
        """)

    # Tabel AFK
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS afk_status (
        user_id BIGINT NOT NULL,
        guild_id BIGINT NOT NULL,
        reason TEXT,
        since TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, guild_id)
    );
    """)

    # # Tabel Statistik Pesan
    # cursor.execute("""
    # CREATE TABLE IF NOT EXISTS user_stats (
    #     user_id BIGINT NOT NULL,
    #     guild_id BIGINT NOT NULL,
    #     message_count INT DEFAULT 0,
    #     last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    #     PRIMARY KEY (user_id, guild_id)
    # );
    # """)

    # Tabel Birthday
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS birthdays (
        user_id BIGINT NOT NULL,
        guild_id BIGINT NOT NULL,
        birthdate DATE NOT NULL,
        display_name VARCHAR(100),
        wish TEXT,
        PRIMARY KEY (user_id, guild_id)
    );
    """)

    # Cek kolom template_url
    cursor.execute("SHOW COLUMNS FROM birthdays LIKE 'template_url';")
    exists = cursor.fetchone()

    if not exists:
        cursor.execute("ALTER TABLE birthdays ADD COLUMN template_url TEXT NULL;")


    cursor.execute("""
    CREATE TABLE IF NOT EXISTS banned_words (
        guild_id BIGINT NOT NULL,
        word VARCHAR(100) NOT NULL,
        response TEXT NOT NULL,
        type ENUM('female', 'partnership', 'pelanggaran') DEFAULT NULL,
        PRIMARY KEY (guild_id, word)
    );
    """)


    cursor.execute("""
    CREATE TABLE IF NOT EXISTS welcome_messages (
        guild_id BIGINT PRIMARY KEY,
        message TEXT NOT NULL
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS timed_words (
        id INT AUTO_INCREMENT PRIMARY KEY,
        guild_id BIGINT NOT NULL,
        title VARCHAR(255) NOT NULL,
        content TEXT NOT NULL,
        interval_minutes INT NOT NULL DEFAULT 30
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS disabled_levels (
    guild_id BIGINT PRIMARY KEY
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS no_xp_roles (
    guild_id BIGINT,
    role_id BIGINT,
    PRIMARY KEY (guild_id, role_id)
    );
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS confessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            confession_id VARCHAR(100) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS werewolf_games (
            id INT AUTO_INCREMENT PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            status ENUM('waiting', 'night', 'day', 'ended') NOT NULL DEFAULT 'waiting',
            current_round INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS werewolf_players (
            id INT AUTO_INCREMENT PRIMARY KEY,
            game_id INT NOT NULL,
            user_id BIGINT NOT NULL,
            username VARCHAR(100) NOT NULL,
            role VARCHAR(50) NOT NULL,
            alive BOOLEAN DEFAULT TRUE,
            revealed BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (game_id) REFERENCES werewolf_games(id) ON DELETE CASCADE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS werewolf_votes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            game_id INT NOT NULL,
            round INT NOT NULL,
            voter_id BIGINT NOT NULL,
            voted_id BIGINT NOT NULL,
            phase ENUM('day', 'night') NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES werewolf_games(id) ON DELETE CASCADE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS werewolf_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            game_id INT NOT NULL,
            round INT NOT NULL,
            event_type VARCHAR(50), -- e.g., 'killed', 'voted', 'revealed'
            target_id BIGINT,
            actor_id BIGINT,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES werewolf_games(id) ON DELETE CASCADE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS werewolf_leaderboards (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            guild_id BIGINT NOT NULL,
            win_count INT DEFAULT 0,
            lose_count INT DEFAULT 0,
            last_played TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, guild_id)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS werewolf_roles_config (
            id INT AUTO_INCREMENT PRIMARY KEY,
            game_id INT NOT NULL,
            role VARCHAR(50) NOT NULL,
            count INT DEFAULT 1,
            FOREIGN KEY (game_id) REFERENCES werewolf_games(id) ON DELETE CASCADE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_last_active (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            last_seen DATETIME NOT NULL,
            last_status VARCHAR(20),
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY unique_user (user_id)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracked_users (
            user_id BIGINT PRIMARY KEY
        );
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS discord_logs (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            event_type VARCHAR(50) NOT NULL,
            event_data JSON NOT NULL,      
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX (event_type),
            INDEX (created_at)
        );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS disabled_commands (
        guild_id BIGINT NOT NULL,
        command_name VARCHAR(100) NOT NULL,
        disabled_by BIGINT,
        disabled_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (guild_id, command_name),
        INDEX (command_name),
        INDEX (disabled_at)
        );
    """)

    try:
        cursor.execute("""
            ALTER TABLE disabled_commands 
            ADD COLUMN feature_type ENUM('command', 'welcome_message', 'reply_words') DEFAULT 'command'
        """)
    except:
        pass  

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feature_status (
            guild_id BIGINT NOT NULL,
            feature_name VARCHAR(100) NOT NULL,
            status BOOLEAN NOT NULL DEFAULT TRUE,
            PRIMARY KEY (guild_id, feature_name),
            INDEX (feature_name)
        );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS feature_status (
        guild_id BIGINT NOT NULL,
        feature_name VARCHAR(100) NOT NULL,
        status BOOLEAN NOT NULL DEFAULT TRUE,
        PRIMARY KEY (guild_id, feature_name),
        INDEX (feature_name)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS streak_pairs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            user1_id BIGINT NOT NULL,
            user2_id BIGINT NOT NULL,
            initiator_id BIGINT NOT NULL,
            status ENUM('PENDING','ACTIVE','DENIED','BROKEN')
                NOT NULL DEFAULT 'PENDING',
            current_streak INT NOT NULL DEFAULT 0,
            max_streak INT NOT NULL DEFAULT 0,
            total_updates INT NOT NULL DEFAULT 0,
            last_update_date DATE NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uniq_pair (guild_id, user1_id, user2_id),
            INDEX idx_guild_status (guild_id, status),
            INDEX idx_user1 (user1_id),
            INDEX idx_user2 (user2_id)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS streak_settings (
            guild_id BIGINT NOT NULL PRIMARY KEY,
            command_channel_id BIGINT DEFAULT NULL,
            log_channel_id BIGINT DEFAULT NULL,
            auto_update BOOLEAN NOT NULL DEFAULT TRUE,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS streak_logs (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            pair_id INT NOT NULL,
            channel_id BIGINT NOT NULL,
            message_id BIGINT NULL,
            author_id BIGINT NOT NULL,
            before_streak INT NOT NULL,
            after_streak INT NOT NULL,
            action_type ENUM('UPDATE','RESTORE') NOT NULL DEFAULT 'UPDATE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_guild_pair (guild_id, pair_id),
            INDEX idx_guild_created (guild_id, created_at)
        );
    """)

    # --- Tambahan kolom restore system ---
    # Kolom: needs_restore
    cursor.execute("""
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='streak_pairs'
          AND COLUMN_NAME='needs_restore';
    """)
    exists = cursor.fetchone()[0] == 1
    if not exists:
        cursor.execute("""
            ALTER TABLE streak_pairs
                ADD COLUMN needs_restore TINYINT(1) NOT NULL DEFAULT 0;
        """)

    # Kolom: restore_deadline
    cursor.execute("""
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='streak_pairs'
          AND COLUMN_NAME='restore_deadline';
    """)
    exists = cursor.fetchone()[0] == 1
    if not exists:
        cursor.execute("""
            ALTER TABLE streak_pairs
                ADD COLUMN restore_deadline DATE NULL;
        """)

    # Kolom: restore_used_this_cycle
    cursor.execute("""
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='streak_pairs'
          AND COLUMN_NAME='restore_used_this_cycle';
    """)
    exists = cursor.fetchone()[0] == 1
    if not exists:
        cursor.execute("""
            ALTER TABLE streak_pairs
                ADD COLUMN restore_used_this_cycle TINYINT(1) NOT NULL DEFAULT 0;
        """)

    # --- Tambahan kolom per-bulan (reset restore tiap bulan) ---
    # Kolom: restore_month
    cursor.execute("""
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='streak_pairs'
          AND COLUMN_NAME='restore_month';
    """)
    exists = cursor.fetchone()[0] == 1
    if not exists:
        cursor.execute("""
            ALTER TABLE streak_pairs
                ADD COLUMN restore_month INT DEFAULT NULL;
        """)

    # Kolom: restore_year
    cursor.execute("""
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='streak_pairs'
          AND COLUMN_NAME='restore_year';
    """)
    exists = cursor.fetchone()[0] == 1
    if not exists:
        cursor.execute("""
            ALTER TABLE streak_pairs
                ADD COLUMN restore_year INT DEFAULT NULL;
        """)




    cursor.execute("""
        CREATE TABLE IF NOT EXISTS streak_emoji_map (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            min_streak INT NOT NULL,
            emoji_id BIGINT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uniq_guild_min (guild_id, min_streak),
            INDEX idx_guild (guild_id)
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS disabled_channels (
            id INT AUTO_INCREMENT PRIMARY KEY,

            guild_id BIGINT UNSIGNED NOT NULL,
            channel_id BIGINT UNSIGNED NOT NULL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE KEY uq_disabled_channel (guild_id, channel_id),
            INDEX idx_guild (guild_id)
        );
    """)

    # ============================================================
    # 1. USER CASH STORAGE
    # ============================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_cash (
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            cash BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );
    """)

    # ============================================================
    # 2. GAMBLE LOGS
    # ============================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gamble_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            guild_id BIGINT,
            user_id BIGINT,
            gamble_type VARCHAR(50),
            amount BIGINT,
            result VARCHAR(10),   -- WIN / LOSE / OTHER
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # ============================================================
    # 3. DAILY CLAIM & STREAK SYSTEM
    # ============================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_daily (
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            last_claim DATE,                -- Tanggal terakhir claim
            streak INT DEFAULT 0,           -- Daily streak
            PRIMARY KEY (guild_id, user_id)
        );
    """)

    # ============================================================
    # 4. ROB VICTIM COOLDOWN (ANTI-SPAM 2 JAM)
    # ============================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_rob_protect (
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            protect_until BIGINT DEFAULT 0,   -- UNIX TIMESTAMP
            PRIMARY KEY (guild_id, user_id)
        );
    """)

    # ============================================================
    # 5. ROB 24-HOUR PROTECTION (BUY FOR 500 CASH)
    # ============================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_protection (
            guild_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            active_until BIGINT DEFAULT 0,     -- UNIX TIMESTAMP
            PRIMARY KEY (guild_id, user_id)
        );
    """)

    # ============================================================
    # 6. DICE DUEL PENDING INVITES
    # ============================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS duel_pending (
            guild_id BIGINT NOT NULL,
            challenger BIGINT NOT NULL,
            target BIGINT NOT NULL,
            bet BIGINT NOT NULL,
            created_at BIGINT NOT NULL,
            PRIMARY KEY (guild_id, challenger)
        );
    """)

    # ============================================================
    # GUILD SETTINGS
    # ============================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gamble_settings (
            guild_id BIGINT NOT NULL,
            setting_key VARCHAR(50) NOT NULL,
            setting_value VARCHAR(255),
            PRIMARY KEY (guild_id, setting_key)
        );
    """)

   # Helper
    def safe_drop_primary(cursor, table_name):
        cursor.execute(f"""
            SELECT COUNT(*)
            FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = '{table_name}'
            AND CONSTRAINT_NAME = 'PRIMARY';
        """)
        has_pk = cursor.fetchone()[0]
        if has_pk:
            cursor.execute(f"ALTER TABLE {table_name} DROP PRIMARY KEY")


    def drop_column_if_exists(cursor, table, column):
        cursor.execute(f"""
            SELECT COUNT(*)
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = '{table}'
            AND COLUMN_NAME = '{column}';
        """)
        exists = cursor.fetchone()[0]
        if exists:
            cursor.execute(f"ALTER TABLE {table} DROP COLUMN {column}")


    # ============================================================
    # user_cash GLOBAL
    # ============================================================
    safe_drop_primary(cursor, "user_cash")
    drop_column_if_exists(cursor, "user_cash", "guild_id")
    cursor.execute("ALTER TABLE user_cash ADD PRIMARY KEY (user_id)")


    # ============================================================
    # user_daily GLOBAL
    # ============================================================
    safe_drop_primary(cursor, "user_daily")
    drop_column_if_exists(cursor, "user_daily", "guild_id")
    cursor.execute("ALTER TABLE user_daily ADD PRIMARY KEY (user_id)")


    # ============================================================
    # user_rob_protect GLOBAL
    # ============================================================
    safe_drop_primary(cursor, "user_rob_protect")
    drop_column_if_exists(cursor, "user_rob_protect", "guild_id")
    cursor.execute("ALTER TABLE user_rob_protect ADD PRIMARY KEY (user_id)")


    # ============================================================
    # user_protection GLOBAL
    # ============================================================
    safe_drop_primary(cursor, "user_protection")
    drop_column_if_exists(cursor, "user_protection", "guild_id")
    cursor.execute("ALTER TABLE user_protection ADD PRIMARY KEY (user_id)")

    # cursor.execute("""
    #     CREATE TABLE IF NOT EXISTS guild_settings (
    #         guild_id BIGINT NOT NULL,
    #         setting_key VARCHAR(50) NOT NULL,
    #         setting_value VARCHAR(255),
    #         PRIMARY KEY (guild_id, setting_key)
    #     );
    # """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rob_stats (
            user_id BIGINT PRIMARY KEY,
            success INT DEFAULT 0,
            fail INT DEFAULT 0
        );
    """)

    # cursor.execute("""
    #     CREATE TABLE IF NOT EXISTS disabled_channels (
    #         id INT AUTO_INCREMENT PRIMARY KEY,
    #         guild_id BIGINT NOT NULL,
    #         channel_id BIGINT NOT NULL
    #     )
    # """)

    db.commit()
    cursor.close()
    
