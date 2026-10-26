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

_LOCKED_EVENT_LOCATION_TYPES = {"event"}

SHELVED_LOCATION_TYPES: set[str] = set()

_ID_ASSIGNABLE_KEYS = sorted(
    key
    for key, data in LOCATIONS.items()
    if data["type"] not in _LOCKED_EVENT_LOCATION_TYPES and data["type"] not in SHELVED_LOCATION_TYPES
)
_LOCATION_INDEX: dict[str, int] = {key: index for index, key in enumerate(_ID_ASSIGNABLE_KEYS)}


def badge_item_label(badge_name: str) -> str:
    return ITEMS[f"badge_{badge_name}"]["label"]


def scenario_event_item_name(event_name: str) -> str:
    return f"{SCENARIO_EVENT_ITEM_PREFIX}{event_name}"


_UNGATED_DEXSANITY_METHODS = frozenset({"land"})
_HEADBUTT_TUTOR_REGION = "ilex_forest_north"

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
    ("route_36", "land"): "route_36_west",
    ("ice_path_b2f", "land"): "ice_path_b2f_west",
    ("national_park", "headbutt_secret"): "national_park_rock_climb",
    ("cherrygrove", "headbutt_secret"): "cherrygrove_rock_climb_surf",
    ("route_38", "headbutt_secret"): "route_38_rock_climb",
}

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
    ("route_39", "headbutt"): ("rock_climb",),
    ("route_42", "headbutt"): ("surf",),
    ("mount_silver", "headbutt"): ("surf",),
}

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
    ("national_park_bug_catching_contest", "land"),
    ("mount_moon_square_clefairy_event", "surf"),
    ("mount_moon_square_clefairy_event", "old_rod"),
    ("mount_moon_square_clefairy_event", "good_rod"),
    ("mount_moon_square_clefairy_event", "super_rod"),
    ("ruins_of_alph_underground_hall_sinjoh_event", "land"),
    ("ruins_of_alph_underground_hall_sinjoh_event_2", "land"),
    ("ruins_of_alph_hall_entrance_sinjoh_event", "land"),
})

_ALPH_PUZZLE_ROOMS = (
    "ruins_of_alph_northeast_entrance_first_room",
    "ruins_of_alph_southeast_entrance_first_room",
    "ruins_of_alph_southwest_entrance_first_room",
    "ruins_of_alph_northwest_entrance_first_room",
)
_ALPH_PUZZLE_SPECIES = frozenset({"unown"})
_ALPH_PUZZLE_ZONES = frozenset({"ruins_of_alph_underground_hall"})


def _needs_alph_puzzle(species: str, source: tuple[str, str]) -> bool:
    return species in _ALPH_PUZZLE_SPECIES or source[0] in _ALPH_PUZZLE_ZONES
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


def dexsanity_source_requirements(
    species: str, source: tuple[str, str]
) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    zone_key, method = source
    region_key = DEXSANITY_ZONE_METHOD_REGIONS.get(source, zone_key)
    extra_regions = (_HEADBUTT_TUTOR_REGION,) if method in ("headbutt", "headbutt_secret") else ()
    items = _dexsanity_required_item_keys(source)
    if not _needs_alph_puzzle(species, source):
        return [(region_key, items, extra_regions)]
    return [(region_key, items, (*extra_regions, room)) for room in _ALPH_PUZZLE_ROOMS]


def _dexsanity_access_rule(
    player: int, sources: frozenset[tuple[str, str]], regions: dict[str, Region], species: str = ""
) -> Callable[[CollectionState], bool]:
    per_region: dict[tuple[str, tuple[str, ...], bool], set[str]] = {}
    for zone_key, method in sources:
        region_key = DEXSANITY_ZONE_METHOD_REGIONS.get((zone_key, method), zone_key)
        moves = DEXSANITY_ZONE_METHOD_FIELD_MOVES.get((zone_key, method), ())
        puzzle = _needs_alph_puzzle(species, (zone_key, method))
        per_region.setdefault((region_key, moves, puzzle), set()).add(method)

    puzzle_rooms = tuple(regions[room] for room in _ALPH_PUZZLE_ROOMS)

    def puzzle_solvable(state: CollectionState) -> bool:
        return any(room.can_reach(state) for room in puzzle_rooms)

    branches: list[tuple[Region, Callable[[CollectionState], bool] | None]] = []
    for region_key, moves, puzzle in sorted(per_region):
        methods = per_region[(region_key, moves, puzzle)]
        region = regions[region_key]
        extra = _both(_field_move_requirement(player, moves), puzzle_solvable if puzzle else None)
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
    return {key: HEARTGOLD_LOCATION_ID_BASE + index for key, index in _LOCATION_INDEX.items()}


