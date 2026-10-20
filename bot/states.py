from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Booking(StatesGroup):
    name = State()
    phone = State()
    company = State()
    meters = State()
    confirm = State()


class AddProduct(StatesGroup):
    photo = State()
    name = State()
    description = State()
    price = State()
    live_price = State()
    stock = State()


class EditProduct(StatesGroup):
    value = State()


class EditManager(StatesGroup):
    value = State()


class SetLiveUrl(StatesGroup):
    url = State()
