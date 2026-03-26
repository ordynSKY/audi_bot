import asyncio
import random
import time
import datetime

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
from db import *

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

def calculate_level(xp):
    return xp // 100

def get_rank(xp):
    rank = RANKS[0][1]
    for req, name in RANKS:
        if xp >= req:
            rank = name
    return rank

# анти-спам XP
last_message_time = {}

@dp.message()
async def debug(message: Message):
    print("🔥 MESSAGE RECEIVED:", message.chat.id, message.from_user.username, message.text)
async def handle_message(message: Message):
    if message.chat.type == "private":
        return

    user_id = message.from_user.id
    now = time.time()

    if user_id in last_message_time:
        if now - last_message_time[user_id] < 30:
            return

    last_message_time[user_id] = now

    xp_gain = random.randint(5, 15)

    await add_xp(
        user_id,
        message.from_user.username or message.from_user.first_name,
        xp_gain
    )

    user = await get_user_full(user_id)
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

@dp.message()
async def debug(message: Message):
    print("🔥 MESSAGE:", message.text)

# 👤 профиль
@dp.message(Command("me"))
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

# 🏆 топ
@dp.message(Command("top"))
async def top(message: Message):
    users = await get_top()

    text = "🏆 Топ участников:\n\n"
    for i, u in enumerate(users, 1):
        text += f"{i}. {u[0]} | {u[2]} — {u[1]} XP\n"

    await message.answer(text)

# ⏰ еженедельный топ
async def weekly_task():
    while True:
        await asyncio.sleep(60)
        now = datetime.datetime.now()

        if now.weekday() == 6 and now.hour == 23 and now.minute == 59:
            users = await get_weekly_top()

            text = "🔥 Еженедельный топ:\n\n"
            for i, u in enumerate(users, 1):
                text += f"{i}. {u[0]} — {u[1]} XP\n"

            if CHAT_ID:
                await bot.send_message(CHAT_ID, text)

            await reset_weekly()

async def main():
    print("🚀 Бот запускается...")
    await init_db()
    asyncio.create_task(weekly_task())
    print("✅ Бот запущен, polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())