from __future__ import annotations

import os


def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def bot_token() -> str:
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Задайте BOT_TOKEN в окружении")
    return token


def database_path() -> str:
    return os.environ.get("DATABASE_PATH", "data/bot.db")


def admin_usernames() -> set[str]:
    raw = os.environ.get("ADMIN_USERNAMES", "Grigori_G_979")
    names: set[str] = set()
    for part in raw.split(","):
        name = part.strip().lstrip("@").lower()
        if name:
            names.add(name)
    return names


def admin_ids() -> set[int]:
    raw = os.environ.get("ADMIN_IDS", "")
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids
