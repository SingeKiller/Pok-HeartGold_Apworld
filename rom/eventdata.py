# rom/eventdata.py
#
# Read/write access to the map event table (task C13): per-map object
# placement (NPCs, hidden items, cuttable trees, breakable rocks, etc.).
# Not currently read by any generation task in this project (`data/
# locations.py`'s ground/hidden items come from the decomp's own scripts/
# event source, not from this NARC -- see docs/architecture.md), but the
# ROM's item/species/trainer/encounter patches applied by the other
# rom/*data.py submodules can only change *what* a location's Pokemon/item
# is, not add or move an in-game object outright; this module exists so a
# later task (e.g. moving a hidden item, adding an HM-gated obstacle
# similar to what ressources/platinum_archipelago/rom/eventdata.py does for
# Platinum) has direct NitroFS access ready, without having to duplicate
# rom/__init__.py's NARC plumbing again.
#
# NitroFS path: like rom/itemdata.py's item table, this table is not
# reachable at its decomp source-tree path in the retail ROM
# (`fielddata/eventdata/zone_event.narc` does not exist in the built ROM).
# `ressources/Decomposition/pokeheartgold/filesystem.mk`'s
# `arc_strip_name` call maps `files/fielddata/eventdata/zone_event.narc`
# -> `files/a/0/3/2`, i.e. the real NitroFS path is `a/0/3/2`, verified
# directly against the real US HeartGold ROM: readable, parses as a NARC
# with 491 sub-files (one per map that has any placed event objects).
#
# No cross-check against any `data/*.py` table is done here (unlike the
# other rom/*data.py submodules): there is no generated table this NARC's
# entry count is expected to line up with. `tests/test_rom_access.py`
# only asserts this table is readable and round-trips through a save/
# reload cycle without corruption, same as the other tables.

from __future__ import annotations

from collections.abc import Sequence

from rom import HeartGoldRom

# See this module's docstring for how this numbered path was derived and
# verified against the real ROM.
NITROFS_PATH = "a/0/3/2"

# Sub-file count confirmed against the real US HeartGold ROM.
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
