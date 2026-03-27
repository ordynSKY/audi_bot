import asyncio
import logging
import os
import time
from datetime import datetime

import pytz
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, IS_NOT_MEMBER, MEMBER
from aiogram.enums import ParseMode, ChatType
from aiogram.client.default import DefaultBotProperties

from database import (
    init_db, get_or_create_user, add_xp, get_user,
    update_user_level_rank, update_last_xp_time,
    get_top_users, update_streak
)
from levels import (
    calculate_level, get_rank, xp_progress,
    make_progress_bar, get_message_xp, get_next_rank,
    XP_COOLDOWN_SECONDS
)
from scheduler import setup_scheduler, get_current_weekly_top

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
            f"🚗 <b>Добро пожаловать в Audi-клуб!</b>\n\n"
            f"Привет, {name}! 👋\n\n"
            f"💬 Пиши в чат — получай XP\n"
            f"📈 Прокачивай уровень и ранг\n"
            f"🏆 Попадай в еженедельный топ\n\n"
            f"Введи /help чтобы узнать все команды.\n"
            f"Удачи на дорогах! 🏎️"
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
            f"🚗 <b>Привет! Я бот Audi-клуба.</b>\n\n"
            f"Добавь меня в группу — и я буду начислять XP за активность!\n\n"
            f"Введи /help для списка команд."
        )
    else:
        text = (
            f"🚗 <b>Audi Club Bot активирован!</b>\n\n"
            f"Пишите в чат — получайте XP, прокачивайте уровень и ранг!\n"
            f"Введи /help для списка команд."
        )
    await message.answer(text)


# ════════════════════════════════════
#   КОМАНДА: /top
# ════════════════════════════════════

@dp.message(Command("top"))
async def cmd_top(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("📊 Эта команда работает только в группах!")
        return

    try:
        chat_id = message.chat.id
        top_users = get_top_users(chat_id, limit=10)

        if not top_users:
            await message.answer("😔 Пока никто не набрал XP. Начните общаться!")
            return

        medals = ["🥇", "🥈", "🥉"]
        lines = []

        for i, user in enumerate(top_users, start=1):
            medal = medals[i - 1] if i <= 3 else f"<b>{i}.</b>"
            name = user.get("full_name") or user.get("username") or "Аноним"
            xp = user["xp"]
            level = user["level"]
            rank = user["rank_title"]

            lines.append(
                f"{medal} <b>{name}</b>\n"
                f"    ├ Уровень: <b>{level}</b> | {rank}\n"
                f"    └ XP: <code>{xp:,}</code>"
            )

        text = (
            f"🏆 <b>ТОП УЧАСТНИКОВ AUDI-КЛУБА</b>\n"
            f"{'═' * 28}\n\n"
            + "\n\n".join(lines)
            + f"\n\n{'═' * 28}\n"
            f"💡 <i>Пиши больше — расти быстрее!</i>"
        )

        await message.answer(text)

    except Exception as e:
        logger.error(f"❌ Ошибка в /top: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка. Попробуй позже.")


# ════════════════════════════════════
#   КОМАНДА: /weekly
# ════════════════════════════════════

@dp.message(Command("weekly"))
async def cmd_weekly(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("📊 Эта команда работает только в группах!")
        return

    try:
        text = await get_current_weekly_top(message.chat.id)

        if not text:
            await message.answer("😔 На этой неделе ещё никто не набрал XP.")
            return

        await message.answer(text)

    except Exception as e:
        logger.error(f"❌ Ошибка в /weekly: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка. Попробуй позже.")


# ════════════════════════════════════
#   КОМАНДА: /rank / /profile
# ════════════════════════════════════

@dp.message(Command(commands=["rank", "profile", "stats"]))
async def cmd_rank(message: Message):
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("👤 Эта команда работает только в группах!")
        return

    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        username = message.from_user.username or ""
        full_name = message.from_user.full_name or "Аноним"

        user = get_or_create_user(user_id, chat_id, username, full_name)

        progress = xp_progress(user["xp"])
        bar = make_progress_bar(progress["percent"], length=12)
        next_rank_info = get_next_rank(progress["level"])
        name = message.from_user.full_name or "Аноним"

        top = get_top_users(chat_id, limit=1000)
        position = next((i + 1 for i, u in enumerate(top) if u["user_id"] == user_id), "?")

        streak = user.get("streak_days", 0)
        streak_text = f"🔥 Стрик: <b>{streak} дн.</b>\n" if streak > 0 else ""

        text = (
            f"👤 <b>{name}</b>\n"
            f"{'━' * 26}\n"
            f"🏅 Ранг: <b>{user['rank_title']}</b>\n"
            f"⭐ Уровень: <b>{progress['level']}</b>\n"
            f"💬 Сообщений: <b>{user['messages']:,}</b>\n"
            f"🏆 Позиция в топе: <b>#{position}</b>\n"
            f"{streak_text}"
            f"{'━' * 26}\n"
            f"📊 <b>Прогресс до ур. {progress['level'] + 1}:</b>\n"
            f"{bar} <code>{progress['percent']}%</code>\n"
            f"XP: <code>{progress['xp_in_level']}</code> / <code>{progress['xp_needed']}</code>\n"
            f"Всего XP: <code>{user['xp']:,}</code>\n"
        )

        if next_rank_info:
            next_rank_level, next_rank_title = next_rank_info
            text += (
                f"{'━' * 26}\n"
                f"🎯 Следующий ранг: <b>{next_rank_title}</b>\n"
                f"   (с {next_rank_level} уровня)"
            )

        await message.answer(text)

    except Exception as e:
        logger.error(f"❌ Ошибка в /rank: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка. Попробуй позже.")


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
                f"  └ с <b>{min_level}</b> ур. | <code>{xp_need:,}</code> XP"
            )

        text = (
            f"📋 <b>СИСТЕМА РАНГОВ AUDI-КЛУБА</b>\n"
            f"{'═' * 28}\n\n"
            + "\n\n".join(lines)
            + f"\n\n{'═' * 28}\n"
            f"💡 XP зависит от типа и длины сообщения\n"
            f"🔥 Стрик-бонус: +3 XP за каждый день подряд\n"
            f"🌅 Первое сообщение дня: +15 XP\n"
            f"⏱ Кулдаун: 60 сек"
        )

        await message.answer(text)

    except Exception as e:
        logger.error(f"❌ Ошибка в /levels: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка. Попробуй позже.")


# ════════════════════════════════════
#   КОМАНДА: /help
# ════════════════════════════════════

@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        f"🚗 <b>AUDI CLUB BOT — Помощь</b>\n"
        f"{'═' * 28}\n\n"
        f"<b>Основные команды:</b>\n"
        f"• /top — 🏆 Топ участников (общий)\n"
        f"• /weekly — 📊 Топ за текущую неделю\n"
        f"• /rank — 👤 Твой профиль и ранг\n"
        f"• /levels — 📋 Таблица всех рангов\n"
        f"• /help — ℹ️ Эта справка\n\n"
        f"<b>Как начисляется XP:</b>\n"
        f"💬 Текст: 10-45 XP (зависит от длины)\n"
        f"📷 Фото/видео: 15-30 XP\n"
        f"🎤 Голосовые/кружочки: 20-35 XP\n"
        f"😄 Стикеры/GIF: 5-15 XP\n"
        f"🔥 Стрик: +3 XP за каждый день подряд (макс +30)\n"
        f"🌅 Первое сообщение дня: +15 XP бонус\n"
        f"⏱ Кулдаун: 60 сек между начислениями\n\n"
        f"🏆 Еженедельный топ — каждое вс в 23:59"
    )
    await message.answer(text)


