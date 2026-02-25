# Telegram бот: прямые рейсы Москва → Паттайя / Бангкок

Простой бот для поиска **прямых** перелётов из Москвы в Паттайю или Бангкок с использованием Aviasales API.

Используется:
- `python-telegram-bot`
- Aviasales / Travelpayouts API (`prices_for_dates` v3)
- Railway для деплоя

## Переменные окружения

Обязательно задайте в Railway / локально:

- `TELEGRAM_BOT_TOKEN` — токен вашего Telegram‑бота от `@BotFather`
- `AVIASALES_API_KEY` — ключ Aviasales (если не задан, используется ключ, который вы передали в задаче)

## Локальный запуск

```bash
pip install -r requirements.txt
set TELEGRAM_BOT_TOKEN=ВАШ_ТОКЕН   # для Windows PowerShell можно: $env:TELEGRAM_BOT_TOKEN="..."
set AVIASALES_API_KEY=ВАШ_API_КЛЮЧ
python bot.py
```

## Деплой на Railway

1. Залейте этот проект в GitHub.
2. В Railway:
   - Создайте новый проект → Deploy from GitHub.
   - Выберите репозиторий с ботом.
3. В разделе **Variables** добавьте:
   - `TELEGRAM_BOT_TOKEN`
   - `AVIASALES_API_KEY` (опционально, если хотите переопределить ключ)
4. Команду запуска можно оставить по умолчанию или указать:

```bash
python bot.py
```

`Procfile` уже содержит строку:

```text
worker: python bot.py
```

Railway может использовать её как процесс‑тип **worker**.

После деплоя бот начнёт работать через long polling.

