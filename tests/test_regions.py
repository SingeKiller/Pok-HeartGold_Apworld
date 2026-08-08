"""Tests for the Johto+Kanto regions data_gen pipeline (tasks C4 + C5).

Regenerates `data/` (via `python data_gen.py`) and checks the actual total
region count observed from the decomp extraction (248 Johto + 202 Kanto =
450 maps -- routes, towns, and dungeon/interior floors -- see
`data_gen/regions.toml`'s header for the extraction methodology:
`zone_event/*.json` warps plus the `map_matrix_0000_EVERYWHERE.bin`
outdoor-overworld grid), not an assumed figure, plus a handful of witness
regions/connections read directly out of the decomp.
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
    """450 is the actual number of Johto (248) + Kanto (202) maps (routes,
    towns, dungeon/interior floors) found by filtering
    `include/constants/maps.h` down to the Johto/Kanto id ranges (see
    `data_gen/regions.toml`'s header for the exact filter), not a guessed
    figure."""
    assert len(regions) == 450


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


def test_johto_kanto_boundary_pendants_are_resolved(regions) -> None:
    """C4 left 'route_28', 'route_27', 'route_22_pokemon_league_reception_gate'
    (via victory_road_1f), 'indigo_plateau' (via victory_road_3f),
    'cliff_cave', 'cliff_edge_gate', 'saffron_magnet_train_station_2f',
    'ss_aqua_olivine_port_interior' and the 3 embedded_tower_* rooms as
    dangling forward references to not-yet-defined Kanto regions. C5 must
    define all of them, resolving every one of these Johto-side `exits`."""
    assert "route_28" in regions["mount_silver"]["exits"]
    assert regions["route_28"]["map_code"] == "R28"
    assert "route_27" in regions["new_bark"]["exits"]
    assert regions["route_27"]["map_code"] == "R27"
    assert "route_22_pokemon_league_reception_gate" in regions["victory_road_1f"]["exits"]
    assert regions["route_22_pokemon_league_reception_gate"]["map_code"] == "R22R0101"
    assert "indigo_plateau" in regions["victory_road_3f"]["exits"]
    assert regions["indigo_plateau"]["map_code"] == "T10"
    assert "cliff_cave" in regions["route_47"]["exits"]
    assert regions["cliff_cave"]["map_code"] == "D50R0101"
    assert "cliff_edge_gate" in regions["cianwood"]["exits"]
    assert regions["cliff_edge_gate"]["map_code"] == "D48R0101"
    assert "ss_aqua_olivine_port_interior" in regions["olivine"]["exits"]
    assert regions["ss_aqua_olivine_port_interior"]["map_code"] == "P01R0101"
    for room in (
        "embedded_tower_groudon_room",
        "embedded_tower_kyogre_room",
        "embedded_tower_rayquaza_room",
    ):
        assert room in regions["route_47"]["exits"]
        assert "route_47" in regions[room]["exits"]


def test_magnet_train_hand_patch_both_ends(regions) -> None:
    """Same spirit as the Ruins of Alph hand patch: the Goldenrod <-> Saffron
    magnet train is a cutscene warp, not a walk-in door -- neither map's own
    zone_event `warps` array has an entry for it at all. C4 already
    hand-patched the Goldenrod side; C5 must hand-patch the Saffron side to
    match, in the same direction."""
    assert "saffron_magnet_train_station_2f" in regions["goldenrod_magnet_train_station_2f"]["exits"]
    assert "goldenrod_magnet_train_station_2f" in regions["saffron_magnet_train_station_2f"]["exits"]


def test_v2_regions_still_dangling(regions) -> None:
    """Unlike the C4 pendants above, these targets are explicitly v2 (out of
    scope, see docs/scope.md): the Pokeathlon Dome, the Safari Zone gate,
    the Battle Frontier, and the Union Room (non-map online feature). C5
    must NOT define regions for these -- they should remain dangling."""
    assert "pokeathlon_dome" not in regions
    assert "safari_zone_gate" not in regions
    assert "battle_frontier_frontier_access" not in regions
    assert "union" not in regions
    assert "pokeathlon_dome" in regions["route_35_national_park_pokeathalon_gatehouse"]["exits"]
    assert "safari_zone_gate" in regions["route_48"]["exits"]
    assert "battle_frontier_frontier_access" in regions["route_40_battle_frontier_gatehouse"]["exits"]


def test_ruins_of_alph_hidden_rooms_hand_patched(regions) -> None:
    """The 4 Ruins of Alph Unown-puzzle hidden rooms have no zone_event warp
    entry (they're reached via a scripted mid-puzzle warp) -- these were
    hand-patched to connect back to their matching entrance room; verify the
    patch is present for one of them."""
    room = regions["ruins_of_alph_northeast_hidden_room"]
    assert "ruins_of_alph_northeast_entrance_second_room" in room["exits"]


def test_pallet_town_witness(regions) -> None:
    """Pallet Town (map code T01) connects to Red's/Blue's houses, Oak's
    Lab (zone_event warps) and Route 1/Route 21 (outdoor continuity) --
    decomp-verified."""
    pallet = regions["pallet"]
    assert pallet["map_code"] == "T01"
    for expected in (
        "pallet_town_reds_house_1f",
        "pallet_town_blues_house_1f",
        "pallet_town_oaks_lab",
        "route_1",
        "route_21",
    ):
        assert expected in pallet["exits"]


def test_saffron_city_witness(regions) -> None:
    """Saffron City (map code T11) connects to the Silph Co. HQ, the gym,
    the magnet train station, and Routes 5/6/7/8 (both the direct outdoor
    boundary and the guarded gatehouses) -- decomp-verified."""
    saffron = regions["saffron"]
    assert saffron["map_code"] == "T11"
    for expected in (
        "saffron_silph_co_hq",
        "saffron_gym",
        "saffron_magnet_train_station_1f",
        "route_5",
        "route_6",
        "route_7",
        "route_8",
    ):
        assert expected in saffron["exits"]


def test_kanto_dungeon_witness(regions) -> None:
    """Cerulean Cave (map code D03R0101) connects to Cerulean City, its own
    2F and B1F -- decomp-verified."""
    cave = regions["cerulean_cave_1f"]
    assert cave["map_code"] == "D03R0101"
    for expected in ("cerulean", "cerulean_cave_2f", "cerulean_cave_b1f"):
        assert expected in cave["exits"]


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