def location_region_key(data: Mapping[str, Any], soulsilver: bool) -> str:
    if soulsilver:
        return data.get("soulsilver_region", data["region"])
    return data["region"]


def get_location_region(key: str, soulsilver: bool = False) -> str:
    return location_region_key(LOCATIONS[key], soulsilver)


DOWSING_MACHINE_ITEM_LABEL = ITEMS["dowsing_mchn"]["label"]


def _hidden_item_access_rule(player: int) -> Callable[[CollectionState], bool]:
    return lambda state: state.has(DOWSING_MACHINE_ITEM_LABEL, player)


_ITEM_GATED_LOCATIONS: dict[str, tuple[str, ...]] = {
    "goldenrod_tunnel_b1f_poke_maniac_donald": ("card_key",),
    "goldenrod_tunnel_b1f_poke_maniac_issac": ("card_key",),
    "goldenrod_tunnel_b1f_super_nerd_eric": ("card_key",),
    "goldenrod_tunnel_b1f_super_nerd_teru": ("card_key",),
    "goldenrod_radio_tower_2f_blue_card": ("card_key",),
    "goldenrod_tunnel_1f_fashion_case": ("card_key",),
    "route_36_berry_pots": ("squirtbottle",),
    "route_34_super_potion_2": ("card_key",),
    "goldenrod_flower_shop_squirtbottle": ("badge_plain",),
    "celadon_condominiums_3f_gb_sounds": ("badge_earth",),
    "ice_path_b1f_iron": ("hm04", "badge_plain"),
    "ice_path_b1f_revive": ("hm04", "badge_plain"),
    "ice_path_1f_protein": ("hm04", "badge_plain"),
    "ice_path_1f_pp_up": ("hm04", "badge_plain"),
    "route_47_white_flute": ("hm03", "badge_fog"),
    "route_47_stardust": ("hm03", "badge_fog"),
    "victory_road_3f_zinc": ("hm06", "badge_zephyr"),
    "route_5_underground_path_tm64": ("ragecandybar",),
    "route_29_twistedspoon": ("badge_zephyr",),
}

_CERULEAN_GYM_GATE = ("route_25", "route_10_power_plant_broken")
_CERULEAN_GYM_KEYS = (
    "cerulean_gym_badge", "cerulean_gym_tm03", "misty_defeated_event",
    "cerulean_gym_sailor_eddie", "cerulean_gym_sailor_parker", "cerulean_gym_swimmer_f_briana",
    "cerulean_gym_swimmer_f_diana", "cerulean_gym_swimmer_f_joy",
)
MAGNET_TRAIN_DROPPED_GATE_REGIONS = frozenset({"route_10_power_plant_broken"})

TAKEOVER_EVENTS = ("morty_defeated", "chuck_defeated", "jasmine_defeated", "pryce_defeated")

LIGHTHOUSE_4F_TRAINER_KEYS = ("olivine_lighthouse_4f_gentleman_preston", "olivine_lighthouse_4f_lass_connie")
HIDEOUT_TRAINER_KEYS = (
    "team_rocket_headquarters_b1f_scientist_gs_gregg", "team_rocket_headquarters_b1f_team_rocket_grunt_15",
    "team_rocket_headquarters_b2f_team_rocket_grunt_16", "team_rocket_headquarters_b2f_team_rocket_grunt_17",
    "team_rocket_headquarters_b2f_team_rocket_grunt_18", "team_rocket_headquarters_b3f_scientist_gs_mitch",
    "team_rocket_headquarters_b3f_scientist_gs_ross", "team_rocket_headquarters_b3f_team_rocket_f_grunt_5",
    "team_rocket_headquarters_b3f_team_rocket_grunt_19",
)
SLOWPOKE_WELL_TRAINER_KEYS = (
    "slowpoke_well_b1f_team_rocket_f_grunt", "slowpoke_well_b1f_team_rocket_grunt",
    "slowpoke_well_b1f_team_rocket_grunt_2",
)
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

