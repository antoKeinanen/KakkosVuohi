from aiogram.fsm.state import State, StatesGroup


class Juoma(StatesGroup):
    start = State()
    miedot = State()
    tiukat = State()
    oma = State()
    omacl = State()


class Jalkikellotus(StatesGroup):
    hours = State()
    drinks = State()


class Laatta(StatesGroup):
    confirm = State()


class Tunnus(StatesGroup):
    weight = State()
    height = State()
    gender = State()
    terms = State()


class Menu(StatesGroup):
    active = State()
