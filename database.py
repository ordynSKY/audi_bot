import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "audi_bot.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Инициализация базы данных"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            chat_id     INTEGER NOT NULL,
            username    TEXT,
            full_name   TEXT,
            xp          INTEGER DEFAULT 0,
            level       INTEGER DEFAULT 1,
            rank_title  TEXT DEFAULT 'Новичок',
            messages    INTEGER DEFAULT 0,
            last_xp_at  REAL DEFAULT 0,
            joined_at   TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS weekly_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            chat_id     INTEGER,
            username    TEXT,
            full_name   TEXT,
            xp_week     INTEGER DEFAULT 0,
            week_start  TEXT,
            week_end    TEXT,
            position    INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS xp_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            chat_id     INTEGER,
            xp_gained   INTEGER,
            reason      TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def get_or_create_user(user_id: int, chat_id: int, username: str, full_name: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id)
    )
    user = cursor.fetchone()

    if not user:
        cursor.execute("""
            INSERT INTO users (user_id, chat_id, username, full_name)
            VALUES (?, ?, ?, ?)
        """, (user_id, chat_id, username, full_name))
        conn.commit()
        cursor.execute(
            "SELECT * FROM users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        user = cursor.fetchone()
    else:
        # Обновим имя если изменилось
        cursor.execute("""
            UPDATE users SET username = ?, full_name = ?
            WHERE user_id = ? AND chat_id = ?
        """, (username, full_name, user_id, chat_id))
        conn.commit()

    conn.close()
    return dict(user)


def add_xp(user_id: int, chat_id: int, xp: int, reason: str = "message"):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE users
        SET xp = xp + ?, messages = messages + 1
        WHERE user_id = ? AND chat_id = ?
    """, (xp, user_id, chat_id))

    cursor.execute("""
        INSERT INTO xp_log (user_id, chat_id, xp_gained, reason)
        VALUES (?, ?, ?, ?)
    """, (user_id, chat_id, xp, reason))

    conn.commit()
    conn.close()


def update_user_level_rank(user_id: int, chat_id: int, level: int, rank_title: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET level = ?, rank_title = ?
        WHERE user_id = ? AND chat_id = ?
    """, (level, rank_title, user_id, chat_id))
    conn.commit()
    conn.close()


def update_last_xp_time(user_id: int, chat_id: int, timestamp: float):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET last_xp_at = ?
        WHERE user_id = ? AND chat_id = ?
    """, (timestamp, user_id, chat_id))
    conn.commit()
    conn.close()


def get_user(user_id: int, chat_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM users WHERE user_id = ? AND chat_id = ?",
        (user_id, chat_id)
    )
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None


def get_top_users(chat_id: int, limit: int = 10):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM users
        WHERE chat_id = ?
        ORDER BY xp DESC
        LIMIT ?
    """, (chat_id, limit))
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users


def get_weekly_xp(chat_id: int, week_start: str):
    """Получить XP набранный за неделю"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, chat_id, SUM(xp_gained) as week_xp
        FROM xp_log
        WHERE chat_id = ? AND created_at >= ?
        GROUP BY user_id
        ORDER BY week_xp DESC
        LIMIT 10
    """, (chat_id, week_start))
    result = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return result


def get_all_chat_ids():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT chat_id FROM users")
    chats = [row["chat_id"] for row in cursor.fetchall()]
    conn.close()
    return chats


def save_weekly_snapshot(entries: list):
    conn = get_connection()
    cursor = conn.cursor()
    for entry in entries:
        cursor.execute("""
            INSERT INTO weekly_snapshots
            (user_id, chat_id, username, full_name, xp_week, week_start, week_end, position)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry["user_id"], entry["chat_id"], entry["username"],
            entry["full_name"], entry["xp_week"],
            entry["week_start"], entry["week_end"], entry["position"]
        ))
    conn.commit()
    conn.close()
