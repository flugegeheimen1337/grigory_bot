from __future__ import annotations

import logging

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, LinkPreviewOptions, Message

logger = logging.getLogger(__name__)

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def extract_image(message: Message) -> tuple[str, str] | None:
    if message.photo:
        return message.photo[-1].file_id, "photo"
    document = message.document
    mime = (document.mime_type if document else "") or ""
    if document and mime.startswith("image/"):
        return document.file_id, "document"
    return None


async def safe_edit(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            link_preview_options=NO_PREVIEW,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        try:
            await message.answer(
                text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
                link_preview_options=NO_PREVIEW,
            )
        except Exception:
            logger.exception("Не удалось показать сообщение заново")
    except Exception:
        logger.exception("Не удалось изменить сообщение")


async def send_product_message(
    message: Message,
    product: dict,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    file_id = product.get("photo_file_id")
    kind = product.get("photo_kind") or "photo"
    if not file_id:
        await message.answer(
            caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            link_preview_options=NO_PREVIEW,
        )
        return
    if len(caption) > 1024:
        if kind == "document":
            await message.answer_document(file_id)
        else:
            await message.answer_photo(file_id)
        await message.answer(
            caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
            link_preview_options=NO_PREVIEW,
        )
        return
    if kind == "document":
        await message.answer_document(
            file_id,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
        return
    await message.answer_photo(
        file_id,
        caption=caption,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )
