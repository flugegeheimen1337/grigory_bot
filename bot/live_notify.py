from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import db as database
from bot.keyboards import main_keyboard

logger = logging.getLogger(__name__)


async def publish_live_state(bot: Bot, *, enabled: bool) -> None:
    url = (await database.get_setting("live_url")).strip()
    visible = enabled and bool(url)
    keyboard = main_keyboard(visible)
    if visible:
        announcement = (
            "Сейчас идёт эфир.\n"
            "В меню появилась кнопка «LIVE СЕЙЧАС», в каталоге действует LIVE-цена."
        )
        link = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="▶️ Смотреть трансляцию", url=url)]
            ]
        )
        follow_up = "Кнопка «LIVE СЕЙЧАС» внизу открывает трансляцию."
    else:
        announcement = (
            "Эфир завершён. Кнопка «LIVE СЕЙЧАС» скрыта, в каталоге снова обычные цены."
        )
        link = None
        follow_up = announcement
    for user_id in await database.audience_ids():
        try:
            if link is not None:
                await bot.send_message(user_id, announcement, reply_markup=link)
            await bot.send_message(user_id, follow_up, reply_markup=keyboard)
        except Exception:
            logger.exception("Не удалось обновить меню пользователя %s", user_id)
