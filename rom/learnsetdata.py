# rom/learnsetdata.py
#
# Read/write access to the per-species level-up learnset table
# (wotbl.narc) -- species.py's randomize_learnsets writes here.
#
# NitroFS path a/0/3/3 (wotbl.narc), verified directly against the real
# US HeartGold ROM: readable, parses as a NARC with exactly 508
# sub-files, matching data/species_index.py's SPECIES_KEY_TO_RAW_INDEX
# 1:1 the same way personal.narc (rom/speciesdata.py, a/0/0/2) does.
# NARC_poketool_personal_wotbl = 33 in the decomp's own
# filesystem_files_def.h; the a/0/3/3 path itself was found empirically
# (the decomp gives no direct symbolic ROM path for a NARC id), not
# derived from that id by any confirmed general formula.
#
# Each sub-file is a variable-length, per-species array of packed u16
# entries (include/pokemon.h): low 9 bits move id (data/moves.py's own
# `id` field, same raw indexing rom/movedata.py already uses against
# waza_tbl.narc), high 7 bits the level it's learned at, terminated by a
# single 0xFFFF sentinel (LEVEL_UP_LEARNSET_END) -- confirmed directly
# against the real ROM: Bulbasaur's (raw index 1) 14 real entries decode
# to exactly the same (level, move) sequence data_gen/species.toml
# already records by hand. Real ROM quirk found while implementing the
# write side: Bulbasaur's own sub-file is 32 bytes (16 words) -- 14 real
# entries + the terminator at word 14, plus one extra 0x0000 padding word
# after it (word 15), presumably a 4-byte NARC member alignment artifact,
# not itself meaningful data. write_species_learnset therefore locates
# the terminator by scanning (same as read_species_learnset), not by
# assuming it's the buffer's last word, and preserves every byte from
# that point on completely untouched. randomize_learnsets only ever
# replaces the move-id bits of an existing entry, one-for-one -- the
# level, the entry count, the terminator, and any trailing padding are
# always left byte-identical, so every write is exactly the same length
# as the data it replaces (no narc member resize, no cross-region ARM9
# append risk -- the same safety property every other in-place NARC
# field rewrite in this project already has, e.g. rom/movedata.py/
# rom/speciesdata.py).

from __future__ import annotations

import struct

from rom import HeartGoldRom

NITROFS_PATH = "a/0/3/3"
EXPECTED_ENTRY_COUNT = 508

_LEARNSET_END = 0xFFFF
_MOVEID_MASK = 0x01FF
_LEVEL_MASK = 0xFE00
_LEVEL_SHIFT = 9


def read_species_learnset(rom: HeartGoldRom, raw_index: int) -> list[tuple[int, int]]:
    """(level, raw_move_id) pairs for raw species `raw_index`, in file
    order, terminator excluded."""
    data = rom.read_narc(NITROFS_PATH).files[raw_index]
    entries = struct.unpack(f"<{len(data) // 2}H", data)
    result = []
    for entry in entries:
        if entry == _LEARNSET_END:
            break
        result.append(((entry & _LEVEL_MASK) >> _LEVEL_SHIFT, entry & _MOVEID_MASK))
    return result


def write_species_learnset(rom: HeartGoldRom, raw_index: int, learnset: list[tuple[int, int]]) -> None:
    """Overwrite raw species `raw_index`'s level-up learnset with
    `learnset` (a list of (level, raw_move_id) pairs, in the same order
    and count as the existing data -- see species.randomize_learnsets,
    which only ever replaces the move id of each of a species' own
    existing entries, never adds/removes one). Bytes from the terminator
    onward (including any trailing alignment padding -- see this module's
    own docstring) are left completely untouched."""
    narc = rom.read_narc(NITROFS_PATH)
    existing = narc.files[raw_index]
    words = struct.unpack(f"<{len(existing) // 2}H", existing)
    try:
        entry_count = words.index(_LEARNSET_END)
    except ValueError:
        raise ValueError(f"raw species index {raw_index}'s learnset has no {_LEARNSET_END:#06x} terminator") from None

    if len(learnset) != entry_count:
        raise ValueError(
            f"learnset for raw species index {raw_index} has {len(learnset)} entries, "
            f"expected {entry_count} to match the existing ROM data exactly"
        )

    packed = bytearray()
    for level, move_id in learnset:
        if not (0 <= move_id <= _MOVEID_MASK):
            raise ValueError(f"move id {move_id} out of range for a 9-bit learnset entry")
        if not (0 <= level <= (_LEVEL_MASK >> _LEVEL_SHIFT)):
            raise ValueError(f"level {level} out of range for a 7-bit learnset entry")
        packed += struct.pack("<H", (level << _LEVEL_SHIFT) | move_id)

    trailing = existing[entry_count * 2 :]  # terminator word + any padding, byte-identical
    narc.files[raw_index] = bytes(packed) + trailing
    rom.write_narc(NITROFS_PATH, narc)
