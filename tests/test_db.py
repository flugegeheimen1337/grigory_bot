import asyncio
import os
import tempfile

from bot import db as database


def test_products_orders_and_settings() -> None:
    asyncio.run(_scenario())


async def _scenario() -> None:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        await database.connect(path)
        assert await database.live_enabled() is False
        assert await database.get_setting("manager_username") == "Grigori_G_979"

        product_id = await database.add_product(
            name="Лён",
            description="145 см",
            price=1200,
            live_price=990,
            stock_m=40,
            photo_file_id="file",
            photo_kind="photo",
        )
        hidden_id = await database.add_product(
            name="Скрытый",
            description="",
            price=10,
            live_price=10,
            stock_m=1,
            photo_file_id=None,
            photo_kind="photo",
        )
        await database.update_product(hidden_id, is_active=0)
        visible = await database.list_products()
        assert [item["id"] for item in visible] == [product_id]
        assert len(await database.list_products(include_hidden=True)) == 2

        await database.set_setting("live_enabled", "1")
        order_id = await database.create_order(
            user_id=5,
            username=None,
            client_name="Анна",
            phone="+79001112233",
            company="Частное лицо",
            product_id=product_id,
            product_name="Лён",
            meters=10,
            unit_price=990,
            is_live=True,
        )
        order = await database.get_order(order_id)
        assert order is not None
        assert order["is_live"] == 1
        assert order["username"] is None
        assert await database.count_orders() == 1
        listed = await database.list_orders(0, 10)
        assert listed[0]["id"] == order_id

        await database.remember_admin(42, "Grigori_G_979")
        assert await database.is_admin_id(42) is True
        assert await database.list_admin_ids() == [42]

        await database.set_setting("manager_name", "Анна")
        await database.close()
        await database.connect(path)
        assert await database.get_setting("manager_name") == "Анна"
        assert await database.live_enabled() is True
    finally:
        await database.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(path + suffix)
            except FileNotFoundError:
                pass
