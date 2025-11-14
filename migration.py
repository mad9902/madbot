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
            current_streak INT NOT NULL DEFAULT 0,   -- streak hari ini (dipakai untuk warna api)
            max_streak INT NOT NULL DEFAULT 0,       -- rekor tertinggi (opsional buat display ☁️)
            total_updates INT NOT NULL DEFAULT 0,    -- total kali nyala (opsional statistik)
            last_update_date DATE NULL,              -- kapan terakhir nyala
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
            command_channel_id BIGINT DEFAULT NULL,  -- #・🔥・streak
            log_channel_id BIGINT DEFAULT NULL,      -- #・🔥・streaks
            auto_update BOOLEAN NOT NULL DEFAULT TRUE,  -- true = cukup reply/mention partner
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

    db.commit()
    cursor.close()
    
