# rom/hiddenitemdata.py
#
# Read/write access to `hidden_item` location item grants (task M4.5) --
# the last of the four item-delivery mechanisms this project's locations
# use (`ground_item`/`hm_tm` -> rom/eventscriptdata.py, `npc_gift`/the
# NPC-delivered half of `hm_tm` -> rom/npcgiftdata.py, `hidden_item` ->
# here).
#
# -- Where this table actually lives (the hard part) --
#
# Unlike every other table this project patches (all plain NitroFS NARC
# sub-files), `sHiddenItemParam` (`src/data/fieldmap/hidden_items.h`, read
# by `GetHiddenItemParams`/`script_manager.c`) is declared as a genuine
# `static const` C array, compiled directly into the ARM9 main binary
# (`script_manager.o` is linked into "Static main" per the decomp's
# `main.lsf`, not any overlay). Blind byte-pattern search against
# `rom.arm9` found nothing at all -- the real, hard-won reason: the ARM9
# binary as packed in the ROM is itself LZ-compressed beyond its first
# 0x4000-byte secure area, and `rom.arm9` (both this project's own
# `HeartGoldRom.arm9` and `ndspy`'s own property) returns that *packed*
# (compressed) form, not decompressed content -- see rom/__init__.py's
# "ARM9 main-image decompressed access" section, added specifically to
# support this module, for the full explanation and the `read_main_code_
# decompressed`/`write_main_code_region` primitives this module builds on.
#
# The table's real location was found via a live BizHawk memory-write
# breakpoint (armed on the RAM address a hidden-item pickup's `SetVar
# VAR_SPECIAL_x8000` write landed on) plus a short instruction trace
# (BizHawk's own Trace Logger, frame-stepped to keep the log a manageable
# size) around the captured PC, which revealed a PC-relative `LDR`
# loading a pointer into the table being read via `LDRH r0,[r3,#0x6]`
# (the `index` field, offset 6 -- matches this module's own `_INDEX_
# OFFSET` below) inside the C source's `for (...) if (idx == table[i].
# index) break;` loop. Live-verified byte-for-byte against the decomp's
# own `hidden_items.h` (all 231 entries, exact match, no discrepancies)
# once the correct (decompressed) image was searched.
#
# `ARM9_TABLE_RAM_ADDRESS` below is a live-boot RAM address (constant --
# the DS has no ASLR, and this is static `.rodata`, not a heap
# allocation), not a NitroFS/NARC location like every other table this
# project patches -- `_table_file_offset` converts it to a byte offset
# into `rom.read_main_code_decompressed()`'s output.
#
# Struct (8 bytes, `struct HiddenItemData` in `src/script_manager.c`):
#   u16 itemId   (offset 0) -- this module's own patch target
#   u8  quantity (offset 2) -- never touched (matches rom/eventscriptdata.
#                py's/rom/npcgiftdata.py's own "only the item id operand"
#                convention)
#   u8  unk3     (offset 3) -- read by a helper (`sub_02040578` in the
#                decomp) for an unknown purpose; never touched here
#   u16 unk4     (offset 4) -- always 0 in every one of the real ROM's
#                231 entries; never touched here
#   u16 index    (offset 6) -- NOT the same as this entry's array
#                position: `sHiddenItemParam` is NOT sorted by `index`
#                (e.g. the real entry at array position 1 has index 1,
#                but position 2 has index 225) -- `include/constants/
#                hidden_items.h`'s `HIDDENITEM_*` constants ARE these
#                `index` values, and `data/locations.py`'s own `id` field
#                for a `hidden_item` location is that same constant (see
#                `data_gen/locations.toml`'s own header comment) -- so a
#                location's `id` must be resolved to an array *position*
#                by scanning for a matching `index` field
#                (`_find_position_by_index` below), never used as a
#                position directly.

from __future__ import annotations

from rom import HeartGoldRom

# Live-boot RAM address (see this module's own docstring for how this was
# found and verified). Constant across boots/ROMs of the same build (no
# ASLR on the DS, and this is static `.rodata`).
ARM9_TABLE_RAM_ADDRESS = 0x020FA558

