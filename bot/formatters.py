from __future__ import annotations

import html
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

MSK = timezone(timedelta(hours=3))

_PRIVATE_COMPANY = {
    "-",
    "—",
    "нет",
    "нету",
    "частное",
    "частное лицо",
    "физлицо",
    "физ лицо",
    "физ. лицо",
}


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def format_money(value: float) -> str:
    number = float(value)
    if abs(number - round(number)) < 1e-9:
        body = f"{int(round(number)):,}".replace(",", " ")
    else:
        body = f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")
    return body + " ₽"


def format_price(value: float) -> str:
    return format_money(value) + "/м"


def format_meters(value: float) -> str:
    number = float(value)
    if abs(number - round(number)) < 1e-9:
        body = f"{int(round(number)):,}".replace(",", " ")
    else:
        body = f"{number:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return body + " м"


def format_dt(value: str) -> str:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(MSK).strftime("%d.%m.%Y %H:%M")


def parse_number(text: str) -> float | None:
    cleaned = text.strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
    cleaned = re.sub(r"[^0-9.]", "", cleaned)
    if not cleaned or cleaned.count(".") > 1:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


def parse_amount(text: str, *, minimum: float, maximum: float) -> float | None:
    value = parse_number(text)
    if value is None or value < minimum or value > maximum:
        return None
    return round(value, 2)


def normalize_phone(text: str) -> str | None:
    raw = text.strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 10 or len(digits) > 15:
        return None
    if raw.startswith("+"):
        return "+" + digits
    return digits


def normalize_company(text: str) -> str | None:
    cleaned = " ".join(text.strip().split())
    if not cleaned or len(cleaned) > 200:
        return None
    if cleaned.casefold() in _PRIVATE_COMPANY:
        return "Частное лицо"
    return cleaned


def valid_username(text: str) -> str | None:
    name = text.strip().lstrip("@")
    if re.fullmatch(r"[A-Za-z0-9_]{5,32}", name):
        return name
    return None


def parse_url(text: str) -> str | None:
    candidate = text.strip().strip("<>")
    if not candidate or len(candidate) > 500 or any(char.isspace() for char in candidate):
        return None
    if not re.match(r"^https?://", candidate, re.IGNORECASE):
        if re.match(r"^[\w.-]+\.[a-z]{2,}(/.*)?$", candidate, re.IGNORECASE):
            candidate = "https://" + candidate
        else:
            return None
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate


def discount_percent(price: float, live_price: float) -> int | None:
    if price <= 0 or live_price >= price:
        return None
    percent = round((price - live_price) / price * 100)
    if percent <= 0:
        return None
    return percent


def unit_price(product: dict[str, Any], live: bool) -> float:
    raw = product["live_price"] if live else product["price"]
    return round(float(raw), 2)


def welcome_text(live: bool) -> str:
    lines = [
        "<b>Здравствуйте!</b>",
        "",
        "Здесь каталог тканей и бронь на время прямого эфира.",
        "",
        "🔴 LIVE СЕЙЧАС — ссылка на трансляцию",
        "📦 КАТАЛОГ — фото, цены и остаток",
        "👤 МОЙ МЕНЕДЖЕР — прямой контакт",
        "ℹ️ ПОМОЩЬ — короткая инструкция",
    ]
    if live:
        lines.extend(["", "Сейчас идёт эфир: в каталоге действует LIVE-цена."])
    return "\n".join(lines)


HELP_TEXT = (
    "<b>Как пользоваться</b>\n\n"
    "1. Откройте «КАТАЛОГ» и выберите ткань: фото, характеристики, цена и остаток.\n"
    "2. Нажмите «Забронировать» и отправьте имя, телефон, компанию и метраж.\n"
    "3. Во время эфира в карточке действует LIVE-цена. Кнопка «LIVE СЕЙЧАС» открывает трансляцию.\n"
    "4. «МОЙ МЕНЕДЖЕР» — прямой контакт, если нужно спросить до брони.\n\n"
    "Заявка не списывает ткань сама: менеджер подтвердит бронь и свяжется с вами.\n\n"
    "Отменить текущий шаг — /cancel."
)

EMPTY_CATALOG = (
    "Каталог пока пуст.\n"
    "Загляните чуть позже или напишите менеджеру через кнопку «МОЙ МЕНЕДЖЕР»."
)


def catalog_header(live: bool, page: int, total_pages: int) -> str:
    lines = ["<b>Каталог тканей</b>"]
    if live:
        lines.append("Сейчас идёт эфир — на кнопках LIVE-цена.")
    else:
        lines.append("Сейчас обычные цены.")
    if total_pages > 1:
        lines.append(f"Страница {page + 1} из {total_pages}.")
    lines.append("Выберите ткань:")
    return "\n".join(lines)


