# rom/encounterdata.py
#
# Read/write access to the wild encounter tables: per-map grass/surf/
# rock-smash/fishing/headbutt species slots.
#
# NitroFS paths a/0/3/7 (HeartGold, g_enc_data.narc) and a/1/3/6
# (SoulSilver, s_enc_data.narc) -- both present in every HGSS ROM
# regardless of version, but which one the compiled game code actually
# reads at runtime is a compile-time #ifdef HEARTGOLD choice, not a
# runtime one -- see NOTES.md for the live verification and why every
# function here picks its path from rom.version (`_nitrofs_path_for`)
# rather than hardcoding HEARTGOLD_NITROFS_PATH.
#
# data/encounters.py's ENCOUNTERS table has 137 zones, fewer than either
# NARC's 142 sub-files -- some maps were filtered out during data_gen
# extraction. Raw index mapping resolved for 134/137 zones via
# gs_enc_data.json's own array order (see NOTES.md); the 3 unmatched
# zones have a headbutt table only, no land/surf/rock_smash/fishing entry
# to patch at all.
#
# Struct: Decomposition include/wild_encounter.h's EncounterData, 0xC4 =
# 196 bytes, confirmed against the real ROM's entry size. Species fields
# throughout are raw species indices (data/species_index.py's
# SPECIES_KEY_TO_RAW_INDEX).

from __future__ import annotations

import struct
from collections.abc import Sequence

from rom import HeartGoldRom

HEARTGOLD_NITROFS_PATH = "a/0/3/7"
SOULSILVER_NITROFS_PATH = "a/1/3/6"

EXPECTED_ENTRY_COUNT = 142


def _nitrofs_path_for(rom: HeartGoldRom) -> str:
    """The NitroFS path this rom's own compiled game code actually reads
    at runtime for wild encounters. rom.version is None (already-patched
    ROM, expect_vanilla=False) falls back to HeartGold rather than
    guessing."""
    if rom.version == "soulsilver":
        return SOULSILVER_NITROFS_PATH
    return HEARTGOLD_NITROFS_PATH


def read_all(rom: HeartGoldRom) -> list[bytes]:
    """Every wild-encounter zone entry as a raw bytes blob, in on-disk
    order, from rom's own version-appropriate table."""
    return rom.read_narc(_nitrofs_path_for(rom)).files


def write_all(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    """Replace every wild-encounter zone entry. `entries` must have
    exactly as many elements as the table currently has."""
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
    """Read a single wild-encounter zone entry by its raw NARC sub-file
    index."""
    return rom.read_narc(_nitrofs_path_for(rom)).files[index]


def write_entry(rom: HeartGoldRom, index: int, data: bytes) -> None:
    """Replace a single wild-encounter zone entry by its raw NARC
    sub-file index."""
    path = _nitrofs_path_for(rom)
    narc = rom.read_narc(path)
    narc.files[index] = data
    rom.write_narc(path, narc)


# Byte offsets within one 196-byte EncounterData entry.
_LAND_SPECIES_MORN_OFFSET = 0x14
_LAND_SPECIES_DAY_OFFSET = 0x2C
_LAND_SPECIES_NITE_OFFSET = 0x44
_LAND_SLOT_COUNT = 12
_SURF_SLOTS_OFFSET = 0x64
_ROCK_SMASH_SLOTS_OFFSET = 0x78
_OLD_ROD_SLOTS_OFFSET = 0x80
_GOOD_ROD_SLOTS_OFFSET = 0x94
_SUPER_ROD_SLOTS_OFFSET = 0xA8
_ENCOUNTER_DATA_SLOT_SIZE = 4  # EncounterDataSlot{u8 min; u8 max; u16 species;}
_ENCOUNTER_DATA_SLOT_SPECIES_OFFSET = 2

# Capacity of each slot array -- writing past these would land in the
# next field entirely, silently, so every write path checks against these
# rather than trusting zone's own slot counts.
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


def write_zone_encounters(rom: HeartGoldRom, zone_key: str, zone: dict) -> None:
    """Overwrite one zone's species fields in place (land morn/day/nite,
    surf, rock_smash, and old/good/super rod fishing), leaving every
    rate/level byte untouched. Headbutt encounters are not covered."""
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
