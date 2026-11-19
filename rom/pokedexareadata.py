from __future__ import annotations

import struct

from rom import HeartGoldRom

NITROFS_PATH = "a/1/3/3"
SPECIES_PER_METHOD = 495
FIRST_LIST = 2
MAX_NATIONAL_DEX = 493
TIMES = ("morn", "day", "nite")
CAVE_BASE = 0
OUTSIDE_BASE = 3
CAVE_HEADBUTT = 6
OUTSIDE_HEADBUTT = 7

CAVE_AREAS: dict[str, int] = {
    "bell_tower_10f": 8, "bell_tower_2f": 8, "bell_tower_3f": 8, "bell_tower_4f": 8, "bell_tower_5f": 8,
    "bell_tower_6f": 8, "bell_tower_7f": 8, "bell_tower_8f": 8, "bell_tower_9f": 8, "burned_tower_1f": 7,
    "burned_tower_b1f": 7, "cerulean_cave_1f": 25, "cerulean_cave_2f": 25, "cerulean_cave_b1f": 25,
    "cliff_cave": 18, "cliff_edge_gate": 17, "dark_cave_route_31_side": 13, "dark_cave_route_45_side": 13,
    "diglett_cave": 23, "dragons_den": 12, "ice_path_1f": 11, "ice_path_b1f": 11, "ice_path_b2f": 11,
    "ice_path_b3f": 11, "ilex_forest": 5, "mount_moon": 14, "mount_moon_square": 14,
    "mount_moon_square_clefairy_event": 14, "mount_moon_square_entrance": 14, "mount_mortar_1f_back": 10,
    "mount_mortar_1f_entrance": 10, "mount_mortar_2f": 10, "mount_mortar_b1f": 10, "mount_silver_cave_1f": 16,
    "mount_silver_cave_2f": 16, "mount_silver_cave_3f": 16, "mount_silver_cave_expert_belt_chamber": 16,
    "mount_silver_cave_lower_mountainside": 16, "mount_silver_cave_moltres_chamber": 16,
    "mount_silver_cave_upper_mountainside": 16, "national_park": 6, "rock_tunnel_1f": 20,
    "rock_tunnel_b1f": 20, "ruins_of_alph": 2, "ruins_of_alph_hall_entrance_sinjoh_event": 2,
    "ruins_of_alph_underground_hall": 2, "ruins_of_alph_underground_hall_sinjoh_event": 2,
    "ruins_of_alph_underground_hall_sinjoh_event_2": 2, "seafoam_islands_1f": 15, "seafoam_islands_b1f": 15,
    "seafoam_islands_b2f": 15, "seafoam_islands_b3f": 15, "seafoam_islands_b4f": 15, "slowpoke_well_b1f": 4,
    "slowpoke_well_b2f": 4, "sprout_tower_2f": 1, "sprout_tower_3f": 1, "tohjo_falls": 22, "union_cave_1f": 3,
    "union_cave_b1f": 3, "union_cave_b2f": 3, "victory_road_1f": 21, "victory_road_2f": 21,
    "victory_road_3f": 21, "viridian_forest": 24, "whirl_islands_1f": 9, "whirl_islands_b1f": 9,
    "whirl_islands_b2f": 9, "whirl_islands_b3f": 9,
}

OUTSIDE_AREAS: dict[str, int] = {
    "azalea": 66, "blackthorn": 24, "celadon": 36, "cerulean": 34, "cherrygrove": 3, "cianwood": 19,
    "cinnabar_island": 38, "ecruteak": 13, "fuchsia": 37, "lake_of_rage": 22, "mount_silver": 28,
    "new_bark": 1, "olivine": 16, "pallet": 32, "pewter": 65, "route_1": 43, "route_10": 52, "route_11": 53,
    "route_12": 29, "route_13": 54, "route_14": 55, "route_15": 56, "route_16": 68, "route_16_east": 57,
    "route_17": 58, "route_18": 59, "route_19": 30, "route_2": 44, "route_20": 31, "route_21": 60,
    "route_22": 61, "route_24": 62, "route_25": 63, "route_26": 40, "route_27": 41, "route_28": 42,
    "route_29": 2, "route_2_east": 64, "route_3": 45, "route_30": 4, "route_31": 5, "route_32": 7,
    "route_33": 8, "route_34": 9, "route_35": 10, "route_36": 11, "route_37": 12, "route_38": 14,
    "route_39": 15, "route_4": 46, "route_40": 17, "route_41": 18, "route_42": 20, "route_43": 21,
    "route_44": 23, "route_45": 25, "route_46": 26, "route_47": 27, "route_48": 39, "route_5": 47,
    "route_6": 48, "route_7": 49, "route_8": 50, "route_9": 51, "vermilion": 35, "violet": 6, "viridian": 33,
}


def _zone_area(zone_key: str) -> tuple[int, int, int] | None:
    if zone_key in CAVE_AREAS:
        return CAVE_BASE, CAVE_HEADBUTT, CAVE_AREAS[zone_key]
    if zone_key in OUTSIDE_AREAS:
        return OUTSIDE_BASE, OUTSIDE_HEADBUTT, OUTSIDE_AREAS[zone_key]
    return None


def _species_at(zone: dict, time_of_day: str) -> set[str]:
    found = {slot[time_of_day] for slot in zone["land"]["slots"]}
    found |= {slot["species"] for slot in zone["surf"]["slots"]}
    found |= {slot["species"] for slot in zone["rock_smash"]["slots"]}
    for rod in zone["fishing"].values():
        found |= {slot["species"] for slot in rod["slots"]}
    return found


def build_area_lists(encounters: dict, species_index: dict[str, int]) -> dict[tuple[int, int], set[int]]:
    lists: dict[tuple[int, int], set[int]] = {}
    for zone_key, zone in encounters.items():
        area = _zone_area(zone_key)
        if area is None:
            continue
        base, headbutt, area_id = area
        for offset, time_of_day in enumerate(TIMES):
            for species in _species_at(zone, time_of_day):
                lists.setdefault((base + offset, species_index[species]), set()).add(area_id)
        for slots in zone.get("headbutt", {}).values():
            for slot in slots:
                lists.setdefault((headbutt, species_index[slot["species"]]), set()).add(area_id)
    return lists


def read_area_list(blob: bytes) -> list[int]:
    values = list(struct.unpack(f"<{len(blob) // 4}I", blob))
    return values[: values.index(0)] if 0 in values else values


def write_area_lists(rom: HeartGoldRom, lists: dict[tuple[int, int], set[int]]) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    expected = FIRST_LIST + 8 * SPECIES_PER_METHOD
    if len(narc.files) != expected:
        raise ValueError(f"Pokedex area archive has {len(narc.files)} files, expected {expected}")
    for method in range(8):
        for species in range(1, MAX_NATIONAL_DEX + 1):
            areas = sorted(lists.get((method, species), ()))
            narc.files[FIRST_LIST + method * SPECIES_PER_METHOD + species] = struct.pack(
                f"<{len(areas) + 1}I", *areas, 0
            )
    rom.write_narc(NITROFS_PATH, narc)
