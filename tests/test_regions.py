"""Tests for the Johto regions data_gen pipeline (task C4).

Regenerates `data/` (via `python data_gen.py`) and checks the actual total
region count observed from the decomp extraction (248 Johto maps -- routes,
towns, and dungeon/interior floors -- see `data_gen/regions.toml`'s header
for the extraction methodology: `zone_event/*.json` warps plus the
`map_matrix_0000_EVERYWHERE.bin` outdoor-overworld grid), not an assumed
figure, plus a handful of witness regions/connections read directly out of
the decomp.
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
def regions():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)

    importlib.invalidate_caches()
    regions_mod = importlib.import_module("data.regions")
    importlib.reload(regions_mod)
    yield regions_mod.REGIONS
    shutil.rmtree(DATA_DIR, ignore_errors=True)


def test_region_count_matches_extraction(regions) -> None:
    """248 is the actual number of Johto maps (routes, towns, dungeon/
    interior floors) found by filtering `include/constants/maps.h` down to
    the Johto id ranges (see `data_gen/regions.toml`'s header for the exact
    filter), not a guessed figure."""
    assert len(regions) == 248


def test_every_region_has_map_code(regions) -> None:
    for key, region in regions.items():
        assert region["map_code"], f"{key} is missing its map_code"
        assert isinstance(region["exits"], list)


def test_new_bark_town_witness(regions) -> None:
    """New Bark Town (data_gen/regions.toml key 'new_bark', decomp map code
    T20) connects to Elm's Lab/player's house/rival's house/the SW house
    (zone_event warps) and to Route 27 and Route 29 (outdoor continuity,
    from map_matrix_0000_EVERYWHERE.bin) -- cross-checked directly against
    the decomp for this test."""
    new_bark = regions["new_bark"]
    assert new_bark["map_code"] == "T20"
    for expected in (
        "new_bark_elms_lab_1f",
        "new_bark_player_house_1f",
        "new_bark_rival_house_1f",
        "route_27",
        "route_29",
    ):
        assert expected in new_bark["exits"], f"missing new_bark -> {expected}"


def test_violet_city_witness(regions) -> None:
    """Violet City (map code T22) connects to Sprout Tower, the Violet Gym,
    Route 31, Route 32 and Route 36 (all decomp-verified)."""
    violet = regions["violet"]
    assert violet["map_code"] == "T22"
    for expected in ("sprout_tower_1f", "violet_gym", "route_31", "route_32", "route_36"):
        assert expected in violet["exits"]


def test_johto_kanto_boundary_regions_have_dangling_exits(regions) -> None:
    """Mount Silver is, per the game's own outdoor map_matrix, only reachable
    via Kanto's Route 28 in this game -- there is no Johto-side connection.
    Its `exits` should still reference 'route_28' (a forward reference to a
    region a future Kanto task will define), not silently omit it."""
    assert "route_28" in regions["mount_silver"]["exits"]


def test_ruins_of_alph_hidden_rooms_hand_patched(regions) -> None:
    """The 4 Ruins of Alph Unown-puzzle hidden rooms have no zone_event warp
    entry (they're reached via a scripted mid-puzzle warp) -- these were
    hand-patched to connect back to their matching entrance room; verify the
    patch is present for one of them."""
    room = regions["ruins_of_alph_northeast_hidden_room"]
    assert "ruins_of_alph_northeast_entrance_second_room" in room["exits"]


def test_regions_are_idempotent() -> None:
    """Running data_gen.py twice must produce a byte-identical regions
    module."""
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    try:
        subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)
        first = (DATA_DIR / "regions.py").read_bytes()
        subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)
        second = (DATA_DIR / "regions.py").read_bytes()
        assert first == second
    finally:
        shutil.rmtree(DATA_DIR, ignore_errors=True)
