# location_flags.py
#
# Maps data/locations.py keys to the vanilla savedata flag id that fires
# when that location's check is triggered in-game (check detection: read
# the existing savedata flag bits directly, no ROM patch needed), and the
# reverse (flag id -> AP location id) map client.py's game_watcher polls.

from __future__ import annotations

from data.locations import LOCATIONS
from locations import SHELVED_LOCATION_TYPES, create_location_label_to_code_map
from save_layout import HIDDEN_ITEMS_FLAG_BASE

# Location types whose data/locations.py `id` is already a real vanilla
# savedata flag id. `hidden_item` is excluded: its id is a small
# HIDDENITEM_* index, not a flag id directly.
_DIRECT_FLAG_ID_TYPES = {"ground_item", "npc_gift", "hm_tm"}

# npc_gift locations with no single-purpose FLAG_GOT_* constant get a
# synthetic id in this reserved band instead -- no real vanilla savedata
# flag to read, so check detection can't observe them via RAM.
_SYNTHETIC_ID_BASE = 9000


def flag_id_for_location(location_key: str) -> int | None:
    """The vanilla savedata flag id that fires when `location_key`'s check
    is triggered in-game, or None if this client can't currently observe
    it (badges, shelved types, synthetic-id npc_gift band)."""
    data = LOCATIONS.get(location_key)
    if data is None:
        raise KeyError(f"unknown location key: {location_key!r}")

    location_type = data["type"]
    raw_id = data.get("id")

    if location_type == "badge" or location_type in SHELVED_LOCATION_TYPES or raw_id is None:
        return None
    if location_type in _DIRECT_FLAG_ID_TYPES:
        return None if raw_id >= _SYNTHETIC_ID_BASE else raw_id
    if location_type == "hidden_item":
        return HIDDEN_ITEMS_FLAG_BASE + raw_id
    return None


def build_flag_id_to_ap_location_id() -> dict[int, int]:
    """flag id -> AP location id, for every location this client can
    actually detect via a savedata flag read. Uses `locations.py`'s own id
    assignment (`create_location_label_to_code_map`) so the ids returned
    always match what `HeartGoldWorld.location_name_to_id` hands out."""
    ap_ids = create_location_label_to_code_map()
    result: dict[int, int] = {}
    for key in LOCATIONS:
        flag_id = flag_id_for_location(key)
        if flag_id is None:
            continue
        ap_id = ap_ids.get(key)
        if ap_id is None:
            raise KeyError(f"location {key!r} has a flag id but no AP location id")
        result[flag_id] = ap_id
    return result


def build_locally_substituted_ap_location_ids() -> set[int]:
    """AP location ids of every ground_item/npc_gift/hm_tm/hidden_item
    location (the same set output_patch.build_item_substitutions can
    ROM-substitute) -- used by client.py to recognize a received item
    that was already physically delivered by ROM substitution, so it
    never gets written into the Bag a second time. See NOTES.md for the
    real double-delivery bug this fixes."""
    ap_ids = create_location_label_to_code_map()
    result: set[int] = set()
    for key, data in LOCATIONS.items():
        if data["type"] not in ("ground_item", "npc_gift", "hm_tm", "hidden_item"):
            continue
        ap_id = ap_ids.get(key)
        if ap_id is not None:
            result.add(ap_id)
    return result


def unsupported_location_keys() -> list[str]:
    """Location keys with a real AP location that this client cannot
    detect via a savedata flag read. Exposed for diagnostics/logging, not
    used in the hot polling path."""
    return sorted(
        key
        for key in LOCATIONS
        if LOCATIONS[key]["type"] != "badge"
        and LOCATIONS[key]["type"] not in SHELVED_LOCATION_TYPES
        and flag_id_for_location(key) is None
    )
