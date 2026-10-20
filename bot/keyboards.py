from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot.formatters import clip, format_price, product_button_label

BTN_LIVE = "🔴 LIVE СЕЙЧАС"
BTN_CATALOG = "📦 КАТАЛОГ"
BTN_MANAGER = "👤 МОЙ МЕНЕДЖЕР"
BTN_HELP = "ℹ️ ПОМОЩЬ"
MENU_TEXTS = (BTN_LIVE, BTN_CATALOG, BTN_MANAGER, BTN_HELP)


def main_keyboard(live: bool) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    if live:
        rows.append([KeyboardButton(text=BTN_LIVE)])
    rows.append([KeyboardButton(text=BTN_CATALOG)])
    rows.append([KeyboardButton(text=BTN_MANAGER), KeyboardButton(text=BTN_HELP)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел",
    )


async def client_keyboard() -> ReplyKeyboardMarkup:
    from bot import db as database

    enabled = await database.live_enabled()
    url = (await database.get_setting("live_url")).strip()
    return main_keyboard(enabled and bool(url))


def nav_row(page: int, total_pages: int, prefix: str) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if page > 0:
        row.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}:{page - 1}"))
    if page + 1 < total_pages:
        row.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}:{page + 1}"))
    return row


def catalog_kb(
    products: list[dict[str, Any]],
    page: int,
    total_pages: int,
    live: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for product in products:
        rows.append(
            [
                InlineKeyboardButton(
                    text=product_button_label(product, live),
                    callback_data=f"prd:{product['id']}",
                )
            ]
        )
    navigation = nav_row(page, total_pages, "cat")
    if navigation:
        rows.append(navigation)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_kb(product_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Забронировать", callback_data=f"rsv:{product_id}")],
            [InlineKeyboardButton(text="✖️ Закрыть", callback_data="cls")],
        ]
    )


def booking_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✖️ Отмена", callback_data="b:no")]]
    )


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="b:ok")],
            [InlineKeyboardButton(text="✖️ Отмена", callback_data="b:no")],
        ]
    )


def cancel_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✖️ Отмена", callback_data="m:adm")]]
    )


def admin_menu_kb(live: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="m:add")],
        [InlineKeyboardButton(text="📋 Товары", callback_data="m:list:0")],
    ]
    if live:
        rows.append([InlineKeyboardButton(text="⏹ Закончить трансляцию", callback_data="m:liveoff")])
    else:
        rows.append([InlineKeyboardButton(text="▶️ Включить трансляцию", callback_data="m:liveon")])
    rows.append([InlineKeyboardButton(text="📨 Заявки", callback_data="m:orders:0")])
    rows.append([InlineKeyboardButton(text="👤 Менеджер", callback_data="m:mgr")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def live_admin_kb(enabled: bool) -> InlineKeyboardMarkup:
    if enabled:
        rows = [[InlineKeyboardButton(text="⏹ Закончить трансляцию", callback_data="m:liveoff")]]
    else:
        rows = [[InlineKeyboardButton(text="▶️ Включить трансляцию", callback_data="m:liveon")]]
    rows.append([InlineKeyboardButton(text="⬅️ В админку", callback_data="m:adm")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_admin_kb(product: dict[str, Any]) -> InlineKeyboardMarkup:
    product_id = int(product["id"])
    hide_label = "🙈 Скрыть" if product["is_active"] else "👁 Показать"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Название", callback_data=f"m:edit:{product_id}:name"),
                InlineKeyboardButton(text="Характеристики", callback_data=f"m:edit:{product_id}:desc"),
            ],
            [
                InlineKeyboardButton(text="Цена", callback_data=f"m:edit:{product_id}:price"),
                InlineKeyboardButton(text="LIVE-цена", callback_data=f"m:edit:{product_id}:live"),
            ],
            [
                InlineKeyboardButton(text="Остаток", callback_data=f"m:edit:{product_id}:stock"),
                InlineKeyboardButton(text="Фото", callback_data=f"m:edit:{product_id}:photo"),
            ],
            [
                InlineKeyboardButton(text=hide_label, callback_data=f"m:hide:{product_id}"),
                InlineKeyboardButton(text="Удалить", callback_data=f"m:del:{product_id}"),
            ],
            [InlineKeyboardButton(text="⬅️ К списку", callback_data="m:list:0")],
        ]
    )


def product_list_label(product: dict[str, Any]) -> str:
    mark = "🚫 " if not product["is_active"] else ""
    return clip(f"{mark}{product['name']} · {format_price(float(product['price']))}", 50)