REGION_GATED_LOCATIONS: dict[str, tuple[str, ...]] = {
    "cianwood_pharmacy_secretpotion": ("olivine_lighthouse_light_room",),
    "route_30_mr_pokemon_house_exp_share": ("lake_of_rage_north",),
    "blackthorn_gym_tm59": ("dragons_den_shrine",),
    "ecruteak_dance_theater_clear_bell": ("dragons_den_shrine", "new_bark_elms_lab_1f"),
    "ecruteak_dance_theater_tidal_bell": ("dragons_den_shrine", "new_bark_elms_lab_1f"),
    "cianwood_hm02": ("cianwood_gym",),
    "lake_of_rage_ace_trainer_f_lois": ("lake_of_rage_north",),
    "lake_of_rage_fisherman_andre": ("lake_of_rage_north",),
    "lake_of_rage_fisherman_raymond": ("lake_of_rage_north",),
    **{
        key: ("goldenrod_department_store_2f",)
        for key in (
            "ruins_of_alph_northeast_entrance_second_room_heal_powder",
            "ruins_of_alph_northeast_entrance_second_room_energypowder",
            "ruins_of_alph_northeast_entrance_second_room_oran_berry",
            "ruins_of_alph_northeast_entrance_second_room_pecha_berry",
        )
    },
    "lake_of_rage_black_belt": ("lake_of_rage_north",),
    "azalea_charcoal_kiln_charcoal": ("ilex_forest",),
    **{key: _CERULEAN_GYM_GATE for key in _CERULEAN_GYM_KEYS},
}

EXCLUDED_LOCATIONS = frozenset({
    "lake_of_rage_black_belt",
    "route_14_lucky_punch",
    "new_bark_elms_lab_1f_everstone",
    "pallet_town_oaks_lab_jade_orb",
    "ss_aqua_captain_room_flame_plate",
    "route_39_moomoo_farm_house_tm83",
    "route_39_moomoo_farm_stable_seal_case",
})


def _region_gated_access_rule(regions: tuple[Region, ...]) -> Callable[[CollectionState], bool]:
    return lambda state: all(region.can_reach(state) for region in regions)

EVENT_GATED_LOCATIONS: dict[str, tuple[str, ...]] = {
    "olivine_gym_badge": ("amphy_healed",),
    "new_bark_elms_lab_1f_s_s_ticket": ("elite_four_defeated",),
    "route_30_youngster_joey": ("mystery_egg_delivered",),
    "route_29_poke_ball": ("mystery_egg_delivered",),
    "route_43_gatehouse_tm36": ("rocket_hideout_cleared",),
    "lake_of_rage_black_belt": ("rocket_hideout_cleared",),
    "pallet_town_oaks_lab_hm08": ("blue_defeated",),
    "vermilion_pp_max": (
        "brock_defeated", "misty_defeated", "lt_surge_defeated", "erika_defeated",
        "janine_defeated", "sabrina_defeated", "blaine_defeated", "blue_defeated",
    ),
    "ilex_forest_hm01": ("proton_defeated",),
    "azalea_charcoal_kiln_charcoal": ("proton_defeated",),
    "goldenrod_radio_tower_5f_basement_key": TAKEOVER_EVENTS,
    "goldenrod_tunnel_warehouse_card_key": TAKEOVER_EVENTS,
    "goldenrod_radio_tower_3f_tm11": ("radio_tower_rockets_defeated",),
    "goldenrod_radio_tower_4f_brightpowder": ("radio_tower_rockets_defeated",),
    **{key: TAKEOVER_EVENTS for key in TAKEOVER_TRAINER_KEYS},
}

POWER_PLANT_PRERESTORED_SKIPPED_LOCATION_KEYS = frozenset({"route_10_power_plant_broken_tm57"})

POWER_PLANT_GATED_LOCATION_KEYS = frozenset({"saffron_copycat_house_2f_pass"})
_POWER_PLANT_EVENT = "power_plant_restored"


def _item_gated_access_rule(player: int, item_keys: tuple[str, ...]) -> Callable[[CollectionState], bool]:
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
    id_map = create_location_label_to_code_map()
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
                rules.append(_dexsanity_access_rule(player, sources, regions, data["species"]))
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
