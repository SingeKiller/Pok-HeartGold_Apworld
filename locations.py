# locations.py
#
# Archipelago location definitions for the HeartGold & SoulSilver world: an
# id map plus `create_locations`, which attaches `Location` objects to the
# `Region` graph built by `regions.create_regions` for every entry of the
# generated `data/locations.py` (586 locations). Follows the same overall
# shape as `ressources/platinum_archipelago/locations.py` (read-only
# reference, not copied).
#
# `data/locations.py`'s own `id` field is NOT globally unique across all 586
# locations (it recycles small per-table indices -- hidden-item table
# indices, item-ball flag offsets, badge indices -- across different
# in-game tables, so the same small integer legitimately appears more than
# once, e.g. both `bellchime_tower_tinymushroom_2` and `ilex_forest_hm01`
# have `id == 128`). This module assigns its own stable id instead (sorted
# by location key, for a deterministic, reviewable ordering), offset by
# `HEARTGOLD_LOCATION_ID_BASE`.
#
# Badge-type locations have no `original_item` in `data/locations.py` at all
# (see `tests/test_locations.py::test_all_eight_johto_badges_present` et
# al.) -- HGSS badges are save-data flags, not bag items, so there is
# nothing to place/randomize there. They are instead built as locked AP
# "event" locations (address=None) carrying a progression event item (see
# `items.py`'s module docstring), matching the standard Archipelago pattern
# for a non-item in-game milestone. `rules.py` reads the event item names
# via `badge_event_item_name` to gate HM field-use on badge ownership.
#
# No randomization logic lives here (see task brief) -- just the id map and
# the Location/Region wiring.

from __future__ import annotations

from BaseClasses import ItemClassification, Location, Region
from data.locations import LOCATIONS
from data.rules import BADGES

from items import HeartGoldItem

# See docs/architecture.md, Spike 4 (same convention as items.py's
# HEARTGOLD_ITEM_ID_BASE, offset into a separate, non-overlapping range).
HEARTGOLD_LOCATION_ID_BASE = 201_000_000

BADGE_EVENT_ITEM_PREFIX = "Badge Obtained - "

# Deterministic id assignment: sorted by location key. Badge-type locations
# are excluded here -- they are events (address=None), which never get a
# real Archipelago location id (see module docstring).
_ID_ASSIGNABLE_KEYS = sorted(key for key, data in LOCATIONS.items() if data["type"] != "badge")
_LOCATION_INDEX: dict[str, int] = {key: index for index, key in enumerate(_ID_ASSIGNABLE_KEYS)}

# data/locations.py badge entries' own `id` field is the badge's index into
# data/rules.py's BADGES table (see tests/test_locations.py witnesses,
# e.g. violet_gym_badge id == 0 == BADGES["zephyr"]), not a location id.
_BADGE_INDEX_TO_NAME: dict[int, str] = {index: name for name, index in BADGES.items()}


def badge_event_item_name(badge_name: str) -> str:
    """AP event-item name granted when the badge location for `badge_name`
    (a `data/rules.py` `BADGES` key, e.g. "zephyr") is checked."""
    return f"{BADGE_EVENT_ITEM_PREFIX}{badge_name}"


class HeartGoldLocation(Location):
    game: str = "Pokemon HeartGold"


def create_location_label_to_code_map() -> dict[str, int]:
    """`data/locations.py` key -> id, unique within this world. Badge
    locations are excluded (see module docstring)."""
    return {key: HEARTGOLD_LOCATION_ID_BASE + index for key, index in _LOCATION_INDEX.items()}


def get_location_region(key: str) -> str:
    """The `data/regions.py` key of `key`'s parent region."""
    return LOCATIONS[key]["region"]


def create_locations(player: int, regions: dict[str, Region]) -> None:
    """Create a `HeartGoldLocation` for every `data/locations.py` entry and
    attach it to its parent `Region` (as built by
    `regions.create_regions`). Badge-type locations get a locked
    progression event item instead of a real address (see module
    docstring)."""
    id_map = create_location_label_to_code_map()
    for key, data in LOCATIONS.items():
        region = regions[data["region"]]
        if data["type"] == "badge":
            badge_name = _BADGE_INDEX_TO_NAME[data["id"]]
            location = HeartGoldLocation(player, key, None, region)
            location.place_locked_item(
                HeartGoldItem(badge_event_item_name(badge_name), ItemClassification.progression, None, player)
            )
        else:
            location = HeartGoldLocation(player, key, id_map[key], region)
        region.locations.append(location)
