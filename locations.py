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

from collections.abc import Callable, Container, Mapping
from typing import Any

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


# Dexsanity (task M3.4) access rules: species.species_encounter_sources
# reports the (zone_key, method) pairs a species actually appears in in
# this seed. `method` decides which bag item is needed:
# _UNGATED_DEXSANITY_METHODS need none at all (walk into the grass, or
# Headbutt a tree -- a Gen4 tutor move, not an HM, see data_gen/rules.toml's
# header), the rest each need a specific one -- an HM+badge pair for
# surf/rock_smash (same data/rules.py BADGES this module already uses for
# badge locations), or just the matching rod for fishing (rods are ungated
# key items, no badge needed to use one already in the bag).
#
# `zone_key` decides *where*, and is the half this used to be missing
# (fixed 2026-08-22): a data/encounters.py zone key is also a
# data/regions.py region key (all 137 of them, asserted by
# tests/test_encounters.py::test_every_zone_key_is_a_known_region), so the
# species' own region is directly usable in the rule. Without it, a
# species living only behind a gate (the real dead seed: Tropius in the
# Burned Tower, holding the Squirtbottle that unlocks Ecruteak, which is
# the only way into that tower) counted as sphere-0 free and the fill
# happily built a circular dependency.
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


def dexsanity_sources_within_regions(
    species_sources: dict[str, frozenset[tuple[str, str]]], region_keys: Container[str]
) -> dict[str, frozenset[tuple[str, str]]]:
    """`species_sources` (species.species_encounter_sources output) with
    every pair whose zone has no Region in `region_keys` dropped, and every
    species left with no pair at all dropped too. `johto_only` is the only
    caller-visible case: a species this seed only placed in Kanto has no
    catchable location once Kanto's regions are never created, so it must
    get no Dexsanity Location -- and, just as importantly, no filler item
    in the pool either. Shared by create_locations below and __init__.py's
    create_items precisely so the two can never disagree on the count."""
    filtered = {
        species: frozenset(source for source in sources if source[0] in region_keys)
        for species, sources in species_sources.items()
    }
    return {species: sources for species, sources in filtered.items() if sources}


def _dexsanity_method_requirement(player: int, method: str) -> Callable[[CollectionState], bool] | None:
    """The bag-item check for one encounter method, or None when the
    method needs nothing at all."""
    if method in _UNGATED_DEXSANITY_METHODS:
        return None
    if method in _DEXSANITY_HM_METHOD_REQUIREMENTS:
        item_key, badge_name = _DEXSANITY_HM_METHOD_REQUIREMENTS[method]
        item_label = ITEMS[item_key]["label"]
        badge_label = badge_item_label(badge_name)
        return lambda state: state.has(item_label, player) and state.has(badge_label, player)
    if method in _DEXSANITY_ROD_METHOD_REQUIREMENTS:
        item_label = ITEMS[_DEXSANITY_ROD_METHOD_REQUIREMENTS[method]]["label"]
        return lambda state: state.has(item_label, player)
    raise ValueError(f"unknown Dexsanity encounter method: {method!r}")


def _dexsanity_access_rule(
    player: int, sources: frozenset[tuple[str, str]], regions: dict[str, Region]
) -> Callable[[CollectionState], bool]:
    """An OR across every place this seed actually put the species: each
    branch is "reach that region AND own what that method needs", and the
    cheapest branch is enough even when the same species also lives
    somewhere much deeper. `sources` must already be filtered to zones
    that have a Region (dexsanity_sources_within_regions above).

    Region objects are captured directly rather than looked up through
    `state.can_reach_region(name, player)` on every call: `Region.can_reach`
    is a cached set membership, so this reduces each branch to that lookup
    plus at most two `state.has` calls -- worth doing on a rule the fill
    re-evaluates for up to ~460 locations on every sweep.

    Branches are collapsed per region and the ungated ones sorted first, so
    a species in one region through both grass and Surf costs a single
    membership test in the common case."""
    per_region: dict[str, set[str]] = {}
    for zone_key, method in sources:
        per_region.setdefault(zone_key, set()).add(method)

    branches: list[tuple[Region, Callable[[CollectionState], bool] | None]] = []
    for zone_key in sorted(per_region):
        methods = per_region[zone_key]
        region = regions[zone_key]
        if methods & _UNGATED_DEXSANITY_METHODS:
            branches.append((region, None))
            continue
        for method in sorted(methods):
            branches.append((region, _dexsanity_method_requirement(player, method)))
    branches.sort(key=lambda branch: branch[1] is not None)

    def rule(state: CollectionState) -> bool:
        return any(
            region.can_reach(state) and (requirement is None or requirement(state))
            for region, requirement in branches
        )

    return rule


class HeartGoldLocation(Location):
    game: str = "Pokemon HGSS"


def create_location_label_to_code_map() -> dict[str, int]:
    """`data/locations.py` key -> id, unique within this world. `type =
    'event'` locations are excluded (see module docstring)."""
    return {key: HEARTGOLD_LOCATION_ID_BASE + index for key, index in _LOCATION_INDEX.items()}


