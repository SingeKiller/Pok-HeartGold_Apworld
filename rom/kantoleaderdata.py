from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

CINNABAR_SCRIPT = 815
COMPARE_OPCODE = 17
VAR_KANTO_LEADERS_BEATEN = 0x4135
VANILLA_COUNT = 7


class KantoLeaderPatchError(Exception):
    pass


def patch_script(blob: bytes, count: int) -> bytes:
    if not 0 <= count <= VANILLA_COUNT:
        raise ValueError(f"Kanto Leader count {count} outside 0..{VANILLA_COUNT}")
    pattern = struct.pack("<HHH", COMPARE_OPCODE, VAR_KANTO_LEADERS_BEATEN, VANILLA_COUNT)
    if blob.count(pattern) != 1:
        raise KantoLeaderPatchError("Cinnabar script: Blue's Kanto Leader test not found exactly once")
    offset = blob.find(pattern)
    out = bytearray(blob)
    struct.pack_into("<H", out, offset + 4, count)
    return bytes(out)


def write_blue_kanto_leaders(rom: HeartGoldRom, count: int) -> None:
    if count == VANILLA_COUNT:
        return
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[CINNABAR_SCRIPT] = patch_script(narc.files[CINNABAR_SCRIPT], count)
    rom.write_narc(NITROFS_PATH, narc)
