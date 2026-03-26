import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from database import get_all_chat_ids, get_weekly_xp, get_user, save_weekly_snapshot

logger = logging.getLogger(__name__)

TIMEZONE = pytz.timezone("Europe/Kyiv")


def get_week_start() -> str:
    """Получить начало текущей недели (понедельник 00:00)"""
    now = datetime.now(TIMEZONE)
    monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.strftime("%Y-%m-%d %H:%M:%S")


async def send_weekly_top(bot):
    """Отправить еженедельный топ во все чаты"""
    logger.info("📊 Запуск еженедельного топа...")

    chat_ids = get_all_chat_ids()
    week_start = get_week_start()
    now = datetime.now(TIMEZONE)
    week_end = now.strftime("%Y-%m-%d %H:%M:%S")

    for chat_id in chat_ids:
        try:
            weekly_data = get_weekly_xp(chat_id, week_start)

            if not weekly_data:
                continue

            lines = []
            medals = ["🥇", "🥈", "🥉"]
            snapshot_entries = []

            for i, entry in enumerate(weekly_data[:10], start=1):
                user = get_user(entry["user_id"], chat_id)
                if not user:
                    continue

                medal = medals[i - 1] if i <= 3 else f"{i}."
                name = user.get("full_name") or user.get("username") or "Аноним"
                xp_week = entry["week_xp"]

                lines.append(f"{medal} <b>{name}</b> — <code>+{xp_week} XP</code>")

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
                continue

            week_start_dt = datetime.strptime(week_start, "%Y-%m-%d %H:%M:%S")

            text = (
                f"🏆 <b>ЕЖЕНЕДЕЛЬНЫЙ ТОП AUDI-КЛУБА</b>\n"
                f"📅 {week_start_dt.strftime('%d.%m')} — {now.strftime('%d.%m.%Y')}\n"
                f"{'═' * 28}\n\n"
                + "\n".join(lines)
                + f"\n\n{'═' * 28}\n"
                f"💬 Участников в топе: <b>{len(lines)}</b>\n"
                f"🔄 Новая неделя началась! Удачи всем! 🚀"
            )

            await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")

            if snapshot_entries:
                save_weekly_snapshot(snapshot_entries)

            logger.info(f"✅ Еженедельный топ отправлен в чат {chat_id}")

        except Exception as e:
            logger.error(f"❌ Ошибка при отправке топа в чат {chat_id}: {e}")


def setup_scheduler(bot) -> AsyncIOScheduler:
    """Настройка планировщика задач"""
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

    logger.info("✅ Планировщик настроен: еженедельный топ в вс 23:59 (Kyiv)")
    return scheduler