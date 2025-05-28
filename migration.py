def migrate(db):
    cursor = db.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_levels (
        user_id BIGINT NOT NULL,
        guild_id BIGINT NOT NULL,
        xp INT NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, guild_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS level_roles (
        guild_id BIGINT NOT NULL,
        level INT NOT NULL,
        role_id BIGINT NOT NULL,
        PRIMARY KEY (guild_id, level)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS channel_settings (
        guild_id BIGINT NOT NULL,
        channel_id BIGINT NOT NULL,
        PRIMARY KEY (guild_id, channel_id)
    );
    """)

    db.commit()
    cursor.close()
