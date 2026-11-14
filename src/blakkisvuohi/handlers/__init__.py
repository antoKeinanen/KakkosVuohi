from __future__ import annotations

from aiogram import Router

from . import account, admin, drinks, fallback, groups, info, menu


def build_routers() -> list[Router]:
    """
    Order matters: all commands come first, so that a command always works, whatever the user was
    in the middle of; then the answers to questions; the catch-all comes last.
    """
    return [
        info.router.build(),
        drinks.router.build(),
        account.router.build(),
        groups.router.build(),
        admin.router.build(),
        menu.router.build(),
        drinks.flows.build(),
        account.flows.build(),
        menu.flows.build(),
        fallback.router.build(),
    ]
