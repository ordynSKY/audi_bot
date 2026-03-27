import random

# ════
#   XP формула
# ════

def xp_required_for_level(level: int) -> int:
    return level ** 2 * 100 + level * 50


def total_xp_for_level(level: int) -> int:
    total = 0
    for lvl in range(1, level):
        total += xp_required_for_level(lvl)
    return total


def calculate_level(xp: int) -> int:
    level = 1
    while xp >= total_xp_for_level(level + 1):
        level += 1
        if level >= 100:
            break
    return level


def xp_progress(xp: int) -> dict:
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


# ════
#   Ранги
# ════

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
    rank = RANKS[0][1]
    for min_level, rank_title in RANKS:
        if level >= min_level:
            rank = rank_title
        else:
            break
    return rank


def get_next_rank(level: int) -> tuple | None:
    for min_level, rank_title in RANKS:
        if min_level > level:
            return min_level, rank_title
    return None


# ════
#   Умный XP по типу/длине сообщения
# ════

XP_COOLDOWN_SECONDS = 60

# Базовый XP по типу контента
CONTENT_XP = {
    "short_text":   (10, 18),   # < 20 символов
    "medium_text":  (18, 30),   # 20-100 символов
    "long_text":    (28, 45),   # > 100 символов
    "photo":        (15, 25),
    "video":        (20, 30),
    "voice":        (20, 35),
    "video_note":   (20, 35),   # кружочки
    "sticker":      (5, 10),
    "document":     (15, 25),
    "animation":    (8, 15),    # GIF
    "default":      (12, 22),
}

# Бонусы
STREAK_BONUS_PER_DAY = 3        # +3 XP за каждый день стрика
STREAK_MAX_BONUS = 30           # макс бонус от стрика
FIRST_MESSAGE_BONUS = 15        # бонус за первое сообщение дня


def get_message_xp(message=None, streak_days: int = 0, is_first_today: bool = False) -> tuple:
    """
    Возвращает (base_xp, streak_bonus, first_msg_bonus, total_xp, reason_detail)
    """
    # Определяем тип контента
    content_type = "default"
    if message:
        if message.text:
            text_len = len(message.text)
            if text_len < 20:
                content_type = "short_text"
            elif text_len <= 100:
                content_type = "medium_text"
            else:
                content_type = "long_text"
        elif message.photo:
            content_type = "photo"
        elif message.video:
            content_type = "video"
        elif message.voice:
            content_type = "voice"
        elif message.video_note:
            content_type = "video_note"
        elif message.sticker:
            content_type = "sticker"
        elif message.document:
            content_type = "document"
        elif message.animation:
            content_type = "animation"

    xp_min, xp_max = CONTENT_XP.get(content_type, CONTENT_XP["default"])
    base_xp = random.randint(xp_min, xp_max)

    # Streak бонус
    streak_bonus = min(streak_days * STREAK_BONUS_PER_DAY, STREAK_MAX_BONUS)

    # Бонус за первое сообщение дня
    first_bonus = FIRST_MESSAGE_BONUS if is_first_today else 0

    total = base_xp + streak_bonus + first_bonus

    detail = content_type
    if streak_bonus > 0:
        detail += f"+streak({streak_days}d)"
    if first_bonus > 0:
        detail += "+first_today"

    return base_xp, streak_bonus, first_bonus, total, detail


# ════
#   Прогресс-бар
# ════

def make_progress_bar(percent: int, length: int = 10) -> str:
    filled = int(length * percent / 100)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}]"