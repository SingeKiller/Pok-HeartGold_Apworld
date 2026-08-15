# locations.py
#
# Archipelago location id map + create_locations, attaching Location
# objects to the Region graph from regions.create_regions, for every entry
# of the generated data/locations.py.
#
# data/locations.py's own `id` field is NOT globally unique (it recycles
# small per-table indices across different in-game tables), so this module
# assigns its own stable id (sorted by location key), offset by
# HEARTGOLD_LOCATION_ID_BASE. `type = 'badge'` locations are real, fillable
# locations like ground_item/npc_gift (task "Badges comme vrais items AP",
# 2026-08-15) -- each has an `original_item` (a synthetic data/items.py
# `badge_*` entry) and a `trainer` field (the gym Leader's own data/
# trainers.py key, used for check detection the same way `type = 'trainer'`
# locations already are). Only `type = 'event'` locations (data_gen/
# rules.toml's scenario/story gates, e.g. having defeated the Elite Four)
# still work the old way: locked AP events with no address, gated via
# scenario_event_item_name.

from __future__ import annotations

from collections.abc import Callable

from BaseClasses import CollectionState, ItemClassification, Location, Region

from data.items import ITEMS
from data.locations import LOCATIONS
from items import HeartGoldItem

HEARTGOLD_LOCATION_ID_BASE = 201_000_000

SCENARIO_EVENT_ITEM_PREFIX = "Event - "

# Location types with no real item to place (locked AP event locations
# instead, address=None) -- excluded from id assignment and the real item
# pool the same way.
_LOCKED_EVENT_LOCATION_TYPES = {"event"}

# Reusable mechanism for excluding a location type from the AP pool
# entirely (a type whose ROM delivery is broken/unimplemented). Currently
# empty.
SHELVED_LOCATION_TYPES: set[str] = set()

_ID_ASSIGNABLE_KEYS = sorted(
    key
    for key, data in LOCATIONS.items()
    if data["type"] not in _LOCKED_EVENT_LOCATION_TYPES and data["type"] not in SHELVED_LOCATION_TYPES
)
_LOCATION_INDEX: dict[str, int] = {key: index for index, key in enumerate(_ID_ASSIGNABLE_KEYS)}


def badge_item_label(badge_name: str) -> str:
    """The AP item label for the badge_<badge_name> synthetic item (a
    `data/rules.py` `BADGES` key, e.g. "zephyr") -- what state.has(...)
    checks against once badges are real, tradeable items rather than
    locked events."""
    return ITEMS[f"badge_{badge_name}"]["label"]


def scenario_event_item_name(event_name: str) -> str:
    """AP event-item name granted when the `type = 'event'` location for
    `event_name` (a `data/locations.py` entry's own `event` field, e.g.
    "elite_four_defeated") is checked."""
    return f"{SCENARIO_EVENT_ITEM_PREFIX}{event_name}"


# Dexsanity (task M3.4) access rules: species.species_encounter_methods
# reports which of these method names a species is obtainable through in
# this seed; _UNGATED_DEXSANITY_METHODS need no item at all (present
# anywhere in vanilla grass or a headbutt tree), the rest each need a
# specific bag item -- an HM+badge pair for surf/rock_smash (same
# data/rules.py BADGES this module already uses for badge locations), or
# just the matching rod for fishing (data_gen/rules.toml's own header: rods
# are ungated key items, no badge needed to use one already in the bag).
_UNGATED_DEXSANITY_METHODS = frozenset({"land", "headbutt"})
_DEXSANITY_HM_METHOD_REQUIREMENTS: dict[str, tuple[str, str]] = {
    "surf": ("hm03", "fog"),
    "rock_smash": ("hm06", "zephyr"),
}
_DEXSANITY_ROD_METHOD_REQUIREMENTS: dict[str, str] = {
    "old_rod": "old_rod",
    "good_rod": "good_rod",
    "super_rod": "super_rod",
}


