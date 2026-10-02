import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")
dp = Dispatcher()

@dp.message(CommandStart())
async def start(message: types.Message):
    if not WEBAPP_URL:
        await message.answer("AUTO DEALER пока не настроен: отсутствует WEBAPP_URL.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚗 Открыть AUTO DEALER", web_app=WebAppInfo(url=WEBAPP_URL.rstrip("/") + "?v=final5"))
    ]])
    await message.answer(
        "🚗 <b>AUTO DEALER</b>\n\n"
        "Покупай машины, торгуйся с продавцами, ремонтируй и перепродавай.\n"
        "🚔 Получай уникальные номера и торгуй ими с игроками.",
        reply_markup=kb, parse_mode="HTML"
    )

def make_bot():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN не задан")
    return Bot(TOKEN)
