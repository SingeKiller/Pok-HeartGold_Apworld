# rom/evodata.py
#
# Read/write access to the evolution table (task M4.5): the
# evolution-target randomizer writes here -- `species.py`'s
# `randomize_evolutions` output needs encoding into this table to actually
# take effect in-game (`data/species.py`'s own `evolutions` field is only
# ever the *logical* model, never patched into the ROM by itself).
#
# NitroFS path: `ressources/Decomposition/pokeheartgold/filesystem.mk`'s
# `arc_strip_name` maps `files/poketool/personal/evo.narc` ->
# `files/a/0/3/4`, verified directly against the real US HeartGold ROM:
# readable, parses as a NARC with exactly 508 sub-files, 44 bytes each --
# same entry count as `rom/speciesdata.py`'s personal.narc (a/0/0/2), and
# index-aligned with it (both ultimately index by the same raw species
# id -- see `data/species_index.py`/`rom/speciesdata.py`'s own docstrings
# for how that mapping was derived).
#
# Struct (Decomposition `include/pokemon_types_def.h`, `struct Evolution`):
#   struct Evolution { u16 method; u16 param; u16 target; }  -- 6 bytes
#   MAX_EVOS_PER_POKE = 7
# i.e. each 44-byte entry is 7 back-to-back 6-byte `Evolution` records (42
# bytes) plus 2 trailing bytes whose purpose was not investigated here (not
# needed -- never read or written by this module, left untouched by every
# write path below since they only ever replace the first 42 bytes).
# `method`/`param`/`target` are `data/species.py`'s own `evolutions` field
# values, already resolved by `data_gen`; `target` is a **raw species
# index** here (see `SPECIES_KEY_TO_RAW_INDEX`), not a `data/species.py`
# key. An unused evolution slot (fewer than 7 real evolutions) is encoded
# as `method=0, param=0, target=0` -- the vanilla convention for "no more
# evolutions in this list" (index 0 is the engine's own "no species"
# placeholder, never a real evolution target).

from __future__ import annotations

import struct
from collections.abc import Sequence

from rom import HeartGoldRom

NITROFS_PATH = "a/0/3/4"
EXPECTED_ENTRY_COUNT = 508
ENTRY_SIZE = 44
MAX_EVOS_PER_SPECIES = 7
_EVOLUTION_STRUCT_SIZE = 6


def read_all(rom: HeartGoldRom) -> list[bytes]:
    """Return every species' evolution entry as a raw bytes blob, one per
    NARC sub-file, in raw-species-index order (see this module's own
    docstring)."""
    return rom.read_narc(NITROFS_PATH).files


def write_all(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    """Replace every species' evolution entry. `entries` must have exactly
    as many elements as the table currently has."""
    narc = rom.read_narc(NITROFS_PATH)
    if len(entries) != len(narc.files):
        raise ValueError(
            f"evolution table has {len(narc.files)} entries, got "
            f"{len(entries)} replacement entries -- entry count must match "
            "exactly (this layer never adds/removes NARC sub-files)."
        )
    narc.files = list(entries)
    rom.write_narc(NITROFS_PATH, narc)


def read_entry(rom: HeartGoldRom, raw_index: int) -> bytes:
    """Read a single species' evolution entry by its raw NARC sub-file
    index."""
    return rom.read_narc(NITROFS_PATH).files[raw_index]


def write_entry(rom: HeartGoldRom, raw_index: int, data: bytes) -> None:
    """Replace a single species' evolution entry by its raw NARC sub-file
    index."""
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[raw_index] = data
    rom.write_narc(NITROFS_PATH, narc)


def encode_evolutions(evolutions: Sequence[tuple[int, int, int]]) -> bytes:
    """Encode up to `MAX_EVOS_PER_SPECIES` `(method, param, target)` raw
    tuples into one evolution entry's first 42 bytes, padding any unused
    slots with `(0, 0, 0)` (see this module's own docstring for why that
    encodes "no evolution"), and leaving the trailing 2 bytes zeroed."""
    if len(evolutions) > MAX_EVOS_PER_SPECIES:
        raise ValueError(f"{len(evolutions)} evolutions given, a species can have at most {MAX_EVOS_PER_SPECIES}")

    out = bytearray(ENTRY_SIZE)
    for i, (method, param, target) in enumerate(evolutions):
        offset = i * _EVOLUTION_STRUCT_SIZE
        struct.pack_into("<HHH", out, offset, method, param, target)
    return bytes(out)


def write_species_evolutions(rom: HeartGoldRom, raw_index: int, evolutions: Sequence[tuple[int, int, int]]) -> None:
    """Overwrite one species' evolution list in place, preserving its
    entry's trailing 2 unstudied bytes exactly as they were (only the
    first 42 bytes -- the 7 `Evolution` records -- are ever replaced)."""
    existing = bytearray(read_entry(rom, raw_index))
    new_records = encode_evolutions(evolutions)
    existing[: len(new_records)] = new_records
    write_entry(rom, raw_index, bytes(existing))


def read_species_evolutions(rom: HeartGoldRom, raw_index: int) -> list[tuple[int, int, int]]:
    """Read every non-empty `(method, param, target)` evolution record for
    one species -- mainly for tests/verification."""
    entry = read_entry(rom, raw_index)
    result = []
    for i in range(MAX_EVOS_PER_SPECIES):
        offset = i * _EVOLUTION_STRUCT_SIZE
        method, param, target = struct.unpack_from("<HHH", entry, offset)
        if method == 0 and param == 0 and target == 0:
            continue
        result.append((method, param, target))
    return result