def location_region_key(data: Mapping[str, Any], soulsilver: bool) -> str:
    """The `data/regions.py` key a `data/locations.py` entry belongs to in
    the generated version. `region` is the HeartGold one; an entry whose
    NPC stands elsewhere in SoulSilver carries a `soulsilver_region`
    override (the two wings: the Radio Tower director and the Pewter old
    man swap which wing they give, scr_seq_0034_D23R0106.s:75-86 and
    scr_seq_0750_T03.s:48-75). Every consumer of a location's region must
    go through this, or a SoulSilver seed places the check in the wrong
    half of the map."""
    if soulsilver:
        return data.get("soulsilver_region", data["region"])
    return data["region"]


def get_location_region(key: str, soulsilver: bool = False) -> str:
    """The `data/regions.py` key of `key`'s parent region."""
    return location_region_key(LOCATIONS[key], soulsilver)


DOWSING_MACHINE_ITEM_LABEL = ITEMS["dowsing_mchn"]["label"]


def _hidden_item_access_rule(player: int) -> Callable[[CollectionState], bool]:
    return lambda state: state.has(DOWSING_MACHINE_ITEM_LABEL, player)


# Vanilla gates that block a single *location* rather than a region exit, so
# they cannot live in data_gen/rules.toml's [[exit_rule]] table (that one
# only ever restricts an edge of the region graph): the room is reachable,
# the check inside it is not yet available. Each entry maps a
# data/locations.py key to the data/items.py keys its own vanilla story flag
# depends on.
#
# - olivine_gym_badge (verrou A8, 2026-08-23): Jasmine is not in her gym at
#   all until the Secret Potion has been delivered to Amphy.
#   FLAG_HIDE_JASMINE_IN_GYM is set at new game (scr_seq_0149.s:32) and only
#   cleared by the Olivine Lighthouse light-room script, right after its
#   `TakeItem ITEM_SECRETPOTION` (scr_seq_0066_D27R0107.s:69). The gym
#   region itself stays freely enterable, which is why this is not an exit
#   rule -- but the Mineral Badge inside it is not obtainable, and it is one
#   of the 8 badges the Elite Four gate asks for.
_ITEM_GATED_LOCATIONS: dict[str, tuple[str, ...]] = {
    "olivine_gym_badge": ("secretpotion",),
}

# Locations that cannot exist when the `magnet_train` option is on, because
# the client then pre-sets FLAG_RESTORED_POWER (client.py's
# _apply_power_plant_prerestored) and the scene that hands them out never
# plays. The Power Plant manager's TM57 is only given inside the repair
# block itself (scr_seq_0196_R10R0202.s:40-56, on the BROKEN map's script,
# behind `HasItem ITEM_MACHINE_PART`), and Route 10's door warps to the
# broken map only while that flag is clear (scr_seq_0191_R10.s:135 jumps to
# the `Warp MAP_ROUTE_10_POWER_PLANT_REPAIRED` branch as soon as it is set).
# The repaired map's manager (scr_seq_0195_R10R0201.s) only talks. Left in
# the pool, whatever the fill put there would be lost for good.
POWER_PLANT_PRERESTORED_SKIPPED_LOCATION_KEYS = frozenset({"route_10_power_plant_broken_tm57"})

# The reverse case: locations that need the Power Plant repaired while
# `magnet_train` is OFF. The Copycat only trades the Pass for the Lost Item,
# and the Fan Club chairman who hands that item out only appears once the
# repair block runs `ClearFlag FLAG_HIDE_VERMILION_FAN_CLUB_LOST_ITEM`
# (scr_seq_0196_R10R0202.s:63). On, the client clears that flag itself
# (client.py's _COPYCAT_CHAIN_FLAGS_TO_CLEAR) and the event is true from the
# start, so no rule is attached. Value: rules.POWER_PLANT_EVENT, spelled out
# here because rules.py imports this module.
POWER_PLANT_GATED_LOCATION_KEYS = frozenset({"saffron_copycat_house_2f_pass"})
_POWER_PLANT_EVENT = "power_plant_restored"


def _item_gated_access_rule(player: int, item_keys: tuple[str, ...]) -> Callable[[CollectionState], bool]:
    """Own every one of `item_keys` (data/items.py keys). Same shape as
    `_hidden_item_access_rule`, generalized over several items."""
    item_labels = tuple(ITEMS[key]["label"] for key in item_keys)
    return lambda state: all(state.has(label, player) for label in item_labels)


