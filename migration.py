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

        # Tabel untuk menyimpan karakter pemain
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_characters (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            character_name VARCHAR(100) NOT NULL UNIQUE,
            level INT DEFAULT 1,
            exp INT DEFAULT 0,
            exp_to_next INT DEFAULT 100,
            base_hp INT DEFAULT 100,
            base_atk INT DEFAULT 20,
            base_def INT DEFAULT 10,
            base_spd INT DEFAULT 10,
            win_streak INT DEFAULT 0,
            train_level INT DEFAULT 1,
            last_checkpoint INT DEFAULT 1,
            skill_point INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)


    # Tabel untuk musuh-musuh preset di arena training
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS enemy_pool (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            base_hp INT NOT NULL,
            base_atk INT NOT NULL,
            base_def INT NOT NULL,
            base_spd INT NOT NULL,
            ai_type VARCHAR(50) DEFAULT 'random',
            skill_json TEXT,
            reward_json TEXT,
            min_level INT DEFAULT 1,
            max_level INT DEFAULT 100
        );
    """)

    # Tabel log pertarungan latihan
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS train_battle_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            character_id INT NOT NULL,
            enemy_id INT NOT NULL,
            result ENUM('win', 'lose') NOT NULL,
            exp_gain INT DEFAULT 0,
            coin_gain INT DEFAULT 0,
            skill_point_gain INT DEFAULT 0,
            turn_log_json LONGTEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES user_characters(id) ON DELETE CASCADE,
            FOREIGN KEY (enemy_id) REFERENCES enemy_pool(id) ON DELETE SET NULL
        );
    """)

        # Tabel skill global
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            type ENUM('active', 'passive') DEFAULT 'active',
            unlock_level INT DEFAULT 1,
            mana_cost INT DEFAULT 0,
            cooldown INT DEFAULT 0,
            effect_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Tabel relasi karakter dan skill
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS character_skills (
            id INT AUTO_INCREMENT PRIMARY KEY,
            character_id INT NOT NULL,
            skill_id INT NOT NULL,
            is_equipped BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES user_characters(id) ON DELETE CASCADE,
            FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
        );
    """)

    # Tabel item global
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            type ENUM('stat_boost', 'special_effect') DEFAULT 'stat_boost', -- 👈 Tambahkan ini
            description TEXT,
            slot ENUM('weapon', 'armor', 'accessory') NOT NULL,
            stat_bonus_json TEXT,
            rarity ENUM('common', 'uncommon', 'rare', 'epic', 'legendary') DEFAULT 'common',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Tabel relasi karakter dan item
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS character_items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            character_id INT NOT NULL,
            item_id INT NOT NULL,
            is_equipped BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES user_characters(id) ON DELETE CASCADE,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
        );
    """)

    # Tabel log tambahan
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            character_id INT NOT NULL,
            log_type ENUM('level_up', 'skill_unlock', 'item_drop') NOT NULL,
            description TEXT,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (character_id) REFERENCES user_characters(id) ON DELETE CASCADE
        );
    """)

    db.commit()
    cursor.close()
    
