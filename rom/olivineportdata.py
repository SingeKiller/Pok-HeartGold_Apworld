from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.deathlinkdata import scrdef_offsets
from rom.eventscriptdata import NITROFS_PATH

OLIVINE_PORT_FILE = 152
FLAG_GAME_CLEAR = 0x964
VAR_TICKET_SHOWN = 0x4002
VAR_PLAYER_FACING = 0x4001

_TESTS_SHIFT = 8
_LEAVE_DOCK = 0x320
_TICKET_ALREADY_SHOWN = 0x356
_SHIP_IN_MAINTENANCE = 0x361

_COMPARE_VAR_TO_VALUE = 17
_GOTO_IF = 28
_CHECKFLAG = 32
_GET_PLAYER_FACING = 386
_FALSE = 0
_EQUAL = 1
_GREATER_OR_EQUAL = 4
_FACING_NORTH = 0


class OlivinePortPatchError(Exception):
    pass


def _goto_if(position: int, condition: int, target: int) -> bytes:
    return struct.pack("<HBi", _GOTO_IF, condition, target - (position + 3) - 4)


def _flag_test(start: int) -> bytes:
    return struct.pack("<HH", _CHECKFLAG, FLAG_GAME_CLEAR) + _goto_if(start + 4, _FALSE, _SHIP_IN_MAINTENANCE)


def _ticket_test(start: int) -> bytes:
    compare = struct.pack("<HHH", _COMPARE_VAR_TO_VALUE, VAR_TICKET_SHOWN, 1)
    return compare + _goto_if(start + 6, _GREATER_OR_EQUAL, _TICKET_ALREADY_SHOWN)


def _facing_test(start: int) -> bytes:
    facing = struct.pack("<HH", _GET_PLAYER_FACING, VAR_PLAYER_FACING)
    compare = struct.pack("<HHH", _COMPARE_VAR_TO_VALUE, VAR_PLAYER_FACING, _FACING_NORTH)
    return facing + compare + _goto_if(start + 10, _EQUAL, _LEAVE_DOCK)


def vanilla_tests(start: int) -> bytes:
    flag = _flag_test(start)
    ticket = _ticket_test(start + len(flag))
    return flag + ticket + _facing_test(start + len(flag) + len(ticket))


def patched_tests(start: int) -> bytes:
    ticket = _ticket_test(start)
    facing = _facing_test(start + len(ticket))
    return ticket + facing + _flag_test(start + len(ticket) + len(facing))


def patch_script(data: bytes) -> bytes:
    start = scrdef_offsets(data)[0] + _TESTS_SHIFT
    expected = vanilla_tests(start)
    if data[start : start + len(expected)] != expected:
        raise OlivinePortPatchError(f"scr_seq_0152: unexpected bytes for the sailor's tests at {start:#x}")
    out = bytearray(data)
    out[start : start + len(expected)] = patched_tests(start)
    return bytes(out)


def write_olivine_port_fix(rom: HeartGoldRom) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[OLIVINE_PORT_FILE] = patch_script(bytes(narc.files[OLIVINE_PORT_FILE]))
    rom.write_narc(NITROFS_PATH, narc)
