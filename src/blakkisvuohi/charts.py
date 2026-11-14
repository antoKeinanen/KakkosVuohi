"""Line charts of the permilles of users: the last 24 hours (solid) and a 12 hour prediction."""

from __future__ import annotations

import io
import random
from collections.abc import Sequence
from datetime import tzinfo

import matplotlib

matplotlib.use("Agg")  # no display, never import pyplot (global state, not thread safe)
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from . import alcomath  # noqa: E402
from .db.models import GroupMember  # noqa: E402

LAST_N_HOURS = 24
PREDICT_N_HOURS = 12
MAX_USERS = 30  # more lines than this cannot be read anyway

# Wad's 16 color palette, http://alumni.media.mit.edu/~wad/color/numbers.html (white left out)
PALETTE = [
    (0, 0, 0),  # Black
    (87, 87, 87),  # Dk. Gray
    (173, 35, 35),  # Red
    (42, 75, 215),  # Blue
    (29, 105, 20),  # Green
    (129, 74, 25),  # Brown
    (129, 38, 192),  # Purple
    (160, 160, 160),  # Lt. Gray
    (129, 197, 122),  # Lt. Green
    (157, 175, 255),  # Lt. Blue
    (41, 208, 208),  # Cyan
    (255, 146, 51),  # Orange
    (255, 238, 51),  # Yellow
    (233, 222, 187),  # Tan
    (255, 205, 243),  # Pink
]


def render_chart(members: Sequence[GroupMember], title: str, now: float, tz: tzinfo) -> bytes:
    fig = Figure(figsize=(10.24, 7.28), dpi=100)
    FigureCanvasAgg(fig)
    ax = fig.add_subplot()

    colors = list(PALETTE)
    random.shuffle(colors)  # noqa: S311 - only for the looks
    labels: list[int] = []
    for i, member in enumerate(members[:MAX_USERS]):
        hourly = alcomath.calculate_ebac_by_hour(
            member, member.drinks, LAST_N_HOURS, PREDICT_N_HOURS, now, tz
        )
        if not labels:
            labels = [h.hour for h in hourly]
        xs = range(len(hourly))
        color = tuple(c / 255 for c in colors[i % len(colors)])
        past = [(x, h.permilles) for x, h in zip(xs, hourly, strict=True) if x <= LAST_N_HOURS]
        future = [(x, h.permilles) for x, h in zip(xs, hourly, strict=True) if x >= LAST_N_HOURS]
        ax.plot(*zip(*past, strict=True), color=color, label=member.nick)
        ax.plot(*zip(*future, strict=True), color=color, linestyle=(0, (5, 5)))

    if labels:
        ax.set_xticks(range(len(labels)), [str(h) for h in labels])
        ax.legend(loc="upper left")
    ax.set_title(title)
    ax.set_xlabel("Aika")
    ax.set_ylabel("Promillet")
    ax.grid(alpha=0.3)

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png")
    return buffer.getvalue()
