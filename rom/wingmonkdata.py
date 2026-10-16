# rom/wingmonkdata.py
#
# The Bell Tower and Whirl Islands monks let the player through with the
# wing ITEM (v0.2.5, user request), instead of only after the vanilla NPC
# hands it over.
#
# Vanilla: each monk runs `GoToIfSet FLAG_UNK_093` (Rainbow Wing, Bell
# Tower 1F, scr_seq_0019_D17R0101.s:69) or `GoToIfSet FLAG_UNK_094` (Silver
# Wing, Whirl Islands B2F, scr_seq_0103_D40R0104.s:40 and :49). Those flags
# are set by the handover scripts only, and they double as the handover
# locations' own check flags, so the client cannot set them without
# reporting a check that was never done.
#
# Here: the flag id inside each of those three CheckFlag instructions is
# rewritten to a fresh one (0x532 / 0x533, unused by the whole game), which
# client.py sets as soon as the wing item has been received, wherever it
# came from. Only the 2-byte flag operand changes; the 11-byte
# CheckFlag + GoToIf TRUE shape and its jump target stay vanilla. Offsets
# verified byte for byte on both the HeartGold and SoulSilver US ROMs.

from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

CHECKFLAG_OPCODE = 32
GOTOIF_OPCODE = 28
GOTOIF_TRUE = 1

FLAG_UNK_093 = 0x93  # Rainbow Wing handed over (vanilla)
FLAG_UNK_094 = 0x94  # Silver Wing handed over (vanilla)
# 0x532/0x533 since 2026-09-24 (the old 0xB5B/0xB5C sat in the daily band,
# wiped at every day change; see rom/badgedata.py). The client sets both.
RAINBOW_WING_PASS_FLAG = 0x532
SILVER_WING_PASS_FLAG = 0x533
LEGACY_RAINBOW_WING_PASS_FLAG = 0xB5B
LEGACY_SILVER_WING_PASS_FLAG = 0xB5C

# (scr_seq narc index, byte offset of the CheckFlag opcode, vanilla flag, new flag)
SITES: tuple[tuple[int, int, int, int], ...] = (
    (19, 193, FLAG_UNK_093, RAINBOW_WING_PASS_FLAG),
    (103, 125, FLAG_UNK_094, SILVER_WING_PASS_FLAG),
    (103, 158, FLAG_UNK_094, SILVER_WING_PASS_FLAG),
)


class WingMonkPatchError(Exception):
    """A monk script does not hold the expected vanilla instruction."""


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
