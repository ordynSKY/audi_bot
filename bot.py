import asyncio
import logging
import os
import random
import time
from datetime import datetime

import pytz
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatMemberUpdated, InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, IS_NOT_MEMBER, MEMBER
from aiogram.enums import ParseMode, ChatType
from aiogram.client.default import DefaultBotProperties

from database import (
    init_db, get_or_create_user, add_xp, get_user,
    update_user_level_rank, update_last_xp_time,
    get_top_users, update_streak
)
from jokes import JOKE_NO, JOKE_YES
from levels import (
    calculate_level, get_rank, xp_progress,
    make_progress_bar, get_message_xp, get_next_rank,
    XP_COOLDOWN_SECONDS, MAX_LEVEL
)
from responses import BMW_RESPONSES
from scheduler import setup_scheduler, get_current_weekly_top

import re

BMW_PATTERN = re.compile(
    r'\b(bmw|бмв|бэмвэ|бэха|бумер|бимер|бэмэвэ|bmv)\b',
    re.IGNORECASE
)



# ────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)
# ────

TIMEZONE = pytz.timezone("Europe/Kyiv")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не установлен!")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


# ════════════════════════════════════
#   ПРИВЕТСТВИЕ НОВЫХ УЧАСТНИКОВ
# ════════════════════════════════════

@dp.chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> MEMBER))
async def on_new_member(event: ChatMemberUpdated):
    """Приветствие нового участника группы"""
    try:
        user = event.new_chat_member.user
        if user.is_bot:
            return

        name = f'<a href="tg://user?id={user.id}">{user.full_name or "друг"}</a>'

        text = (
            f"🚗 <b>Ласкаво просимо до Audi-клубу!</b>\n\n"
            f"Привіт, {name}! 👋\n\n"
            f"💬 Пиши в чат - отримуй XP\n"
            f"📈 Прокачуй рівень та ранг\n"
            f"🏆 Попадай у щотижневий топ\n\n"
            f"Введи /howto щоб дізнатися про всі команди.\n"
            f"Успіхів на дорогах! 🏎️"
        )

        await bot.send_message(chat_id=event.chat.id, text=text)
        logger.info(f"👋 Новый участник: {user.full_name} ({user.id}) в чате {event.chat.id}")

    except Exception as e:
        logger.error(f"❌ Ошибка приветствия: {e}", exc_info=True)


# ════════════════════════════════════
#   КОМАНДА: /start
# ════════════════════════════════════

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        text = (
            f"🚗 <b>Привіт! Я бот Audi-клубу.</b>\n\n"
            f"Додай мене до групи — і я нараховуватиму XP за активність!\n\n"
            f"Введіть /howto для списку команд."
        )
    else:
        text = (
            f"🚗 <b>Audi Club Bot активовано!</b>\n\n"
            f"Пишіть у чат – отримуйте XP, прокачуйте рівень та ранг!\n"
            f"Введіть /howto для списку команд."
        )
    await message.answer(text)


# ════════════════════════════════════
#   КОМАНДА: /top
# ════════════════════════════════════

