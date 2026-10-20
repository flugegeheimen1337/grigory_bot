from __future__ import annotations

from aiogram import F, Router


def private_router() -> Router:
    router = Router()
    router.message.filter(F.chat.type == "private")
    router.callback_query.filter(F.message.chat.type == "private")
    return router
