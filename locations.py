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

from BaseClasses import CollectionState, ItemClassification, Location, LocationProgressType, Region

from data.items import ITEMS
from data.locations import LOCATIONS
from data.rules import HM_BADGES, HM_ITEMS
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
# _UNGATED_DEXSANITY_METHODS need none at all (walk into the grass),
# headbutt needs the Headbutt tutor (a Gen4 tutor move, not an HM, see
# _HEADBUTT_TUTOR_REGION), the rest each need a specific one -- an HM+badge pair for
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
_UNGATED_DEXSANITY_METHODS = frozenset({"land"})
# The Headbutt tutor (obj_D36R0101_gsbigman at (36, 37), script
# scr_seq_0092_D36R0101.s:1149 `SetMonMove ... MOVE_HEADBUTT`) stands past
# Ilex Forest's Cut tree when coming from Azalea (ROM collision flood fill,
# 2026-09-17), i.e. in `ilex_forest_north`. HGSS has no Headbutt TM, so
# reaching him is what the headbutt tables need (headbutt tables are in
# the ROM since v0.2.5, rom/encounterdata.write_headbutt_tables). Assumes
# some party member can learn it, which nearly every species can.
_HEADBUTT_TUTOR_REGION = "ilex_forest_north"

# (zone, method) pairs whose table is only usable from a sub-region of the
# zone's own region. Route 14's only tall grass sits behind a Cut tree
# (data_gen/regions.toml's [route_14_grass]). The rest were found on
# 2026-09-23 by checking every table against the ROM's own encounter tiles
# (grass/cave floor, surfable water, water next to a walkable tile for the
# rods): Route 2's northern table is rolled in the grass by Pewter, not on
# the Diglett's Cave side it was filed under, and Route 27's grass is all on
# the Tohjo Falls side, not on the shore reached by surfing from New Bark.
DEXSANITY_ZONE_METHOD_REGIONS: dict[tuple[str, str], str] = {
    ("route_14", "land"): "route_14_grass",
    ("route_2_east", "land"): "route_2_north",
    ("route_27", "land"): "route_27_east",
    ("cliff_edge_gate", "surf"): "cliff_edge_gate_rock_climb_surf",
    ("cliff_edge_gate", "old_rod"): "cliff_edge_gate_rock_climb_surf",
    ("cliff_edge_gate", "good_rod"): "cliff_edge_gate_rock_climb_surf",
    ("cliff_edge_gate", "super_rod"): "cliff_edge_gate_rock_climb_surf",
    ("dragons_den", "old_rod"): "dragons_den_water",
    ("dragons_den", "good_rod"): "dragons_den_water",
    ("dragons_den", "super_rod"): "dragons_den_water",
    ("cerulean", "old_rod"): "cerulean_river",
    ("cerulean", "good_rod"): "cerulean_river",
    ("cerulean", "super_rod"): "cerulean_river",
    # 2026-09-27 Sudowoodo audit (ROM walk with the tree as a wall): all 44
    # reachable grass tiles of Route 36 are south-west of the tree, none on
    # the Violet side the `route_36` zone key belongs to. Its headbutt
    # trees stay on `route_36` (the Violet side has every tree column).
    ("route_36", "land"): "route_36_west",
    # The National Park's five secret headbutt trees (80-82, 15-21) stand on
    # the Rock Climb ledge, the 22 others need nothing.
    ("national_park", "headbutt_secret"): "national_park_rock_climb",
}

# Same check, (zone, method) pairs whose tiles sit behind a field move
# inside the zone's own region, with no sub-region of their own: the extra
# field moves (HM + badge each, data/rules.py HM_ITEMS/HM_BADGES) on top of
# the method's own requirement. Fishing spots that need Surf are water
# fenced off from every walkable tile.
DEXSANITY_ZONE_METHOD_FIELD_MOVES: dict[tuple[str, str], tuple[str, ...]] = {
    ("route_8", "land"): ("cut",),
    ("route_10", "land"): ("surf",),
    ("route_10", "old_rod"): ("surf",),
    ("route_10", "good_rod"): ("surf",),
    ("route_10", "super_rod"): ("surf",),
    ("route_13", "land"): ("cut",),
    ("route_16_east", "land"): ("cut",),
    ("route_4", "old_rod"): ("surf",),
    ("route_4", "good_rod"): ("surf",),
    ("route_4", "super_rod"): ("surf",),
    ("route_44", "land"): ("surf",),
    ("route_47", "land"): ("surf", "waterfall"),
    ("ruins_of_alph", "land"): ("surf",),
    ("mount_mortar_1f_entrance", "old_rod"): ("surf",),
    ("mount_mortar_1f_entrance", "good_rod"): ("surf",),
    ("mount_mortar_1f_entrance", "super_rod"): ("surf",),
}

# Tables the game can never roll: their map has no surfable tile at all
# (not shared with any other map either, map_headers.h wildEncounterBank).
# Dropped from the Dexsanity sources like an unwritten table.
DEXSANITY_UNUSABLE_ZONE_METHODS: frozenset[tuple[str, str]] = frozenset({
    ("cerulean_cave_2f", "surf"),
    ("cerulean_cave_2f", "old_rod"),
    ("cerulean_cave_2f", "good_rod"),
    ("cerulean_cave_2f", "super_rod"),
    ("mount_silver_cave_2f", "surf"),
    ("mount_silver_cave_2f", "old_rod"),
    ("mount_silver_cave_2f", "good_rod"),
    ("mount_silver_cave_2f", "super_rod"),
    ("mount_silver_cave_3f", "surf"),
    ("mount_silver_cave_3f", "old_rod"),
    ("mount_silver_cave_3f", "good_rod"),
    ("mount_silver_cave_3f", "super_rod"),
    ("mount_silver_cave_moltres_chamber", "surf"),
    ("mount_silver_cave_moltres_chamber", "old_rod"),
    ("mount_silver_cave_moltres_chamber", "good_rod"),
    ("mount_silver_cave_moltres_chamber", "super_rod"),
    ("mount_silver_cave_upper_mountainside", "surf"),
    ("mount_silver_cave_upper_mountainside", "old_rod"),
    ("mount_silver_cave_upper_mountainside", "good_rod"),
    ("mount_silver_cave_upper_mountainside", "super_rod"),
})
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
    species_sources: dict[str, frozenset[tuple[str, str]]],
    region_keys: Container[str],
    available_items: Container[str] | None = None,
) -> dict[str, frozenset[tuple[str, str]]]:
    """`species_sources` (species.species_encounter_sources output) with
    every pair whose zone has no Region in `region_keys` dropped, and every
    species left with no pair at all dropped too. `johto_only` is the only
    caller-visible case: a species this seed only placed in Kanto has no
    catchable location once Kanto's regions are never created, so it must
    get no Dexsanity Location -- and, just as importantly, no filler item
    in the pool either. Shared by create_locations below and __init__.py's
    create_items precisely so the two can never disagree on the count.

    `available_items` (item keys that can be in the pool, or None for all)
    also drops pairs whose method needs an item that cannot exist: under
    `johto_only` the Super Rod (Route 12) is never in the pool."""
    def usable(source: tuple[str, str]) -> bool:
        if DEXSANITY_ZONE_METHOD_REGIONS.get(source, source[0]) not in region_keys:
            return False
        if available_items is None:
            return True
        return all(item in available_items for item in _dexsanity_required_item_keys(source))

    filtered = {
        species: frozenset(source for source in sources if usable(source))
        for species, sources in species_sources.items()
    }
    return {species: sources for species, sources in filtered.items() if sources}


