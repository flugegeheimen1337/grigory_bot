from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.types import ChatMemberUpdated, Message

from bot import db as database
from bot.live_notify import publish_live_state

logger = logging.getLogger(__name__)
router = Router()

_BROADCAST_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL}
_PRESENT = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}
_ABSENT = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}


async def _remember_chat(chat_id: int, title: str) -> None:
    await database.set_setting("live_chat_id", str(chat_id))
    if title.strip():
        await database.set_setting("live_chat_title", title.strip())


async def _chat_is_watched(chat_id: int) -> bool:
    saved = (await database.get_setting("live_chat_id")).strip()
    if not saved:
        return True
    return saved == str(chat_id)


async def _tell_admins(bot, text: str) -> None:  # type: ignore[no-untyped-def]
    for admin_id in await database.list_admin_ids():
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            logger.exception("Не удалось сообщить админу %s о эфире", admin_id)


async def _apply(message: Message, *, enabled: bool) -> None:
    chat = message.chat
    if chat.type not in _BROADCAST_TYPES:
        return
    if not await _chat_is_watched(chat.id):
        logger.info("Эфир в другом чате %s, пропускаю", chat.id)
        return
    await _remember_chat(chat.id, chat.title or "")
    url = (await database.get_setting("live_url")).strip()
    if enabled and not url and chat.username:
        await database.set_setting("live_url", f"https://t.me/{chat.username}")
    was = await database.live_enabled()
    if was == enabled:
        return
    await database.set_setting("live_enabled", "1" if enabled else "0")
    logger.info(
        "Эфир %s в чате %s (%s)",
        "начался" if enabled else "закончился",
        chat.id,
        chat.title or "",
    )
    if enabled and not (await database.get_setting("live_url")).strip():
        await _tell_admins(
            message.bot,
            "В канале начался эфир, но ссылка для клиентов не задана. "
            "Откройте /admin и пришлите ссылку на канал.",
        )
        return
    await publish_live_state(message.bot, enabled=enabled)


@router.message(F.video_chat_started)
@router.channel_post(F.video_chat_started)
async def stream_started(message: Message) -> None:
    await _apply(message, enabled=True)


@router.message(F.video_chat_ended)
@router.channel_post(F.video_chat_ended)
async def stream_ended(message: Message) -> None:
    await _apply(message, enabled=False)


@router.my_chat_member()
async def bot_membership(event: ChatMemberUpdated) -> None:
    chat = event.chat
    if chat.type not in _BROADCAST_TYPES:
        return
    status = event.new_chat_member.status
    saved = (await database.get_setting("live_chat_id")).strip()
    if status in _PRESENT:
        await _remember_chat(chat.id, chat.title or "")
        title = chat.title or "канал"
        logger.info("Бот подключён к чату эфира %s (%s)", chat.id, title)
        await _tell_admins(
            event.bot,
            f"Бот подключён к каналу «{title}». "
            "Кнопка «LIVE СЕЙЧАС» появится у клиентов, когда там начнётся эфир, "
            "и исчезнет, когда эфир закончится.",
        )
        return
    if status in _ABSENT and saved == str(chat.id):
        await database.set_setting("live_chat_id", "")
        await database.set_setting("live_chat_title", "")
        logger.info("Бот удалён из чата эфира %s", chat.id)
        if await database.live_enabled():
            await database.set_setting("live_enabled", "0")
            await publish_live_state(event.bot, enabled=False)
