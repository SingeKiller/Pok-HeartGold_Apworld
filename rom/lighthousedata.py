from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.deathlinkdata import scrdef_offsets
from rom.eventscriptdata import NITROFS_PATH

LIGHTHOUSE_TOP_FILE = 66
FLAG_GOT_SECRETPOTION = 0xB9
VAR_SCENE_LIGHTHOUSE_JASMINE = 0x40A5

_TESTS_SHIFT = 8
_FIRST_TALK = 0x62
_HAND_OVER = 0xB5

_CHECKFLAG = 32
_COMPARE_VAR_TO_VALUE = 17
_GOTO_IF = 28
_TRUE = 1
_EQUAL = 1


class LighthousePatchError(Exception):
    pass


def _goto_if(position: int, condition: int, target: int) -> bytes:
    return struct.pack("<HBi", _GOTO_IF, condition, target - (position + 3) - 4)


def vanilla_tests(start: int) -> bytes:
    flag_test = struct.pack("<HH", _CHECKFLAG, FLAG_GOT_SECRETPOTION) + _goto_if(start + 4, _TRUE, _HAND_OVER)
    var_start = start + len(flag_test)
    var_test = struct.pack("<HHH", _COMPARE_VAR_TO_VALUE, VAR_SCENE_LIGHTHOUSE_JASMINE, 0)
    return flag_test + var_test + _goto_if(var_start + 6, _EQUAL, _FIRST_TALK)


def patched_tests(start: int) -> bytes:
    var_test = struct.pack("<HHH", _COMPARE_VAR_TO_VALUE, VAR_SCENE_LIGHTHOUSE_JASMINE, 0)
    var_test += _goto_if(start + 6, _EQUAL, _FIRST_TALK)
    flag_start = start + len(var_test)
    flag_test = struct.pack("<HH", _CHECKFLAG, FLAG_GOT_SECRETPOTION) + _goto_if(flag_start + 4, _TRUE, _HAND_OVER)
    return var_test + flag_test


def patch_script(data: bytes) -> bytes:
    start = scrdef_offsets(data)[0] + _TESTS_SHIFT
    expected = vanilla_tests(start)
    if data[start : start + len(expected)] != expected:
        raise LighthousePatchError(f"scr_seq_0066: unexpected bytes for Jasmine's tests at {start:#x}")
    out = bytearray(data)
    out[start : start + len(expected)] = patched_tests(start)
    return bytes(out)


def write_lighthouse_fix(rom: HeartGoldRom) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[LIGHTHOUSE_TOP_FILE] = patch_script(bytes(narc.files[LIGHTHOUSE_TOP_FILE]))
    rom.write_narc(NITROFS_PATH, narc)