@dp.message(Command("top"))
async def cmd_top(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("📊 Ця команда працює лише у групах!")
        return

    try:
        chat_id = message.chat.id
        top_users = get_top_users(chat_id, limit=10)

        if not top_users:
            await message.answer("😔 Поки що ніхто не набрав XP. Почніть спілкуватися!")
            return

        medals = ["🥇", "🥈", "🥉"]
        lines = []

        for i, user in enumerate(top_users, start=1):
            medal = medals[i - 1] if i <= 3 else f"<b>{i}.</b>"
            name = user.get("full_name") or user.get("username") or "Анонім"
            xp = user["xp"]
            level = user["level"]
            rank = user["rank_title"]

            lines.append(
                f"{medal} <b>{name}</b>\n"
                f"    ├ Рівень: <b>{level}</b> | {rank}\n"
                f"    └ XP: <code>{xp:,}</code>"
            )

        text = (
            f"🏆 <b>ТОП УЧАСНИКІВ AUDI-КЛУБУ</b>\n"
            f"{'═' * 28}\n\n"
            + "\n\n".join(lines)
            + f"\n\n{'═' * 28}\n"
            f"💡 <i>Пиши більше – рости швидше!</i>"
        )

        await message.answer(text)

    except Exception as e:
        logger.error(f"❌ Помилка в /top: {e}", exc_info=True)
        await message.answer("⚠️ Сталася помилка. Спробуй пізніше.")


# ════════════════════════════════════
#   КОМАНДА: /weekly
# ════════════════════════════════════

@dp.message(Command("weekly"))
async def cmd_weekly(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("📊 Ця команда працює лише у групах!")
        return

    try:
        text = await get_current_weekly_top(message.chat.id)

        if not text:
            await message.answer("😔 На цьому тижні ще ніхто не набрав XP.")
            return

        await message.answer(text)

    except Exception as e:
        logger.error(f"❌ Помилка в /weekly: {e}", exc_info=True)
        await message.answer("⚠️ Сталася помилка. Спробуй пізніше.")


# ════════════════════════════════════
#   КОМАНДА: /rank / /profile
# ════════════════════════════════════

@dp.message(Command(commands=["rank", "profile", "stats"]))
async def cmd_rank(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("👤 Ця команда працює лише у групах!")
        return

    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        username = message.from_user.username or ""
        full_name = message.from_user.full_name or "Анонім"

        user = get_or_create_user(user_id, chat_id, username, full_name)

        progress = xp_progress(user["xp"])
        bar = make_progress_bar(progress["percent"], length=12)
        next_rank_info = get_next_rank(progress["level"])
        name = message.from_user.full_name or "Анонім"

        top = get_top_users(chat_id, limit=1000)
        position = next((i + 1 for i, u in enumerate(top) if u["user_id"] == user_id), "?")

        streak = user.get("streak_days", 0)
        streak_text = f"🔥 Стрік: <b>{streak} дн.</b>\n" if streak > 0 else ""

        text = (
            f"👤 <b>{name}</b>\n"
            f"{'━' * 26}\n"
            f"🏅 Ранг: <b>{user['rank_title']}</b>\n"
            f"⭐ Рівень: <b>{progress['level']}</b>\n"
            f"💬 Повідомленнь: <b>{user['messages']:,}</b>\n"
            f"🏆 Позиція у топі: <b>#{position}</b>\n"
            f"{streak_text}"
            f"{'━' * 26}\n"
        )

        if progress["level"] >= MAX_LEVEL:
            text += (
                f"🏆 <b>Максимальний рівень досягнуто!</b>\n"
                f"Усього XP: <code>{user['xp']:,}</code>\n"
            )
        else:
            text += (
                f"📊 <b>Прогрес до рів. {progress['level'] + 1}:</b>\n"
                f"{bar} <code>{progress['percent']}%</code>\n"
                f"XP: <code>{progress['xp_in_level']}</code> / <code>{progress['xp_needed']}</code>\n"
                f"Усьго XP: <code>{user['xp']:,}</code>\n"
            )

        if next_rank_info:
            next_rank_level, next_rank_title = next_rank_info
            text += (
                f"{'━' * 26}\n"
                f"🎯 Наступний ранг: <b>{next_rank_title}</b>\n"
                f"   (з {next_rank_level} рівня)"
            )

        await message.answer(text)

    except Exception as e:
        logger.error(f"❌ Ошибка в /rank: {e}", exc_info=True)
        await message.answer("⚠️ Сталася помилка. Спробуй пізніше.")


# ════════════════════════════════════
#   КОМАНДА: /levels
# ════════════════════════════════════

@dp.message(Command("levels"))
async def cmd_levels(message: Message):
    try:
        from levels import RANKS, total_xp_for_level

        lines = []
        for min_level, rank_title in RANKS:
            xp_need = total_xp_for_level(min_level)
            lines.append(
                f"{rank_title}\n"
                f"  └ з <b>{min_level}</b> рів. | <code>{xp_need:,}</code> XP"
            )

        text = (
            f"📋 <b>СИСТЕМА РАНГІВ AUDI-КЛУБУ</b>\n"
            f"{'═' * 28}\n\n"
            + "\n\n".join(lines)
            + f"\n\n{'═' * 28}\n"
            f"💡 XP залежить від типу та довжини повідомлення\n"
            f"🔥 Стрик-бонус: +3 XP за кожен день поспіль\n"
            f"⏱ Кулдаун: 60 сек"
        )

        await message.answer(text)

    except Exception as e:
        logger.error(f"❌ Ошибка в /levels: {e}", exc_info=True)
        await message.answer("⚠️ Сталася помилка. Спробуй пізніше.")


# ════════════════════════════════════
#   КОМАНДА: /howto
# ════════════════════════════════════

@dp.message(Command("howto"))
async def cmd_help(message: Message):
    text = (
        f"🚗 <b>AUDI CLUB BOT — Допомога</b>\n"
        f"{'═' * 28}\n\n"
        f"<b>Основні команди:</b>\n"
        f"• /top — 🏆 Топ учасників (загальний)\n"
        f"• /weekly — 📊 Топ за поточний тиждень\n"
        f"• /rank — 👤 Твій профіль та ранг\n"
        f"• /levels — 📋 Таблиця всіх рангів\n"
        f"• /howto — ℹ️ Ця довідка\n\n"
        f"<b>Як нараховується XP:</b>\n"
        f"💬 Текст: 10-45 XP (залежить від довжини)\n"
        f"📷 Фото/відео: 15-30 XP\n"
        f"🎤 Голосові/кружочки: 20-35 XP\n"
        f"😄 Стікери/GIF: 5-15 XP\n"
        f"🔥 Стрик: +3 XP за кожен день поспіль (макс +30)\n"
        f"⏱ Кулдаун: 60 сек між нарахуванням\n\n"
        f"🏆 Щотижневий топ — кожну неділю в 23:59"
    )
    await message.answer(text)


# ════════════════════════════════════
#   УМЕСТНА ЛИ ШУТКА
# ════════════════════════════════════   

@dp.inline_query()
async def inline_handler(query: InlineQuery):
    results = [
        InlineQueryResultArticle(
            id="joke_check",
            title="😂 Доречний був жарт?",
            description="Дізнайся, чи був доречним жарт?",
            input_message_content=InputTextMessageContent(
                message_text=random.choice(JOKE_YES) if random.random() < 0.5 else random.choice(JOKE_NO)
            ),
            thumbnail_url="https://img.icons8.com/emoji/96/rolling-on-the-floor-laughing-emoji.png",
        ),
    ]

    await query.answer(results, cache_time=0)  # cache_time=0 чтобы каждый раз новый результат

# ════════════════════════════════════
#   XP ЗА СООБЩЕНИЯ (ПОСЛЕ всех команд!)
# ════════════════════════════════════



@dp.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def handle_group_message(message: Message):
    if not message.from_user or message.from_user.is_bot:
        return

    try:
        # --- BMW фильтр ---
        if message.text and BMW_PATTERN.search(message.text):
            response = random.choice(BMW_RESPONSES)
            await message.reply(response)
        
        user_id = message.from_user.id
        chat_id = message.chat.id
        username = message.from_user.username or ""
        full_name = message.from_user.full_name or "Анонім"

        user = get_or_create_user(user_id, chat_id, username, full_name)

        # Кулдаун
        now = time.time()
        if now - user.get("last_xp_at", 0) < XP_COOLDOWN_SECONDS:
            return

# ── Стрик ──
        today_str = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        last_active = user.get("last_active_date", "")
        streak = user.get("streak_days", 0)

        if last_active != today_str:
            yesterday = (datetime.now(TIMEZONE) - __import__('datetime').timedelta(days=1)).strftime("%Y-%m-%d")
            if last_active == yesterday:
                streak += 1
            else:
                streak = 1
            update_streak(user_id, chat_id, streak, today_str)

        # ── Умный XP ──
        base_xp, streak_bonus, total_xp, detail = get_message_xp(
            message=message,
            streak_days=streak,
        )

        add_xp(user_id, chat_id, total_xp, reason=detail)
        update_last_xp_time(user_id, chat_id, now)



        # ── Проверка level-up ──
        updated_user = get_user(user_id, chat_id)
        new_level = calculate_level(updated_user["xp"])
        new_rank = get_rank(new_level)
        old_level = user.get("level", 1)

        if new_level > old_level:
            update_user_level_rank(user_id, chat_id, new_level, new_rank)

            name = f'<a href="tg://user?id={user_id}">{full_name}</a>'
            old_rank = get_rank(old_level)

            level_up_text = (
                f"🎉 <b>LEVEL UP!</b>\n\n"
                f"👤 {name}\n"
                f"━━━━\n"
                f"📈 Рівень: <b>{old_level}</b> → <b>{new_level}</b>\n"
            )

            if new_rank != old_rank:
                level_up_text += f"🏅 Новий ранг: <b>{new_rank}</b>\n"

            level_up_text += f"⭐ Усього XP: <code>{updated_user['xp']}</code>"

            await message.reply(level_up_text)

        elif new_rank != user.get("rank_title"):
            update_user_level_rank(user_id, chat_id, new_level, new_rank)

    except Exception as e:
        logger.error(f"❌ Ошибка при начислении XP: {e}", exc_info=True)


# ════════════════════════════════════
#   СТАРТ
# ════════════════════════════════════

async def main():
    logger.info("🚀 Запуск Audi Club Bot...")

    init_db()
    logger.info("✅ База данных инициализирована")

    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("✅ Планировщик запущен")

    logger.info("✅ Бот запущен и ожидает сообщений...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())