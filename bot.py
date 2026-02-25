import asyncio
import logging
import os
from datetime import datetime
from typing import List, Dict, Any

import requests
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AVIASALES_API_KEY = os.getenv(
    "AVIASALES_API_KEY", "6c48242837234d39f1e8320332f1f779"
)

# Коды городов / аэропортов
ORIGIN_CODE = "MOW"  # Москва (городской код)
DESTINATIONS = {
    "UTP": "Паттайя (аэропорт U-Tapao)",
    "BKK": "Бангкок (аэропорт Suvarnabhumi)",
}


def search_direct_flights(destination: str, departure_date: datetime.date) -> List[Dict[str, Any]]:
    """
    Поиск прямых перелётов через Aviasales API (Travelpayouts).
    Документация: prices_for_dates v3.
    """
    if not AVIASALES_API_KEY:
        logger.warning("AVIASALES_API_KEY is not set")
        return []

    url = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
    params = {
        "origin": ORIGIN_CODE,
        "destination": destination,
        "departure_at": departure_date.isoformat(),
        "direct": "true",
        "one_way": "true",
        "sorting": "price",
        "limit": 10,
        "token": AVIASALES_API_KEY,
        "currency": "rub",
        "locale": "ru",
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.error("Error calling Aviasales API: %s", e)
        return []

    flights = data.get("data") or data.get("tickets") or []
    if isinstance(flights, dict):
        flights = list(flights.values())
    return flights


def format_flights_message(
    flights: List[Dict[str, Any]], destination: str, departure_date: datetime.date
) -> str:
    if not flights:
        return (
            f"К сожалению, я не нашёл прямых перелётов из Москвы в {DESTINATIONS.get(destination, destination)} "
            f"на дату {departure_date.strftime('%d.%m.%Y')}."
        )

    lines = [
        f"Прямые рейсы из Москвы в {DESTINATIONS.get(destination, destination)}",
        f"Дата вылета: {departure_date.strftime('%d.%m.%Y')}",
        "",
    ]

    for i, f in enumerate(flights[:5], start=1):
        price = f.get("price") or f.get("value")
        airline = f.get("airline") or f.get("airline_iata") or "авиакомпания не указана"
        flight_number = f.get("flight_number") or ""

        depart_at = f.get("departure_at") or f.get("departure_time")
        return_at = f.get("return_at") or f.get("arrival_time")

        def fmt_time(value: Any) -> str:
            if not value:
                return "не указано"
            text = str(value)
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(text, fmt)
                    return dt.strftime("%d.%m %H:%M")
                except Exception:
                    continue
            return text

        depart_str = fmt_time(depart_at)
        arrive_str = fmt_time(return_at)

        line = f"{i}) {airline} {flight_number} — вылет {depart_str}, прилёт {arrive_str}"
        if price:
            line += f", цена от {price} ₽"
        lines.append(line)

    # Примерная deeplink-ссылка на Aviasales (без API, просто ссылка на поиск)
    date_str = departure_date.strftime("%Y%m%d")
    deeplink = f"https://www.aviasales.ru/search/{ORIGIN_CODE}{destination}{date_str}1"

    lines.append("")
    lines.append("Подробнее и покупка билетов:")
    lines.append(deeplink)

    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton("Паттайя", callback_data="dest_UTP"),
            InlineKeyboardButton("Бангкок", callback_data="dest_BKK"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "Привет! Я помогу найти *прямые* перелёты из Москвы:\n\n"
        "• в Паттайю\n"
        "• в Бангкок\n\n"
        "Выбери направление:"
    )

    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.reply_text(
            text, reply_markup=reply_markup, parse_mode="Markdown"
        )


async def handle_destination_choice(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("dest_"):
        return

    destination = data.split("_", maxsplit=1)[1]
    context.user_data["destination"] = destination

    human_name = DESTINATIONS.get(destination, destination)

    await query.message.reply_text(
        f"Напиши дату вылета в формате ГГГГ-ММ-ДД.\n\n"
        f"Например: `2026-03-10`\n\n"
        f"Направление: Москва → {human_name}",
        parse_mode="Markdown",
    )


async def handle_date_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "destination" not in context.user_data:
        # Пользователь пока не выбрал направление
        return

    destination = context.user_data["destination"]
    date_text = (update.message.text or "").strip()

    try:
        departure_date = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text(
            "Не получилось распознать дату 😔\n"
            "Пожалуйста, введи дату в формате ГГГГ-ММ-ДД, например: 2026-03-10"
        )
        return

    await update.message.reply_text("Ищу прямые рейсы, подожди пару секунд…")

    flights = await asyncio.to_thread(search_direct_flights, destination, departure_date)
    message = format_flights_message(flights, destination, departure_date)

    await update.message.reply_text(message)

    # Сбрасываем состояние, чтобы можно было начать поиск заново
    context.user_data.pop("destination", None)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Команды:\n"
        "/start — начать поиск\n"
        "/help — помощь\n\n"
        "Алгоритм работы:\n"
        "1) Нажми Паттайя или Бангкок\n"
        "2) Введи дату вылета в формате ГГГГ-ММ-ДД\n"
        "3) Получи список прямых рейсов 😉"
    )


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(handle_destination_choice, pattern=r"^dest_"))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date_message)
    )

    logger.info("Bot is starting (long polling)…")
    application.run_polling()


if __name__ == "__main__":
    main()

