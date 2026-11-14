"""
Who may use which handler. Handlers declare it with flags, one middleware enforces it
(see middlewares.AccessMiddleware), so that it cannot be forgotten in an individual handler.
"""

from __future__ import annotations

from aiogram.filters import Command

# scope: where the handler may be used
PRIVATE = "private"  # only in a private chat with the bot
CHAT = "chat"  # only in group chats
ANYWHERE = "all"

# privilege: who may use it
USER = "user"  # registered users that have accepted the terms
ADMIN = "admin"
EVERYONE = "all"


def access(scope: str = ANYWHERE, privilege: str = EVERYONE) -> dict[str, str]:
    return {"scope": scope, "privilege": privilege}


def cmd(name: str) -> Command:
    return Command(name, ignore_case=True)
