from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import Message


class NotCommand(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return not (message.text or "").startswith("/")
