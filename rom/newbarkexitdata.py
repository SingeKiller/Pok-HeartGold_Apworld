from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

SETVAR_OPCODE = 41
VAR_SCENE_NEW_BARK_EAST_EXIT = 0x4081
EAST_EXIT_OPEN = 3

SITES: tuple[tuple[int, int, int], ...] = (
    (112, 776, 1),
    (843, 3175, 2),
)


class NewBarkExitPatchError(Exception):
    pass


def patch_script(data: bytes, offset: int, vanilla_value: int) -> bytes:
    expected = struct.pack("<HHH", SETVAR_OPCODE, VAR_SCENE_NEW_BARK_EAST_EXIT, vanilla_value)
    if data[offset : offset + len(expected)] != expected:
        raise NewBarkExitPatchError(
            f"no `SetVar VAR_SCENE_NEW_BARK_EAST_EXIT, {vanilla_value}` at offset {offset}"
        )
    out = bytearray(data)
    struct.pack_into("<H", out, offset + 4, EAST_EXIT_OPEN)
    return bytes(out)


def write_new_bark_east_exit_open(rom: HeartGoldRom) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    for index, offset, vanilla_value in SITES:
        narc.files[index] = patch_script(bytes(narc.files[index]), offset, vanilla_value)
    rom.write_narc(NITROFS_PATH, narc)
