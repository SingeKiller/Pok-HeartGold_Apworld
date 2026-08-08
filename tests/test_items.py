"""Tests for the items data_gen pipeline (task C3).

Regenerates `data/` (via `python data_gen.py`) and checks the actual total
item count observed in the decomp reference (`item_data.csv` has 514 rows:
513 real items + the `ITEM_NONE` placeholder, minus the documented
`ITEM_EXPLORER_KIT` gap -- see `data_gen/items.toml`'s header and
docs/architecture.md Spike 3), plus a handful of witness items with values
read directly out of the decomp, and the progression/useful/filler
classification for the HMs (the 8 CS/HM items) required by the project plan.

Note: HGSS tracks its 16 gym badges as save-data flags
(`include/constants/badge.h`), not as `ITEM_*` bag items -- there is no
`ITEM_*_BADGE` constant in `include/constants/items.h` (cross-checked
against `ressources/platinum_archipelago`, a Gen IV game where badges ARE
items). There is therefore no "16 badges are progression items" case to
test here; see `data_gen/items.toml`'s header for the full explanation.
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


@pytest.fixture(scope="module")
def items():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)

    importlib.invalidate_caches()
    items_mod = importlib.import_module("data.items")
    importlib.reload(items_mod)
    yield items_mod.ITEMS
    shutil.rmtree(DATA_DIR, ignore_errors=True)


def test_item_count_matches_decomp(items) -> None:
    """include/constants/items.h declares 537 possible id slots (0-536), of
    which 22 (ids 113-134) are explicit ITEM_UNUSED_* placeholders, leaving
    515 real named constants. files/itemtool/itemdata/item_data.csv has 514
    rows (513 real items + ITEM_NONE) -- ITEM_EXPLORER_KIT is the one real
    constant with no matching CSV stats row (a genuine, documented gap, see
    docs/architecture.md Spike 3). ITEM_NONE itself is not a real obtainable
    item and is excluded from data/items.py. 513 is the actual figure found
    in the decomp, not an assumed one.
    """
    assert len(items) == 513
    assert "item_none" not in items
    assert "explorer_kit" not in items


def test_no_badge_items(items) -> None:
    """HGSS tracks gym badges as save-data flags, not bag items -- there is
    no ITEM_*_BADGE constant in include/constants/items.h, unlike Gen IV
    (Platinum) where badges are items. Nothing badge-related should appear
    in data/items.py.
    """
    assert not any("badge" in key for key in items)


def test_hms_are_progression(items) -> None:
    """The 8 CS/HM items (HM01-08) must be classified progression (movement-
    gating, required by the project plan)."""
    hm_keys = [f"hm0{n}" for n in range(1, 9)]
    for key in hm_keys:
        assert key in items, f"missing expected HM item {key!r}"
        assert items[key]["pocket"] == "tm_hm"
        assert items[key]["classification"] == "progression"


def test_master_ball(items) -> None:
    master_ball = items["master_ball"]
    assert master_ball["id"] == 1
    assert master_ball["label"] == "MASTER_BALL"
    assert master_ball["price"] == 0
    assert master_ball["pocket"] == "balls"


def test_potion(items) -> None:
    potion = items["potion"]
    assert potion["id"] == 17
    assert potion["label"] == "POTION"
    assert potion["price"] == 300
    assert potion["pocket"] == "medicine"


def test_hm01_cut(items) -> None:
    hm01 = items["hm01"]
    assert hm01["id"] == 420
    assert hm01["label"] == "HM01"
    assert hm01["price"] == 0
    assert hm01["pocket"] == "tm_hm"
    assert hm01["classification"] == "progression"


def test_tm01(items) -> None:
    tm01 = items["tm01"]
    assert tm01["id"] == 328
    assert tm01["label"] == "TM01"
    assert tm01["price"] == 3000
    assert tm01["pocket"] == "tm_hm"


def test_items_data_is_idempotent() -> None:
    """Running data_gen.py twice must produce a byte-identical items module."""
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    try:
        subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)
        first = (DATA_DIR / "items.py").read_bytes()
        subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)
        second = (DATA_DIR / "items.py").read_bytes()
        assert first == second
    finally:
        shutil.rmtree(DATA_DIR, ignore_errors=True)
