import asyncio
import logging
import os
from datetime import datetime, date, timedelta

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram_calendar import SimpleCalendar, simple_cal_callback
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
AVIASALES_TOKEN = "6c48242837234d39f1e8320332f1f779"

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


class FlightSearch(StatesGroup):
    destination = State()


DESTINATIONS = {
    "bkk": {"name": "Бангкок", "code": "BKK"},
    "utp": {"name": "Паттайя", "code": "UTP"}
}


async def get_direct_flights(dest_code: str, dep_date: date = None):
    """Поиск прямых рейсов. Если dep_date=None — ближайшие 3 месяца"""
    origin = "MOW"
    flights = []

    if dep_date:
        # точная дата
        dates = [dep_date.strftime("%Y-%m-%d")]
    else:
        # ближайшие ~3 месяца
        dates = [(datetime.now() + timedelta(days=30 * i)).strftime("%Y-%m") for i in range(4)]

    for d in dates:
        url = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
        params = {
            "origin": origin,
            "destination": dest_code,
            "departure_at": d,
            "one_way": "true",
            "direct": "true",
            "sorting": "price",
            "limit": 15,
            "currency": "rub",
            "token": AVIASALES_TOKEN
        }

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success"):
                            flights.extend(data.get("data", []))
            except:
                continue

    flights = [f for f in flights if f.get("price")]
    flights.sort(key=lambda x: x["price"])
    return flights[:10]


def format_flights(flights, city_name, selected_date=None):
    if not flights:
        return f"❌ Прямых рейсов в {city_name} не найдено на выбранный период 😔"

    text = f"<b>✈️ Прямые рейсы Москва → {city_name}</b>\n"
    if selected_date:
        text += f"<b>Дата: {selected_date.strftime('%d %B %Y')}</b>\n\n"
    else:
        text += "<b>Ближайшие рейсы (3+ месяца)</b>\n\n"

    for f in flights:
        dep = datetime.fromisoformat(f["departure_at"].replace("Z", "+00:00"))
        date_str = dep.strftime("%d.%m %H:%M")
        price = f'{f["price"]:,}'.replace(',', ' ')
        airline = f.get("airline", "??")
        duration = f.get("duration", 0) // 60

        link = f"https://www.aviasales.ru{f.get('link', '')}" if f.get("link") else "#"

        text += f"<b>{date_str}</b> — <b>{price} ₽</b>\n"
        text += f"   {airline} • {duration} ч\n"
        text += f"   <a href='{link}'>Купить билет →</a>\n\n"

    text += "\n<i>Данные из кэша Aviasales • цены меняются</i>"
    return text


# ====================== ХЕНДЛЕРЫ ======================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌴 Паттайя (UTP)", callback_data="utp")],
        [InlineKeyboardButton(text="🏙 Бангкок (BKK)", callback_data="bkk")]
    ])
    await message.answer(
        "👋 Привет! Я ищу <b>только прямые</b> рейсы из Москвы.\nВыбери направление:",
        reply_markup=kb
    )


@dp.callback_query(lambda c: c.data in DESTINATIONS)
async def choose_action(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data
    dest = DESTINATIONS[code]
    await state.update_data(destination=code)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Выбрать дату вылета", callback_data=f"date:{code}")],
        [InlineKeyboardButton(text="🔥 Ближайшие рейсы", callback_data=f"nearest:{code}")],
        [InlineKeyboardButton(text="← Другое направление", callback_data="back")]
    ])

    await callback.message.edit_text(
        f"✅ Направление: <b>{dest['name']}</b>\n\nЧто смотрим?",
        reply_markup=kb
    )


@dp.callback_query(lambda c: c.data.startswith("date:"))
async def show_calendar(callback: types.CallbackQuery, state: FSMContext):
    _, code = callback.data.split(":")
    await state.update_data(destination=code)
    dest_name = DESTINATIONS[code]["name"]

    await callback.message.edit_text(
        f"📆 Выбери дату вылета в <b>{dest_name}</b>:",
        reply_markup=await SimpleCalendar(locale='ru').start_calendar()   # русский календарь
    )


@dp.callback_query(simple_cal_callback.filter())
async def process_date_selection(callback: types.CallbackQuery, callback_data: dict, state: FSMContext):
    selected, selected_date = await SimpleCalendar(locale='ru').process_selection(callback, callback_data)

    if not selected:
        return

    data = await state.get_data()
    dest_code = data["destination"]
    dest_name = DESTINATIONS[dest_code]["name"]

    await callback.message.edit_text(f"🔍 Ищу прямые рейсы на <b>{selected_date.strftime('%d %B %Y')}</b>...")

    flights = await get_direct_flights(dest_code, selected_date)
    text = format_flights(flights, dest_name, selected_date)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Другая дата", callback_data=f"date:{dest_code}")],
        [InlineKeyboardButton(text="🔥 Ближайшие рейсы", callback_data=f"nearest:{dest_code}")],
        [InlineKeyboardButton(text="← Города", callback_data="back")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)


@dp.callback_query(lambda c: c.data.startswith("nearest:"))
async def show_nearest(callback: types.CallbackQuery, state: FSMContext):
    _, code = callback.data.split(":")
    dest_name = DESTINATIONS[code]["name"]

    await callback.message.edit_text(f"🔍 Ищу ближайшие прямые рейсы в {dest_name}...")

    flights = await get_direct_flights(code)          # без даты = ближайшие
    text = format_flights(flights, dest_name)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Выбрать дату", callback_data=f"date:{code}")],
        [InlineKeyboardButton(text="← Другое направление", callback_data="back")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)


@dp.callback_query(lambda c: c.data == "back")
async def back_to_cities(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌴 Паттайя (UTP)", callback_data="utp")],
        [InlineKeyboardButton(text="🏙 Бангкок (BKK)", callback_data="bkk")]
    ])
    await callback.message.edit_text("Выбери направление:", reply_markup=kb)


async def main():
    logging.basicConfig(level=logging.INFO)
    print("🚀 Бот с календарем запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())