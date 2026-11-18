"""
Removes what the Worker never uses from python_modules/ (vendored by `pywrangler sync`), after the
sync and before `wrangler deploy` (package.json: `pnpm run deploy`).

A Worker may be 64 MiB, together with the memory snapshot that Cloudflare takes of it at deploy
time. With everything that matplotlib brings it is over that. The bot only draws PNG charts with
the Agg backend, DejaVu Sans and the math fonts, so the other fonts, the sample data, the GUI images and
backends, the parts of numpy and fontTools that matplotlib does not load, and type stubs can go.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REMOVE = [
    "matplotlib/mpl-data/sample_data",
    "matplotlib/mpl-data/images",
    "matplotlib/mpl-data/fonts/afm",
    "matplotlib/mpl-data/fonts/pdfcorefonts",
    "matplotlib/backends/web_backend",
    "numpy/f2py",
    "numpy/random",
    "numpy/polynomial",
    "numpy/fft",
    "numpy/testing",
]
REMOVE_GLOBS = [
    "matplotlib/backends/backend_gtk*",
    "matplotlib/backends/_backend_gtk*",
    "matplotlib/backends/backend_qt*",
    "matplotlib/backends/qt_compat.py",
    "matplotlib/backends/backend_tk*",
    "matplotlib/backends/_backend_tk*",
    "matplotlib/backends/_tkagg*",
    "matplotlib/backends/backend_wx*",
    "matplotlib/backends/backend_macosx.py",
    "matplotlib/backends/_macosx.pyi",
    "matplotlib/backends/backend_nbagg.py",
    "matplotlib/backends/backend_webagg*",
    "matplotlib/backends/backend_cairo.py",
    "matplotlib/backends/backend_pgf.py",
    "matplotlib/backends/backend_template.py",
    "numpy/**/tests",
    "**/*.pyi",  # type stubs
]
# matplotlib needs only these of fontTools
KEEP_FONTTOOLS = ("__init__.py", "agl.py", "misc")
# The fonts that stay: DejaVu Sans, and the ones mathtext uses (chat titles and nicknames are
# drawn as matplotlib text, so `$x'$` in one is math): DejaVu Sans Mono, STIX, Computer Modern.
# Only DejaVu Serif and Humor Sans go.
KEEP_FONTS = ("DejaVuSans", "STIX", "cm", "LastResortHE-", "LICENSE")


def size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def prune(root: Path) -> int:
    targets = [root / p for p in REMOVE]
    targets += [p for pattern in REMOVE_GLOBS for p in root.glob(pattern)]
    fonttools = root / "fontTools"
    if fonttools.is_dir():
        targets += [f for f in fonttools.iterdir() if f.name not in KEEP_FONTTOOLS]
    ttf = root / "matplotlib/mpl-data/fonts/ttf"
    if ttf.is_dir():
        targets += [f for f in ttf.iterdir() if not f.name.startswith(KEEP_FONTS)]
    freed = 0
    for target in targets:
        if not target.exists():
            continue
        freed += size(target)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    return freed


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "python_modules")
    if not (root / "matplotlib").is_dir():
        sys.exit(f"{root} has no matplotlib: run `uv run pywrangler sync` first")
    print(f"Pruned {prune(root) / 1048576:.1f} MiB from {root}")
