"""The definition of the /start menu (formerly app/commands/start.js and app/commands/start/*)."""

from __future__ import annotations

import random

from .. import alcomath, constants
from ..db import LateDrink, TooManyDrinks
from ..drinkinput import MAX_LATE_DRINKS, DrinkInputError, milligrams
from ..formatting import drinks_list, esc, format_datetime, hours_and_minutes, num, rnum
from ..handlers.common import consumption, nick_of, short_permilles
from ..parsing import parse_float, parse_int, parse_leading_int, strip_suffix
from ..strings import S
from .engine import Menu, MenuContext, Node, Reply, Requires

ST = S.commands.start
JUO = ST.juo
ASET = ST.asetukset
LUO = ST.luo_tunnus
TIL = ST.tilastoja
HELP = ST.help
# the ranges offered as buttons; only those within the retention period are shown
DAY_CHOICES = (1, 3, 7, 14, 30, 60)


def _user(ctx: MenuContext):  # noqa: ANN202
    assert ctx.user is not None, "the node requires a user"
    return ctx.user


# -- headers --------------------------------------------------------------------------------------


async def root_header(ctx: MenuContext, title: str) -> str:
    if ctx.user is None:
        return ST.header_nonuser.format(title=title)
    ebac = await ctx.store.drinks.ebac(ctx.user)
    return ST.header_user.format(
        title=title,
        permilles=rnum(ebac.permilles, 2),
        permilles30Min=rnum(ebac.permilles_30min, 2),
    )


async def juo_header(ctx: MenuContext, title: str) -> str:
    ebac, last_drinks = await ctx.store.drinks.ebac_with_recent(_user(ctx), 1)
    drinks_text = (
        JUO.header_drinks1h.format(
            drinkList1h=drinks_list(last_drinks, ctx.settings.tzinfo, max_chars=1500)
        )
        if last_drinks
        else ""
    )
    return JUO.header.format(
        title=title,
        permilles=rnum(ebac.permilles, 2),
        permilles30Min=rnum(ebac.permilles_30min, 2),
        drink_list=drinks_text,
    )


async def settings_header(ctx: MenuContext, title: str) -> str:
    return ASET.header.format(title=title)


async def help_header(ctx: MenuContext, title: str) -> str:
    return HELP.header.format(title=title)


# -- root -----------------------------------------------------------------------------------------


async def root_select(ctx: MenuContext) -> str:
    if ctx.user is None:
        return ST.on_select_nonuser
    ebac, last_drinks = await ctx.store.drinks.ebac_with_recent(ctx.user, 3)
    hours, minutes = hours_and_minutes(ebac.burn_hours)
    drinks_text = (
        ST.on_select_drinks3h.format(
            drinkList3h=drinks_list(last_drinks, ctx.settings.tzinfo, max_chars=2000)
        )
        if last_drinks
        else ""
    )
    return ST.on_select.format(
        grams=rnum(ebac.grams),
        standard_drinks=rnum(alcomath.to_standard_drinks(ebac.grams), 2),
        hours=hours,
        minutes=minutes,
        drink_list=drinks_text,
    )


# -- Juo ------------------------------------------------------------------------------------------


def drink(key: str, label: str, vol: float, litres: float) -> Node:
    mg = constants.calc_alcohol_milligrams(vol, litres)

    async def on_select(ctx: MenuContext) -> str:
        return await _drink_saved(ctx, mg, label)

    return Node(key, label, on_select=on_select)


async def _drink_saved(ctx: MenuContext, mg: int, description: str) -> str:
    user = _user(ctx)
    try:
        await ctx.store.drinks.add(user, mg, description)
    except TooManyDrinks:
        return S.commands.blakkis.error
    return JUO.on_drink.format(drink_response=random.choice(S.drink_responses))  # noqa: S311


async def juo_select(ctx: MenuContext) -> str:
    last2 = await ctx.store.drinks.last_unique(_user(ctx), 2, JUO.jalkikellotus.drink_name)
    # needed to show (and handle) the quick pick buttons
    ctx.vars["juo_last2_drinks"] = [
        {"alcohol": d.alcohol, "description": d.description or ""} for d in last2
    ]
    return JUO.on_select


def _last2(ctx: MenuContext) -> list[dict]:
    return ctx.vars.get("juo_last2_drinks") or []


def quick_pick(index: int) -> Node:
    async def on_select(ctx: MenuContext) -> str:
        picked = _last2(ctx)[index]
        return await _drink_saved(ctx, picked["alcohol"], picked["description"])

    return Node(
        f"latest{index + 1}",
        available=lambda ctx: len(_last2(ctx)) > index,
        label_fn=lambda ctx: _last2(ctx)[index]["description"],
        on_select=on_select,
    )


async def oma_text(ctx: MenuContext) -> str:
    help_example = JUO.oma.help_example
    words = ctx.words
    if len(words) != 2:
        return JUO.oma.error_words.format(help_example=help_example)
    cl = parse_float(strip_suffix(words[0].lower(), "cl"))
    vol = parse_float(strip_suffix(words[1], "%"))
    if cl is None or cl <= 0:
        return JUO.oma.error_cl.format(help_example=help_example)
    if vol is None or not 0 < vol <= 100:
        return JUO.oma.error_vol.format(help_example=help_example)
    mg = milligrams(cl, vol)
    if isinstance(mg, DrinkInputError):
        # either a nonsensical amount or more alcohol than a single drink can contain
        return (
            JUO.oma.error_exceeds
            if mg is DrinkInputError.OUT_OF_LIMITS
            else JUO.oma.error_cl.format(help_example=help_example)
        )
    return await _drink_saved(ctx, mg, f"Oma juoma - {num(cl)}cl {num(vol)}%")


def _forget_late(ctx: MenuContext) -> None:
    ctx.vars.pop("jalkikellotus_hours", None)
    ctx.vars.pop("jalkikellotus_drinks", None)


async def late_text(ctx: MenuContext) -> str:
    texts = JUO.jalkikellotus
    hours = ctx.vars.get("jalkikellotus_hours")
    drinks: list[list[float]] = ctx.vars.get("jalkikellotus_drinks") or []

    words = ctx.words
    if not words:
        return texts.hours_error if hours is None else texts.input_drinks_words_error

    if hours is None:
        input_hours = parse_float(words[0])
        if input_hours is None or not 0 < input_hours <= 24:
            return texts.hours_error
        ctx.vars["jalkikellotus_hours"] = input_hours
        return texts.input_drinks_start

    if len(words) < 2 or len(words) % 2 != 0 or len(words) > 2 * MAX_LATE_DRINKS:
        return texts.input_drinks_words_error

    parsed: list[list[float]] = []
    for number, i in enumerate(range(0, len(words), 2), start=1):
        cl = parse_float(strip_suffix(words[i].lower(), "cl"))
        vol = parse_float(strip_suffix(words[i + 1], "%"))
        result = milligrams(cl, vol)
        if result is DrinkInputError.INVALID:
            return texts.input_drinks_drink_error.format(drink=number)
        if result is DrinkInputError.OUT_OF_LIMITS:
            return texts.error_out_of_limits.format(drink=number)
        parsed.append([cl, vol])  # type: ignore[list-item]

    if len(drinks) + len(parsed) > MAX_LATE_DRINKS:
        return texts.too_many_drinks
    ctx.vars["jalkikellotus_drinks"] = drinks + parsed
    return texts.input_drinks_drinks_correct.format(
        drinks_amount=len(parsed),
        drinks_list="\n".join(f"{num(cl)}cl {num(vol)}%" for cl, vol in drinks + parsed),
    )


