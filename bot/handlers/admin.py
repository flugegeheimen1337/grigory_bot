from __future__ import annotations

import logging

from aiogram import F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import db as database
from bot.access import AdminGate, claim_first_admin, denial_text, ensure_admin_commands, is_admin
from bot.filters import NotCommand
from bot.formatters import (
    clamp_page,
    esc,
    live_admin_text,
    order_admin_text,
    pages,
    parse_amount,
    parse_url,
    product_admin_text,
    product_text,
    valid_username,
    normalize_phone,
)
from bot.handlers.ui import NO_PREVIEW, extract_image, safe_edit, send_product_message
from bot.live_notify import publish_live_state
from bot.keyboards import (
    admin_menu_kb,
    cancel_inline,
    live_admin_kb,
    nav_row,
    product_admin_kb,
    product_list_label,
)
from bot.routing import private_router
from bot.states import AddProduct, EditManager, EditProduct, SetLiveUrl

logger = logging.getLogger(__name__)
router = private_router()
router.message.middleware(AdminGate())
router.callback_query.middleware(AdminGate())

ADMIN_PAGE = 8
ORDER_PAGE = 4
_EDIT_FIELDS = {"name", "desc", "price", "live", "stock", "photo"}


async def show_admin_home(message: Message, *, edit: bool) -> None:
    live = await database.live_enabled()
    products = await database.list_products(include_hidden=True)
    active = sum(1 for product in products if product["is_active"])
    orders = await database.count_orders()
    url = await database.get_setting("live_url")
    text = (
        "<b>Админ-панель</b>\n\n"
        f"{live_admin_text(live, url)}\n\n"
        f"Товаров в каталоге: {active}\n"
        f"Заявок: {orders}\n\n"
        "Клиентское меню — /start."
    )
    keyboard = admin_menu_kb(live)
    if edit:
        await safe_edit(message, text, keyboard)
        return
    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
        link_preview_options=NO_PREVIEW,
    )


async def show_live_screen(message: Message, *, edit: bool) -> None:
    enabled = await database.live_enabled()
    url = await database.get_setting("live_url")
    text = live_admin_text(enabled, url)
    keyboard = live_admin_kb(enabled)
    if edit:
        await safe_edit(message, text, keyboard)
        return
    await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


async def show_product_admin(message: Message, product: dict, *, edit: bool) -> None:
    text = product_admin_text(product)
    keyboard = product_admin_kb(product)
    if edit:
        await safe_edit(message, text, keyboard)
        return
    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
        link_preview_options=NO_PREVIEW,
    )


