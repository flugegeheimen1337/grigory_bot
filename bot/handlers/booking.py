from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import db as database
from bot.filters import NotCommand
from bot.formatters import (
    booking_summary,
    format_price,
    new_order_notification,
    normalize_company,
    normalize_phone,
    parse_amount,
    unit_price,
)
from bot.handlers.ui import NO_PREVIEW
from bot.keyboards import booking_cancel_kb, client_keyboard, confirm_kb
from bot.routing import private_router
from bot.states import Booking

logger = logging.getLogger(__name__)
router = private_router()
_confirm_locks: dict[int, asyncio.Lock] = {}


def _confirm_lock(user_id: int) -> asyncio.Lock:
    lock = _confirm_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _confirm_locks[user_id] = lock
    return lock


async def start_booking(message: Message, state: FSMContext, product: dict) -> None:
    live = await database.live_enabled()
    price = unit_price(product, live)
    mode = "LIVE-цена" if live else "Цена"
    await state.set_state(Booking.name)
    await state.set_data({"product_id": int(product["id"])})
    await message.answer(
        f"Бронь: {product['name']}\n"
        f"{mode}: {format_price(price)}\n\n"
        "Шаг 1 из 4. Как к вам обращаться?",
        reply_markup=booking_cancel_kb(),
    )


@router.message(Booking.name, F.text, NotCommand())
async def booking_name(message: Message, state: FSMContext) -> None:
    name = " ".join((message.text or "").split())
    if len(name) < 2 or len(name) > 100:
        await message.answer("Имя: от 2 до 100 символов.", reply_markup=booking_cancel_kb())
        return
    await state.update_data(client_name=name)
    await state.set_state(Booking.phone)
    await message.answer(
        "Шаг 2 из 4. Телефон для связи.\nНапример: +7 999 123-45-67",
        reply_markup=booking_cancel_kb(),
    )


@router.message(Booking.name, NotCommand())
async def booking_name_invalid(message: Message) -> None:
    await message.answer("Пришлите имя текстом.", reply_markup=booking_cancel_kb())


@router.message(Booking.phone, F.text, NotCommand())
async def booking_phone(message: Message, state: FSMContext) -> None:
    phone = normalize_phone(message.text or "")
    if phone is None:
        await message.answer(
            "Не похоже на телефон. Пришлите номер ещё раз.",
            reply_markup=booking_cancel_kb(),
        )
        return
    await state.update_data(phone=phone)
    await state.set_state(Booking.company)
    await message.answer(
        "Шаг 3 из 4. Компания.\nЕсли покупаете как частное лицо — отправьте «-».",
        reply_markup=booking_cancel_kb(),
    )


@router.message(Booking.phone, NotCommand())
async def booking_phone_invalid(message: Message) -> None:
    await message.answer("Пришлите телефон текстом.", reply_markup=booking_cancel_kb())


@router.message(Booking.company, F.text, NotCommand())
async def booking_company(message: Message, state: FSMContext) -> None:
    company = normalize_company(message.text or "")
    if company is None:
        await message.answer(
            "Название компании слишком длинное или пустое. "
            "Если покупаете как частное лицо — отправьте «-».",
            reply_markup=booking_cancel_kb(),
        )
        return
    await state.update_data(company=company)
    await state.set_state(Booking.meters)
    await message.answer(
        "Шаг 4 из 4. Сколько метров нужно?",
        reply_markup=booking_cancel_kb(),
    )


@router.message(Booking.company, NotCommand())
async def booking_company_invalid(message: Message) -> None:
    await message.answer("Пришлите название компании текстом.", reply_markup=booking_cancel_kb())


@router.message(Booking.meters, F.text, NotCommand())
async def booking_meters(message: Message, state: FSMContext) -> None:
    meters = parse_amount(message.text or "", minimum=0.01, maximum=100_000)
    if meters is None:
        await message.answer(
            "Сколько метров? Например: 15 или 12,5",
            reply_markup=booking_cancel_kb(),
        )
        return
    data = await state.get_data()
    product = await database.get_product(int(data["product_id"]))
    if not product or not product["is_active"]:
        await state.clear()
        await message.answer(
            "Этот товар уже недоступен. Откройте каталог ещё раз.",
            reply_markup=await client_keyboard(),
        )
        return
    live = await database.live_enabled()
    snapshot = {
        "product_id": int(product["id"]),
        "product_name": product["name"],
        "unit_price": unit_price(product, live),
        "is_live": live,
        "client_name": data["client_name"],
        "phone": data["phone"],
        "company": data["company"],
        "meters": meters,
    }
    await state.set_state(Booking.confirm)
    await state.set_data(snapshot)
    await message.answer(
        booking_summary(snapshot),
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_kb(),
    )


@router.message(Booking.meters, NotCommand())
async def booking_meters_invalid(message: Message) -> None:
    await message.answer("Пришлите метраж числом.", reply_markup=booking_cancel_kb())


@router.callback_query(F.data == "b:no")
async def cancel_booking(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is not None:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        await callback.message.answer("Бронь отменена.", reply_markup=await client_keyboard())
    await callback.answer("Бронь отменена")


@router.callback_query(F.data == "b:ok")
async def confirm_booking(callback: CallbackQuery, state: FSMContext) -> None:
    user = callback.from_user
    if user is None or callback.message is None:
        await callback.answer()
        return
    async with _confirm_lock(user.id):
        if await state.get_state() != Booking.confirm.state:
            await callback.answer("Заявка уже отправлена или отменена", show_alert=True)
            return
        data = await state.get_data()
        required = (
            "product_id",
            "product_name",
            "unit_price",
            "is_live",
            "client_name",
            "phone",
            "company",
            "meters",
        )
        if any(key not in data for key in required):
            await state.clear()
            await callback.answer("Данные заявки потеряны. Начните бронь заново", show_alert=True)
            return
        await state.clear()
        try:
            order_id = await database.create_order(
                user_id=user.id,
                username=user.username,
                client_name=str(data["client_name"]),
                phone=str(data["phone"]),
                company=str(data["company"]),
                product_id=int(data["product_id"]),
                product_name=str(data["product_name"]),
                meters=float(data["meters"]),
                unit_price=float(data["unit_price"]),
                is_live=bool(data["is_live"]),
            )
        except Exception:
            logger.exception("Не удалось сохранить заявку")
            await state.set_state(Booking.confirm)
            await state.set_data(data)
            await callback.answer("Не удалось сохранить заявку. Нажмите ещё раз", show_alert=True)
            return
    order = await database.get_order(order_id)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.answer("Заявка принята")
    await callback.message.answer(
        "Заявка принята! Менеджер свяжется с вами.",
        reply_markup=await client_keyboard(),
    )
    if order is not None:
        await notify_admins(callback.bot, order)


async def notify_admins(bot: Bot, order: dict) -> None:
    text = new_order_notification(order)
    username = (order.get("username") or "").strip()
    keyboard = None
    if username:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Написать клиенту", url=f"https://t.me/{username}")]
            ]
        )
    for admin_id in await database.list_admin_ids():
        try:
            await bot.send_message(
                admin_id,
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                link_preview_options=NO_PREVIEW,
            )
        except Exception:
            logger.exception("Не удалось отправить заявку админу %s", admin_id)
