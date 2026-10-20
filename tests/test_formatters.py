from bot.formatters import (
    booking_summary,
    clamp_page,
    discount_percent,
    format_dt,
    format_meters,
    format_money,
    format_price,
    normalize_company,
    normalize_phone,
    paginate,
    parse_amount,
    parse_url,
    product_text,
    valid_username,
)


def test_default_admins_include_both(monkeypatch) -> None:
    monkeypatch.delenv("ADMIN_USERNAMES", raising=False)
    from bot import config

    assert config.admin_usernames() == {"grigori_g_979", "maxm_dm"}


def test_money_and_meters() -> None:
    assert format_price(1200) == "1 200 ₽/м"
    assert format_price(1200.5) == "1 200,50 ₽/м"
    assert format_money(9900) == "9 900 ₽"
    assert format_meters(15) == "15 м"
    assert format_meters(1.5) == "1,5 м"
    assert format_meters(1000) == "1 000 м"


def test_parse_amount_accepts_russian_input() -> None:
    assert parse_amount("1 200,50", minimum=0.01, maximum=10_000) == 1200.5
    assert parse_amount("15", minimum=0.01, maximum=1000) == 15
    assert parse_amount("0", minimum=0, maximum=10) == 0
    assert parse_amount("0", minimum=0.01, maximum=10) is None
    assert parse_amount("нет", minimum=0, maximum=10) is None


def test_phone_company_username_and_url() -> None:
    assert normalize_phone("+7 (999) 123-45-67") == "+79991234567"
    assert normalize_phone("89991234567") == "89991234567"
    assert normalize_phone("123") is None
    assert normalize_company("-") == "Частное лицо"
    assert normalize_company("  ООО Ромашка  ") == "ООО Ромашка"
    assert valid_username("@Grigori_G_979") == "Grigori_G_979"
    assert valid_username("bad") is None
    assert parse_url("https://example.com/live") == "https://example.com/live"
    assert parse_url("t.me/somechannel/1") == "https://t.me/somechannel/1"
    assert parse_url("не ссылка") is None


def test_live_price_caption_and_discount() -> None:
    product = {
        "name": "<Лён>",
        "description": "лён & хлопок",
        "price": 100,
        "live_price": 80,
        "stock_m": 0,
        "is_active": 1,
    }
    text = product_text(product, live=True)
    assert "&lt;Лён&gt;" in text
    assert "лён &amp; хлопок" in text
    assert "LIVE-цена" in text
    assert "−20%" in text
    assert "под заказ" in text
    assert discount_percent(100, 80) == 20
    regular = product_text(product, live=False)
    assert "LIVE-цена" not in regular
    assert "100 ₽/м" in regular


def test_booking_summary_uses_live_price() -> None:
    text = booking_summary(
        {
            "is_live": True,
            "meters": 10,
            "unit_price": 990,
            "product_name": "Лён",
            "client_name": "Анна",
            "phone": "+79001112233",
            "company": "ООО Ткани",
        }
    )
    assert "LIVE-цена" in text
    assert "990 ₽/м" in text
    assert "9 900 ₽" in text


def test_moscow_time_and_pages() -> None:
    assert format_dt("2026-10-20T09:00:00+00:00") == "20.10.2026 12:00"
    assert clamp_page(5, 1) == 0
    chunk, page, total = paginate([1, 2, 3, 4, 5], 1, 2)
    assert chunk == [3, 4]
    assert page == 1
    assert total == 3
