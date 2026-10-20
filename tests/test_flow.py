import asyncio
import os
import tempfile
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.enums import ChatType
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import (
    CallbackQuery,
    Chat,
    Message,
    PhotoSize,
    Update,
    User,
)

from bot import db as database
from bot.keyboards import BTN_CATALOG, BTN_LIVE
from bot.main import build_dispatcher


class DummySession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []

    async def close(self) -> None:
        return None

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):  # type: ignore[no-untyped-def]
        yield b""

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,
    ) -> TelegramType:
        self.calls.append(method)
        name = type(method).__name__
        if name in {"SendMessage", "SendPhoto", "SendDocument"}:
            return Message(
                message_id=len(self.calls),
                date=datetime.now(timezone.utc),
                chat=Chat(id=int(method.chat_id), type=ChatType.PRIVATE),
                text=getattr(method, "text", None) or getattr(method, "caption", None),
            )
        return True  # type: ignore[return-value]


def test_admin_can_add_product_and_client_books_live_price() -> None:
    asyncio.run(_flow())


def _user(user_id: int, username: str, first_name: str) -> User:
    return User(id=user_id, is_bot=False, first_name=first_name, username=username)


def _message(update_id: int, user: User, text: str | None = None, photo: bool = False) -> Update:
    kwargs = {}
    if photo:
        kwargs["photo"] = [
            PhotoSize(file_id="fabric-photo", file_unique_id="fabric-photo-uid", width=800, height=600)
        ]
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=user.id, type=ChatType.PRIVATE),
            from_user=user,
            text=text,
            **kwargs,
        ),
    )


def _callback(update_id: int, user: User, data: str) -> Update:
    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=f"cb-{update_id}",
            from_user=user,
            chat_instance="test",
            data=data,
            message=Message(
                message_id=update_id,
                date=datetime.now(timezone.utc),
                chat=Chat(id=user.id, type=ChatType.PRIVATE),
                from_user=User(id=1, is_bot=True, first_name="bot", username="shopbot"),
                text="кнопка",
            ),
        ),
    )


def _sent(session: DummySession, chat_id: int) -> list[str]:
    texts: list[str] = []
    for method in session.calls:
        if getattr(method, "chat_id", None) != chat_id:
            continue
        text = getattr(method, "text", None) or getattr(method, "caption", None)
        if text:
            texts.append(text)
    return texts


async def _flow() -> None:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    session = DummySession()
    bot = Bot(token="1:test", session=session)
    admin = _user(501, "Grigori_G_979", "Григорий")
    client = _user(502, "client_buyer", "Анна")
    stranger = _user(777, "stranger_user", "Чужой")
    dispatcher: Dispatcher | None = None
    try:
        await database.connect(path)
        dispatcher = build_dispatcher()

        await dispatcher.feed_update(bot, _message(2, admin, "/start"))
        assert any("Здравствуйте" in text for text in _sent(session, admin.id))

        await dispatcher.feed_update(bot, _message(1, stranger, "/admin"))
        stranger_texts = _sent(session, stranger.id)
        assert any("Нет доступа" in text for text in stranger_texts)
        assert not any("Админ-панель" in text for text in stranger_texts)

        await dispatcher.feed_update(bot, _message(3, admin, "/admin"))
        assert any("Админ-панель" in text for text in _sent(session, admin.id))

        await dispatcher.feed_update(bot, _callback(4, admin, "m:add"))
        await dispatcher.feed_update(bot, _message(5, admin, photo=True))
        await dispatcher.feed_update(bot, _message(6, admin, "Лён умягчённый"))
        await dispatcher.feed_update(
            bot,
            _message(7, admin, "Состав: 100% лён\nШирина: 145 см"),
        )
        await dispatcher.feed_update(bot, _message(8, admin, "1 200"))
        await dispatcher.feed_update(bot, _message(9, admin, "990"))
        await dispatcher.feed_update(bot, _message(10, admin, "40"))

        products = await database.list_products()
        assert len(products) == 1
        product = products[0]
        assert product["name"] == "Лён умягчённый"
        assert product["price"] == 1200
        assert product["live_price"] == 990
        assert product["stock_m"] == 40
        assert "145 см" in product["description"]

        await dispatcher.feed_update(bot, _callback(11, admin, "m:liveon"))
        await dispatcher.feed_update(bot, _message(12, admin, "https://example.com/live"))
        assert await database.live_enabled() is True
        assert await database.get_setting("live_url") == "https://example.com/live"

        await dispatcher.feed_update(bot, _message(13, client, "/start"))
        assert any("LIVE-цена" in text for text in _sent(session, client.id))

        await dispatcher.feed_update(bot, _message(14, client, BTN_CATALOG))
        assert any("Каталог тканей" in text for text in _sent(session, client.id))

        product_id = int(product["id"])
        await dispatcher.feed_update(bot, _callback(15, client, f"prd:{product_id}"))
        await dispatcher.feed_update(bot, _callback(16, client, f"rsv:{product_id}"))
        await dispatcher.feed_update(bot, _message(17, client, "Анна Иванова"))
        await dispatcher.feed_update(bot, _message(18, client, "+7 (900) 111-22-33"))
        await dispatcher.feed_update(bot, _message(19, client, "ООО Ткани"))
        await dispatcher.feed_update(bot, _message(20, client, "10"))
        await dispatcher.feed_update(bot, _callback(21, client, "b:ok"))

        orders = await database.list_orders(0, 10)
        assert len(orders) == 1
        order = orders[0]
        assert order["client_name"] == "Анна Иванова"
        assert order["phone"] == "+79001112233"
        assert order["company"] == "ООО Ткани"
        assert order["meters"] == 10
        assert order["unit_price"] == 990
        assert order["is_live"] == 1
        assert order["product_name"] == "Лён умягчённый"
        assert order["username"] == "client_buyer"

        fresh = await database.get_product(product_id)
        assert fresh is not None
        assert fresh["stock_m"] == 40

        client_texts = _sent(session, client.id)
        assert any(text == "Заявка принята! Менеджер свяжется с вами." for text in client_texts)
        assert any("Проверьте заявку" in text and "LIVE-цена" in text for text in client_texts)

        admin_texts = _sent(session, admin.id)
        assert any("Новая заявка" in text and "+79001112233" in text for text in admin_texts)

        await dispatcher.feed_update(bot, _callback(40, admin, "m:liveoff"))
        assert await database.live_enabled() is False
        await dispatcher.feed_update(bot, _message(41, client, BTN_LIVE))
        assert any("эфир не идёт" in text for text in _sent(session, client.id))
    finally:
        await bot.session.close()
        await database.close()
        if dispatcher is not None:
            await dispatcher.storage.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(path + suffix)
            except FileNotFoundError:
                pass