def _dexsanity_required_item_keys(source: tuple[str, str]) -> tuple[str, ...]:
    """Item keys (HMs, their badges, rods) a (zone, method) pair needs."""
    zone_key, method = source
    keys: list[str] = []
    if method in _DEXSANITY_HM_METHOD_REQUIREMENTS:
        item_key, badge_name = _DEXSANITY_HM_METHOD_REQUIREMENTS[method]
        keys += [item_key, f"badge_{badge_name}"]
    if method in _DEXSANITY_ROD_METHOD_REQUIREMENTS:
        keys.append(_DEXSANITY_ROD_METHOD_REQUIREMENTS[method])
    for move in DEXSANITY_ZONE_METHOD_FIELD_MOVES.get(source, ()):
        keys += [HM_ITEMS[move], f"badge_{HM_BADGES[move]}"]
    return tuple(keys)


def _dexsanity_method_requirement(
    player: int, method: str, regions: dict[str, Region]
) -> Callable[[CollectionState], bool] | None:
    """The bag-item check for one encounter method, or None when the
    method needs nothing at all."""
    if method in _UNGATED_DEXSANITY_METHODS:
        return None
    if method in ("headbutt", "headbutt_secret"):
        tutor = regions[_HEADBUTT_TUTOR_REGION]
        return lambda state: tutor.can_reach(state)
    if method in _DEXSANITY_HM_METHOD_REQUIREMENTS:
        item_key, badge_name = _DEXSANITY_HM_METHOD_REQUIREMENTS[method]
        item_label = ITEMS[item_key]["label"]
        badge_label = badge_item_label(badge_name)
        return lambda state: state.has(item_label, player) and state.has(badge_label, player)
    if method in _DEXSANITY_ROD_METHOD_REQUIREMENTS:
        item_label = ITEMS[_DEXSANITY_ROD_METHOD_REQUIREMENTS[method]]["label"]
        return lambda state: state.has(item_label, player)
    raise ValueError(f"unknown Dexsanity encounter method: {method!r}")


def _field_move_requirement(player: int, moves: tuple[str, ...]) -> Callable[[CollectionState], bool] | None:
    """HM + badge for each of `moves`, or None when there is none."""
    if not moves:
        return None
    labels = tuple(
        label
        for move in moves
        for label in (ITEMS[HM_ITEMS[move]]["label"], badge_item_label(HM_BADGES[move]))
    )
    return lambda state: all(state.has(label, player) for label in labels)


def _both(
    first: Callable[[CollectionState], bool] | None, second: Callable[[CollectionState], bool] | None
) -> Callable[[CollectionState], bool] | None:
    if first is None or second is None:
        return first or second
    return lambda state: first(state) and second(state)


def dexsanity_source_requirement(source: tuple[str, str]) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """(region to reach, item keys to own, other regions to reach) for one
    (zone, method) source: the same terms _dexsanity_access_rule ANDs in a
    branch, written for the trackers (slot data "dexsanity_logic"), which
    do not know where this seed put each species."""
    zone_key, method = source
    region_key = DEXSANITY_ZONE_METHOD_REGIONS.get(source, zone_key)
    extra_regions = (_HEADBUTT_TUTOR_REGION,) if method in ("headbutt", "headbutt_secret") else ()
    return region_key, _dexsanity_required_item_keys(source), extra_regions


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
    per_region: dict[tuple[str, tuple[str, ...]], set[str]] = {}
    for zone_key, method in sources:
        region_key = DEXSANITY_ZONE_METHOD_REGIONS.get((zone_key, method), zone_key)
        moves = DEXSANITY_ZONE_METHOD_FIELD_MOVES.get((zone_key, method), ())
        per_region.setdefault((region_key, moves), set()).add(method)

    branches: list[tuple[Region, Callable[[CollectionState], bool] | None]] = []
    for region_key, moves in sorted(per_region):
        methods = per_region[(region_key, moves)]
        region = regions[region_key]
        extra = _field_move_requirement(player, moves)
        if methods & _UNGATED_DEXSANITY_METHODS:
            branches.append((region, extra))
            continue
        for method in sorted(methods):
            branches.append((region, _both(_dexsanity_method_requirement(player, method, regions), extra)))
    branches.sort(key=lambda branch: branch[1] is not None)

    def rule(state: CollectionState) -> bool:
        return any(
            region.can_reach(state) and (requirement is None or requirement(state))
            for region, requirement in branches
        )

    return rule


class HeartGoldLocation(Location):
    game: str = "Pokemon HGSS Singe"


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
    # Gone or refusing while the Radio Tower takeover runs; see the Card Key
    # note on the Goldenrod doors in data_gen/rules.toml (2026-09-23).
    "goldenrod_tunnel_b1f_poke_maniac_donald": ("card_key",),
    "goldenrod_tunnel_b1f_poke_maniac_issac": ("card_key",),
    "goldenrod_tunnel_b1f_super_nerd_eric": ("card_key",),
    "goldenrod_tunnel_b1f_super_nerd_teru": ("card_key",),
    "goldenrod_radio_tower_2f_blue_card": ("card_key",),
    # The Fashion Case scene runs on VAR_UNK_40F8 == 0 on entering the
    # tunnel (scr_seq_0354_D37R0101_hdr.s:14): the takeover's start sets it
    # to 2 (scr_seq_0930_T28.s:25 and the two others) and Archer's defeat
    # puts it back to 0 (scr_seq_0034_D23R0106.s:140). Found 2026-09-26.
    "goldenrod_tunnel_1f_fashion_case": ("card_key",),
    # Given inside the Sudowoodo's own script, after the first watering
    # (scr_seq_0243_R36.s:48 `HasItem ITEM_SQUIRTBOTTLE`, :129 the gift);
    # its region is free from Goldenrod. Found 2026-09-27.
    "route_36_berry_pots": ("squirtbottle",),
    # Hidden in Goldenrod's Bike Shop alley, behind the takeover Rockets
    # (see its data_gen/locations.toml entry). Found 2026-09-27.
    "route_34_super_potion_2": ("card_key",),
    # NPC-gift audit, 2026-09-17: outside the gym scripts (the only ones
    # rom/badgegatedata.py re-gates), `CheckBadge` reads the profile bit,
    # i.e. whether the badge *item* has been received.
    # scr_seq_0896_T25R0601.s:122, the flower shop girl.
    "goldenrod_flower_shop_squirtbottle": ("badge_plain",),
    # scr_seq_0798_T07R0203.s:188.
    "celadon_condominiums_3f_gb_sounds": ("badge_earth",),
}

# Misty and her whole gym (FLAG_HIDE_CERULEAN_GYM_POPULATION, set at new
# game, scr_seq_0149.s:78) only show up once her Route 25 date has been cut
# short (scr_seq_0216_R25.s:169). That scene runs on VAR_UNK_4088 == 1, set
# as the Cerulean Gym Rocket runs off (scr_seq_0760_T04GYM0101.s:127), and
# that Rocket only stands there on VAR_UNK_411C == 1, which the Power Plant
# manager's story sets (scr_seq_0196_R10R0202.s:118). With `magnet_train`
# on, the client sets VAR_UNK_411C itself (client.py, _CERULEAN_CHAIN_VAR)
# and the Power Plant drops out (MAGNET_TRAIN_DROPPED_GATE_REGIONS).
# Found 2026-09-26; the logic used to count the gym as open on arrival.
_CERULEAN_GYM_GATE = ("route_25", "route_10_power_plant_broken")
_CERULEAN_GYM_KEYS = (
    "cerulean_gym_badge", "cerulean_gym_tm03", "misty_defeated_event",
    "cerulean_gym_sailor_eddie", "cerulean_gym_sailor_parker", "cerulean_gym_swimmer_f_briana",
    "cerulean_gym_swimmer_f_diana", "cerulean_gym_swimmer_f_joy",
)
MAGNET_TRAIN_DROPPED_GATE_REGIONS = frozenset({"route_10_power_plant_broken"})

