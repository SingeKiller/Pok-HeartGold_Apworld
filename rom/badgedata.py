from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

GIVEBADGE_OPCODE = 295
NOP_OPCODE = 0
SETFLAG_OPCODE = 30

TABLE: dict[str, tuple[int, int]] = {
    "zephyr": (859, 230),
    "hive": (869, 283),
    "plain": (886, 431),
    "fog": (922, 372),
    "storm": (877, 121),
    "mineral": (913, 426),
    "glacier": (932, 270),
    "rising": (112, 618),
    "boulder": (752, 314),
    "cascade": (760, 703),
    "thunder": (778, 827),
    "rainbow": (786, 326),
    "soul": (809, 1817),
    "marsh": (829, 200),
    "volcano": (15, 311),
    "earth": (743, 164),
}


BADGE_SENTINEL_INJECTIONS: dict[str, int] = {
    "hive": 0x520,
    "fog": 0x521,
    "storm": 0x522,
    "mineral": 0x523,
    "glacier": 0x524,
    "boulder": 0x525,
    "cascade": 0x526,
    "rainbow": 0x527,
    "soul": 0x528,
    "marsh": 0x529,
}


LEGACY_BADGE_SENTINEL_INJECTIONS: dict[str, int] = {
    "hive": 0xB50,
    "fog": 0xB51,
    "storm": 0xB52,
    "mineral": 0xB53,
    "glacier": 0xB54,
    "boulder": 0xB55,
    "cascade": 0xB56,
    "rainbow": 0xB57,
    "soul": 0xB58,
    "marsh": 0xB59,
}


class BadgeDataError(Exception):
    pass


def read_givebadge_operand(rom: HeartGoldRom, narc_index: int, offset: int) -> tuple[int, int]:
    narc = rom.read_narc(NITROFS_PATH)
    blob = narc.files[narc_index]
    return struct.unpack_from("<HH", blob, offset)


def write_badge_neutralized(rom: HeartGoldRom, narc_index: int, offset: int) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    blob = bytearray(narc.files[narc_index])
    struct.pack_into("<HH", blob, offset, NOP_OPCODE, NOP_OPCODE)
    narc.files[narc_index] = bytes(blob)
    rom.write_narc(NITROFS_PATH, narc)


def write_badge_sentinel_injected(rom: HeartGoldRom, narc_index: int, offset: int, flag_id: int) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    blob = bytearray(narc.files[narc_index])
    struct.pack_into("<HH", blob, offset, SETFLAG_OPCODE, flag_id)
    narc.files[narc_index] = bytes(blob)
    rom.write_narc(NITROFS_PATH, narc)


def write_all_badges_neutralized(rom: HeartGoldRom) -> None:
    for badge_name, (narc_index, offset) in TABLE.items():
        flag_id = BADGE_SENTINEL_INJECTIONS.get(badge_name)
        if flag_id is not None:
            write_badge_sentinel_injected(rom, narc_index, offset, flag_id)
        else:
            write_badge_neutralized(rom, narc_index, offset)
