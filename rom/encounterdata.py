from __future__ import annotations

import struct
from collections.abc import Sequence

from rom import HeartGoldRom

HEARTGOLD_NITROFS_PATH = "a/0/3/7"
SOULSILVER_NITROFS_PATH = "a/1/3/6"

EXPECTED_ENTRY_COUNT = 142


def _nitrofs_path_for(rom: HeartGoldRom) -> str:
    if rom.version == "soulsilver":
        return SOULSILVER_NITROFS_PATH
    return HEARTGOLD_NITROFS_PATH


def read_all(rom: HeartGoldRom) -> list[bytes]:
    return rom.read_narc(_nitrofs_path_for(rom)).files


def write_all(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    path = _nitrofs_path_for(rom)
    narc = rom.read_narc(path)
    if len(entries) != len(narc.files):
        raise ValueError(
            f"encounter data table has {len(narc.files)} entries, got "
            f"{len(entries)} replacement entries -- entry count must match "
            "exactly (this layer never adds/removes NARC sub-files)."
        )
    narc.files = list(entries)
    rom.write_narc(path, narc)


def read_entry(rom: HeartGoldRom, index: int) -> bytes:
    return rom.read_narc(_nitrofs_path_for(rom)).files[index]


def write_entry(rom: HeartGoldRom, index: int, data: bytes) -> None:
    path = _nitrofs_path_for(rom)
    narc = rom.read_narc(path)
    narc.files[index] = data
    rom.write_narc(path, narc)


_LAND_SPECIES_MORN_OFFSET = 0x14
_LAND_SPECIES_DAY_OFFSET = 0x2C
_LAND_SPECIES_NITE_OFFSET = 0x44
_LAND_SLOT_COUNT = 12
_SURF_SLOTS_OFFSET = 0x64
_ROCK_SMASH_SLOTS_OFFSET = 0x78
_OLD_ROD_SLOTS_OFFSET = 0x80
_GOOD_ROD_SLOTS_OFFSET = 0x94
_SUPER_ROD_SLOTS_OFFSET = 0xA8
_ENCOUNTER_DATA_SLOT_SIZE = 4
_ENCOUNTER_DATA_SLOT_SPECIES_OFFSET = 2

_SURF_SLOT_CAPACITY = 5
_ROCK_SMASH_SLOT_CAPACITY = 2
_FISHING_SLOT_CAPACITY = 5


def _write_land_species(entry: bytearray, land: dict, species_index: dict[str, int]) -> None:
    slots = land["slots"]
    if not slots:
        return
    if len(slots) != _LAND_SLOT_COUNT:
        raise ValueError(f"land encounter data has {len(slots)} slots, expected exactly {_LAND_SLOT_COUNT}")
    for time_key, offset in (
        ("morn", _LAND_SPECIES_MORN_OFFSET),
        ("day", _LAND_SPECIES_DAY_OFFSET),
        ("nite", _LAND_SPECIES_NITE_OFFSET),
    ):
        for i in range(_LAND_SLOT_COUNT):
            species_id = species_index[slots[i][time_key]]
            struct.pack_into("<H", entry, offset + i * 2, species_id)


def _write_slot_array_species(
    entry: bytearray, slots: Sequence[dict], base_offset: int, species_index: dict[str, int], capacity: int
) -> None:
    if len(slots) > capacity:
        raise ValueError(f"{len(slots)} slots given for a {capacity}-slot array at offset {base_offset:#x}")
    for i, slot in enumerate(slots):
        offset = base_offset + i * _ENCOUNTER_DATA_SLOT_SIZE + _ENCOUNTER_DATA_SLOT_SPECIES_OFFSET
        struct.pack_into("<H", entry, offset, species_index[slot["species"]])


WRITTEN_ENCOUNTER_METHODS = frozenset(
    {"land", "surf", "rock_smash", "old_rod", "good_rod", "super_rod", "headbutt"}
)


def zone_is_written(zone_key: str) -> bool:
    from data.encounter_zone_index import ENCOUNTER_ZONE_KEY_TO_RAW_INDEX

    return zone_key in ENCOUNTER_ZONE_KEY_TO_RAW_INDEX


def zone_method_is_written(zone_key: str, method: str) -> bool:
    if method in ("headbutt", "headbutt_secret"):
        return zone_key in HEADBUTT_ZONE_KEY_TO_MEMBER
    return method in WRITTEN_ENCOUNTER_METHODS and zone_is_written(zone_key)


def write_zone_encounters(rom: HeartGoldRom, zone_key: str, zone: dict) -> None:
    from data.encounter_zone_index import ENCOUNTER_ZONE_KEY_TO_RAW_INDEX
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = ENCOUNTER_ZONE_KEY_TO_RAW_INDEX[zone_key]
    entry = bytearray(read_entry(rom, raw_index))

    _write_land_species(entry, zone["land"], SPECIES_KEY_TO_RAW_INDEX)
    _write_slot_array_species(
        entry, zone["surf"]["slots"], _SURF_SLOTS_OFFSET, SPECIES_KEY_TO_RAW_INDEX, _SURF_SLOT_CAPACITY
    )
    _write_slot_array_species(
        entry,
        zone["rock_smash"]["slots"],
        _ROCK_SMASH_SLOTS_OFFSET,
        SPECIES_KEY_TO_RAW_INDEX,
        _ROCK_SMASH_SLOT_CAPACITY,
    )
    _write_slot_array_species(
        entry,
        zone["fishing"]["old_rod"]["slots"],
        _OLD_ROD_SLOTS_OFFSET,
        SPECIES_KEY_TO_RAW_INDEX,
        _FISHING_SLOT_CAPACITY,
    )
    _write_slot_array_species(
        entry,
        zone["fishing"]["good_rod"]["slots"],
        _GOOD_ROD_SLOTS_OFFSET,
        SPECIES_KEY_TO_RAW_INDEX,
        _FISHING_SLOT_CAPACITY,
    )
    _write_slot_array_species(
        entry,
        zone["fishing"]["super_rod"]["slots"],
        _SUPER_ROD_SLOTS_OFFSET,
        SPECIES_KEY_TO_RAW_INDEX,
        _FISHING_SLOT_CAPACITY,
    )

    write_entry(rom, raw_index, bytes(entry))


HEADBUTT_NITROFS_PATH = "a/2/5/2"
HEADBUTT_SLOTS_PER_TABLE = 6
_HEADBUTT_HEADER_SIZE = 4
_HEADBUTT_SLOT_SIZE = 4
_HEADBUTT_TIERS = ("common", "rare", "secret")

HEADBUTT_ZONE_KEY_TO_MEMBER: dict[str, int] = {
    "azalea": 74, "celadon": 55, "cerulean": 52, "cherrygrove": 67,
    "ecruteak": 78, "fuchsia": 56, "ilex_forest": 117, "lake_of_rage": 88,
    "mount_silver": 90, "mount_silver_cave_lower_mountainside": 460,
    "national_park": 96, "new_bark": 60, "pallet": 49, "pewter": 51,
    "route_1": 9, "route_11": 19, "route_12": 20, "route_13": 21,
    "route_14": 22, "route_15": 23, "route_16": 24, "route_16_east": 422,
    "route_18": 26, "route_2": 10, "route_21": 93, "route_22": 27,
    "route_25": 29, "route_26": 30, "route_27": 31, "route_28": 32,
    "route_29": 33, "route_2_east": 414, "route_3": 11, "route_30": 34,
    "route_31": 35, "route_32": 36, "route_33": 37, "route_34": 38,
    "route_35": 39, "route_36": 40, "route_37": 41, "route_38": 42,
    "route_39": 43, "route_4": 12, "route_42": 44, "route_43": 45,
    "route_44": 46, "route_45": 47, "route_46": 48, "route_47": 151,
    "route_48": 152, "route_5": 13, "route_6": 14, "route_7": 15,
    "route_8": 16, "vermilion": 54, "violet": 73, "viridian": 50,
    "viridian_forest": 147,
}


def headbutt_tree_counts(member: bytes) -> tuple[int, int]:
    regular, secret = struct.unpack_from("<HH", member, 0)
    return regular, secret


def _headbutt_species_offset(tier_index: int, slot_index: int) -> int:
    return _HEADBUTT_HEADER_SIZE + (tier_index * HEADBUTT_SLOTS_PER_TABLE + slot_index) * _HEADBUTT_SLOT_SIZE


def write_headbutt_tables(rom: HeartGoldRom, encounters: dict) -> None:
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    narc = rom.read_narc(HEADBUTT_NITROFS_PATH)
    for zone_key, zone in encounters.items():
        headbutt = zone.get("headbutt")
        if headbutt is None or zone_key not in HEADBUTT_ZONE_KEY_TO_MEMBER:
            continue
        index = HEADBUTT_ZONE_KEY_TO_MEMBER[zone_key]
        member = bytearray(narc.files[index])
        regular, secret = headbutt_tree_counts(member)
        if regular == 0 and secret == 0:
            raise ValueError(f"headbutt member {index} ({zone_key}) has no trees, refusing to write it")
        for tier_index, tier in enumerate(_HEADBUTT_TIERS):
            slots = headbutt[tier]
            if len(slots) > HEADBUTT_SLOTS_PER_TABLE:
                raise ValueError(f"{zone_key} headbutt {tier}: {len(slots)} slots, at most {HEADBUTT_SLOTS_PER_TABLE}")
            for slot_index, slot in enumerate(slots):
                struct.pack_into(
                    "<H",
                    member,
                    _headbutt_species_offset(tier_index, slot_index),
                    SPECIES_KEY_TO_RAW_INDEX[slot["species"]],
                )
        narc.files[index] = bytes(member)
    rom.write_narc(HEADBUTT_NITROFS_PATH, narc)