# The Radio Tower takeover starts once Morty, Chuck, Jasmine and Pryce are
# beaten (see the takeover note in data_gen/rules.toml). These trainers only
# stand while it runs (FLAG_HIDE_ROCKET_TAKEOVER_1, cleared on
# VAR_SCENE_ROCKET_TAKEOVER == 4 only, e.g. scr_seq_0096_D37R0104.s:43) and
# are gone for good once Archer is beaten.
TAKEOVER_EVENTS = ("morty_defeated", "chuck_defeated", "jasmine_defeated", "pryce_defeated")

# More trainers the game hides for good at some point (2026-09-27 logic
# audit); client.py sends the ones still missing once that happens.
#   - Olivine Lighthouse 4F: FLAG_UNK_1DA/1DB, set in the Amphy healing
#     scene (scr_seq_0066_D27R0107.s:109-110).
LIGHTHOUSE_4F_TRAINER_KEYS = ("olivine_lighthouse_4f_gentleman_preston", "olivine_lighthouse_4f_lass_connie")
#   - The Mahogany hideout: FLAG_HIDE_MAHOGANY_SHOP_SHADY_SALESMAN, set when
#     Ariana and her grunt fall on B2F (scr_seq_0090_D35R0103.s:394).
HIDEOUT_TRAINER_KEYS = (
    "team_rocket_headquarters_b1f_scientist_gs_gregg", "team_rocket_headquarters_b1f_team_rocket_grunt_15",
    "team_rocket_headquarters_b2f_team_rocket_grunt_16", "team_rocket_headquarters_b2f_team_rocket_grunt_17",
    "team_rocket_headquarters_b2f_team_rocket_grunt_18", "team_rocket_headquarters_b3f_scientist_gs_mitch",
    "team_rocket_headquarters_b3f_scientist_gs_ross", "team_rocket_headquarters_b3f_team_rocket_f_grunt_5",
    "team_rocket_headquarters_b3f_team_rocket_grunt_19",
)
#   - Slowpoke Well B1F: FLAG_UNK_1A9, set when Proton falls
#     (scr_seq_0060_D26R0102.s:54-58). The corridors force each fight on
#     the way to him, so this is only a safety net.
SLOWPOKE_WELL_TRAINER_KEYS = (
    "slowpoke_well_b1f_team_rocket_f_grunt", "slowpoke_well_b1f_team_rocket_grunt",
    "slowpoke_well_b1f_team_rocket_grunt_2",
)
#   - Lake of Rage's Alton never appears: FLAG_UNK_1FE is set on every map
#     load (scr_seq_0938_T29.s:29-49), the only clearing branch tests
#     VAR_UNK_4037 == 61993, a var nothing ever writes.
NEVER_PRESENT_TRAINER_KEYS = ("lake_of_rage_ace_trainer_m_alton",)
TAKEOVER_TRAINER_KEYS = (
    "goldenrod_radio_tower_2f_team_rocket_f_grunt_2", "goldenrod_radio_tower_2f_team_rocket_grunt_4",
    "goldenrod_radio_tower_2f_team_rocket_grunt_5", "goldenrod_radio_tower_2f_team_rocket_grunt_6",
    "goldenrod_radio_tower_3f_scientist_gs_garett", "goldenrod_radio_tower_3f_team_rocket_grunt_7",
    "goldenrod_radio_tower_3f_team_rocket_grunt_8", "goldenrod_radio_tower_3f_team_rocket_grunt_9",
    "goldenrod_radio_tower_4f_executive_proton_proton_2", "goldenrod_radio_tower_4f_scientist_gs_trenton",
    "goldenrod_radio_tower_4f_team_rocket_grunt_10", "goldenrod_radio_tower_5f_executive_ariana_ariana",
    "goldenrod_tunnel_b2f_burglar_duncan", "goldenrod_tunnel_b2f_burglar_orson",
    "goldenrod_tunnel_b2f_team_rocket_f_grunt_3", "goldenrod_tunnel_b2f_team_rocket_grunt_11",
    "goldenrod_tunnel_b2f_team_rocket_grunt_12", "goldenrod_tunnel_b2f_team_rocket_grunt_23",
    "goldenrod_tunnel_warehouse_team_rocket_grunt_13", "goldenrod_tunnel_warehouse_team_rocket_grunt_14",
    "goldenrod_tunnel_warehouse_team_rocket_grunt_22",
)

