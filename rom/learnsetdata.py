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
    data = rom.read_narc(NITROFS_PATH).files[raw_index]
    entries = struct.unpack(f"<{len(data) // 2}H", data)
    result = []
    for entry in entries:
        if entry == _LEARNSET_END:
            break
        result.append(((entry & _LEVEL_MASK) >> _LEVEL_SHIFT, entry & _MOVEID_MASK))
    return result


def write_species_learnset(rom: HeartGoldRom, raw_index: int, learnset: list[tuple[int, int]]) -> None:
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

    trailing = existing[entry_count * 2 :]
    narc.files[raw_index] = bytes(packed) + trailing
    rom.write_narc(NITROFS_PATH, narc)
