# rom/speciesdata.py
#
# Read/write access to the species/personal stats table (task C13): base
# stats, types, catch rate, TM/HM compatibility etc. -- the table
# `species.py`'s evolution/starter/encounter randomization (task C11) will
# eventually need patched into the ROM to actually take effect in-game.
#
# NitroFS path: like rom/itemdata.py's item table, this table is not
# reachable at its decomp source-tree path in the retail ROM
# (`poketool/personal/personal.narc` does not exist in the built ROM).
# `ressources/Decomposition/pokeheartgold/filesystem.mk`'s
# `arc_strip_name` call maps `files/poketool/personal/personal.narc` ->
# `files/a/0/0/2`, i.e. the real NitroFS path is `a/0/0/2`, verified
# directly against the real US HeartGold ROM: readable, parses as a NARC
# with exactly 508 sub-files.
#
# Index question, RESOLVED (task M4.5, see docs/architecture.md's "## M4.5"
# section): `data/species.py`'s `SPECIES` table has 505 entries (493 real
# Pokedex species + 12 HGSS alternate forms, see species.py's own
# `real_species_pool` docstring), 3 fewer than this NARC's 508 sub-files.
# The extra 3 are index 0 ("no species" placeholder) and 494/495 ("EGG"/
# "BAD_EGG", engine-reserved) -- every one of the other 505 raw entries
# matches exactly one `data/species.py` key by label, generated once into
# `data/species_index.py`'s `SPECIES_KEY_TO_RAW_INDEX` (see
# `data_gen/species_index.toml`'s own header for the derivation).
# `tests/test_rom_access.py`'s loose entry-count check predates this and
# was not tightened further (not needed -- the real mapping now lives in
# `data/species_index.py`, generated and tested on its own terms).

from __future__ import annotations

from collections.abc import Sequence

from rom import HeartGoldRom

# See this module's docstring for how this numbered path was derived and
# verified against the real ROM.
NITROFS_PATH = "a/0/0/2"

# Sub-file count confirmed against the real US HeartGold ROM.
EXPECTED_ENTRY_COUNT = 508

# Decomposition `include/pokemon_types_def.h`, `struct BaseStats`: the six
# base-stat fields are the entry's first 6 bytes, one `u8` each, in this
# exact order -- no padding/alignment ambiguity (plain byte fields).
_BASE_STAT_FIELD_OFFSETS: dict[str, int] = {
    "hp": 0,
    "atk": 1,
    "def": 2,
    "speed": 3,
    "spatk": 4,
    "spdef": 5,
}

# `struct BaseStats`: `type1`/`type2` immediately follow the six base-stat
# bytes above. A single-type species (`data/species.py`'s `types` is a
# 1-tuple) has `type1 == type2` in the raw data -- the standard Gen 3+
# convention. Live-verified against all 505 real species, zero mismatches
# (cross-referencing `rom.movedata.TYPE_NAME_TO_ID`, the same raw type
# byte values moves use).
_TYPE1_OFFSET = 6
_TYPE2_OFFSET = 7


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
    """Overwrite one species' six base-stat bytes (`hp`/`atk`/`def`/
    `speed`/`spatk`/`spdef`, matching `data/species.py`'s own
    `base_stats` dict shape) in place, leaving every other byte of its
    entry (types, catch rate, abilities, TM/HM compatibility, ...)
    untouched -- the base-stat randomizer's own documented contract:
    only the six stat values change, everything else (including the
    species' growth rate/EXP curve, "on garde le scaling") stays vanilla."""
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = bytearray(read_entry(rom, raw_index))
    for field, offset in _BASE_STAT_FIELD_OFFSETS.items():
        entry[offset] = base_stats[field]
    write_entry(rom, raw_index, bytes(entry))


def read_base_stats(rom: HeartGoldRom, species_key: str) -> dict[str, int]:
    """Read one species' six base-stat bytes directly from the ROM --
    mainly for tests/verification, `write_base_stats` is the normal write
    path."""
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = read_entry(rom, raw_index)
    return {field: entry[offset] for field, offset in _BASE_STAT_FIELD_OFFSETS.items()}


def write_types(rom: HeartGoldRom, species_key: str, type1: int, type2: int) -> None:
    """Overwrite one species' `type1`/`type2` bytes in place, leaving
    every other byte of its entry (base stats, catch rate, abilities,
    TM/HM compatibility, ...) untouched. `type1 == type2` for a
    single-type species (see this module's own docstring)."""
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = bytearray(read_entry(rom, raw_index))
    entry[_TYPE1_OFFSET] = type1
    entry[_TYPE2_OFFSET] = type2
    write_entry(rom, raw_index, bytes(entry))


def read_types(rom: HeartGoldRom, species_key: str) -> tuple[int, int]:
    """Read one species' `(type1, type2)` raw bytes directly from the ROM
    -- mainly for tests/verification, `write_types` is the normal write
    path."""
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]
    entry = read_entry(rom, raw_index)
    return entry[_TYPE1_OFFSET], entry[_TYPE2_OFFSET]
