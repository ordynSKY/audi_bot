import sqlite3
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "audi_bot.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # ── Миграция: проверяем PK таблицы users ──
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
    row = cursor.fetchone()

    if row:
        create_sql = row["sql"]
        needs_migration = "PRIMARY KEY (user_id, chat_id)" not in create_sql

        # Проверяем наличие новых колонок
        cursor.execute("PRAGMA table_info(users)")
        existing_cols = {r["name"] for r in cursor.fetchall()}
        needs_new_cols = "streak_days" not in existing_cols

        if needs_migration:
            logger.warning("⚠️ Миграция: пересоздаём таблицу users с новой схемой")
            cursor.execute("ALTER TABLE users RENAME TO users_old")
            _create_users_table(cursor)
            # Переносим данные — новые колонки получат дефолты
            cursor.execute("""
                INSERT OR IGNORE INTO users
                    (user_id, chat_id, username, full_name, xp, level,
                     rank_title, messages, last_xp_at, joined_at)
                SELECT user_id, chat_id, username, full_name, xp, level,
                       rank_title, messages, last_xp_at, joined_at
                FROM users_old
            """)
            cursor.execute("DROP TABLE users_old")
            logger.info("✅ Миграция завершена")
        elif needs_new_cols:
            logger.warning("⚠️ Миграция: добавляем новые колонки в users")
            for col, default in [
                ("streak_days", "0"),
                ("last_active_date", "''"),
            ]:
                if col not in existing_cols:
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {col} DEFAULT {default}")
            logger.info("✅ Колонки добавлены")
    else:
        _create_users_table(cursor)

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

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_chat_xp ON users(chat_id, xp DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_xp_log_chat_date ON xp_log(chat_id, created_at)")

    cursor.execute(
        "UPDATE users SET rank_title = '🔩 Новачок' WHERE rank_title = '🔩 Новичок'"
    )

    cursor.execute("""
        INSERT INTO users (user_id, chat_id, xp, level, rank_title)
        VALUES (6318919732, -1001573891561, 33082500, 100, '🌟 Вічний водій')
        ON CONFLICT(user_id, chat_id) DO UPDATE SET
            xp = excluded.xp,
            level = excluded.level,
            rank_title = excluded.rank_title
        WHERE users.xp < excluded.xp
    """)

    conn.commit()
    conn.close()


def _create_users_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id         INTEGER NOT NULL,
            chat_id         INTEGER NOT NULL,
            username        TEXT,
            full_name       TEXT,
            xp              INTEGER DEFAULT 0,
            level           INTEGER DEFAULT 1,
            rank_title      TEXT DEFAULT '🔩 Новачок',
            messages        INTEGER DEFAULT 0,
            last_xp_at      REAL DEFAULT 0,
            streak_days     INTEGER DEFAULT 0,
            last_active_date TEXT DEFAULT '',
            joined_at       TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, chat_id)
        )
    """)


def get_or_create_user(user_id: int, chat_id: int, username: str, full_name: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        user = cursor.fetchone()

        if not user:
            cursor.execute("""
                INSERT OR IGNORE INTO users (user_id, chat_id, username, full_name)
                VALUES (?, ?, ?, ?)
            """, (user_id, chat_id, username, full_name))
            conn.commit()
            cursor.execute(
                "SELECT * FROM users WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id)
            )
            user = cursor.fetchone()
        else:
            cursor.execute("""
                UPDATE users SET username = ?, full_name = ?
                WHERE user_id = ? AND chat_id = ?
            """, (username, full_name, user_id, chat_id))
            conn.commit()

        return dict(user) if user else None
    finally:
        conn.close()


def add_xp(user_id: int, chat_id: int, xp: int, reason: str = "message"):
    conn = get_connection()
    try:
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
    finally:
        conn.close()


def update_user_level_rank(user_id: int, chat_id: int, level: int, rank_title: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET level = ?, rank_title = ?
            WHERE user_id = ? AND chat_id = ?
        """, (level, rank_title, user_id, chat_id))
        conn.commit()
    finally:
        conn.close()


def update_last_xp_time(user_id: int, chat_id: int, timestamp: float):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET last_xp_at = ?
            WHERE user_id = ? AND chat_id = ?
        """, (timestamp, user_id, chat_id))
        conn.commit()
    finally:
        conn.close()


def update_streak(user_id: int, chat_id: int, streak_days: int, date_str: str):
    """Обновить стрик и дату активности"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users
            SET streak_days = ?, last_active_date = ?
            WHERE user_id = ? AND chat_id = ?
        """, (streak_days, date_str, user_id, chat_id))
        conn.commit()
    finally:
        conn.close()


def get_user(user_id: int, chat_id: int):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        user = cursor.fetchone()
        return dict(user) if user else None
    finally:
        conn.close()


def get_top_users(chat_id: int, limit: int = 10):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM users
            WHERE chat_id = ?
            ORDER BY xp DESC
            LIMIT ?
        """, (chat_id, limit))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_weekly_xp(chat_id: int, week_start: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, chat_id, SUM(xp_gained) as week_xp
            FROM xp_log
            WHERE chat_id = ? AND created_at >= ?
            GROUP BY user_id
            ORDER BY week_xp DESC
            LIMIT 10
        """, (chat_id, week_start))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_all_chat_ids():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT chat_id FROM users")
        return [row["chat_id"] for row in cursor.fetchall()]
    finally:
        conn.close()


def save_weekly_snapshot(entries: list):
    conn = get_connection()
    try:
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
    finally:
        conn.close()


def get_last_weekly_snapshot(chat_id: int):
    """Получить последний сохранённый еженедельный снапшот для сравнения"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Берём самый свежий week_end для этого чата
        cursor.execute("""
            SELECT * FROM weekly_snapshots
            WHERE chat_id = ? AND week_end = (
                SELECT MAX(week_end) FROM weekly_snapshots WHERE chat_id = ?
            )
            ORDER BY position ASC
        """, (chat_id, chat_id))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def get_all_chats() -> list[int]:
    """Возвращает список уникальных chat_id из базы."""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT DISTINCT chat_id FROM users").fetchall()
        return [row[0] for row in rows]
    
    