def product_text(product: dict[str, Any], *, live: bool) -> str:
    lines = [f"<b>{esc(product['name'])}</b>"]
    description = (product.get("description") or "").strip()
    if len(description) > 500:
        description = description[:500].rstrip() + "…"
    if description:
        lines.extend(["", esc(description)])
    lines.append("")
    price = float(product["price"])
    live_price = float(product["live_price"])
    if live:
        lines.append(f"🔥 <b>LIVE-цена: {format_price(live_price)}</b>")
        if live_price < price:
            lines.append(f"Обычная цена: <s>{format_price(price)}</s>")
            percent = discount_percent(price, live_price)
            if percent:
                lines.append(f"Скидка эфира: −{percent}%")
    else:
        lines.append(f"💰 Цена: <b>{format_price(price)}</b>")
    stock = float(product["stock_m"])
    if stock <= 0:
        lines.append("📦 Остаток: под заказ")
    else:
        lines.append(f"📦 Остаток: {format_meters(stock)}")
    return "\n".join(lines)


def product_admin_text(product: dict[str, Any]) -> str:
    status = "в каталоге" if product["is_active"] else "скрыт"
    photo = "загружено" if product.get("photo_file_id") else "нет"
    description = (product.get("description") or "").strip() or "—"
    if len(description) > 800:
        description = description[:800].rstrip() + "…"
    return (
        f"<b>{esc(product['name'])}</b>\n"
        f"Статус: {status}\n"
        f"Фото: {photo}\n\n"
        f"{esc(description)}\n\n"
        f"Цена: {format_price(float(product['price']))}\n"
        f"LIVE-цена: {format_price(float(product['live_price']))}\n"
        f"Остаток: {format_meters(float(product['stock_m']))}"
    )


def product_button_label(product: dict[str, Any], live: bool) -> str:
    prefix = "🔥 " if live else ""
    label = f"{prefix}{product['name']} — {format_price(unit_price(product, live))}"
    return clip(label, 50)


def booking_summary(data: dict[str, Any]) -> str:
    mode = "LIVE-цена" if data["is_live"] else "Цена"
    total = round(float(data["meters"]) * float(data["unit_price"]), 2)
    return (
        "<b>Проверьте заявку</b>\n\n"
        f"Ткань: {esc(data['product_name'])}\n"
        f"{mode}: {format_price(float(data['unit_price']))}\n"
        f"Метраж: {format_meters(float(data['meters']))}\n"
        f"Сумма ориентировочно: {format_money(total)}\n\n"
        f"Имя: {esc(data['client_name'])}\n"
        f"Телефон: {esc(data['phone'])}\n"
        f"Компания: {esc(data['company'])}\n\n"
        "Если всё верно — подтвердите заявку."
    )


def order_admin_text(order: dict[str, Any]) -> str:
    mode = "LIVE" if order["is_live"] else "обычная цена"
    username = (order.get("username") or "").strip()
    if username:
        who = f"@{esc(username)}"
    else:
        who = f'<a href="tg://user?id={int(order["user_id"])}">открыть профиль</a>'
    total = round(float(order["meters"]) * float(order["unit_price"]), 2)
    created = format_dt(str(order["created_at"]))
    return (
        f"<b>Заявка #{int(order['id'])}</b> · {esc(created)}\n"
        f"{esc(order['product_name'])}\n"
        f"{format_meters(float(order['meters']))} · {format_price(float(order['unit_price']))} ({mode})\n"
        f"Сумма ориентировочно: {format_money(total)}\n"
        f"{esc(order['client_name'])}\n"
        f"Телефон: <code>{esc(order['phone'])}</code>\n"
        f"Компания: {esc(order.get('company') or '—')}\n"
        f"Telegram: {who}"
    )


def new_order_notification(order: dict[str, Any]) -> str:
    return "<b>Новая заявка</b>\n" + order_admin_text(order)


def live_admin_text(enabled: bool, url: str) -> str:
    status = "включён" if enabled else "выключен"
    lines = [
        "<b>Режим LIVE</b>",
        "",
        f"Сейчас: {status}.",
        "Когда LIVE включён, в карточках показывается LIVE-цена, а кнопка «LIVE СЕЙЧАС» ведёт на трансляцию.",
    ]
    if url:
        lines.extend(["", f"Ссылка: {esc(url)}"])
    else:
        lines.extend(["", "Ссылка ещё не задана."])
    return "\n".join(lines)


def pages(total: int, size: int) -> int:
    if size <= 0:
        raise ValueError("size must be positive")
    if total <= 0:
        return 1
    return (total + size - 1) // size


def clamp_page(page: int, total_pages: int) -> int:
    if total_pages <= 1:
        return 0
    return max(0, min(page, total_pages - 1))


def paginate(items: list[Any], page: int, size: int) -> tuple[list[Any], int, int]:
    total_pages = pages(len(items), size)
    current = clamp_page(page, total_pages)
    start = current * size
    return items[start : start + size], current, total_pages
