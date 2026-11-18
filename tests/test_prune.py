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
        "matplotlib/mpl-data/fonts/ttf/STIXGeneral.ttf": False,
        "matplotlib/mpl-data/fonts/ttf/cmr10.ttf": False,
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
