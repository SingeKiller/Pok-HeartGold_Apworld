# rom/itemdata.py
#
# Read/write access to the item stats table (task C13), the NARC the real
# game engine uses at runtime for item prices, pockets, held-item effects
# etc. -- distinct from `data/items.py` (generated from the decomp's own
# source CSV, see docs/architecture.md "## Spikes" -> Spike 3), which this
# module cross-checks against but never reads at import time (this module
# has no dependency on `data/`, so it stays usable before `data_gen.py` has
# ever been run, matching this project's "rom/ is a plain access layer"
# scope for C13 -- see this module's own EXPECTED_ENTRY_COUNT note below).
#
# NitroFS path: this table is **not** reachable at any human-readable path
# in the retail ROM (`itemtool/itemdata/item_data.narc`, the decomp's own
# source-tree location, does not exist in the built ROM -- confirmed
# against the real ROM). `ressources/Decomposition/pokeheartgold/
# filesystem.mk`'s `arc_strip_name` calls reveal why: the retail build
# process renames this file to an anonymous numbered path before packing
# the NitroFS image, matching a long-standing Game Freak/Nintendo
# convention. `filesystem.mk` maps
# `files/itemtool/itemdata/item_data.narc` -> `files/a/0/1/7`, i.e. the
# real NitroFS path is `a/0/1/7`, verified directly against the real US
# HeartGold ROM (MD5 in rom/__init__.py's HEARTGOLD_US_MD5): readable,
# parses as a NARC with exactly 514 sub-files.
#
# Note this is a *different* file from `pbr/item_data.narc` (also present
# in the ROM, and used as tests/test_rom_roundtrip.py's arbitrary
# round-trip sample) -- the `pbr/` tree holds a separate, smaller copy of
# item/species/move data kept for Pokemon Battle Revolution (Wii)
# connectivity, not the data the HeartGold engine itself uses for bag
# items. Randomization/patching must target `a/0/1/7`, not `pbr/
# item_data.narc`.
#
# Open question, deliberately left unresolved here (out of scope for a
# pure access layer -- see this module's docstring intro): the real NARC
# has exactly 514 sub-files (matching the decomp's own `item_data.csv` row
# count, see Spike 3), while `data/items.py`'s `id` field spans 1-536 with
# 23 gaps (22 unused legacy `ITEM_UNUSED_*` slots plus the documented
# `ITEM_EXPLORER_KIT` gap). This means raw NARC sub-file index is very
# likely a *compacted* row position, not a direct match for `data/
# items.py`'s `id` values -- resolving that mapping (needed before any
# field-level item patch can target the right sub-file for a given named
# item) is left to whichever later task actually writes item-stat patches.
# `tests/test_rom_access.py` only asserts the *count* relationship (514
# sub-files == 1 `ITEM_NONE` placeholder + the 513 real items in
# `data/items.py`), not an index<->id equivalence.

from __future__ import annotations

from collections.abc import Sequence

from rom import HeartGoldRom

# See this module's docstring for how this numbered path was derived and
# verified against the real ROM.
NITROFS_PATH = "a/0/1/7"

# Sub-file count confirmed against the real US HeartGold ROM: 1 `ITEM_NONE`
# placeholder (index 0) + the 513 real items also present in
# `data/items.py` (see docs/architecture.md Spike 3).
EXPECTED_ENTRY_COUNT = 514


def read_all(rom: HeartGoldRom) -> list[bytes]:
    """Return every item stats entry as a raw bytes blob, one per NARC
    sub-file, in on-disk order (index 0 is the `ITEM_NONE` placeholder)."""
    return rom.read_narc(NITROFS_PATH).files


def write_all(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    """Replace every item stats entry. `entries` must have exactly as many
    elements as the table currently has (`read_all` performed just before
    this call) -- this layer never adds or removes NARC sub-files, only
    replaces their contents."""
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
    """Read a single item stats entry by its raw NARC sub-file index (see
    this module's docstring for the open question around what this index
    means relative to `data/items.py`'s `id` field)."""
    return rom.read_narc(NITROFS_PATH).files[index]


def write_entry(rom: HeartGoldRom, index: int, data: bytes) -> None:
    """Replace a single item stats entry by its raw NARC sub-file index."""
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[index] = data
    rom.write_narc(NITROFS_PATH, narc)
