# location_flags.py
#
# Task C16 -- maps `data/locations.py` keys to the vanilla savedata flag id
# that fires when that location's check is triggered in-game (the
# check-detection mechanism designed in docs/architecture.md's "## C14"
# section: "read the existing `FLAG_HIDE_ITEMBALL_*` (etc.) savedata bits
# directly -- no ROM patch needed"), and the reverse (flag id -> AP location
# id) map `client.py`'s `game_watcher` actually polls against.
#
# Needs the generated `data/` package (`data.locations.LOCATIONS`), same as
# `locations.py` itself -- no BizHawk/Archipelago-core import, so this is
# importable/testable the same way `locations.py`/`items.py` are (see
# tests/test_client.py).

from __future__ import annotations

from data.locations import LOCATIONS

from locations import SHELVED_LOCATION_TYPES, create_location_label_to_code_map
from save_layout import HIDDEN_ITEMS_FLAG_BASE

# Location types whose `data/locations.py` `id` is already a real vanilla
# savedata flag id (see data_gen/locations.toml's own header, and
# rom/eventscriptdata.py's `BLOCK_INDEX_BY_ITEMBALL_FLAG_ID`, whose keys --
# e.g. 1081, 1056 -- are real `FLAG_HIDE_ITEMBALL_*` values, confirming
# ground_item ids need no transform). `hidden_item` is deliberately excluded
# here: its `id` is a small `HIDDENITEM_*` index, not a flag id directly
# (see `_flag_id_for_location` below).
_DIRECT_FLAG_ID_TYPES = {"ground_item", "npc_gift", "hm_tm"}

# npc_gift locations with no single-purpose `FLAG_GOT_*` constant get a
# synthetic id in this reserved band instead (data_gen/locations.toml's own
# header: "a handful of gifts have no single-purpose FLAG_GOT_* constant
# ... and get a sequential id in a reserved 9000+ band instead"). These have
# no real vanilla savedata flag to read -- check-detection cannot currently
# observe them via a RAM flag read. `hm_tm` locations routed through the
# npc_gift delivery mechanism could in principle also land in this band,
# hence checking it generically here rather than assuming it only affects
# `type == "npc_gift"`.
_SYNTHETIC_ID_BASE = 9000


def flag_id_for_location(location_key: str) -> int | None:
    """The vanilla savedata flag id that fires when `location_key`'s check
    is triggered in-game, or `None` if this location has no such flag this
    client can currently observe (badge locations -- never real AP
    locations to begin with, see `locations.py`'s own module docstring --
    shelved-type locations -- also never real AP locations, see
    `locations.SHELVED_LOCATION_TYPES` -- and the synthetic-id npc_gift band
    above)."""
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
        # Currently unreachable (hidden_item is in SHELVED_LOCATION_TYPES,
        # caught above) -- the transform itself is real, live-verified ROM
        # knowledge (see docs/architecture.md), kept ready for when
        # hidden_item is reconnected.
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
            # Should not happen (badges and shelved-type locations are the
            # only LOCATIONS entries missing from
            # create_location_label_to_code_map, and both never reach here
            # -- flag_id_for_location returns None for them above), but
            # never silently drop a real flag mapping.
            raise KeyError(f"location {key!r} has a flag id but no AP location id")
        result[flag_id] = ap_id
    return result


def unsupported_location_keys() -> list[str]:
    """Location keys with a real AP location that this client cannot detect
    via a savedata flag read (currently: only the synthetic-id npc_gift/
    hm_tm band, see this module's own docstring) -- exposed for
    diagnostics/logging, not used in the hot polling path. Badge and
    shelved-type (locations.SHELVED_LOCATION_TYPES) keys are excluded here
    too -- they have no real AP location to begin with, so "undetectable"
    doesn't apply to them the same way."""
    return sorted(
        key
        for key in LOCATIONS
        if LOCATIONS[key]["type"] != "badge"
        and LOCATIONS[key]["type"] not in SHELVED_LOCATION_TYPES
        and flag_id_for_location(key) is None
    )