async def late_save(ctx: MenuContext) -> str:
    hours = ctx.vars.get("jalkikellotus_hours")
    drinks = ctx.vars.get("jalkikellotus_drinks") or []
    _forget_late(ctx)
    late = [
        LateDrink(
            f"{JUO.jalkikellotus.drink_name} {num(cl)}cl {num(vol)}%",
            constants.calc_alcohol_milligrams(vol / 100, cl / 100),
        )
        for cl, vol in drinks
    ]
    user = _user(ctx)
    try:
        await ctx.store.drinks.add_late(user, late, hours)
    except TooManyDrinks:
        return S.commands.blakkis.error
    ebac = await ctx.store.drinks.ebac(user)
    return JUO.jalkikellotus.save.on_select.format(
        drink_response=random.choice(S.drink_responses),  # noqa: S311
        drinks_amount=len(late),
        short_permilles_text=short_permilles(ebac),
    )


async def late_exit(ctx: MenuContext, next_node: Node) -> None:
    # do not forget the drinks when moving on to saving them
    if next_node.key != "save":
        _forget_late(ctx)


async def kumoa_select(ctx: MenuContext) -> str:
    last = await ctx.store.drinks.last(_user(ctx))
    if last is None:
        ctx.vars.pop("kumoa_drink", None)
        return JUO.kumoa.on_select_no_drinks
    ctx.vars["kumoa_drink"] = {"description": last.description, "created": last.created}
    return JUO.kumoa.on_select.format(
        last_drink_name=esc(last.description or ""),
        last_drink_created=format_datetime(last.created, ctx.settings.tzinfo),
    )


async def kumoa_exit(ctx: MenuContext, next_node: Node) -> None:
    ctx.vars.pop("kumoa_drink", None)


async def kumoa_yes(ctx: MenuContext) -> str:
    user = _user(ctx)
    ctx.vars.pop("kumoa_drink", None)  # one confirmation undoes exactly one drink
    await ctx.store.drinks.undo_last(user)
    ebac = await ctx.store.drinks.ebac(user)
    return JUO.kumoa.success.format(
        permilles=rnum(ebac.permilles, 2), permilles30Min=rnum(ebac.permilles_30min, 2)
    )


def _juo() -> Node:
    def beers(spec):  # noqa: ANN001, ANN202
        return [
            drink(f"m{i}", label, vol, litres) for i, (label, vol, litres) in enumerate(spec, 1)
        ]

    b, w, s = constants.BEER, constants.WINE, "🥃"
    return Node(
        "juo",
        JUO.button_text,
        title=JUO.header_title,
        header=juo_header,
        requires=Requires.USER,
        on_select=juo_select,
        children=[
            Node(
                "miedot",
                JUO.miedot.button_text,
                text=JUO.miedot.on_select,
                title=JUO.miedot.header_title,
                children=beers(
                    [
                        (f"{b} 33cl 4.7%", 0.047, 0.33),
                        (f"{b} 33cl 5.3%", 0.053, 0.33),
                        (f"{b} 40cl 4.7%", 0.047, 0.40),
                        (f"{b} 50cl 4.7%", 0.047, 0.50),
                        (f"{b} 56.8cl 4.7%", 0.047, 0.568),
                        ("Lonkero 33cl 5.3%", 0.053, 0.33),
                        ("Siideri 33cl 4.7%", 0.047, 0.33),
                    ]
                ),
            ),
            Node(
                "viinit",
                JUO.viinit.button_text,
                text=JUO.viinit.on_select,
                title=JUO.viinit.header_title,
                children=beers(
                    [
                        (f"{w} 12cl 12%", 0.12, 0.12),
                        (f"{w} 16cl 12%", 0.16, 0.12),
                        ("🍹 20cl 12%", 0.20, 0.12),
                        ("🥂 12cl 11%", 0.12, 0.11),
                    ]
                ),
            ),
            Node(
                "shotit",
                JUO.shotit.button_text,
                text=JUO.shotit.on_select,
                title=JUO.shotit.header_title,
                children=beers(
                    [
                        (f"{s}4cl 20%", 0.2, 0.04),
                        (f"{s}4cl 32%", 0.32, 0.04),
                        (f"{s}4cl 38%", 0.38, 0.04),
                        (f"{s}4cl 40%", 0.40, 0.04),
                        (f"{s}4cl 60%", 0.60, 0.04),
                    ]
                ),
            ),
            Node(
                "oma",
                JUO.oma.button_text,
                text=JUO.oma.on_select.format(help_example=JUO.oma.help_example),
                title=JUO.oma.header_title,
                on_text=oma_text,
            ),
            Node(
                "jalkikellotus",
                JUO.jalkikellotus.button_text,
                text=JUO.jalkikellotus.on_select,
                title=JUO.jalkikellotus.header_title,
                on_text=late_text,
                on_exit=late_exit,
                children=[
                    Node(
                        "save",
                        JUO.jalkikellotus.save.button_text,
                        on_select=late_save,
                        available=lambda ctx: bool(ctx.vars.get("jalkikellotus_drinks")),
                    )
                ],
            ),
            Node(
                "kumoa",
                JUO.kumoa.button_text,
                title=JUO.kumoa.header_title,
                on_select=kumoa_select,
                on_exit=kumoa_exit,
                children=[
                    Node(
                        "yes",
                        S.yes,
                        on_select=kumoa_yes,
                        available=lambda ctx: ctx.vars.get("kumoa_drink") is not None,
                    )
                ],
            ),
            quick_pick(0),
            quick_pick(1),
        ],
    )


