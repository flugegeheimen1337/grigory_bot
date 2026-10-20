from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards import client_keyboard
from bot.routing import private_router

router = private_router()


@router.message()
async def fallback(message: Message, state: FSMContext) -> None:
    text = message.text or ""
    if text.startswith("/"):
        await message.answer("Неизвестная команда. Меню — /start, отмена — /cancel.")
        return
    if await state.get_state():
        return
    await message.answer("Выберите раздел в меню ниже.", reply_markup=await client_keyboard())