def _dexsanity_access_rule(player: int, methods: frozenset[str]) -> Callable[[CollectionState], bool] | None:
    """None means unconditionally accessible (methods includes land or
    headbutt); otherwise an OR across every gated method the species is
    obtainable through in this seed -- the cheapest one is enough, even if
    the same species also needs something harder somewhere else."""
    if methods & _UNGATED_DEXSANITY_METHODS:
        return None

    sub_rules: list[Callable[[CollectionState], bool]] = []
    for method in methods:
        if method in _DEXSANITY_HM_METHOD_REQUIREMENTS:
            item_key, badge_name = _DEXSANITY_HM_METHOD_REQUIREMENTS[method]
            item_label = ITEMS[item_key]["label"]
            badge_label = badge_item_label(badge_name)
            sub_rules.append(
                lambda state, item_label=item_label, badge_label=badge_label: (
                    state.has(item_label, player) and state.has(badge_label, player)
                )
            )
        elif method in _DEXSANITY_ROD_METHOD_REQUIREMENTS:
            item_label = ITEMS[_DEXSANITY_ROD_METHOD_REQUIREMENTS[method]]["label"]
            sub_rules.append(lambda state, item_label=item_label: state.has(item_label, player))

    def rule(state: CollectionState) -> bool:
        return any(sub_rule(state) for sub_rule in sub_rules)

    return rule


class HeartGoldLocation(Location):
    game: str = "Pokemon HGSS"


def create_location_label_to_code_map() -> dict[str, int]:
    """`data/locations.py` key -> id, unique within this world. `type =
    'event'` locations are excluded (see module docstring)."""
    return {key: HEARTGOLD_LOCATION_ID_BASE + index for key, index in _LOCATION_INDEX.items()}


def get_location_region(key: str) -> str:
    """The `data/regions.py` key of `key`'s parent region."""
    return LOCATIONS[key]["region"]


def create_locations(
    player: int,
    regions: dict[str, Region],
    *,
    trainersanity: bool = False,
    dexsanity: bool = False,
    dexsanity_species_methods: dict[str, frozenset[str]] | None = None,
    legendarysanity: bool = False,
) -> None:
    """Create a `HeartGoldLocation` for every `data/locations.py` entry and
    attach it to its parent `Region` (as built by
    `regions.create_regions`). `type = 'event'` locations get a locked
    progression event item instead of a real address (see module
    docstring). `type = 'trainer'` locations (task M3.3, Trainersanity)
    are real, fillable locations, but only created at all when
    `trainersanity` is set -- unlike SHELVED_LOCATION_TYPES (a fixed,
    process-wide constant), this is per-call/per-player, since it's driven
    by this player's own `trainersanity` option, not a global toggle.
    `type = 'dexsanity'` locations (task M3.4) work the same way, gated on
    `dexsanity`, but additionally only created per-entry when that entry's
    `species` key is present in `dexsanity_species_methods` (i.e. this
    seed's own randomized wild-encounter tables actually place that species
    somewhere) -- caller passes species.species_encounter_methods(world.
    generated_encounters) here. `type = 'static_pokemon'` locations
    (Ho-Oh/Lugia) work the same way, gated on `legendarysanity` -- off by
    default, matching every other Pokemon Archipelago world, which leaves
    static legendary encounters entirely vanilla rather than tracking
    them as a check."""
    id_map = create_location_label_to_code_map()
    for key, data in LOCATIONS.items():
        if data["type"] in SHELVED_LOCATION_TYPES:
            continue
        if data["type"] == "trainer" and not trainersanity:
            continue
        if data["type"] == "static_pokemon" and not legendarysanity:
            continue
        methods: frozenset[str] | None = None
        if data["type"] == "dexsanity":
            if not dexsanity:
                continue
            methods = (dexsanity_species_methods or {}).get(data["species"])
            if methods is None:
                continue
        region = regions[data["region"]]
        if data["type"] == "event":
            location = HeartGoldLocation(player, key, None, region)
            location.place_locked_item(
                HeartGoldItem(scenario_event_item_name(data["event"]), ItemClassification.progression, None, player)
            )
        else:
            location = HeartGoldLocation(player, key, id_map[key], region)
            if data["type"] == "dexsanity":
                assert methods is not None
                rule = _dexsanity_access_rule(player, methods)
                if rule is not None:
                    location.access_rule = rule
        region.locations.append(location)
