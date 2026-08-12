# locations.py
#
# Archipelago location id map + create_locations, attaching Location
# objects to the Region graph from regions.create_regions, for every entry
# of the generated data/locations.py.
#
# data/locations.py's own `id` field is NOT globally unique (it recycles
# small per-table indices across different in-game tables), so this module
# assigns its own stable id (sorted by location key), offset by
# HEARTGOLD_LOCATION_ID_BASE. Badge locations have no real item to place
# (HGSS badges are save-data flags, not bag items) -- they're locked AP
# event locations instead (address=None), gated via badge_event_item_name.

from __future__ import annotations

from BaseClasses import ItemClassification, Location, Region

from data.locations import LOCATIONS
from data.rules import BADGES
from items import HeartGoldItem

HEARTGOLD_LOCATION_ID_BASE = 201_000_000

BADGE_EVENT_ITEM_PREFIX = "Badge Obtained - "

# Reusable mechanism for excluding a location type from the AP pool
# entirely (a type whose ROM delivery is broken/unimplemented). Currently
# empty.
SHELVED_LOCATION_TYPES: set[str] = set()

_ID_ASSIGNABLE_KEYS = sorted(
    key for key, data in LOCATIONS.items() if data["type"] != "badge" and data["type"] not in SHELVED_LOCATION_TYPES
)
_LOCATION_INDEX: dict[str, int] = {key: index for index, key in enumerate(_ID_ASSIGNABLE_KEYS)}

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
        if data["type"] in SHELVED_LOCATION_TYPES:
            continue
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
