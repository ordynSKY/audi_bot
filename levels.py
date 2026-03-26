# ══════════════════════════════════════════
#   Система уровней, XP и рангов для
#   Audi Owners Bot
# ══════════════════════════════════════════

import random

# XP необходимый для каждого уровня (кумулятивно)
# Формула: level^2 * 100 + level * 50
def xp_required_for_level(level: int) -> int:
    return level ** 2 * 100 + level * 50


def total_xp_for_level(level: int) -> int:
    """Суммарный XP нужный чтобы достичь этого уровня"""
    total = 0
    for lvl in range(1, level):
        total += xp_required_for_level(lvl)
    return total


def calculate_level(xp: int) -> int:
    """Определить текущий уровень по XP"""
    level = 1
    while xp >= total_xp_for_level(level + 1):
        level += 1
        if level >= 100:  # Кап уровня
            break
    return level


def xp_progress(xp: int) -> dict:
    """Прогресс до следующего уровня"""
    level = calculate_level(xp)
    current_level_xp = total_xp_for_level(level)
    next_level_xp = total_xp_for_level(level + 1)

    xp_in_level = xp - current_level_xp
    xp_needed = next_level_xp - current_level_xp
    percent = min(int((xp_in_level / xp_needed) * 100), 100) if xp_needed > 0 else 100

    return {
        "level": level,
        "xp_in_level": xp_in_level,
        "xp_needed": xp_needed,
        "percent": percent,
        "next_level_xp": next_level_xp,
        "total_xp": xp
    }


# ──────────────────────────────────────────
#   Ранги по уровням (Audi-тематика)
# ──────────────────────────────────────────
RANKS = [
    (1,  "🔩 Новичок"),
    (5,  "🚗 Водитель"),
    (10, "⚙️ Механик"),
    (15, "🔧 Мастер гаража"),
    (20, "🏁 Гонщик"),
    (25, "💨 Турбо-драйвер"),
    (30, "🏎️ Пилот quattro"),
    (40, "⭐ Ас"),
    (50, "🔥 Легенда Audi"),
    (60, "💎 Элита четырёх колец"),
    (75, "👑 Мастер Ингольштадта"),
    (90, "🚀 Бог скорости"),
    (100,"🌟 Вечный водитель"),
]


def get_rank(level: int) -> str:
    """Получить ранг по уровню"""
    rank = RANKS[0][1]
    for min_level, rank_title in RANKS:
        if level >= min_level:
            rank = rank_title
        else:
            break
    return rank


def get_next_rank(level: int) -> tuple | None:
    """Следующий ранг и уровень для его получения"""
    for min_level, rank_title in RANKS:
        if min_level > level:
            return min_level, rank_title
    return None


# ──────────────────────────────────────────
#   Генератор XP за сообщение
# ──────────────────────────────────────────
XP_COOLDOWN_SECONDS = 60  # Кулдаун между начислениями XP

def get_message_xp() -> int:
    """Случайный XP за сообщение (15-35)"""
    return random.randint(15, 35)


# ──────────────────────────────────────────
#   Прогресс-бар
# ──────────────────────────────────────────
def make_progress_bar(percent: int, length: int = 10) -> str:
    filled = int(length * percent / 100)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}]"
