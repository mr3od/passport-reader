from __future__ import annotations

import logging

from dotenv import load_dotenv

from passport_telegram.bot import build_application, telegram_error_handler
from passport_telegram.config import TelegramSettings


def main() -> int:
    load_dotenv()
    settings = TelegramSettings()
    load_dotenv(settings.core_env_file, override=False)

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    application = build_application(settings)
    application.add_error_handler(telegram_error_handler)
    services = application.bot_data["services"]

    try:
        application.run_polling(drop_pending_updates=True)
    finally:
        services.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
