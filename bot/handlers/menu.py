from __future__ import annotations

import logging
import re

from aiogram import F
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import db as database
from bot.access import ensure_admin_commands, is_admin
from bot.formatters import HELP_TEXT, esc, welcome_text
from bot.handlers.catalog import show_catalog
from bot.keyboards import BTN_CATALOG, BTN_HELP, BTN_LIVE, BTN_MANAGER, MENU_TEXTS, main_keyboard
from bot.routing import private_router

logger = logging.getLogger(__name__)
router = private_router()


@router.message(CommandStart())
@router.message(Command("menu"))
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user:
        logger.info(
            "Команда /start: id=%s username=%s",
            message.from_user.id,
            message.from_user.username,
        )
        await ensure_admin_commands(message.bot, message.from_user)
    live = await database.live_enabled()
    await message.answer(
        welcome_text(live),
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    text = "Действие отменено."
    if message.from_user and await is_admin(message.from_user):
        text += "\nАдмин-панель: /admin"
    await message.answer(text, reply_markup=main_keyboard())


@router.message(F.text.in_(MENU_TEXTS))
async def on_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.text == BTN_LIVE:
        await send_live(message)
    elif message.text == BTN_CATALOG:
        await show_catalog(message)
    elif message.text == BTN_MANAGER:
        await send_manager(message)
    elif message.text == BTN_HELP:
        await message.answer(HELP_TEXT, parse_mode=ParseMode.HTML, reply_markup=main_keyboard())


async def send_live(message: Message) -> None:
    enabled = await database.live_enabled()
    url = (await database.get_setting("live_url")).strip()
    if not enabled:
        await message.answer(
            "Сейчас эфир не идёт.\n"
            "В каталоге обычные цены. Когда включим LIVE, здесь появится ссылка на трансляцию.",
            reply_markup=main_keyboard(),
        )
        return
    text = (
        "Сейчас идёт эфир.\n"
        "В каталоге действует LIVE-цена — откройте «КАТАЛОГ» и забронируйте ткань."
    )
    if not url:
        await message.answer(
            "Эфир отмечен как идущий, но ссылка ещё не задана. Напишите менеджеру.",
            reply_markup=main_keyboard(),
        )
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="▶️ Смотреть трансляцию", url=url)]]
    )
    try:
        await message.answer(text, reply_markup=keyboard)
    except TelegramBadRequest:
        logger.exception("Telegram не принял ссылку эфира")
        await message.answer(f"{text}\n\n{url}", reply_markup=main_keyboard())


async def send_manager(message: Message) -> None:
    name = await database.get_setting("manager_name", "Менеджер") or "Менеджер"
    username = (await database.get_setting("manager_username")).strip().lstrip("@")
    phone = (await database.get_setting("manager_phone")).strip()
    lines = ["<b>Ваш менеджер</b>", esc(name)]
    if phone:
        tel = re.sub(r"[^\d+]", "", phone)
        lines.append(f'Телефон: <a href="tel:{esc(tel)}">{esc(phone)}</a>')
    lines.append("Напишите или позвоните — подскажем по ткани и брони.")
    keyboard = None
    if username:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Написать в Telegram", url=f"https://t.me/{username}")]
            ]
        )
    await message.answer(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )
