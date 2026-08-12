# rom/itemdata.py
#
# Read/write access to the item stats table -- distinct from
# data/items.py (generated from the decomp's own source CSV). No
# dependency on data/ at import time, so this stays usable before
# data_gen.py has ever been run.
#
# NitroFS path a/0/1/7 (item_data.narc, renamed to an anonymous numbered
# path by the retail build), verified directly against the real US
# HeartGold ROM: readable, parses as a NARC with exactly 514 sub-files.
# Not to be confused with pbr/item_data.narc (also present in the ROM,
# used as tests/test_rom_roundtrip.py's round-trip sample) -- that's a
# separate, smaller copy kept for Pokemon Battle Revolution connectivity,
# not what the HeartGold engine itself reads for bag items.
#
# Open question, deliberately unresolved: the real NARC has exactly 514
# sub-files, while data/items.py's id field spans 1-536 with 23 gaps
# (unused legacy slots) -- raw NARC sub-file index is likely a compacted
# row position, not a direct match for data/items.py's id values.
# tests/test_rom_access.py only asserts the count relationship, not an
# index<->id equivalence.

from __future__ import annotations

from collections.abc import Sequence

from rom import HeartGoldRom

NITROFS_PATH = "a/0/1/7"
EXPECTED_ENTRY_COUNT = 514


def read_all(rom: HeartGoldRom) -> list[bytes]:
    """Every item stats entry as a raw bytes blob, in on-disk order
    (index 0 is the ITEM_NONE placeholder)."""
    return rom.read_narc(NITROFS_PATH).files


def write_all(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    """Replace every item stats entry. `entries` must have exactly as
    many elements as the table currently has."""
    narc = rom.read_narc(NITROFS_PATH)
    if len(entries) != len(narc.files):
        raise ValueError(
            f"item data table has {len(narc.files)} entries, got "
            f"{len(entries)} replacement entries -- entry count must match "
            "exactly (this layer never adds/removes NARC sub-files)."
        )
    narc.files = list(entries)
    rom.write_narc(NITROFS_PATH, narc)


def read_entry(rom: HeartGoldRom, index: int) -> bytes:
    """Read a single item stats entry by its raw NARC sub-file index."""
    return rom.read_narc(NITROFS_PATH).files[index]


def write_entry(rom: HeartGoldRom, index: int, data: bytes) -> None:
    """Replace a single item stats entry by its raw NARC sub-file index."""
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[index] = data
    rom.write_narc(NITROFS_PATH, narc)
