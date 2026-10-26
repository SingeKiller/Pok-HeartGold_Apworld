from __future__ import annotations

from data.locations import LOCATIONS
from data.species import SPECIES
from data.trainers import TRAINERS
from locations import SHELVED_LOCATION_TYPES, create_location_label_to_code_map
from save_layout import HIDDEN_ITEMS_FLAG_BASE

_DIRECT_FLAG_ID_TYPES = {"ground_item", "npc_gift", "hm_tm"}

TRAINER_FLAG_BASE = 0x550

_STATIC_POKEMON_FLAG_IDS: dict[str, int] = {
    "catch_ho_oh": 0x116,
    "catch_lugia": 0x117,
}

_SYNTHETIC_ID_BASE = 9000

_SYNTHETIC_ID_FLAG_OVERRIDES: dict[str, int] = {
    "sprout_tower_3f_tm70": 0x76,
    "new_bark_elms_lab_1f_s_s_ticket": 0xF2,
    "route_30_mr_pokemon_house_exp_share": 0x6C,
    "route_10_power_plant_broken_tm57": 0x258,
    "ecruteak_dance_theater_clear_bell": 0x103,
    "ecruteak_dance_theater_tidal_bell": 0x104,
    "route_39_moomoo_farm_stable_seal_case": 0x100,
    "route_5_underground_path_tm64": 0x164,
    "saffron_copycat_house_2f_pass": 0x87,
    "goldenrod_radio_tower_observation_deck_rainbow_wing": 0x93,
    "goldenrod_radio_tower_observation_deck_silver_wing": 0x94,
    "goldenrod_tunnel_1f_fashion_case": 0x14C,
    "route_36_berry_pots": 0x1CF,
    "goldenrod_tunnel_warehouse_card_key": 0x1C1,
    "ss_aqua_captain_room_flame_plate": 0xABB,
    "goldenrod_bike_shop_bicycle": 0x89,
    "violet_gym_badge": 0x192,
    "goldenrod_gym_badge": 0x84,
    "vermilion_gym_badge": 0x31A,
    "dragons_den_shrine_badge": 0xD1,
    "seafoam_islands_cinnabar_gym_badge": 0x265,
    "viridian_gym_badge": 0x97F,
    "azalea_gym_badge": 0x520,
    "ecruteak_gym_badge": 0x521,
    "cianwood_gym_badge": 0x522,
    "olivine_gym_badge": 0x523,
    "mahogany_gym_leader_room_badge": 0x524,
    "pewter_gym_badge": 0x525,
    "cerulean_gym_badge": 0x526,
    "celadon_gym_badge": 0x527,
    "fuchsia_gym_badge": 0x528,
    "saffron_gym_badge": 0x529,
}

from rom.giftflagdata import GIFT_FLAGS
from rom.npcgiftgatedata import GATE_FLAGS

_SYNTHETIC_ID_FLAG_OVERRIDES.update(GIFT_FLAGS)
_SYNTHETIC_ID_FLAG_OVERRIDES.update(
    {key: flag for key, flag in GATE_FLAGS.items() if key != "goldenrod_tunnel_warehouse_card_key"}
)


def flag_id_for_location(location_key: str) -> int | None:
    data = LOCATIONS.get(location_key)
    if data is None:
        raise KeyError(f"unknown location key: {location_key!r}")

    override = _SYNTHETIC_ID_FLAG_OVERRIDES.get(location_key)
    if override is not None:
        return override

    location_type = data["type"]
    raw_id = data.get("id")

    if location_type in SHELVED_LOCATION_TYPES or raw_id is None:
        return None
    if location_type in _DIRECT_FLAG_ID_TYPES:
        return None if raw_id >= _SYNTHETIC_ID_BASE else raw_id
    if location_type == "hidden_item":
        return HIDDEN_ITEMS_FLAG_BASE + raw_id
    if location_type == "trainer":
        return TRAINER_FLAG_BASE + TRAINERS[data["trainer"]]["id"]
    if location_type == "badge":
        return None
    if location_type == "static_pokemon":
        return _STATIC_POKEMON_FLAG_IDS[location_key]
    return None


def dexsanity_pokedex_bit_for_species(species_id: int) -> int:
    return species_id - 1


def build_dexsanity_flag_to_ap_location_id() -> dict[int, int]:
    ap_ids = create_location_label_to_code_map()
    result: dict[int, int] = {}
    for key, data in LOCATIONS.items():
        if data["type"] != "dexsanity":
            continue
        ap_id = ap_ids.get(key)
        if ap_id is None:
            continue
        bit = dexsanity_pokedex_bit_for_species(SPECIES[data["species"]]["id"])
        result[bit] = ap_id
    return result


def build_flag_id_to_ap_location_id() -> dict[int, int]:
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


def build_locally_substituted_ap_location_ids(*, remote_items: bool = False) -> set[int]:
    ap_ids = create_location_label_to_code_map()
    always_local_keys = frozenset(unsupported_location_keys()) if remote_items else None
    result: set[int] = set()
    for key, data in LOCATIONS.items():
        if data["type"] not in ("ground_item", "npc_gift", "hm_tm", "hidden_item"):
            continue
        if remote_items and key not in always_local_keys:
            continue
        ap_id = ap_ids.get(key)
        if ap_id is not None:
            result.add(ap_id)
    return result


def build_badge_index_to_sentinel_flag_id() -> dict[int, int]:
    from data.rules import BADGES

    result: dict[int, int] = {}
    for key, data in LOCATIONS.items():
        if data["type"] != "badge":
            continue
        flag_id = flag_id_for_location(key)
        if flag_id is None:
            continue
        badge_name = data["original_item"].removeprefix("badge_")
        result[BADGES[badge_name]] = flag_id
    return result


VAR_CHECKED_LOCATIONS: dict[str, tuple[int, int]] = {
    "team_rocket_headquarters_b2f_hm05": (0x40AC, 10),
}


def unsupported_location_keys() -> list[str]:
    return sorted(
        key
        for key in LOCATIONS
        if LOCATIONS[key]["type"] not in ("event", "dexsanity")
        and LOCATIONS[key]["type"] not in SHELVED_LOCATION_TYPES
        and flag_id_for_location(key) is None
        and key not in VAR_CHECKED_LOCATIONS
    )