# NPC-gift audit, 2026-09-17: gifts that only happen once something
# elsewhere has been done, expressed as "reach every one of these regions"
# (the scene that unlocks the gift runs there, with no item involved).
REGION_GATED_LOCATIONS: dict[str, tuple[str, ...]] = {
    # VAR_SCENE_LIGHTHOUSE_JASMINE == 1 (scr_seq_0881_T24R0501.s:12), set by
    # talking to Jasmine at the top of the lighthouse (scr_seq_0066:58).
    "cianwood_pharmacy_secretpotion": ("olivine_lighthouse_light_room",),
    # FLAG_GOT_RED_SCALE (scr_seq_0229_R30R0201.s:69), the Red Gyarados
    # check's own flag. The Red Scale item itself is not needed
    # (TakeItemNoCheck).
    "route_30_mr_pokemon_house_exp_share": ("lake_of_rage_north",),
    # FLAG_UNK_0EA (scr_seq_0943_T30GYM0101.s:~100), set by the Dragon's
    # Den shrine test (scr_seq_0112_D44R0103.s:184).
    "blackthorn_gym_tm59": ("dragons_den_shrine",),
    # The Kimono Girls hand the bell over (scr_seq_0928_T27R0501.s:807, on
    # VAR_UNK_410C == 4) once the Ecruteak rival scene has run
    # (scr_seq_0920_T27.s:121), which fires on VAR_UNK_4079 == 3, set by
    # the Elm's lab scene that follows Clair's badge at the Dragon's Den
    # Shrine (scr_seq_0843_T20R0101.s:946, on VAR_SCENE_ELMS_LAB == 8 from
    # scr_seq_0112_D44R0103.s:190). Corrected 2026-09-24 (player report):
    # was Morty's gym, which only runs a scene of its own. The client puts
    # the chain back if Morty is beaten after the lab scene
    # (client.py, _repair_story_vars).
    "ecruteak_dance_theater_clear_bell": ("dragons_den_shrine", "new_bark_elms_lab_1f"),
    "ecruteak_dance_theater_tidal_bell": ("dragons_den_shrine", "new_bark_elms_lab_1f"),
    # The Fly scene fires on VAR_UNK_4116 == 1 (scr_seq_0648_T24_hdr.s:14),
    # set in Chuck's win branch (scr_seq_0877_T24GYM0101.s:46).
    "cianwood_hm02": ("cianwood_gym",),
    # Hidden from the new game on (scr_seq_0149.s:92-93) until the Red
    # Gyarados has been faced, which takes Surf across the lake: Lois
    # appears in the same block as FLAG_GOT_RED_SCALE
    # (scr_seq_0938_T29.s:303-304), the two fishermen on the next map load
    # (:42-50). Same condition as the Exp. Share above. Found 2026-09-27.
    "lake_of_rage_ace_trainer_f_lois": ("lake_of_rage_north",),
    "lake_of_rage_fisherman_andre": ("lake_of_rage_north",),
    "lake_of_rage_fisherman_raymond": ("lake_of_rage_north",),
    # The charcoal maker's son only hands the Charcoal over once HM01 has
    # been given (`GoToIfSet FLAG_GOT_HM01`, scr_seq_0873_T23R0201.s:43), in
    # Ilex Forest; see ilex_forest_hm01 in EVENT_GATED_LOCATIONS for Proton.
    "azalea_charcoal_kiln_charcoal": ("ilex_forest",),
    **{key: _CERULEAN_GYM_GATE for key in _CERULEAN_GYM_KEYS},
}