# -- Tilastoja ------------------------------------------------------------------------------------


async def _consumption_text(ctx: MenuContext, template: str, days: int | None) -> str:
    user = _user(ctx)
    drink_sum = await ctx.store.drinks.sum_for_hours(
        user, (days or ctx.settings.retention_days) * 24
    )
    return template.format(**consumption(drink_sum, days, ctx.store.drinks.now(), ceil=True))


async def kulutus_select(ctx: MenuContext) -> str:
    return await _consumption_text(ctx, TIL.kulutus.on_select, None)


async def kulutus_text(ctx: MenuContext) -> str:
    days = parse_leading_int(ctx.words[0] if ctx.words else None)
    days = min(days, ctx.settings.retention_days) if days else ctx.settings.retention_days
    return await _consumption_text(ctx, TIL.kulutus.on_select, days)


def kulutus_days(days: int) -> Node:
    async def on_select(ctx: MenuContext) -> str:
        return await _consumption_text(ctx, TIL.kulutus.prefilled, days)

    return Node(
        f"d{days}",
        "1 päivä" if days == 1 else f"{days} päivää",
        on_select=on_select,
        available=lambda ctx: days <= ctx.settings.retention_days,
    )


async def otinko_select(ctx: MenuContext) -> str:
    drinks = await ctx.store.drinks.last_hours(_user(ctx), 72)
    return TIL.otinko.on_select.format(
        drink_list=drinks_list(drinks, ctx.settings.tzinfo, with_dates=True)
    )


def _tilastoja() -> Node:
    return Node(
        "tilastoja",
        TIL.button_text,
        text=TIL.on_select,
        title=TIL.header_title,
        requires=Requires.USER,
        children=[
            Node(
                "kulutus",
                TIL.kulutus.button_text,
                on_select=kulutus_select,
                on_text=kulutus_text,
                children=[kulutus_days(days) for days in DAY_CHOICES],
            ),
            Node("otinko", TIL.otinko.button_text, on_select=otinko_select),
        ],
    )


# -- Asetukset ------------------------------------------------------------------------------------


def _weight_node() -> Node:
    async def on_select(ctx: MenuContext) -> str:
        return ASET.muokkaa.paino.on_select.format(weight=_user(ctx).weight)

    async def on_text(ctx: MenuContext) -> str:
        weight = parse_int(ctx.words[0] if ctx.words else None)
        if weight is None or not constants.WEIGHT_RANGE[0] <= weight <= constants.WEIGHT_RANGE[1]:
            return LUO.weight_error
        await ctx.store.users.update_weight(_user(ctx), weight)
        return ASET.muokkaa.paino.on_change

    return Node("paino", ASET.muokkaa.paino.button_text, on_select=on_select, on_text=on_text)


