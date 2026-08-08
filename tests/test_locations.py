"""Tests for the Johto locations data_gen pipeline (task C4).

Regenerates `data/` (via `python data_gen.py`) and checks the actual total
location count observed from the decomp extraction (400 Johto locations:
169 ground_item + 139 hidden_item + 45 hm_tm + 39 npc_gift + 8 badge -- see
`data_gen/locations.toml`'s header for the extraction methodology), not an
assumed figure, plus that the 8 Johto badges are present and correctly
typed, that every location references an existing region, and a handful of
witness locations read directly out of the decomp.
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

_JOHTO_BADGES = {
    "violet_gym_badge": ("violet_gym", 0),
    "azalea_gym_badge": ("azalea_gym", 1),
    "goldenrod_gym_badge": ("goldenrod_gym", 2),
    "ecruteak_gym_badge": ("ecruteak_gym", 3),
    "cianwood_gym_badge": ("cianwood_gym", 4),
    "olivine_gym_badge": ("olivine_gym", 5),
    "mahogany_gym_leader_room_badge": ("mahogany_gym_leader_room", 6),
    "dragons_den_shrine_badge": ("dragons_den_shrine", 7),
}


@pytest.fixture(scope="module")
def data_modules():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)

    importlib.invalidate_caches()
    locations_mod = importlib.import_module("data.locations")
    regions_mod = importlib.import_module("data.regions")
    items_mod = importlib.import_module("data.items")
    importlib.reload(locations_mod)
    importlib.reload(regions_mod)
    importlib.reload(items_mod)
    yield locations_mod.LOCATIONS, regions_mod.REGIONS, items_mod.ITEMS
    shutil.rmtree(DATA_DIR, ignore_errors=True)


@pytest.fixture(scope="module")
def locations(data_modules):
    return data_modules[0]


@pytest.fixture(scope="module")
def regions(data_modules):
    return data_modules[1]


@pytest.fixture(scope="module")
def items(data_modules):
    return data_modules[2]


def test_location_count_matches_extraction(locations) -> None:
    """400 is the actual number of Johto locations found by the C4
    extraction (169 ground_item + 139 hidden_item + 45 hm_tm + 39 npc_gift +
    8 badge), not a guessed figure."""
    assert len(locations) == 400
    by_type: dict[str, int] = {}
    for loc in locations.values():
        by_type[loc["type"]] = by_type.get(loc["type"], 0) + 1
    assert by_type == {
        "ground_item": 169,
        "hidden_item": 139,
        "hm_tm": 45,
        "npc_gift": 39,
        "badge": 8,
    }


def test_all_eight_johto_badges_present(locations) -> None:
    """The 8 Johto gym badges (include/constants/badge.h BADGE_ZEPHYR
    .. BADGE_RISING, ids 0-7) must each have exactly one badge-type
    location, in the correct gym region, with badge.h's own id."""
    for key, (expected_region, expected_id) in _JOHTO_BADGES.items():
        assert key in locations, f"missing badge location {key!r}"
        loc = locations[key]
        assert loc["type"] == "badge"
        assert loc["region"] == expected_region
        assert loc["id"] == expected_id
        assert "original_item" not in loc  # badges are save-flags, not items


def test_rising_badge_is_at_dragons_den_not_the_gym(locations) -> None:
    """Decomp-verified vanilla mechanic (not a bug): `GiveBadge BADGE_RISING`
    is in the Dragon's Den Shrine script, not the Blackthorn Gym script --
    Clair's gym battle alone doesn't hand over the badge in this game."""
    assert locations["dragons_den_shrine_badge"]["region"] == "dragons_den_shrine"
    assert "blackthorn_gym_badge" not in locations


def test_every_location_references_an_existing_region(locations, regions) -> None:
    for key, loc in locations.items():
        assert loc["region"] in regions, f"{key} references unknown region {loc['region']!r}"


def test_every_original_item_references_an_existing_item(locations, items) -> None:
    for key, loc in locations.items():
        original_item = loc.get("original_item")
        if original_item is not None:
            assert original_item in items, f"{key} references unknown item {original_item!r}"


def test_hm_tm_type_used_regardless_of_delivery_mechanism(locations) -> None:
    """HM01 (Cut) is an NPC gift in vanilla (the Ilex Forest apprentice, no
    item ball) while TM39 (Rock Tomb) is a ground item ball in Union Cave B1F
    -- both should be typed 'hm_tm', not 'npc_gift'/'ground_item', per this
    task's location-type spec."""
    cut = locations["ilex_forest_hm01"]
    assert cut["type"] == "hm_tm"
    assert cut["original_item"] == "hm01"
    assert cut["region"] == "ilex_forest"

    tm39 = locations["union_cave_b1f_tm39"]
    assert tm39["type"] == "hm_tm"
    assert tm39["original_item"] == "tm39"
    assert tm39["region"] == "union_cave_b1f"


def test_sprout_tower_1f_ground_item_witness(locations) -> None:
    """Read directly from the decomp: files/fielddata/eventdata/zone_event's
    Sprout Tower 1F (D15R0101) has a `std_itemball_d15r0101_parlyz_heal`
    object at x=24, z=16, and include/constants/flags.h's
    FLAG_HIDE_ITEMBALL_D15R0101_PARLYZ_HEAL = 0x425 (1061)."""
    loc = locations["sprout_tower_1f_parlyz_heal"]
    assert loc["type"] == "ground_item"
    assert loc["region"] == "sprout_tower_1f"
    assert loc["original_item"] == "parlyz_heal"
    assert loc["id"] == 1061
    assert loc["x"] == 24
    assert loc["z"] == 16


def test_new_bark_hidden_item_witness(locations) -> None:
    """Read directly from the decomp: include/constants/hidden_items.h's
    HIDDENITEM_T20_POTION = 0, at New Bark Town (T20)."""
    loc = locations["new_bark_potion"]
    assert loc["type"] == "hidden_item"
    assert loc["region"] == "new_bark"
    assert loc["original_item"] == "potion"
    assert loc["id"] == 0


def test_violet_gym_badge_witness(locations) -> None:
    """Read directly from the decomp:
    files/fielddata/script/scr_seq/scr_seq_0859_T22GYM0101.s has
    `GiveBadge BADGE_ZEPHYR`, and include/constants/badge.h's
    BADGE_ZEPHYR = 0."""
    loc = locations["violet_gym_badge"]
    assert loc["type"] == "badge"
    assert loc["region"] == "violet_gym"
    assert loc["id"] == 0


def test_locations_are_idempotent() -> None:
    """Running data_gen.py twice must produce a byte-identical locations
    module."""
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    try:
        subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)
        first = (DATA_DIR / "locations.py").read_bytes()
        subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)
        second = (DATA_DIR / "locations.py").read_bytes()
        assert first == second
    finally:
        shutil.rmtree(DATA_DIR, ignore_errors=True)