# NPC-gift audit, 2026-09-17: gifts whose condition the logic cannot
# express. They stay checks, but only ever hold non-progression items
# (LocationProgressType.EXCLUDED), so missing one never blocks a seed.
EXCLUDED_LOCATIONS = frozenset({
    # A living Chansey in the lead, not on a bike (scr_seq_0202_R14.s:476).
    "route_14_lucky_punch",
    # Showing Elm a Togepi hatched from his assistant's egg
    # (scr_seq_0843_T20R0101.s:304, FLAG_SYS_HATCHED_TOGEPI_EGG).
    "new_bark_elms_lab_1f_everstone",
    # After the Embedded Tower legendary event (VAR_SCENE_EMBEDDED_TOWER,
    # scr_seq_0740_T01R0301.s:~330).
    "pallet_town_oaks_lab_jade_orb",
    # Earth Badge item plus an S.S. Aqua voyage counter
    # (scr_seq_0157_P01R0302.s:40-50), and the plate given rotates.
    "ss_aqua_captain_room_flame_plate",
    # The sick Miltank fed seven Oran Berries (FLAG_UNK_0AA,
    # scr_seq_0251_R39R0201.s:241): the farm woman's TM83
    # (scr_seq_0250_R39R0101.s:103) and the girl's Seal Case
    # (scr_seq_0251_R39R0201.s:35). Added 2026-09-23.
    "route_39_moomoo_farm_house_tm83",
    "route_39_moomoo_farm_stable_seal_case",
})


def _region_gated_access_rule(regions: tuple[Region, ...]) -> Callable[[CollectionState], bool]:
    return lambda state: all(region.can_reach(state) for region in regions)

