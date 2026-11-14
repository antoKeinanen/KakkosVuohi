"""
A small engine for menus that are made of inline keyboards.

A menu is a tree of Nodes. Selecting a node shows its text with a keyboard of its children (and a
"back" button). Nodes may ask the user for text (`on_text`), and may only be shown to registered
users, or only to unregistered ones (`requires`).

Compared to the previous version, the callback data of a button is now only the *path* of the
node (e.g. "start/juo/miedot/m1"), which the handler re-validates against the user's current
position in the tree, so a button cannot be used to reach anything the user was not offered.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types import User as TelegramUser

from ..config import Settings
from ..db import Store
from ..db.models import User
from ..strings import S


class Requires(Enum):
    ANY = "any"
    USER = "user"  # a registered user who has accepted the terms
    NON_USER = "non_user"  # somebody who does not have an account (yet)


class MenuCB(CallbackData, prefix="m"):
    path: str
    back: bool = False


@dataclass
class Reply:
    """An answer that asks the user to pick from a (one time) reply keyboard."""

    text: str
    keyboard: list[list[str]]


@dataclass
class Screen:
    text: str
    keyboard: InlineKeyboardMarkup | None = None
    reply_keyboard: list[list[str]] | None = None


@dataclass
class MenuContext:
    store: Store
    settings: Settings
    user: User | None
    tg_user: TelegramUser
    state: Node
    vars: dict[str, Any] = field(default_factory=dict)  # the user's variables, JSON serialisable
    text: str | None = None  # what the user typed, for on_text

    @property
    def words(self) -> list[str]:
        return (self.text or "").split()

    async def reload_user(self) -> None:
        """The user may have been created, changed or deleted by the node that just ran."""
        user = await self.store.users.find(self.tg_user.id)
        self.user = user if user is not None and user.read_terms else None


TextHandler = Callable[[MenuContext], Awaitable[str]]
InputHandler = Callable[[MenuContext], Awaitable["str | Reply"]]
ExitHandler = Callable[[MenuContext, "Node"], Awaitable[None]]
HeaderHandler = Callable[[MenuContext, str], Awaitable[str]]
AvailableHandler = Callable[[MenuContext], bool]
LabelHandler = Callable[[MenuContext], str]


class Node:
    def __init__(
        self,
        key: str,
        label: str = "",
        *,
        text: str | None = None,
        title: str | None = None,
        header: HeaderHandler | None = None,
        requires: Requires | None = None,
        on_select: TextHandler | None = None,
        on_text: InputHandler | None = None,
        on_exit: ExitHandler | None = None,
        available: AvailableHandler | None = None,
        label_fn: LabelHandler | None = None,
        children: Iterable[Node] = (),
    ) -> None:
        self.key = key
        self.label = label
        self.parent: Node | None = None
        self.children: list[Node] = list(children)
        self._text = text
        self._title = title
        self._header = header
        self._requires = requires
        self.on_select = on_select
        self.on_text = on_text
        self.on_exit = on_exit
        self._available = available
        self.label_fn = label_fn
        for child in self.children:
            child.parent = self

    # -- tree ---------------------------------------------------------------------------------

    @property
    def path(self) -> str:
        return self.key if self.parent is None else f"{self.parent.path}/{self.key}"

    @property
    def title(self) -> str:
        if self._title is not None:
            return self._title
        assert self.parent is not None, "the root of a menu needs a title"
        return self.parent.title

    @property
    def header(self) -> HeaderHandler:
        if self._header is not None:
            return self._header
        assert self.parent is not None, "the root of a menu needs a header"
        return self.parent.header

    @property
    def requires(self) -> Requires:
        if self._requires is not None:
            return self._requires
        return self.parent.requires if self.parent else Requires.ANY

    def is_available(self, ctx: MenuContext) -> bool:
        if ctx.user is not None:
            if self.requires is Requires.NON_USER:
                return False
        elif self.requires is Requires.USER:
            return False
        return self._available(ctx) if self._available else True

    # -- rendering ----------------------------------------------------------------------------

    def keyboard(self, ctx: MenuContext) -> InlineKeyboardMarkup:
        rows: list[list[InlineKeyboardButton]] = []
        pair: list[InlineKeyboardButton] = []
        for child in self.children:
            if child.is_available(ctx):
                label = child.label_fn(ctx) if child.label_fn else child.label
                pair.append(
                    InlineKeyboardButton(text=label, callback_data=MenuCB(path=child.path).pack())
                )
            if len(pair) == 2:
                rows.append(pair)
                pair = []
        if self.parent is not None:
            pair.append(
                InlineKeyboardButton(
                    text=S.commands.blakkis.back,
                    callback_data=MenuCB(path=self.path, back=True).pack(),
                )
            )
            rows.append(pair)
            pair = []
        if pair:
            rows.append(pair)
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def _screen(self, ctx: MenuContext, body: str | Reply) -> Screen:
        await ctx.reload_user()
        header = await self.header(ctx, self.title)
        if isinstance(body, Reply):
            return Screen(text=header + body.text, reply_keyboard=body.keyboard)
        return Screen(text=header + body, keyboard=ctx.state.keyboard(ctx))

    # -- behaviour ----------------------------------------------------------------------------

    async def select(self, ctx: MenuContext) -> Screen:
        """Called when the user presses this node's button (or when it is the root)."""
        if self.children or self.on_text:
            ctx.state = self  # leaves are actions: the user stays where they were
        body = await self.on_select(ctx) if self.on_select else (self._text or "")
        return await self._screen(ctx, body)

    async def handle_text(self, ctx: MenuContext) -> Screen | None:
        if self.on_text is None:
            return None
        return await self._screen(ctx, await self.on_text(ctx))

    async def exit(self, ctx: MenuContext, next_node: Node) -> None:
        if self.on_exit:
            await self.on_exit(ctx, next_node)


class Menu:
    def __init__(self, root: Node) -> None:
        self.root = root
        self._index: dict[str, Node] = {}
        stack = [root]
        while stack:
            node = stack.pop()
            if node.path in self._index:
                raise ValueError(f"duplicate menu path {node.path}")
            self._index[node.path] = node
            stack.extend(node.children)

    def find(self, path: str | None) -> Node | None:
        return self._index.get(path) if path else None
