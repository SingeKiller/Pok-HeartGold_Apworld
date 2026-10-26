from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

CHECKFLAG_OPCODE = 32
GOTOIF_OPCODE = 28
GOTOIF_TRUE = 1

FLAG_UNK_093 = 0x93
FLAG_UNK_094 = 0x94
RAINBOW_WING_PASS_FLAG = 0x532
SILVER_WING_PASS_FLAG = 0x533
LEGACY_RAINBOW_WING_PASS_FLAG = 0xB5B
LEGACY_SILVER_WING_PASS_FLAG = 0xB5C

SITES: tuple[tuple[int, int, int, int], ...] = (
    (19, 193, FLAG_UNK_093, RAINBOW_WING_PASS_FLAG),
    (103, 125, FLAG_UNK_094, SILVER_WING_PASS_FLAG),
    (103, 158, FLAG_UNK_094, SILVER_WING_PASS_FLAG),
)


class WingMonkPatchError(Exception):
    pass


def patch_script(data: bytes, offset: int, vanilla_flag: int, new_flag: int) -> bytes:
    expected = struct.pack("<HH", CHECKFLAG_OPCODE, vanilla_flag) + struct.pack("<HB", GOTOIF_OPCODE, GOTOIF_TRUE)
    if data[offset : offset + len(expected)] != expected:
        raise WingMonkPatchError(f"no `GoToIfSet {vanilla_flag:#x}` at offset {offset}")
    out = bytearray(data)
    struct.pack_into("<H", out, offset + 2, new_flag)
    return bytes(out)


def write_wing_monk_regate(rom: HeartGoldRom) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    for index, offset, vanilla_flag, new_flag in SITES:
        narc.files[index] = patch_script(bytes(narc.files[index]), offset, vanilla_flag, new_flag)
    rom.write_narc(NITROFS_PATH, narc)
