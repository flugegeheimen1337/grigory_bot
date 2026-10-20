from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, ErrorEvent

from bot import config
from bot import db as database
from bot.handlers import admin, booking, catalog, fallback, menu

logger = logging.getLogger(__name__)


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(menu.router)
    dispatcher.include_router(catalog.router)
    dispatcher.include_router(booking.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(fallback.router)

    @dispatcher.error()
    async def on_error(event: ErrorEvent) -> None:
        logger.exception("Ошибка обработки обновления: %s", event.exception)
        update = event.update
        if update.callback_query:
            try:
                await update.callback_query.answer(
                    "Не получилось выполнить действие",
                    show_alert=True,
                )
            except Exception:
                logger.debug("Callback уже закрыт", exc_info=True)
        target = update.message
        if target is None and update.callback_query and update.callback_query.message:
            target = update.callback_query.message
        if target is not None and hasattr(target, "answer"):
            try:
                await target.answer("Произошла ошибка. Попробуйте ещё раз или отправьте /start.")
            except Exception:
                logger.debug("Не удалось сообщить об ошибке", exc_info=True)

    return dispatcher


async def configure_bot(bot: Bot) -> None:
    me = await bot.get_me()
    logger.info("Бот запущен: @%s", me.username)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="cancel", description="Отменить текущее действие"),
        ]
    )
    try:
        await bot.set_my_short_description("VIP Camilla: каталог тканей и заявки на бронь")
        await bot.set_my_description(
            "Каталог тканей VIP Camilla: фото, цены и остатки. "
            "Во время эфира действует LIVE-цена, заявку на бронь можно оставить прямо в боте."
        )
    except Exception:
        logger.exception("Не удалось обновить описание бота")


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config.load_dotenv()
    await database.connect(config.database_path())
    bot = Bot(token=config.bot_token())
    dispatcher = build_dispatcher()
    try:
        await configure_bot(bot)
        await dispatcher.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await database.close()
        await bot.session.close()


def main() -> None:
    asyncio.run(run())
