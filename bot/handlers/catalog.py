from __future__ import annotations

from aiogram import F
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import db as database
from bot.formatters import EMPTY_CATALOG, catalog_header, paginate, product_text
from bot.handlers.booking import start_booking
from bot.handlers.ui import send_product_message
from bot.keyboards import catalog_kb, main_keyboard, product_kb
from bot.routing import private_router

router = private_router()
CATALOG_PAGE = 6


async def show_catalog(message: Message, page: int = 0, *, edit: bool = False) -> None:
    products = await database.list_products(include_hidden=False)
    live = await database.live_enabled()
    if not products:
        if edit:
            from bot.handlers.ui import safe_edit

            await safe_edit(message, EMPTY_CATALOG, None)
        else:
            await message.answer(EMPTY_CATALOG, reply_markup=main_keyboard())
        return
    chunk, page, total_pages = paginate(products, page, CATALOG_PAGE)
    text = catalog_header(live, page, total_pages)
    keyboard = catalog_kb(chunk, page, total_pages, live)
    if edit:
        from bot.handlers.ui import safe_edit

        await safe_edit(message, text, keyboard)
        return
    await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


@router.callback_query(F.data.regexp(r"^cat:\d+$"))
async def on_page(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    page = int(callback.data.split(":")[1])
    await show_catalog(callback.message, page, edit=True)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^prd:\d+$"))
async def open_product(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    product_id = int(callback.data.split(":")[1])
    product = await database.get_product(product_id)
    if not product or not product["is_active"]:
        await callback.answer("Товар недоступен", show_alert=True)
        return
    live = await database.live_enabled()
    await send_product_message(
        callback.message,
        product,
        product_text(product, live=live),
        product_kb(product_id),
    )
    await callback.answer()


@router.callback_query(F.data == "cls")
async def close_card(callback: CallbackQuery) -> None:
    if callback.message is not None:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
    await callback.answer()


@router.callback_query(F.data.regexp(r"^rsv:\d+$"))
async def reserve(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    product_id = int(callback.data.split(":")[1])
    product = await database.get_product(product_id)
    if not product or not product["is_active"]:
        await callback.answer("Этого товара уже нет в каталоге", show_alert=True)
        return
    await start_booking(callback.message, state, product)
    await callback.answer()
