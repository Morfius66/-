"""Entry point that runs the aiogram bot loop."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher

from ..db import init_db, make_engine, make_session_factory
from ..settings import Settings, load_settings
from .handlers import build_router

if TYPE_CHECKING:
    pass

log = logging.getLogger("xservis.bot")


async def run_bot(settings: Settings | None = None) -> None:
    """Start polling Telegram and never return until cancelled."""

    settings = settings or load_settings()
    if not settings.bot.token:
        msg = "bot.token is empty; set XSERVIS_BOT__TOKEN or fill config.yaml"
        raise RuntimeError(msg)

    engine = make_engine(settings.database.url)
    await init_db(engine)
    session_factory = make_session_factory(engine)

    bot = Bot(token=settings.bot.token)
    dp = Dispatcher()
    dp.include_router(build_router(settings, session_factory=session_factory))

    log.info("Starting Xservis bot (WEBAPP_URL will be used from env)")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
