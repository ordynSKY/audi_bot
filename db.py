import aiosqlite

DB_NAME = "bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            rank TEXT DEFAULT '🚗 A1 Новичок',
            weekly_xp INTEGER DEFAULT 0
        )
        """)
        await db.commit()

async def add_xp(user_id, username, amount):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        INSERT INTO users (user_id, username, xp, weekly_xp)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            xp = xp + ?,
            weekly_xp = weekly_xp + ?
        """, (user_id, username, amount, amount, amount, amount))
        await db.commit()

async def get_user_full(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT xp, level, rank FROM users WHERE user_id = ?",
            (user_id,)
        )
        return await cursor.fetchone()

async def update_level(user_id, level):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET level = ? WHERE user_id = ?",
            (level, user_id)
        )
        await db.commit()

async def update_rank(user_id, rank):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET rank = ? WHERE user_id = ?",
            (rank, user_id)
        )
        await db.commit()

async def get_top():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
        SELECT username, xp, rank FROM users
        ORDER BY xp DESC LIMIT 10
        """)
        return await cursor.fetchall()

async def get_weekly_top():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
        SELECT username, weekly_xp FROM users
        ORDER BY weekly_xp DESC LIMIT 10
        """)
        return await cursor.fetchall()

async def reset_weekly():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET weekly_xp = 0")
        await db.commit()