def create_locations(
    player: int,
    regions: dict[str, Region],
    *,
    trainersanity: bool = False,
    dexsanity: bool = False,
    dexsanity_species_sources: dict[str, frozenset[tuple[str, str]]] | None = None,
    legendarysanity: bool = False,
    hidden_items_require_dowsing_machine: bool = False,
    excluded_region_keys: frozenset[str] = frozenset(),
    bicycle_enabled: bool = False,
    power_plant_prerestored: bool = False,
    soulsilver: bool = False,
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
    `species` key is present in `dexsanity_species_sources` (i.e. this
    seed's own randomized wild-encounter tables actually place that species
    somewhere the ROM patcher genuinely writes) -- caller passes
    species.species_encounter_sources(world.generated_encounters,
    source_filter=rom.encounterdata.zone_method_is_written) here, so the
    location count legitimately varies from seed to seed. Each one gets
    `_dexsanity_access_rule`, which requires reaching a region the species
    actually lives in. `type = 'static_pokemon'` locations
    (Ho-Oh/Lugia) work the same way, gated on `legendarysanity` -- off by
    default, matching every other Pokemon Archipelago world, which leaves
    static legendary encounters entirely vanilla rather than tracking
    them as a check. `type = 'hidden_item'` locations get an access_rule
    requiring the Dowsing Machine when `hidden_items_require_dowsing_
    machine` is set -- off by default, since vanilla never actually
    requires it to pick up an already-known hidden item (it's purely a
    detection aid). Locations listed in `_ITEM_GATED_LOCATIONS` get an
    access_rule of their own for a vanilla story gate that blocks the check
    itself rather than the way to its region (see that constant). `excluded_region_keys` (`johto_only`'s
    regions.KANTO_REGION_KEYS, or empty) skips any location whose own
    `region` is excluded -- must be the exact same region set passed to
    `regions.create_regions`, or `regions[data["region"]]` below raises
    KeyError for a location whose parent Region was never created.
    `goldenrod_bike_shop_bicycle` (a plain `type = 'npc_gift'` entry) is
    only created when `bicycle_enabled` (`randomize_bicycle`) is set --
    same reasoning as `trainersanity`/`legendarysanity` above, just keyed
    by a specific location rather than a whole type. The same goes for
    `POWER_PLANT_PRERESTORED_SKIPPED_LOCATION_KEYS`, skipped when
    `power_plant_prerestored` (`magnet_train` on) is set. The `randomize_bag`/
    `randomize_trainer_card`/`randomize_pokedex`/`randomize_options_
    button`/`randomize_save_button`/`randomize_pokegear` per-icon toggles
    this project briefly had (task "randomize_menu_unlocks", 2026-08-17)
    were all removed the same day: a live playtest found the compiled
    Start Menu's own icon-confirm dispatch breaks whenever any icon
    *before* Save/Options in ring order is unavailable while later ones
    are visible -- an invariant only ever true in vanilla (every one of
    these flags is set together, in one uninterrupted scene), which a
    randomized, possibly-long-delayed unlock necessarily violates. No
    client-side-only fix exists (the dispatch logic is compiled, and this
    project avoids ASM hooks after 2 real hook crashes earlier in its own
    history) -- so Bag/Trainer Card/Pokedex/Save/Options/Pokegear are all
    once again always unconditionally granted by their own real vanilla
    trigger, like before this feature existed. `soulsilver` (the
    `game_version` option) picks each entry's region through
    `location_region_key`."""
    id_map = create_location_label_to_code_map()
    # Pre-filtered once, not per location: `regions` is the authoritative
    # set of Regions that exist for this player (johto_only drops Kanto's).
    reachable_sources = dexsanity_sources_within_regions(dexsanity_species_sources or {}, regions)
    for key, data in LOCATIONS.items():
        if data["type"] in SHELVED_LOCATION_TYPES:
            continue
        region_key = location_region_key(data, soulsilver)
        if region_key in excluded_region_keys:
            continue
        if data["type"] == "trainer" and not trainersanity:
            continue
        if data["type"] == "static_pokemon" and not legendarysanity:
            continue
        if key == "goldenrod_bike_shop_bicycle" and not bicycle_enabled:
            continue
        if power_plant_prerestored and key in POWER_PLANT_PRERESTORED_SKIPPED_LOCATION_KEYS:
            continue
        sources: frozenset[tuple[str, str]] | None = None
        if data["type"] == "dexsanity":
            if not dexsanity:
                continue
            sources = reachable_sources.get(data["species"])
            if sources is None:
                continue
        region = regions[region_key]
        if data["type"] == "event":
            location = HeartGoldLocation(player, key, None, region)
            location.place_locked_item(
                HeartGoldItem(scenario_event_item_name(data["event"]), ItemClassification.progression, None, player)
            )
        else:
            location = HeartGoldLocation(player, key, id_map[key], region)
            if data["type"] == "dexsanity":
                assert sources is not None
                location.access_rule = _dexsanity_access_rule(player, sources, regions)
            elif data["type"] == "hidden_item" and hidden_items_require_dowsing_machine:
                location.access_rule = _hidden_item_access_rule(player)
            elif key in _ITEM_GATED_LOCATIONS:
                location.access_rule = _item_gated_access_rule(player, _ITEM_GATED_LOCATIONS[key])
            elif key in POWER_PLANT_GATED_LOCATION_KEYS and not power_plant_prerestored:
                event_item = scenario_event_item_name(_POWER_PLANT_EVENT)
                location.access_rule = lambda state, event_item=event_item: state.has(event_item, player)
        region.locations.append(location)