# ════════════════════════════════════
#   XP ЗА СООБЩЕНИЯ (ПОСЛЕ всех команд!)
# ════════════════════════════════════

@dp.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def handle_group_message(message: Message):
    if not message.from_user or message.from_user.is_bot:
        return

    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        username = message.from_user.username or ""
        full_name = message.from_user.full_name or "Аноним"

        user = get_or_create_user(user_id, chat_id, username, full_name)

        # Кулдаун
        now = time.time()
        if now - user.get("last_xp_at", 0) < XP_COOLDOWN_SECONDS:
            return

        # ── Стрик и первое сообщение дня ──
        today_str = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        last_active = user.get("last_active_date", "")
        streak = user.get("streak_days", 0)
        is_first_today = False

        if last_active != today_str:
            # Новый день
            yesterday = (datetime.now(TIMEZONE) - __import__('datetime').timedelta(days=1)).strftime("%Y-%m-%d")
            if last_active == yesterday:
                streak += 1  # продолжаем стрик
            else:
                streak = 1   # стрик сброшен

            is_first_today = True
            update_streak(user_id, chat_id, streak, today_str, 1)
        elif not user.get("first_msg_today", 0):
            is_first_today = True
            update_streak(user_id, chat_id, streak, today_str, 1)

        # ── Умный XP ──
        base_xp, streak_bonus, first_bonus, total_xp, detail = get_message_xp(
            message=message,
            streak_days=streak,
            is_first_today=is_first_today
        )

        add_xp(user_id, chat_id, total_xp, reason=detail)
        update_last_xp_time(user_id, chat_id, now)

        # ── Уведомление о первом сообщении дня ──
        if is_first_today and streak > 1:
            bonus_text = (
                f"🌅 <b>Первое сообщение дня!</b>\n"
                f"🔥 Стрик: <b>{streak} дн.</b> (+{streak_bonus} XP бонус)\n"
                f"⭐ +{total_xp} XP"
            )
            await message.reply(bonus_text)
            # Не дублируем level-up ниже если уже ответили
            # (проверяем level-up всё равно)

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
                f"📈 Уровень: <b>{old_level}</b> → <b>{new_level}</b>\n"
            )

            if new_rank != old_rank:
                level_up_text += f"🏅 Новый ранг: <b>{new_rank}</b>\n"

            level_up_text += f"⭐ Всего XP: <code>{updated_user['xp']}</code>"

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