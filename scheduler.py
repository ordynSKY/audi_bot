import logging
import os
from datetime import datetime, timedelta
import random
from aiogram import Bot
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from database import (
    get_all_chat_ids, get_all_chats, get_weekly_xp, get_user,
    save_weekly_snapshot, get_last_weekly_snapshot
)
from quotes import QUOTES
from ads import ADS

logger = logging.getLogger(__name__)

TIMEZONE = pytz.timezone("Europe/Kyiv")
MAIN_CHAT_ID = int(os.getenv("MAIN_CHAT_ID", "-1001573891561"))

async def send_ads(bot: Bot, chat_id: int | None = None):
    """Публикует все рекламные посты подряд. По умолчанию — в основной чат."""
    target = chat_id if chat_id is not None else MAIN_CHAT_ID

    order = list(range(len(ADS)))
    random.shuffle(order)

    for idx in order:
        ad = ADS[idx]
        try:
            photo = FSInputFile(str(ad["image"]))
            await bot.send_photo(
                chat_id=target,
                photo=photo,
                caption=ad["caption"],
            )
            logger.info(f"📢 Реклама отправлена в {target} (ad index {idx})")
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке рекламы (ad {idx}): {e}", exc_info=True)


async def send_hourly_quote(bot: Bot):
    """Отправляет цитату во все группы с 08:00 до 23:59 по Киеву."""
    kyiv_now = datetime.now(TIMEZONE)
    if not (8 <= kyiv_now.hour <= 23):
        return

    quote = random.choice(QUOTES)
    text = f"💬 *Цитата години:*\n\n_{quote}_"

    chats = get_all_chats()
    for chat_id in chats:
        try:
            await bot.send_message(chat_id, text, parse_mode="Markdown")
        except Exception as e:
            logging.warning(f"Не удалось отправить цитату в {chat_id}: {e}")


def get_week_start() -> str:
    now = datetime.now(TIMEZONE)
    monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.strftime("%Y-%m-%d %H:%M:%S")


def _build_weekly_top_text(chat_id: int, week_start: str, now: datetime, save: bool = True):
    """Общая логика построения еженедельного топа (для шедулера и /weekly)"""
    weekly_data = get_weekly_xp(chat_id, week_start)
    if not weekly_data:
        return None, []

    # Получаем прошлый снапшот для сравнения позиций
    last_snapshot = get_last_weekly_snapshot(chat_id)
    old_positions = {}
    for snap in last_snapshot:
        old_positions[snap["user_id"]] = snap["position"]

    lines = []
    medals = ["🥇", "🥈", "🥉"]
    snapshot_entries = []
    week_end = now.strftime("%Y-%m-%d %H:%M:%S")

    for i, entry in enumerate(weekly_data[:10], start=1):
        user = get_user(entry["user_id"], chat_id)
        if not user:
            continue

        medal = medals[i - 1] if i <= 3 else f"{i}."
        name = user.get("full_name") or user.get("username") or "Аноним"
        xp_week = entry["week_xp"]

        # Изменение позиции
        change = ""
        old_pos = old_positions.get(entry["user_id"])
        if old_pos is not None:
            diff = old_pos - i  # положительный = поднялся
            if diff > 0:
                change = f" 🔼+{diff}"
            elif diff < 0:
                change = f" 🔽{diff}"
            else:
                change = " ➖"
        else:
            change = " 🆕"

        lines.append(f"{medal} <b>{name}</b> — <code>+{xp_week} XP</code>{change}")

        snapshot_entries.append({
            "user_id": entry["user_id"],
            "chat_id": chat_id,
            "username": user.get("username", ""),
            "full_name": name,
            "xp_week": xp_week,
            "week_start": week_start,
            "week_end": week_end,
            "position": i
        })

    if not lines:
        return None, []

    week_start_dt = datetime.strptime(week_start, "%Y-%m-%d %H:%M:%S")

    text = (
        f"🏆 <b>ЩОТИЖНЕВИЙ ТОП AUDI-КЛУБУ</b>\n"
        f"📅 {week_start_dt.strftime('%d.%m')} — {now.strftime('%d.%m.%Y')}\n"
        f"{'═' * 28}\n\n"
        + "\n".join(lines)
        + f"\n\n{'═' * 28}\n"
        f"💬 Учасників в топі: <b>{len(lines)}</b>\n"
    )

    return text, snapshot_entries


async def send_weekly_top(bot):
    logger.info("📊 Запуск еженедельного топа...")

    chat_ids = get_all_chat_ids()
    week_start = get_week_start()
    now = datetime.now(TIMEZONE)

    for chat_id in chat_ids:
        try:
            text, snapshot_entries = _build_weekly_top_text(chat_id, week_start, now)

            if not text:
                continue

            text += "🔄 Новий тиждень розпочався! Успіхів усім! 🚀"

            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

            if snapshot_entries:
                save_weekly_snapshot(snapshot_entries)

            logger.info(f"✅ Еженедельный топ отправлен в чат {chat_id}")

        except Exception as e:
            logger.error(f"❌ Ошибка при отправке топа в чат {chat_id}: {e}", exc_info=True)


async def get_current_weekly_top(chat_id: int) -> str | None:
    """Для команды /weekly — текущий топ без сохранения снапшота"""
    week_start = get_week_start()
    now = datetime.now(TIMEZONE)
    text, _ = _build_weekly_top_text(chat_id, week_start, now, save=False)
    if text:
        text += "⏳ Підсумки тижня - у неділю о 23:59"
    return text


def setup_scheduler(bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    scheduler.add_job(
        func=send_weekly_top,
        trigger=CronTrigger(
            day_of_week="sun",
            hour=23,
            minute=59,
            second=0,
            timezone=TIMEZONE
        ),
        args=[bot],
        id="weekly_top",
        name="Еженедельный топ",
        replace_existing=True
    )

    scheduler.add_job(
    send_hourly_quote,
    CronTrigger(hour="10,22", minute=0, timezone=TIMEZONE),
    args=[bot],
    id="hourly_quote",
    replace_existing=True,
    )

    scheduler.add_job(
        send_ads,
        CronTrigger(hour="10,15,20", minute=0, timezone=TIMEZONE),
        args=[bot],
        id="ad_post",
        replace_existing=True,
    )

    logger.info("✅ Планировщик настроен: еженедельный топ в вс 23:59 (Kyiv)")
    return scheduler