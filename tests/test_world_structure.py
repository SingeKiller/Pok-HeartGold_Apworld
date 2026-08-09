"""Tests for the Archipelago world structure (tasks C8 + C9): `items.py`'s
item id map, `locations.py`'s location id map and region attachment,
`regions.py`'s `Region`/`Entrance` graph, and `rules.py`'s application of
`data/rules.py`'s `EXIT_RULES` onto that graph.

Regenerates `data/` (via `python data_gen.py`) and builds a real, minimal
`BaseClasses.MultiWorld` (no `World`/`AutoWorld` class exists yet -- see
docs/architecture.md -- so a bare stand-in is registered in
`multiworld.worlds` to satisfy `CollectionState`'s own assertion) to check:

  - the item id map and the location id map are each bijective (no id
    collision within either map), and the two maps don't collide with each
    other either (this project's own Spike 4 convention, not a hard AP
    requirement);
  - every one of the 586 `data/locations.py` locations is attached to the
    region graph `regions.create_regions` actually built (real region
    reference, not just a same-named string);
  - every one of the 67 `data/rules.py` `EXIT_RULES` entries applies without
    exception to an `Entrance` that actually exists in that graph, and the
    resulting rule evaluates (as a plain bool, no exception) both with an
    empty and with a full inventory.

Needs a local Archipelago checkout importable as `BaseClasses` (see
tests/conftest.py) -- skips cleanly if unavailable.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

bc = pytest.importorskip("BaseClasses")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

PLAYER = 1

_MODULES = (
    "data.items",
    "data.locations",
    "data.regions",
    "data.rules",
    "items",
    "locations",
    "regions",
    "rules",
)


@pytest.fixture(scope="module")
def world_modules():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)

    importlib.invalidate_caches()
    modules = {}
    # Import order matters: locations.py imports items.py, rules.py imports
    # locations.py -- importing/reloading in the declared (dependency-safe)
    # order avoids working from a stale module reloaded out of order.
    for name in _MODULES:
        if name in sys.modules:
            modules[name] = importlib.reload(sys.modules[name])
        else:
            modules[name] = importlib.import_module(name)
    yield modules
    shutil.rmtree(DATA_DIR, ignore_errors=True)


@pytest.fixture()
def built_world(world_modules):
    """A freshly-built MultiWorld + region graph + locations + rules for
    one player, from scratch, for every test (rules.py mutates Entrance
    objects in place, so each test gets its own graph)."""
    items_mod = world_modules["items"]
    locations_mod = world_modules["locations"]
    regions_mod = world_modules["regions"]
    rules_mod = world_modules["rules"]

    multiworld = bc.MultiWorld(1)
    # This module tests items.py/locations.py/regions.py/rules.py directly,
    # without going through the real HeartGoldWorld (__init__.py, task C12)
    # to keep them testable standalone. `.game` is required now that
    # __init__.py exists: importing it (even indirectly, via pytest's
    # package collection) registers HeartGoldWorld with worlds.AutoWorld,
    # whose autoload pulls in every other world's init_mixin (e.g. OOT's),
    # some of which inspect `multiworld.worlds[player].game` when building a
    # CollectionState.
    multiworld.worlds[PLAYER] = SimpleNamespace(game="Pokemon HeartGold")

    region_map = regions_mod.create_regions(PLAYER, multiworld)
    locations_mod.create_locations(PLAYER, region_map)
    rules_mod.set_rules(PLAYER, multiworld, region_map)

    return SimpleNamespace(
        multiworld=multiworld,
        regions=region_map,
        items=items_mod,
        locations=locations_mod,
        regions_mod=regions_mod,
        rules_mod=rules_mod,
    )


# --- id maps: bijective, no collisions ------------------------------------


def test_item_id_map_is_bijective(world_modules):
    id_map = world_modules["items"].create_item_label_to_code_map()
    assert len(id_map) == len(world_modules["data.items"].ITEMS)
    assert len(id_map) == len(set(id_map.values())), "duplicate item id in create_item_label_to_code_map()"


def test_location_id_map_is_bijective(world_modules):
    locations_data = world_modules["data.locations"].LOCATIONS
    id_map = world_modules["locations"].create_location_label_to_code_map()
    non_badge_count = sum(1 for data in locations_data.values() if data["type"] != "badge")
    assert len(id_map) == non_badge_count
    assert len(id_map) == len(set(id_map.values())), "duplicate location id in create_location_label_to_code_map()"


def test_item_and_location_id_maps_do_not_collide(world_modules):
    """Not a hard Archipelago requirement (see docs/architecture.md, Spike
    4) but this project's own chosen convention (separate
    HEARTGOLD_ITEM_ID_BASE / HEARTGOLD_LOCATION_ID_BASE ranges) -- lock it
    with a test."""
    item_ids = set(world_modules["items"].create_item_label_to_code_map().values())
    location_ids = set(world_modules["locations"].create_location_label_to_code_map().values())
    assert item_ids.isdisjoint(location_ids)


# --- locations reference a region that really exists in the graph --------


def test_every_location_is_attached_to_a_real_region_object(built_world, world_modules):
    locations_data = world_modules["data.locations"].LOCATIONS
    all_ap_locations = {
        location.name: location for region in built_world.regions.values() for location in region.locations
    }
    assert len(all_ap_locations) == len(locations_data)
    for key, data in locations_data.items():
        location = all_ap_locations[key]
        expected_region = built_world.regions[data["region"]]
        assert location.parent_region is expected_region
        assert location in expected_region.locations


def test_badge_locations_are_locked_events_with_no_address(built_world, world_modules):
    locations_data = world_modules["data.locations"].LOCATIONS
    all_ap_locations = {
        location.name: location for region in built_world.regions.values() for location in region.locations
    }
    badge_keys = [key for key, data in locations_data.items() if data["type"] == "badge"]
    assert len(badge_keys) == 16
    for key in badge_keys:
        location = all_ap_locations[key]
        assert location.address is None
        assert location.locked
        assert location.item is not None
        assert location.item.advancement


def test_non_badge_locations_have_the_mapped_address(built_world, world_modules):
    locations_data = world_modules["data.locations"].LOCATIONS
    id_map = built_world.locations.create_location_label_to_code_map()
    all_ap_locations = {
        location.name: location for region in built_world.regions.values() for location in region.locations
    }
    for key, data in locations_data.items():
        if data["type"] == "badge":
            continue
        assert all_ap_locations[key].address == id_map[key]


# --- rules apply without exception to entrances that really exist --------


def test_every_exit_rule_applies_to_a_real_entrance(built_world, world_modules):
    exit_rules = world_modules["data.rules"].EXIT_RULES
    applied = 0
    for src, dest in exit_rules:
        entrance = built_world.multiworld.get_entrance(f"{src} -> {dest}", PLAYER)
        assert entrance.access_rule is not bc.Entrance.access_rule, f"{src} -> {dest} rule was not applied"
        applied += 1
    assert applied == len(exit_rules) == 67


def test_exit_rules_evaluate_without_exception(built_world, world_modules):
    items_data = world_modules["data.items"].ITEMS
    badges = world_modules["data.rules"].BADGES
    exit_rules = world_modules["data.rules"].EXIT_RULES

    empty_state = bc.CollectionState(built_world.multiworld)

    full_state = bc.CollectionState(built_world.multiworld)
    for data in items_data.values():
        full_state.prog_items[PLAYER][data["label"]] += 1
    for badge_name in badges:
        full_state.prog_items[PLAYER][built_world.locations.badge_event_item_name(badge_name)] += 1

    for src, dest in exit_rules:
        entrance = built_world.multiworld.get_entrance(f"{src} -> {dest}", PLAYER)
        assert isinstance(entrance.access_rule(empty_state), bool)
        assert entrance.access_rule(full_state) is True


def test_exit_rules_only_target_pre_existing_exits(built_world, world_modules):
    """`rules.set_rules` must never invent an Entrance -- every rule it
    applies has to land on an exit `regions.create_regions` already built
    from `data/regions.py`'s own `exits` (verified at the `data/`
    generation layer too, see tests/test_rules.py, but re-checked here at
    the AP-object level)."""
    exit_rules = world_modules["data.rules"].EXIT_RULES
    regions_data = world_modules["data.regions"].REGIONS
    for src, dest in exit_rules:
        assert dest in regions_data[src]["exits"]
        source_region = built_world.regions[src]
        assert any(exit_.connected_region is built_world.regions[dest] for exit_ in source_region.exits)
