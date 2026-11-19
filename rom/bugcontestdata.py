from __future__ import annotations

import struct

from rom import HeartGoldRom, msgdata
from rom.eventscriptdata import NITROFS_PATH
from rom.prizedata import encode_codes

BUG_CONTEST_FLAG = 0x54E

CONTEST_SCRIPT_FILE = 151
GATE_SCRIPT_FILES = (242, 245)
MESSAGE_BANK = 246
TUESDAY_MESSAGE = 4

GET_WEEKDAY = 484
_COMPARE = 17
_CALL = 26
_RETURN = 27
_GOTO_IF = 28
_SET_FLAG = 30
_CLEAR_FLAG = 31
_SET_VAR = 41
_NOP = 0
_EQUAL = 1
_PAGE_WAIT = 0x25BC

VAR_TEMP_4000 = 0x4000
VAR_CONTEST_STATE = 0x4118
FLAG_DAILY_DID_CONTEST = 0xAA7
FLAG_CONTEST_ACTIVE = 0x993
CONTEST_DAYS = (2, 4, 6)
TUESDAY = 2

REGISTRATION_WEEKDAY = struct.pack("<HHHHH", GET_WEEKDAY, VAR_TEMP_4000, _COMPARE, VAR_TEMP_4000, TUESDAY)
GATE_WEEKDAY = struct.pack("<HHHHH", GET_WEEKDAY, VAR_TEMP_4000, _COMPARE, VAR_CONTEST_STATE, 1)
JUDGING_END = struct.pack("<HHHH", _SET_FLAG, FLAG_DAILY_DID_CONTEST, _CLEAR_FLAG, FLAG_CONTEST_ACTIVE)

DAILY_TEXT = "The Bug-Catching Contest is on\ntoday, as it is every day."


class BugContestPatchError(Exception):
    pass


def _find_once(data: bytes, pattern: bytes, what: str) -> int:
    count = data.count(pattern)
    if count != 1:
        raise BugContestPatchError(f"expected exactly one {what}, found {count}")
    return data.find(pattern)


def _append(out: bytearray, blob: bytes) -> int:
    if len(out) % 2:
        out.append(0)
    position = len(out)
    out += blob
    return position


def _call(out: bytearray, site: int, routine: int, length: int) -> None:
    out[site : site + length] = struct.pack("<Hi", _CALL, routine - (site + 2) - 4) + struct.pack("<H", _NOP) * (
        (length - 6) // 2
    )


def _weekday_routine() -> bytes:
    blob = struct.pack("<HH", GET_WEEKDAY, VAR_TEMP_4000)
    end = 4 + len(CONTEST_DAYS) * 13 + 6
    for day in CONTEST_DAYS:
        blob += struct.pack("<HHH", _COMPARE, VAR_TEMP_4000, day)
        blob += struct.pack("<HBi", _GOTO_IF, _EQUAL, end - (len(blob) + 7))
    blob += struct.pack("<HHH", _SET_VAR, VAR_TEMP_4000, TUESDAY)
    if len(blob) != end:
        raise BugContestPatchError("weekday routine has the wrong size")
    blob += struct.pack("<HHH", _COMPARE, VAR_TEMP_4000, TUESDAY)
    blob += struct.pack("<H", _RETURN)
    return blob


def patch_contest_script(data: bytes) -> bytes:
    weekday = _find_once(data, REGISTRATION_WEEKDAY, "weekday test of the contest entry")
    ending = _find_once(data, JUDGING_END, "end of the contest judging")
    out = bytearray(data)
    routine = _append(out, _weekday_routine())
    _call(out, weekday, routine, len(REGISTRATION_WEEKDAY))
    routine = _append(
        out,
        struct.pack("<HH", _SET_FLAG, FLAG_DAILY_DID_CONTEST)
        + struct.pack("<HH", _SET_FLAG, BUG_CONTEST_FLAG)
        + struct.pack("<HH", _CLEAR_FLAG, FLAG_CONTEST_ACTIVE)
        + struct.pack("<H", _RETURN),
    )
    _call(out, ending, routine, len(JUDGING_END))
    return bytes(out)


def patch_gate_script(data: bytes) -> bytes:
    site = _find_once(data, GATE_WEEKDAY, "weekday test of the gate guard")
    out = bytearray(data)
    routine = _append(
        out,
        struct.pack("<HHH", _SET_VAR, VAR_TEMP_4000, TUESDAY)
        + struct.pack("<HHH", _COMPARE, VAR_CONTEST_STATE, 1)
        + struct.pack("<H", _RETURN),
    )
    _call(out, site, routine, len(GATE_WEEKDAY))
    return bytes(out)


def daily_message_codes(original: list[int]) -> list[int]:
    if original.count(_PAGE_WAIT) < 2:
        raise BugContestPatchError("the contest entry message has an unexpected layout")
    second = [i for i, code in enumerate(original) if code == _PAGE_WAIT][1]
    return encode_codes(DAILY_TEXT) + [_PAGE_WAIT] + original[second + 1 :]


def apply_bug_contest(rom: HeartGoldRom) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[CONTEST_SCRIPT_FILE] = patch_contest_script(bytes(narc.files[CONTEST_SCRIPT_FILE]))
    for index in GATE_SCRIPT_FILES:
        narc.files[index] = patch_gate_script(bytes(narc.files[index]))
    rom.write_narc(NITROFS_PATH, narc)
    original = msgdata.read_message_codes(rom, MESSAGE_BANK, TUESDAY_MESSAGE)
    msgdata.replace_message_codes(rom, MESSAGE_BANK, {TUESDAY_MESSAGE: daily_message_codes(original)})
