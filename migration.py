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

    db.commit()
    cursor.close()
