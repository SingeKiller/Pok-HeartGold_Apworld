# rom/eventdata.py
#
# Read/write access to the map event table: per-map object placement
# (NPCs, hidden items, cuttable trees, breakable rocks, etc.). Not
# currently read by any generation task -- exists so a later task has
# direct NitroFS access ready, without duplicating rom/__init__.py's NARC
# plumbing again.
#
# NitroFS path a/0/3/2 (arc_strip_name maps zone_event.narc there),
# verified directly against the real US HeartGold ROM: readable, parses
# as a NARC with 491 sub-files.

from __future__ import annotations

from collections.abc import Sequence

from rom import HeartGoldRom

NITROFS_PATH = "a/0/3/2"
EXPECTED_ENTRY_COUNT = 491


def read_all(rom: HeartGoldRom) -> list[bytes]:
    """Return every map's event data as a raw bytes blob, one per NARC
    sub-file, in on-disk order."""
    return rom.read_narc(NITROFS_PATH).files


def write_all(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    """Replace every map's event data. `entries` must have exactly as many
    elements as the table currently has -- this layer never adds or
    removes NARC sub-files, only replaces their contents."""
    narc = rom.read_narc(NITROFS_PATH)
    if len(entries) != len(narc.files):
        raise ValueError(
            f"event data table has {len(narc.files)} entries, got "
            f"{len(entries)} replacement entries -- entry count must match "
            "exactly (this layer never adds/removes NARC sub-files)."
        )
    narc.files = list(entries)
    rom.write_narc(NITROFS_PATH, narc)


def read_entry(rom: HeartGoldRom, index: int) -> bytes:
    """Read a single map's event data by its raw NARC sub-file index."""
    return rom.read_narc(NITROFS_PATH).files[index]


def write_entry(rom: HeartGoldRom, index: int, data: bytes) -> None:
    """Replace a single map's event data by its raw NARC sub-file index."""
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[index] = data
    rom.write_narc(NITROFS_PATH, narc)
