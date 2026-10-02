# AUTO DEALER

Telegram Mini App: авторынок, осмотр, AI-торг, гараж, ремонт, уникальные номера и P2P-сделки.

## BotHost

- Python 3.11
- Dockerfile: включить
- Внутренний порт: 8000
- Главный файл: run.py
- `WEBAPP_URL` — HTTPS-домен BotHost

## Environment

Заполни `.env`/переменные BotHost по `.env.example`. Секреты в GitHub не загружай.

Минимум:

- `BOT_TOKEN`
- `WEBAPP_URL`
- `DATABASE_URL=sqlite+aiosqlite:///./auto_dealer.db`
- `PORT=8000`
- `ALLOW_DEMO_MODE=1`

Для большого рынка и фотографий:

- `APIFY_TOKEN`
- `AVITO_ACTOR_ID=getascraper~avito-auto-scraper`
- `AVITO_CITY_SLUG=kislovodsk`
- `AVITO_CITIES=kislovodsk,pyatigorsk,stavropol`
- `AVITO_MAX_ITEMS=100`
- `AVITO_MAX_PAGES=5`
- `AVITO_SYNC_MINUTES=30`

Для Gemini:

- `GEMINI_API_KEY`
- `GEMINI_MODEL=gemini-3.8-flash`

## Поведение без внешних ключей

Приложение стартует и показывает демонстрационные объявления, даже если Apify/Gemini ещё не настроены. Без Gemini используется резервный диалог, без внешнего источника — встроенный резервный рынок.

## Важное

Перед публичным запуском проверь права и условия использования внешнего источника данных и фотографий, а также отключи `ALLOW_DEMO_MODE` после тестирования.


## Final4 deployment
After redeploy, send /start in Telegram and open the newest button. Old Telegram messages may keep an older URL.
