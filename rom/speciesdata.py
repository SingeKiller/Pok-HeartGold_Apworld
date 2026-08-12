# rom/speciesdata.py
#
# Read/write access to the species/personal stats table: base stats,
# types, catch rate, TM/HM compatibility etc.
#
# NitroFS path a/0/0/2 (personal.narc), verified directly against the
# real US HeartGold ROM: readable, parses as a NARC with exactly 508
# sub-files.
#
# data/species.py's SPECIES table has 505 entries, 3 fewer than this
# NARC's 508 -- the extra 3 are index 0 ("no species" placeholder) and
# 494/495 (EGG/BAD_EGG, engine-reserved). Every other raw entry matches
# exactly one data/species.py key by label, generated once into
# data/species_index.py's SPECIES_KEY_TO_RAW_INDEX.

from __future__ import annotations

from collections.abc import Sequence

from rom import HeartGoldRom

NITROFS_PATH = "a/0/0/2"
EXPECTED_ENTRY_COUNT = 508

# struct BaseStats: the six base-stat fields are the entry's first 6
# bytes, one u8 each, no padding/alignment ambiguity.
_BASE_STAT_FIELD_OFFSETS: dict[str, int] = {
    "hp": 0,
    "atk": 1,
    "def": 2,
    "speed": 3,
    "spatk": 4,
    "spdef": 5,
}

# type1/type2 immediately follow the base-stat bytes. A single-type
# species has type1 == type2 in the raw data (standard Gen 3+
# convention). Live-verified against all 505 real species, zero
# mismatches.
_TYPE1_OFFSET = 6
_TYPE2_OFFSET = 7

# abilities[2] at offset 0x16 -- confirmed both by a field-by-field
# struct walk and a live read against the real HeartGold ROM: Diglett/
# Dugtrio/Trapinch have Arena Trap (71) at 0x17, Wobbuffet has Shadow Tag
# (23) at 0x16 with 0x17==0 (mono-ability), Nosepass/Probopass/Magnezone
# have Magnet Pull (42). ability2==0 is ABILITY_NONE, not a duplicate of
# ability1.
_ABILITY1_OFFSET = 22
_ABILITY2_OFFSET = 23


def read_all(rom: HeartGoldRom) -> list[bytes]:
    """Return every species stats entry as a raw bytes blob, one per NARC
    sub-file, in on-disk order."""
    return rom.read_narc(NITROFS_PATH).files


def write_all(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    """Replace every species stats entry. `entries` must have exactly as
    many elements as the table currently has -- this layer never adds or
    removes NARC sub-files, only replaces their contents."""
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
    """Read a single species stats entry by its raw NARC sub-file index."""
    return rom.read_narc(NITROFS_PATH).files[index]


def write_entry(rom: HeartGoldRom, index: int, data: bytes) -> None:
    """Replace a single species stats entry by its raw NARC sub-file
    index."""
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[index] = data
    rom.write_narc(NITROFS_PATH, narc)


def write_base_stats(rom: HeartGoldRom, species_key: str, base_stats: dict[str, int]) -> None:
    """Overwrite one species' six base-stat bytes in place, leaving
    every other byte of its entry untouched."""
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = bytearray(read_entry(rom, raw_index))
    for field, offset in _BASE_STAT_FIELD_OFFSETS.items():
        entry[offset] = base_stats[field]
    write_entry(rom, raw_index, bytes(entry))


def read_base_stats(rom: HeartGoldRom, species_key: str) -> dict[str, int]:
    """Read one species' six base-stat bytes directly from the ROM --
    mainly for tests/verification."""
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = read_entry(rom, raw_index)
    return {field: entry[offset] for field, offset in _BASE_STAT_FIELD_OFFSETS.items()}


def write_types(rom: HeartGoldRom, species_key: str, type1: int, type2: int) -> None:
    """Overwrite one species' type1/type2 bytes in place, leaving every
    other byte untouched. type1 == type2 for a single-type species."""
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = bytearray(read_entry(rom, raw_index))
    entry[_TYPE1_OFFSET] = type1
    entry[_TYPE2_OFFSET] = type2
    write_entry(rom, raw_index, bytes(entry))


def read_types(rom: HeartGoldRom, species_key: str) -> tuple[int, int]:
    """Read one species' (type1, type2) raw bytes -- mainly for tests/
    verification."""
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = read_entry(rom, raw_index)
    return entry[_TYPE1_OFFSET], entry[_TYPE2_OFFSET]


def write_abilities(rom: HeartGoldRom, species_key: str, ability1: int, ability2: int) -> None:
    """Overwrite one species' abilities[2] bytes in place, leaving every
    other byte untouched. ability2 == 0 is ABILITY_NONE -- callers pass
    it explicitly, this function never invents a default."""
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = bytearray(read_entry(rom, raw_index))
    entry[_ABILITY1_OFFSET] = ability1
    entry[_ABILITY2_OFFSET] = ability2
    write_entry(rom, raw_index, bytes(entry))


def read_abilities(rom: HeartGoldRom, species_key: str) -> tuple[int, int]:
    """Read one species' (ability1, ability2) raw bytes -- mainly for
    tests/verification."""
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = read_entry(rom, raw_index)
    return entry[_ABILITY1_OFFSET], entry[_ABILITY2_OFFSET]