def _height_node() -> Node:
    async def on_select(ctx: MenuContext) -> str:
        return ASET.muokkaa.pituus.on_select.format(height=_user(ctx).height)

    async def on_text(ctx: MenuContext) -> str:
        height = parse_int(ctx.words[0] if ctx.words else None)
        if height is None or not constants.HEIGHT_RANGE[0] <= height <= constants.HEIGHT_RANGE[1]:
            return LUO.height_error
        await ctx.store.users.update_height(_user(ctx), height)
        return ASET.muokkaa.pituus.on_change

    return Node("pituus", ASET.muokkaa.pituus.button_text, on_select=on_select, on_text=on_text)


def _gender_node() -> Node:
    async def on_select(ctx: MenuContext) -> str:
        return ASET.muokkaa.sukupuoli.on_select.format(gender=_user(ctx).gender)

    def set_gender(key: str, label: str, gender: str) -> Node:
        async def choose(ctx: MenuContext) -> str:
            assert ctx.state.parent is not None
            ctx.state = ctx.state.parent  # go back one level
            await ctx.store.users.update_gender(_user(ctx), gender)
            return ASET.muokkaa.sukupuoli.on_change

        return Node(key, label, on_select=choose)

    return Node(
        "sukupuoli",
        ASET.muokkaa.sukupuoli.button_text,
        on_select=on_select,
        children=[
            set_gender("mies", S.gender.male, constants.GENDER_MALE),
            set_gender("nainen", S.gender.female, constants.GENDER_FEMALE),
        ],
    )


async def muokkaa_select(ctx: MenuContext) -> str:
    user = _user(ctx)
    return ASET.muokkaa.on_select.format(
        username=esc(user.nick),
        user_id=user.user_id,
        weight=user.weight,
        height=user.height,
        gender=user.gender,
    )


async def paivita_select(ctx: MenuContext) -> str:
    await ctx.store.users.update_nick(_user(ctx), nick_of(ctx.tg_user))
    await ctx.reload_user()
    return ASET.paivita.on_select.format(username=esc(_user(ctx).nick))


async def delete_cancel_second(ctx: MenuContext) -> str:
    assert ctx.state.parent and ctx.state.parent.parent
    ctx.state = ctx.state.parent.parent  # back two levels
    return ASET.poista.canceled


async def delete_confirm(ctx: MenuContext) -> str:
    user = _user(ctx)
    assert ctx.state.parent and ctx.state.parent.parent and ctx.state.parent.parent.parent
    ctx.state = ctx.state.parent.parent.parent  # back to the beginning
    await ctx.store.users.delete(user)
    ctx.vars.clear()
    return ASET.poista.deleted


async def delete_cancel_first(ctx: MenuContext) -> str:
    return ASET.poista.canceled


def _asetukset() -> Node:
    return Node(
        "asetukset",
        ASET.button_text,
        text=ASET.on_select,
        title=ASET.header_title,
        header=settings_header,
        requires=Requires.USER,
        children=[
            Node(
                "muokkaa",
                ASET.muokkaa.button_text,
                on_select=muokkaa_select,
                children=[
                    _weight_node(),
                    _height_node(),
                    _gender_node(),
                    Node("paivita", ASET.paivita.button_text, on_select=paivita_select),
                ],
            ),
            Node(
                "poista",
                ASET.poista.button_text,
                text=ASET.poista.on_select,
                children=[
                    Node(
                        "yes",
                        S.yes,
                        text=ASET.poista.double_confirm,
                        children=[
                            Node("no", S.no_1st, on_select=delete_cancel_second),
                            Node("yes", S.yes, on_select=delete_confirm),
                        ],
                    ),
                    Node("no", S.no_1st, on_select=delete_cancel_first),
                ],
            ),
        ],
    )


