"""Tests for the data_gen pipeline bootstrap (task C1).

Verifies that `python data_gen.py` is idempotent -- two consecutive runs
produce a byte-identical `data/` package -- and that the generated
`data/__init__.py` is actually written and importable.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def _snapshot_data_dir() -> dict[str, bytes]:
    return {
        str(path.relative_to(DATA_DIR)): path.read_bytes()
        for path in sorted(DATA_DIR.rglob("*"))
        if path.is_file()
    }


def _run_data_gen() -> None:
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)


@pytest.fixture()
def clean_data_dir():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    yield
    shutil.rmtree(DATA_DIR, ignore_errors=True)


def test_data_gen_is_idempotent(clean_data_dir: None) -> None:
    """Two consecutive runs must produce a strictly byte-identical data/."""
    _run_data_gen()
    first_run = _snapshot_data_dir()

    _run_data_gen()
    second_run = _snapshot_data_dir()

    assert first_run  # sanity: the run actually generated something
    assert first_run == second_run


def test_data_gen_produces_importable_data_package(clean_data_dir: None) -> None:
    _run_data_gen()

    init_path = DATA_DIR / "__init__.py"
    assert init_path.is_file()

    importlib.invalidate_caches()
    data = importlib.import_module("data")
    importlib.reload(data)

    assert data.GAME_VERSION["name"] == "HeartGold"
    assert data.GAME_VERSION["version"] == 7
    assert data.GAME_VERSION["language"] == "ENGLISH"
    assert data.GAME_VERSION["language_code"] == 2