# Locations whose NPC only hands the item over after a story event, with no
# region edge to carry that condition (the NPC stands in a region reachable
# long before). Value: the `event` name of a data/locations.py event.
#   - Elm's S.S. Ticket: scr_seq_0843_T20R0101.s:290, `GoToIfSet
#     FLAG_GAME_CLEAR, _0526` is the only way into the give branch. Found
#     2026-09-17 while building the tracker demo; until then the logic
#     counted it as free from the start.
EVENT_GATED_LOCATIONS: dict[str, tuple[str, ...]] = {
    # Jasmine only comes back to her gym once Amphy has been healed at the
    # top of the lighthouse (scr_seq_0066_D27R0107.s:108), which takes both
    # the Secret Potion and the climb; was the Potion item alone until
    # 2026-09-23 (see the note on _ITEM_GATED_LOCATIONS).
    "olivine_gym_badge": ("amphy_healed",),
    "new_bark_elms_lab_1f_s_s_ticket": ("elite_four_defeated",),
    # Youngster Joey only stands on Route 30 once the Mystery Egg has been
    # handed to Elm (ClearFlag FLAG_HIDE_ROUTE_30_YOUNGSTER_JOEY,
    # scr_seq_0843_T20R0101.s:759).
    "route_30_youngster_joey": ("mystery_egg_delivered",),
    # The catching tutorial runs on VAR_UNK_408B == 1, set in that same
    # Mystery Egg scene (scr_seq_0843_T20R0101.s:761). Found 2026-09-26.
    "route_29_poke_ball": ("mystery_egg_delivered",),
    # The Route 43 gate guard is hidden from the new game on
    # (scr_seq_0149.s:37) and only comes back when the Mahogany hideout is
    # cleared (scr_seq_0090_D35R0103.s:711); Rockets hold the gate before.
    "route_43_gatehouse_tm36": ("rocket_hideout_cleared",),
    # VAR_UNK_4096 == 2 (scr_seq_0740_T01R0301.s:182): Oak's phone call in
    # Viridian (scr_seq_0741_T02.s:51) after Blue's win branch set it to 1.
    "pallet_town_oaks_lab_hm08": ("blue_defeated",),
    # VAR_UNK_4135 >= 8 (scr_seq_0776_T06.s), one per Kanto Leader beaten.
    "vermilion_pp_max": (
        "brock_defeated", "misty_defeated", "lt_surge_defeated", "erika_defeated",
        "janine_defeated", "sabrina_defeated", "blaine_defeated", "blue_defeated",
    ),
    # The apprentice and his Farfetch'd are hidden from the new game on
    # (scr_seq_0149.s:21-23) until Proton is beaten in the Slowpoke Well
    # (scr_seq_0060_D26R0102.s:104-106); HM01 ends that quest.
    "ilex_forest_hm01": ("proton_defeated",),
    "azalea_charcoal_kiln_charcoal": ("proton_defeated",),
    # Only while VAR_SCENE_ROCKET_TAKEOVER == 4: Petrel posing as the
    # director (scr_seq_0033_D23R0105.s:32) and the real one in the
    # warehouse (scr_seq_0097_D37R0105.s:15). The client sends both once
    # Archer is beaten if they were missed (client.py, _TAKEOVER_ONLY).
    "goldenrod_radio_tower_5f_basement_key": TAKEOVER_EVENTS,
    "goldenrod_tunnel_warehouse_card_key": TAKEOVER_EVENTS,
    # Only once the takeover is over (phase 5): the TM11 woman and Mary
    # refuse at phase 4 (scr_seq_0031_D23R0103.s:66, scr_seq_0032_D23R0104.s:59),
    # and the 2F policeman keeps everyone off the upper floors before it.
    "goldenrod_radio_tower_3f_tm11": ("radio_tower_rockets_defeated",),
    "goldenrod_radio_tower_4f_brightpowder": ("radio_tower_rockets_defeated",),
    **{key: TAKEOVER_EVENTS for key in TAKEOVER_TRAINER_KEYS},
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
    trainer_keys: frozenset[str] | None = None,
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
        if data["type"] == "trainer" and (not trainersanity or (trainer_keys is not None and key not in trainer_keys)):
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
        rules: list[Callable[[CollectionState], bool]] = []
        if data["type"] == "event":
            location = HeartGoldLocation(player, key, None, region)
            location.place_locked_item(
                HeartGoldItem(scenario_event_item_name(data["event"]), ItemClassification.progression, None, player)
            )
        else:
            location = HeartGoldLocation(player, key, id_map[key], region)
            if data["type"] == "dexsanity":
                assert sources is not None
                rules.append(_dexsanity_access_rule(player, sources, regions))
            elif data["type"] == "hidden_item" and hidden_items_require_dowsing_machine:
                rules.append(_hidden_item_access_rule(player))
            if key in EXCLUDED_LOCATIONS:
                location.progress_type = LocationProgressType.EXCLUDED
        rules += _story_gate_rules(player, key, regions, power_plant_prerestored)
        if len(rules) == 1:
            location.access_rule = rules[0]
        elif rules:
            location.access_rule = lambda state, rules=tuple(rules): all(rule(state) for rule in rules)
        region.locations.append(location)


def _story_gate_rules(
    player: int, key: str, regions: dict[str, Region], power_plant_prerestored: bool
) -> list[Callable[[CollectionState], bool]]:
    """Every story gate listed for `key`, all of which must hold (a gift can
    need an item as well as an earlier scene). Event locations get them too:
    a Leader who is not in the gym yet cannot be beaten either."""
    rules: list[Callable[[CollectionState], bool]] = []
    if key in _ITEM_GATED_LOCATIONS:
        rules.append(_item_gated_access_rule(player, _ITEM_GATED_LOCATIONS[key]))
    if key in REGION_GATED_LOCATIONS:
        names = REGION_GATED_LOCATIONS[key]
        if power_plant_prerestored:
            names = tuple(name for name in names if name not in MAGNET_TRAIN_DROPPED_GATE_REGIONS)
        if names:
            rules.append(_region_gated_access_rule(tuple(regions[name] for name in names)))
    if key in EVENT_GATED_LOCATIONS:
        event_items = tuple(scenario_event_item_name(name) for name in EVENT_GATED_LOCATIONS[key])
        rules.append(lambda state, event_items=event_items: state.has_all(event_items, player))
    if key in POWER_PLANT_GATED_LOCATION_KEYS and not power_plant_prerestored:
        event_item = scenario_event_item_name(_POWER_PLANT_EVENT)
        rules.append(lambda state, event_item=event_item: state.has(event_item, player))
    return rules