ENTRY_COUNT = 231
ENTRY_SIZE = 8
_ITEM_ID_OFFSET = 0
_INDEX_OFFSET = 6


class HiddenItemDataError(Exception):
    """Base class for every error this module raises."""


def _table_file_offset(rom: HeartGoldRom) -> int:
    return ARM9_TABLE_RAM_ADDRESS - rom.arm9_ram_address


def read_all(rom: HeartGoldRom) -> list[bytes]:
    """Return every hidden-item table entry as a raw 8-byte blob, in
    on-disk (array) order -- NOT sorted by `index`, see this module's own
    docstring."""
    decompressed = rom.read_main_code_decompressed()
    base = _table_file_offset(rom)
    return [decompressed[base + i * ENTRY_SIZE : base + (i + 1) * ENTRY_SIZE] for i in range(ENTRY_COUNT)]


def read_entry(rom: HeartGoldRom, position: int) -> bytes:
    """Read a single hidden-item table entry by its raw array position
    (0..230) -- NOT its `index` field, see `_find_position_by_index` to
    resolve one from the other."""
    if not (0 <= position < ENTRY_COUNT):
        raise ValueError(f"position {position} out of range (0..{ENTRY_COUNT - 1})")
    decompressed = rom.read_main_code_decompressed()
    offset = _table_file_offset(rom) + position * ENTRY_SIZE
    return decompressed[offset : offset + ENTRY_SIZE]


def write_item_id(rom: HeartGoldRom, position: int, item_id: int) -> None:
    """Overwrite a single hidden-item table entry's `itemId` field in
    place (array position, not `index` -- see `_find_position_by_index`),
    leaving quantity/unk3/unk4/index byte-identical."""
    if not (0 <= position < ENTRY_COUNT):
        raise ValueError(f"position {position} out of range (0..{ENTRY_COUNT - 1})")
    if not (0 <= item_id <= 0xFFFF):
        raise ValueError(f"item id {item_id} does not fit the table's itemId field (an unsigned 16-bit value).")
    offset = _table_file_offset(rom) + position * ENTRY_SIZE + _ITEM_ID_OFFSET
    rom.write_main_code_region(offset, item_id.to_bytes(2, "little"))


def _find_position_by_index(rom: HeartGoldRom, index: int) -> int:
    """Array position (0..230) of the entry whose `index` field equals
    `index` (a `HIDDENITEM_*` constant / `data/locations.py`'s own `id`
    field for a `hidden_item` location) -- see this module's own
    docstring for why this scan is necessary rather than using `index`
    as a position directly."""
    entries = read_all(rom)
    for position, entry in enumerate(entries):
        entry_index = int.from_bytes(entry[_INDEX_OFFSET : _INDEX_OFFSET + 2], "little")
        if entry_index == index:
            return position
    raise HiddenItemDataError(f"no hidden-item table entry has index {index}")


def write_hidden_item_substitution(rom: HeartGoldRom, location_key: str, item_key: str) -> None:
    """Patch the hidden-item table entry for a `hidden_item` location (a
    key of `data/locations.py`'s `LOCATIONS`) so it grants a different
    item (a key of `data/items.py`'s `ITEMS`) instead of its vanilla
    `original_item`. Lazily imports `data.locations`/`data.items` (same
    "rom/ never depends on data/ at import time" convention rom/
    eventscriptdata.py's/rom/npcgiftdata.py's own substitution functions
    already use)."""
    from data.items import ITEMS
    from data.locations import LOCATIONS

    location = LOCATIONS.get(location_key)
    if location is None:
        raise KeyError(f"unknown location key: {location_key!r}")
    if location["type"] != "hidden_item":
        raise HiddenItemDataError(
            f"location {location_key!r} is type {location['type']!r}, not 'hidden_item' -- "
            "this module only patches the hidden-item table (ground_item/npc_gift/hm_tm/badge "
            "are out of scope, see rom/eventscriptdata.py/rom/npcgiftdata.py instead)."
        )
    item = ITEMS.get(item_key)
    if item is None:
        raise KeyError(f"unknown item key: {item_key!r}")

    position = _find_position_by_index(rom, location["id"])
    write_item_id(rom, position, item["id"])