async def show_product_list(message: Message, page: int, *, edit: bool) -> None:
    products = await database.list_products(include_hidden=True)
    if not products:
        text = "<b>Товары</b>\n\nСписок пуст."
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить товар", callback_data="m:add")],
                [InlineKeyboardButton(text="⬅️ В админку", callback_data="m:adm")],
            ]
        )
    else:
        from bot.formatters import paginate

        chunk, page, total_pages = paginate(products, page, ADMIN_PAGE)
        lines = ["<b>Товары</b>", "Нажмите, чтобы изменить."]
        if total_pages > 1:
            lines.append(f"Страница {page + 1} из {total_pages}.")
        text = "\n".join(lines)
        rows = [
            [
                InlineKeyboardButton(
                    text=product_list_label(product),
                    callback_data=f"m:item:{product['id']}",
                )
            ]
            for product in chunk
        ]
        navigation = nav_row(page, total_pages, "m:list")
        if navigation:
            rows.append(navigation)
        rows.append([InlineKeyboardButton(text="⬅️ В админку", callback_data="m:adm")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    if edit:
        await safe_edit(message, text, keyboard)
        return
    await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


async def show_orders(message: Message, page: int, *, edit: bool) -> None:
    total = await database.count_orders()
    total_pages = pages(total, ORDER_PAGE)
    page = clamp_page(page, total_pages)
    if total == 0:
        text = (
            "<b>Заявки</b>\n\n"
            "Пока пусто. Новые брони придут сюда и в личные сообщения админов."
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⬅️ В админку", callback_data="m:adm")]]
        )
    else:
        orders = await database.list_orders(page * ORDER_PAGE, ORDER_PAGE)
        header = (
            f"<b>Заявки</b>\n"
            f"Новые сверху. Страница {page + 1} из {total_pages}. Всего: {total}."
        )
        text = header + "\n\n" + "\n\n".join(order_admin_text(order) for order in orders)
        rows: list[list[InlineKeyboardButton]] = []
        for order in orders:
            username = (order.get("username") or "").strip()
            if not username:
                continue
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"Написать: {str(order['client_name'])[:24]}",
                        url=f"https://t.me/{username}",
                    )
                ]
            )
        navigation = nav_row(page, total_pages, "m:orders")
        if navigation:
            rows.append(navigation)
        rows.append([InlineKeyboardButton(text="⬅️ В админку", callback_data="m:adm")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    if edit:
        await safe_edit(message, text, keyboard)
        return
    await message.answer(
        text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
        link_preview_options=NO_PREVIEW,
    )


async def show_manager_admin(message: Message, *, edit: bool) -> None:
    name = await database.get_setting("manager_name", "Менеджер")
    username = await database.get_setting("manager_username")
    phone = await database.get_setting("manager_phone")
    lines = [
        "<b>Контакт менеджера</b>",
        "",
        "Его видят клиенты по кнопке «МОЙ МЕНЕДЖЕР».",
        "",
        f"Имя: {esc(name) if name else '—'}",
        f"Telegram: @{esc(username)}" if username else "Telegram: не указан",
        f"Телефон: {esc(phone)}" if phone else "Телефон: не указан",
    ]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Изменить имя", callback_data="m:mgr:name")],
            [InlineKeyboardButton(text="Изменить Telegram", callback_data="m:mgr:username")],
            [InlineKeyboardButton(text="Изменить телефон", callback_data="m:mgr:phone")],
            [InlineKeyboardButton(text="⬅️ В админку", callback_data="m:adm")],
        ]
    )
    text = "\n".join(lines)
    if edit:
        await safe_edit(message, text, keyboard)
        return
    await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


def edit_prompt(product: dict, field: str) -> str:
    if field == "name":
        return f"Текущее название: {product['name']}\n\nПришлите новое название."
    if field == "desc":
        current = product.get("description") or "—"
        return (
            f"Текущие характеристики:\n{current[:800]}\n\n"
            "Пришлите новый текст или «-», чтобы очистить."
        )
    if field == "price":
        from bot.formatters import format_price

        return (
            f"Текущая цена: {format_price(float(product['price']))}\n\n"
            "Пришлите обычную цену за метр."
        )
    if field == "live":
        from bot.formatters import format_price

        return (
            f"Текущая LIVE-цена: {format_price(float(product['live_price']))}\n\n"
            "Пришлите LIVE-цену за метр."
        )
    if field == "stock":
        from bot.formatters import format_meters

        return (
            f"Текущий остаток: {format_meters(float(product['stock_m']))}\n\n"
            "Пришлите остаток в метрах. Можно 0."
        )
    return "Пришлите новое фото ткани."


async def _saved_product(message: Message, state: FSMContext, product_id: int) -> None:
    await state.clear()
    product = await database.get_product(product_id)
    await message.answer("Сохранено.")
    if product:
        await show_product_admin(message, product, edit=False)


@router.message(Command("admin"))
async def open_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = message.from_user
    if user is None:
        return
    logger.info("Команда /admin: id=%s username=%s", user.id, user.username)
    if not await is_admin(user) and not await claim_first_admin(user):
        await message.answer(denial_text(user))
        return
    await ensure_admin_commands(message.bot, user)
    await show_admin_home(message, edit=False)


@router.callback_query(F.data == "m:adm")
async def admin_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is None:
        await callback.answer()
        return
    await show_admin_home(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "m:add")
