import asyncio
import random
import time
import datetime
import os

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message

from db import *  # твои функции add_xp, get_user_full, update_level, update_rank, get_top, get_weekly_top, reset_weekly, init_db

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID") or 0)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# 🏎️ Ранги
RANKS = [
    (0, "🚗 A1 Новичок"),
    (100, "🚙 A3 Городской"),
    (300, "🚘 A4 Водитель"),
    (700, "🚖 A6 Профи"),
    (1500, "🏎 S5 Быстрый"),
    (3000, "🔥 RS6 Гонщик"),
    (6000, "👑 R8 Легенда")
]

def calculate_level(xp: int) -> int:
    return xp // 100

def get_rank(xp: int) -> str:
    rank = RANKS[0][1]
    for req, name in RANKS:
        if xp >= req:
            rank = name
    return rank

# антиспам XP
last_message_time = {}

# ---------------------------
# 📩 Обработка всех сообщений
# ---------------------------
@dp.message()
async def handle_all_messages(message: Message):
    # DEBUG
    print("🔥 MESSAGE RECEIVED:", message.chat.id, message.from_user.username, message.text)

    # Игнорируем приватные чаты (если не хочешь обрабатывать)
    if message.chat.type == "private":
        return

    # Игнорируем команды, они идут в отдельные хэндлеры
    if message.text and message.text.startswith("/"):
        return

    user_id = message.from_user.id
    now = time.time()

    if user_id in last_message_time and now - last_message_time[user_id] < 30:
        return  # антиспам 30 секунд

    last_message_time[user_id] = now
    xp_gain = random.randint(5, 15)

    await add_xp(user_id, message.from_user.username or message.from_user.first_name, xp_gain)
    user = await get_user_full(user_id)
    if not user:
        return

    xp, level, rank = user

    # уровень
    new_level = calculate_level(xp)
    if new_level > level:
        await update_level(user_id, new_level)
        await message.reply(f"🎉 Новый уровень: {new_level}")

    # ранг
    new_rank = get_rank(xp)
    if new_rank != rank:
        await update_rank(user_id, new_rank)
        await message.reply(f"🏎 Новый ранг: {new_rank}")

# ---------------------------
# 👤 Профиль
# ---------------------------
@dp.message(F.text.startswith("/me"))
async def me(message: Message):
    user = await get_user_full(message.from_user.id)
    if not user:
        await message.answer("Нет данных")
        return

    xp, level, rank = user
    await message.answer(
        f"👤 Профиль\n\n"
        f"🏎 Ранг: {rank}\n"
        f"⭐ XP: {xp}\n"
        f"🏅 Уровень: {level}"
    )

# ---------------------------
# 🏆 Топ пользователей
# ---------------------------
@dp.message(F.text.startswith("/top"))
async def top(message: Message):
    users = await get_top()
    text = "🏆 Топ участников:\n\n"
    for i, u in enumerate(users, 1):
        text += f"{i}. {u[0]} | {u[2]} — {u[1]} XP\n"
    await message.answer(text)

# ---------------------------
# ⏰ Еженедельный топ
# ---------------------------
async def weekly_task():
    while True:
        await asyncio.sleep(60)  # проверка каждую минуту
        now = datetime.datetime.now()

        # Воскресенье 23:59
        if now.weekday() == 6 and now.hour == 23 and now.minute == 59:
            users = await get_weekly_top()
            text = "🔥 Еженедельный топ:\n\n"
            for i, u in enumerate(users, 1):
                text += f"{i}. {u[0]} — {u[1]} XP\n"
            if CHAT_ID:
                await bot.send_message(CHAT_ID, text)
            await reset_weekly()

# ---------------------------
# 🔹 Main
# ---------------------------
async def main():
    print("🚀 Бот запускается...")
    await init_db()
    asyncio.create_task(weekly_task())
    print("✅ Бот запущен, polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())