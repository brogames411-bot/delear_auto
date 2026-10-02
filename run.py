import asyncio
import logging
import os

import uvicorn
from dotenv import load_dotenv

from backend.main import app
from bot.bot import make_bot, dp
from backend.database import init_db

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log = logging.getLogger("auto_dealer")

async def bot_loop() -> None:
    while True:
        bot = None
        try:
            bot = make_bot()
            try:
                await bot.delete_webhook(drop_pending_updates=False)
            except Exception:
                log.exception("Не удалось удалить webhook")
            log.info("Telegram-бот запущен")
            await dp.start_polling(bot, handle_signals=False, allowed_updates=dp.resolve_used_update_types())
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Telegram-бот остановился; повтор через 5 секунд")
            await asyncio.sleep(5)
        finally:
            if bot:
                try:
                    await bot.session.close()
                except Exception:
                    pass

async def main() -> None:
    await init_db()
    port = int(os.getenv("PORT", "8000"))
    log.info("HTTP сервер запускается на порту %s", port)
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info", proxy_headers=True, forwarded_allow_ips="*"))
    task = asyncio.create_task(bot_loop(), name="telegram-bot")
    try:
        await server.serve()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

if __name__ == "__main__":
    asyncio.run(main())