async def add_begin(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddProduct.photo)
    await state.set_data({})
    if callback.message is not None:
        await callback.message.answer(
            "Новый товар. Шаг 1 из 6.\nПришлите фото ткани.",
            reply_markup=cancel_inline(),
        )
    await callback.answer()


@router.message(AddProduct.photo, F.photo | F.document)
async def add_photo(message: Message, state: FSMContext) -> None:
    image = extract_image(message)
    if image is None:
        await message.answer(
            "Нужно именно фото. Пришлите изображение ткани.",
            reply_markup=cancel_inline(),
        )
        return
    file_id, kind = image
    await state.update_data(photo_file_id=file_id, photo_kind=kind)
    await state.set_state(AddProduct.name)
    await message.answer("Шаг 2 из 6.\nНазвание ткани.", reply_markup=cancel_inline())


@router.message(AddProduct.photo, NotCommand())
async def add_photo_invalid(message: Message) -> None:
    await message.answer("Пришлите фото ткани.", reply_markup=cancel_inline())


@router.message(AddProduct.name, F.text, NotCommand())
async def add_name(message: Message, state: FSMContext) -> None:
    name = " ".join((message.text or "").split())
    if len(name) < 2 or len(name) > 120:
        await message.answer("Название: от 2 до 120 символов.", reply_markup=cancel_inline())
        return
    await state.update_data(name=name)
    await state.set_state(AddProduct.description)
    await message.answer(
        "Шаг 3 из 6.\n"
        "Характеристики: состав, ширина, плотность, цвет.\n"
        "Можно несколькими строками. Если пока нечего указать — отправьте «-».",
        reply_markup=cancel_inline(),
    )


@router.message(AddProduct.name, NotCommand())
async def add_name_invalid(message: Message) -> None:
    await message.answer("Пришлите название текстом.", reply_markup=cancel_inline())


