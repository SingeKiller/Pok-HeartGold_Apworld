from __future__ import annotations

from collections.abc import Sequence

from rom import HeartGoldRom

NITROFS_PATH = "a/0/0/2"
EXPECTED_ENTRY_COUNT = 508

_BASE_STAT_FIELD_OFFSETS: dict[str, int] = {
    "hp": 0,
    "atk": 1,
    "def": 2,
    "speed": 3,
    "spatk": 4,
    "spdef": 5,
}

_TYPE1_OFFSET = 6
_TYPE2_OFFSET = 7

_ABILITY1_OFFSET = 22
_ABILITY2_OFFSET = 23


def read_all(rom: HeartGoldRom) -> list[bytes]:
    return rom.read_narc(NITROFS_PATH).files


def write_all(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    if len(entries) != len(narc.files):
        raise ValueError(
            f"species data table has {len(narc.files)} entries, got "
            f"{len(entries)} replacement entries -- entry count must match "
            "exactly (this layer never adds/removes NARC sub-files)."
        )
    narc.files = list(entries)
    rom.write_narc(NITROFS_PATH, narc)


def read_entry(rom: HeartGoldRom, index: int) -> bytes:
    return rom.read_narc(NITROFS_PATH).files[index]


def write_entry(rom: HeartGoldRom, index: int, data: bytes) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[index] = data
    rom.write_narc(NITROFS_PATH, narc)


def write_base_stats(rom: HeartGoldRom, species_key: str, base_stats: dict[str, int]) -> None:
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = bytearray(read_entry(rom, raw_index))
    for field, offset in _BASE_STAT_FIELD_OFFSETS.items():
        entry[offset] = base_stats[field]
    write_entry(rom, raw_index, bytes(entry))


def read_base_stats(rom: HeartGoldRom, species_key: str) -> dict[str, int]:
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = read_entry(rom, raw_index)
    return {field: entry[offset] for field, offset in _BASE_STAT_FIELD_OFFSETS.items()}


def write_types(rom: HeartGoldRom, species_key: str, type1: int, type2: int) -> None:
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = bytearray(read_entry(rom, raw_index))
    entry[_TYPE1_OFFSET] = type1
    entry[_TYPE2_OFFSET] = type2
    write_entry(rom, raw_index, bytes(entry))


def read_types(rom: HeartGoldRom, species_key: str) -> tuple[int, int]:
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = read_entry(rom, raw_index)
    return entry[_TYPE1_OFFSET], entry[_TYPE2_OFFSET]


def write_abilities(rom: HeartGoldRom, species_key: str, ability1: int, ability2: int) -> None:
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = bytearray(read_entry(rom, raw_index))
    entry[_ABILITY1_OFFSET] = ability1
    entry[_ABILITY2_OFFSET] = ability2
    write_entry(rom, raw_index, bytes(entry))


def read_abilities(rom: HeartGoldRom, species_key: str) -> tuple[int, int]:
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = read_entry(rom, raw_index)
    return entry[_ABILITY1_OFFSET], entry[_ABILITY2_OFFSET]