# -- Luo tunnus -----------------------------------------------------------------------------------


async def luo_text(ctx: MenuContext) -> str | Reply:
    words = ctx.words
    word = words[0] if words else ""
    weight = ctx.vars.get("weight")
    height = ctx.vars.get("height")
    gender = ctx.vars.get("gender")

    if weight is None:
        parsed = parse_int(word)
        if parsed is None or not constants.WEIGHT_RANGE[0] <= parsed <= constants.WEIGHT_RANGE[1]:
            return LUO.weight_error
        ctx.vars["weight"] = parsed
        return LUO.height

    if height is None:
        parsed = parse_int(word)
        if parsed is None or not constants.HEIGHT_RANGE[0] <= parsed <= constants.HEIGHT_RANGE[1]:
            return LUO.height_error
        ctx.vars["height"] = parsed
        return Reply(LUO.gender, [[S.gender.male, S.gender.female]])

    if gender is None:
        chosen = word.lower()
        if chosen not in (constants.GENDER_MALE, constants.GENDER_FEMALE):
            return Reply(LUO.gender_error, [[S.gender.male, S.gender.female]])
        ctx.vars["gender"] = chosen
        return Reply(LUO.terms.format(terms=S.commands.terms.reply), [[S.yes, S.no]])

    if word.lower() != S.yes.lower():
        return LUO.terms_on_reject

    user, created = await ctx.store.users.create_or_update(
        ctx.tg_user.id, nick_of(ctx.tg_user), weight, gender, height
    )
    for key in ("weight", "height", "gender"):
        ctx.vars.pop(key, None)
    return LUO.new_user.format(username=esc(user.nick)) if created else LUO.update


async def luo_exit(ctx: MenuContext, next_node: Node) -> None:
    for key in ("weight", "height", "gender"):
        ctx.vars.pop(key, None)


def _luo_tunnus() -> Node:
    return Node(
        "luo_tunnus",
        LUO.button_text,
        text=LUO.on_select,
        title=LUO.header_title,
        requires=Requires.NON_USER,
        on_text=luo_text,
        on_exit=luo_exit,
    )


# -- Help -----------------------------------------------------------------------------------------


async def privacy_select(ctx: MenuContext) -> str:
    workers = ctx.settings.bot_mode == "worker"  # the data is with Cloudflare, see README
    return HELP.privacy.on_select.format(
        retention_days=ctx.settings.retention_days,
        account_days=ctx.settings.account_days,
        where=HELP.privacy.where_workers if workers else HELP.privacy.where_server,
        deletion=HELP.privacy.deletion_workers if workers else HELP.privacy.deletion_server,
    )


def _help() -> Node:
    def page(key: str, button: str, texts, children=()) -> Node:  # noqa: ANN001
        return Node(key, button, text=texts.on_select, title=texts.header_title, children=children)

    faq = HELP.faq
    return Node(
        "help",
        HELP.button_text,
        text=HELP.on_select,
        title=HELP.header_title,
        header=help_header,
        children=[
            page("general", HELP.general.button_text, HELP.general),
            page(
                "faq",
                faq.button_text,
                faq,
                [
                    page("juominen", faq.juominen.button_text, faq.juominen),
                    page("ryhmat", faq.ryhmat.button_text, faq.ryhmat),
                    page("koodi", faq.koodi.button_text, faq.koodi),
                ],
            ),
            Node(
                "privacy",
                HELP.privacy.button_text,
                title=HELP.privacy.header_title,
                on_select=privacy_select,
            ),
        ],
    )


def build_menu() -> Menu:
    root = Node(
        "start",
        text=None,
        title=ST.header_title,
        header=root_header,
        on_select=root_select,
        children=[_juo(), _luo_tunnus(), _tilastoja(), _asetukset(), _help()],
    )
    return Menu(root)


MENU = build_menu()