@router.message(AddProduct.description, F.text, NotCommand())
async def add_description(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text == "-":
        text = ""
    if len(text) > 1500:
        await message.answer("Слишком длинно. До 1500 символов.", reply_markup=cancel_inline())
        return
    await state.update_data(description=text)
    await state.set_state(AddProduct.price)
    await message.answer(
        "Шаг 4 из 6.\nОбычная цена за метр, в рублях.\nНапример: 1200 или 1 200,50",
        reply_markup=cancel_inline(),
    )


@router.message(AddProduct.description, NotCommand())
async def add_description_invalid(message: Message) -> None:
    await message.answer("Пришлите характеристики текстом.", reply_markup=cancel_inline())


@router.message(AddProduct.price, F.text, NotCommand())
async def add_price(message: Message, state: FSMContext) -> None:
    price = parse_amount(message.text or "", minimum=0.01, maximum=10_000_000)
    if price is None:
        await message.answer("Нужна цена больше нуля. Например: 1200", reply_markup=cancel_inline())
        return
    await state.update_data(price=price)
    await state.set_state(AddProduct.live_price)
    await message.answer(
        "Шаг 5 из 6.\n"
        "LIVE-цена за метр — её увидят во время эфира.\n"
        "Если скидки нет, укажите ту же цену.",
        reply_markup=cancel_inline(),
    )


@router.message(AddProduct.price, NotCommand())
async def add_price_invalid(message: Message) -> None:
    await message.answer("Пришлите цену числом.", reply_markup=cancel_inline())


@router.message(AddProduct.live_price, F.text, NotCommand())
async def add_live_price(message: Message, state: FSMContext) -> None:
    live_price = parse_amount(message.text or "", minimum=0.01, maximum=10_000_000)
    if live_price is None:
        await message.answer(
            "Нужна LIVE-цена больше нуля. Например: 990",
            reply_markup=cancel_inline(),
        )
        return
    await state.update_data(live_price=live_price)
    await state.set_state(AddProduct.stock)
    await message.answer(
        "Шаг 6 из 6.\nОстаток в метрах. Если пока неизвестен — 0.",
        reply_markup=cancel_inline(),
    )


@router.message(AddProduct.live_price, NotCommand())
async def add_live_price_invalid(message: Message) -> None:
    await message.answer("Пришлите LIVE-цену числом.", reply_markup=cancel_inline())


@router.message(AddProduct.stock, F.text, NotCommand())
async def add_stock(message: Message, state: FSMContext) -> None:
    stock = parse_amount(message.text or "", minimum=0, maximum=10_000_000)
    if stock is None:
        await message.answer("Остаток: число от 0. Например: 40", reply_markup=cancel_inline())
        return
    data = await state.get_data()
    product_id = await database.add_product(
        name=str(data["name"]),
        description=str(data.get("description") or ""),
        price=float(data["price"]),
        live_price=float(data["live_price"]),
        stock_m=stock,
        photo_file_id=data.get("photo_file_id"),
        photo_kind=str(data.get("photo_kind") or "photo"),
    )
    await state.clear()
    product = await database.get_product(product_id)
    live = await database.live_enabled()
    if product:
        await send_product_message(message, product, product_text(product, live=live))
    await message.answer("Товар добавлен в каталог.", reply_markup=admin_menu_kb(live))


@router.message(AddProduct.stock, NotCommand())
async def add_stock_invalid(message: Message) -> None:
    await message.answer("Пришлите остаток числом.", reply_markup=cancel_inline())


@router.callback_query(F.data.regexp(r"^m:list:\d+$"))
async def product_list(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is None:
        await callback.answer()
        return
    page = int(callback.data.split(":")[2])
    await show_product_list(callback.message, page, edit=True)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^m:item:\d+$"))
async def open_admin_product(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is None:
        await callback.answer()
        return
    product = await database.get_product(int(callback.data.split(":")[2]))
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    await show_product_admin(callback.message, product, edit=True)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^m:edit:\d+:(name|desc|price|live|stock|photo)$"))
async def begin_edit(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, raw_id, field = callback.data.split(":")
    if field not in _EDIT_FIELDS:
        await callback.answer("Нельзя изменить это поле", show_alert=True)
        return
    product = await database.get_product(int(raw_id))
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    await state.set_state(EditProduct.value)
    await state.set_data({"product_id": int(product["id"]), "field": field})
    if callback.message is not None:
        await callback.message.answer(edit_prompt(product, field), reply_markup=cancel_inline())
    await callback.answer()


@router.message(EditProduct.value, F.photo | F.document)
async def edit_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("field") != "photo":
        await message.answer("Сейчас жду текст.", reply_markup=cancel_inline())
        return
    image = extract_image(message)
    if image is None:
        await message.answer("Пришлите изображение.", reply_markup=cancel_inline())
        return
    product = await database.get_product(int(data["product_id"]))
    if not product:
        await state.clear()
        await message.answer("Товар уже удалён.", reply_markup=admin_menu_kb(await database.live_enabled()))
        return
    file_id, kind = image
    await database.update_product(int(product["id"]), photo_file_id=file_id, photo_kind=kind)
    await _saved_product(message, state, int(product["id"]))


@router.message(EditProduct.value, F.text, NotCommand())
async def edit_text_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = str(data.get("field") or "")
    if field == "photo":
        await message.answer("Сейчас жду фото.", reply_markup=cancel_inline())
        return
    product = await database.get_product(int(data["product_id"]))
    if not product:
        await state.clear()
        await message.answer("Товар уже удалён.", reply_markup=admin_menu_kb(await database.live_enabled()))
        return
    text = message.text or ""
    if field == "name":
        name = " ".join(text.split())
        if len(name) < 2 or len(name) > 120:
            await message.answer("Название: от 2 до 120 символов.", reply_markup=cancel_inline())
            return
        await database.update_product(int(product["id"]), name=name)
    elif field == "desc":
        description = text.strip()
        if description == "-":
            description = ""
        if len(description) > 1500:
            await message.answer("До 1500 символов.", reply_markup=cancel_inline())
            return
        await database.update_product(int(product["id"]), description=description)
    elif field == "price":
        price = parse_amount(text, minimum=0.01, maximum=10_000_000)
        if price is None:
            await message.answer("Нужна цена больше нуля.", reply_markup=cancel_inline())
            return
        await database.update_product(int(product["id"]), price=price)
    elif field == "live":
        live_price = parse_amount(text, minimum=0.01, maximum=10_000_000)
        if live_price is None:
            await message.answer("Нужна LIVE-цена больше нуля.", reply_markup=cancel_inline())
            return
        await database.update_product(int(product["id"]), live_price=live_price)
    elif field == "stock":
        stock = parse_amount(text, minimum=0, maximum=10_000_000)
        if stock is None:
            await message.answer("Остаток: число от 0.", reply_markup=cancel_inline())
            return
        await database.update_product(int(product["id"]), stock_m=stock)
    else:
        await state.clear()
        await message.answer("Не понял, что менять.", reply_markup=admin_menu_kb(await database.live_enabled()))
        return
    await _saved_product(message, state, int(product["id"]))


@router.message(EditProduct.value, NotCommand())
async def edit_invalid(message: Message) -> None:
    await message.answer("Пришлите новое значение текстом или фото.", reply_markup=cancel_inline())


@router.callback_query(F.data.regexp(r"^m:hide:\d+$"))
async def toggle_hidden(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    product = await database.get_product(int(callback.data.split(":")[2]))
    if not product or callback.message is None:
        await callback.answer("Товар не найден", show_alert=True)
        return
    visible = 0 if product["is_active"] else 1
    await database.update_product(int(product["id"]), is_active=visible)
    updated = await database.get_product(int(product["id"]))
    if updated:
        await show_product_admin(callback.message, updated, edit=True)
    await callback.answer("Скрыт" if not visible else "Снова в каталоге")


@router.callback_query(F.data.regexp(r"^m:del:\d+$"))
async def ask_delete(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    product = await database.get_product(int(callback.data.split(":")[2]))
    if not product or callback.message is None:
        await callback.answer("Товар не найден", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, удалить",
                    callback_data=f"m:yesdel:{product['id']}",
                )
            ],
            [InlineKeyboardButton(text="Нет", callback_data=f"m:item:{product['id']}")],
        ]
    )
    await safe_edit(
        callback.message,
        f"Удалить «{esc(product['name'])}» без восстановления?",
        keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^m:yesdel:\d+$"))
async def delete_product(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is None:
        await callback.answer()
        return
    await database.delete_product(int(callback.data.split(":")[2]))
    await callback.answer("Товар удалён")
    await show_product_list(callback.message, 0, edit=True)


@router.callback_query(F.data == "m:live")
async def live_screen(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is None:
        await callback.answer()
        return
    await show_live_screen(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data == "m:liveoff")
async def live_off(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    was_enabled = await database.live_enabled()
    await database.set_setting("live_enabled", "0")
    if callback.message is not None:
        await show_admin_home(callback.message, edit=True)
    await callback.answer("Трансляция закончена")
    if was_enabled:
        await publish_live_state(callback.bot, enabled=False)


@router.callback_query(F.data.in_({"m:liveon", "m:seturl"}))
async def ask_live_url(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SetLiveUrl.url)
    await state.set_data({})
    url = (await database.get_setting("live_url")).strip()
    rows: list[list[InlineKeyboardButton]] = []
    if url:
        rows.append([InlineKeyboardButton(text="Оставить прежнюю ссылку", callback_data="m:keepurl")])
    rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data="m:adm")])
    if callback.message is not None:
        await callback.message.answer(
            "Вставьте ссылку на трансляцию.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    await callback.answer()


async def _start_broadcast(bot, url: str) -> None:  # type: ignore[no-untyped-def]
    was_enabled = await database.live_enabled()
    await database.set_setting("live_url", url)
    await database.set_setting("live_enabled", "1")
    if not was_enabled:
        await publish_live_state(bot, enabled=True)


@router.callback_query(SetLiveUrl.url, F.data == "m:keepurl")
async def keep_live_url(callback: CallbackQuery, state: FSMContext) -> None:
    url = (await database.get_setting("live_url")).strip()
    if not url:
        await callback.answer("Сохранённой ссылки нет", show_alert=True)
        return
    await state.clear()
    await _start_broadcast(callback.bot, url)
    if callback.message is not None:
        await callback.message.answer(
            "Трансляция включена.\nКлиентам видна кнопка «LIVE СЕЙЧАС», в каталоге действует LIVE-цена.",
            reply_markup=admin_menu_kb(True),
        )
    await callback.answer("Трансляция включена")


@router.callback_query(F.data == "m:keepurl")
async def keep_live_url_outside(callback: CallbackQuery) -> None:
    await callback.answer("Сначала нажмите «Включить трансляцию»", show_alert=True)


@router.message(SetLiveUrl.url, F.text, NotCommand())
async def save_live_url(message: Message, state: FSMContext) -> None:
    url = parse_url(message.text or "")
    if url is None:
        await message.answer(
            "Нужна ссылка, например https://t.me/...",
            reply_markup=cancel_inline(),
        )
        return
    await state.clear()
    await _start_broadcast(message.bot, url)
    await message.answer(
        "Трансляция включена.\nКлиентам видна кнопка «LIVE СЕЙЧАС», в каталоге действует LIVE-цена.",
        reply_markup=admin_menu_kb(True),
    )


@router.message(SetLiveUrl.url, NotCommand())
async def save_live_url_invalid(message: Message) -> None:
    await message.answer("Пришлите ссылку текстом.", reply_markup=cancel_inline())


@router.callback_query(F.data.regexp(r"^m:orders:\d+$"))
async def orders_page(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is None:
        await callback.answer()
        return
    page = int(callback.data.split(":")[2])
    await show_orders(callback.message, page, edit=True)
    await callback.answer()


@router.callback_query(F.data == "m:mgr")
async def manager_screen(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is None:
        await callback.answer()
        return
    await show_manager_admin(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^m:mgr:(name|username|phone)$"))
async def begin_manager_edit(callback: CallbackQuery, state: FSMContext) -> None:
    field = callback.data.split(":")[2]
    prompts = {
        "name": "Пришлите имя менеджера.",
        "username": "Пришлите @username менеджера или «-», чтобы убрать.",
        "phone": "Пришлите телефон менеджера или «-», чтобы убрать.",
    }
    await state.set_state(EditManager.value)
    await state.set_data({"field": field})
    if callback.message is not None:
        await callback.message.answer(prompts[field], reply_markup=cancel_inline())
    await callback.answer()


@router.message(EditManager.value, F.text, NotCommand())
async def save_manager(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = str(data.get("field") or "")
    text = message.text or ""
    if field == "name":
        value = " ".join(text.split())
        if len(value) < 2 or len(value) > 80:
            await message.answer("Имя: от 2 до 80 символов.", reply_markup=cancel_inline())
            return
        await database.set_setting("manager_name", value)
    elif field == "username":
        if text.strip() == "-":
            value = ""
        else:
            parsed = valid_username(text)
            if not parsed:
                await message.answer(
                    "Пришлите @username или «-», чтобы убрать.",
                    reply_markup=cancel_inline(),
                )
                return
            value = parsed
        await database.set_setting("manager_username", value)
    elif field == "phone":
        if text.strip() == "-":
            value = ""
        else:
            parsed = normalize_phone(text)
            if not parsed:
                await message.answer(
                    "Пришлите телефон или «-», чтобы убрать.",
                    reply_markup=cancel_inline(),
                )
                return
            value = parsed
        await database.set_setting("manager_phone", value)
    else:
        await state.clear()
        return
    await state.clear()
    await message.answer("Контакт обновлён.")
    await show_manager_admin(message, edit=False)


@router.message(EditManager.value, NotCommand())
async def save_manager_invalid(message: Message) -> None:
    await message.answer("Пришлите значение текстом.", reply_markup=cancel_inline())
