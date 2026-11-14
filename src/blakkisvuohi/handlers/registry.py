"""
aiogram routers can be attached to only one parent, so a module-level Router makes it impossible
to build more than one Dispatcher in a process (which tests need). HandlerSet collects handlers
with the same decorator API and builds a fresh Router every time it is asked for one.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aiogram import Router


class HandlerSet:
    def __init__(self, name: str, *, message_filters: tuple[Any, ...] = ()) -> None:
        self.name = name
        self._message_filters = message_filters
        self._registrations: list[tuple[str, Callable, tuple[Any, ...], dict[str, Any] | None]] = []

    def _decorator(self, event: str, filters: tuple[Any, ...], flags: dict[str, Any] | None):
        def decorate(handler: Callable) -> Callable:
            self._registrations.append((event, handler, filters, flags))
            return handler

        return decorate

    def message(self, *filters: Any, flags: dict[str, Any] | None = None):  # noqa: ANN201
        return self._decorator("message", filters, flags)

    def callback_query(self, *filters: Any, flags: dict[str, Any] | None = None):  # noqa: ANN201
        return self._decorator("callback_query", filters, flags)

    def build(self) -> Router:
        router = Router(name=self.name)
        if self._message_filters:
            router.message.filter(*self._message_filters)
        for event, handler, filters, flags in self._registrations:
            getattr(router, event).register(handler, *filters, flags=flags)
        return router
