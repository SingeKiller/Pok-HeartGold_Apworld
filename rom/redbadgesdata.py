from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

OAK_LAB_SCRIPT = 740
GOTO_OPCODE = 22
GOTOIF_OPCODE = 28
COMPARE_OPCODE = 17
COUNT_BADGES_OPCODE = 296
VAR_RED_PATH_TEMP = 0x4000
VAR_BLUE_BEATEN_CALL = 0x4096
BLUE_BEATEN_CALL_VALUE = 2
GOTOIF_EQUAL = 1
GOTOIF_GREATER_OR_EQUAL = 4
VANILLA_COUNT = 16
SITE_OFFSET = 268
SITE_SIZE = 13


class RedBadgesPatchError(Exception):
    pass


def _goto(position: int, target: int) -> bytes:
    return struct.pack("<Hi", GOTO_OPCODE, target - (position + 6))


def _goto_if(position: int, condition: int, target: int) -> bytes:
    return struct.pack("<HBi", GOTOIF_OPCODE, condition, target - (position + 7))


def patch_script(blob: bytes, count: int) -> bytes:
    if not 0 <= count <= VANILLA_COUNT:
        raise ValueError(f"Red badge count {count} outside 0..{VANILLA_COUNT}")
    compare = struct.pack("<HHH", COMPARE_OPCODE, VAR_BLUE_BEATEN_CALL, BLUE_BEATEN_CALL_VALUE)
    site = bytes(blob[SITE_OFFSET : SITE_OFFSET + SITE_SIZE])
    if (
        blob.count(compare) != 1
        or blob.find(compare) != SITE_OFFSET
        or site[6:9] != struct.pack("<HB", GOTOIF_OPCODE, GOTOIF_EQUAL)
    ):
        raise RedBadgesPatchError("Oak's lab script: Mt. Silver unlock test not found at the expected place")
    gift = SITE_OFFSET + SITE_SIZE + struct.unpack_from("<i", site, 9)[0]
    extra = len(blob)
    tail = struct.pack("<HH", COUNT_BADGES_OPCODE, VAR_RED_PATH_TEMP)
    tail += struct.pack("<HHH", COMPARE_OPCODE, VAR_RED_PATH_TEMP, count)
    tail += _goto_if(extra + len(tail), GOTOIF_GREATER_OR_EQUAL, gift)
    tail += _goto(extra + len(tail), SITE_OFFSET + SITE_SIZE)
    out = bytearray(blob)
    out[SITE_OFFSET : SITE_OFFSET + SITE_SIZE] = _goto(SITE_OFFSET, extra) + bytes(SITE_SIZE - 6)
    out += tail
    return bytes(out)


def write_red_badges(rom: HeartGoldRom, count: int) -> None:
    if count == VANILLA_COUNT:
        return
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[OAK_LAB_SCRIPT] = patch_script(bytes(narc.files[OAK_LAB_SCRIPT]), count)
    rom.write_narc(NITROFS_PATH, narc)
