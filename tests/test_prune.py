"""scripts/prune_worker_bundle.py: what the Worker needs stays, the rest goes."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "prune_worker_bundle.py"


def load():
    spec = importlib.util.spec_from_file_location("prune_worker_bundle", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pruning_keeps_what_charts_need(tmp_path):
    files = {
        "matplotlib/__init__.py": True,
        "matplotlib/backends/backend_agg.py": True,
        "matplotlib/backends/backend_qtagg.py": False,
        "matplotlib/backends/web_backend/all.css": False,
        "matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf": True,
        "matplotlib/mpl-data/fonts/ttf/DejaVuSans-Bold.ttf": True,
        "matplotlib/mpl-data/fonts/ttf/DejaVuSansDisplay.ttf": True,
        "matplotlib/mpl-data/fonts/ttf/DejaVuSansMono.ttf": True,
        "matplotlib/mpl-data/fonts/ttf/STIXGeneral.ttf": True,
        "matplotlib/mpl-data/fonts/ttf/cmr10.ttf": True,
        "matplotlib/mpl-data/fonts/ttf/DejaVuSerif.ttf": False,
        "matplotlib/mpl-data/fonts/ttf/Humor-Sans.ttf": False,
        "matplotlib/mpl-data/sample_data/x.npy": False,
        "fontTools/__init__.py": True,
        "fontTools/agl.py": True,
        "fontTools/misc/textTools.py": True,
        "fontTools/ttLib/__init__.py": False,
        "numpy/__init__.py": True,
        "numpy/linalg/__init__.py": True,
        "numpy/ma/__init__.py": True,
        "numpy/random/__init__.py": False,
        "numpy/_core/tests/test_x.py": False,
        "numpy/__init__.pyi": False,
        "aiogram/__init__.py": True,
    }
    for name in files:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(b"x" * 10)

    freed = load().prune(tmp_path)

    assert {name: (tmp_path / name).exists() for name in files} == files
    assert freed == 10 * sum(not keep for keep in files.values())


def test_charts_look_the_same_with_the_fonts_that_stay():
    """Chat titles and nicknames are matplotlib text: `$x'$` is math, with its own fonts."""
    import random
    import time
    from zoneinfo import ZoneInfo

    import matplotlib
    from matplotlib import font_manager, mathtext

    from blakkisvuohi import charts
    from blakkisvuohi.db.models import DrinkRow, GroupMember

    keep = load().KEEP_FONTS
    now = time.time()
    members = [
        GroupMember("u", r"$\alpha$ nick", 80, "mies", 180, [DrinkRow(12000, "x", int(now - 3600))])
    ]
    titles = ["$x'$", r"$\sum\alpha^2$ ja $5", "Bileet $1 $2", r"$\mathcal{A}\mathbb{R}$"]

    def forget_fonts() -> None:
        font_manager.FontManager._findfont_cached.cache_clear()
        font_manager._get_font.cache_clear()
        mathtext.MathTextParser._parse_cached.cache_clear()

    def render() -> list[bytes]:
        forget_fonts()
        pngs = []
        for title in titles:
            random.seed(0)
            pngs.append(charts.render_chart(members, title, now, ZoneInfo("Europe/Helsinki")))
        return pngs

    manager = font_manager.fontManager
    every = manager.ttflist
    # the fonts matplotlib ships, read from its files (not from the font cache of this host)
    ttf = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    bundled = [
        font_manager.ttfFontProperty(font_manager.get_font(str(path)))
        for path in sorted(ttf.glob("*.ttf"))
    ]
    try:
        manager.ttflist = bundled  # as in the Worker: no system fonts
        full = render()
        manager.ttflist = [f for f in bundled if Path(f.fname).name.startswith(keep)]
        assert render() == full
    finally:
        manager.ttflist = every
        forget_fonts()
