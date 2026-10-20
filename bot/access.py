from __future__ import annotations

import logging

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, User
from aiogram.types import BotCommand, BotCommandScopeChat

from bot import config
from bot import db as database

logger = logging.getLogger(__name__)
_commands_ready: set[int] = set()

_CLIENT_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="cancel", description="Отменить текущее действие"),
]
_ADMIN_COMMANDS = [
    *_CLIENT_COMMANDS,
    BotCommand(command="admin", description="Админ-панель"),
]


async def is_admin(user: User) -> bool:
    username = (user.username or "").lower()
    allowed = user.id in config.admin_ids() or (
        bool(username) and username in config.admin_usernames()
    )
    if allowed:
        await database.remember_admin(user.id, user.username)
        return True
    return await database.is_admin_id(user.id)


async def claim_first_admin(user: User) -> bool:
    if await database.list_admin_ids():
        return False
    await database.remember_admin(user.id, user.username)
    logger.warning(
        "Первый админ сохранён по /admin: id=%s username=%s",
        user.id,
        user.username,
    )
    return True


def denial_text(user: User) -> str:
    who = f"@{user.username}" if user.username else "без username"
    names = ", ".join(f"@{name}" for name in sorted(config.admin_usernames()))
    return (
        "Нет доступа к админке.\n"
        f"Telegram видит этот аккаунт как {who}, id {user.id}.\n"
        f"В списке: {names}."
    )


async def ensure_admin_commands(bot: Bot, user: User) -> None:
    if user.id in _commands_ready:
        return
    if not await is_admin(user):
        return
    try:
        await bot.set_my_commands(
            _ADMIN_COMMANDS,
            scope=BotCommandScopeChat(chat_id=user.id),
        )
    except Exception:
        logger.exception("Не удалось задать команды админа")
        return
    _commands_ready.add(user.id)


class AdminGate(BaseMiddleware):
    async def __call__(self, handler, event, data):  # type: ignore[no-untyped-def]
        text = getattr(event, "text", None) or ""
        if text.startswith("/admin"):
            return await handler(event, data)
        user = getattr(event, "from_user", None)
        if user is None or not await is_admin(user):
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("Недостаточно прав", show_alert=True)
                except Exception:
                    logger.exception("Не удалось ответить на чужой callback")
            return None
        return await handler(event, data)
