from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

GET_WEEKDAY = 484
GET_TIME_OF_DAY = 379
GET_HOUR = 522
_COMPARE_VAR_TO_VALUE = 17
_SET_VAR = 41
_CALL = 26
_RETURN = 27
_NOP = 0

VAR_TEMP_4000 = 0x4000
VAR_TEMP_4001 = 0x4001
VAR_TEMP_4002 = 0x4002
VAR_SPECIAL_RESULT = 0x800C

SUNDAY, MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY = range(7)
NIGHT = 3

SITES: tuple[tuple[int, str, int, int, int, int, int], ...] = (
    (962, "Monica shown (Route 40)", GET_WEEKDAY, VAR_TEMP_4000, MONDAY, 0, MONDAY),
    (962, "Monica's Sharp Beak", GET_WEEKDAY, VAR_SPECIAL_RESULT, MONDAY, 0, MONDAY),
    (225, "Tuscany shown (Route 29)", GET_WEEKDAY, VAR_TEMP_4000, TUESDAY, 0, TUESDAY),
    (225, "Tuscany's TwistedSpoon", GET_WEEKDAY, VAR_SPECIAL_RESULT, TUESDAY, 0, TUESDAY),
    (938, "Wesley's Black Belt (Lake of Rage)", GET_WEEKDAY, VAR_SPECIAL_RESULT, WEDNESDAY, 0, WEDNESDAY),
    (243, "Arthur shown (Route 36)", GET_WEEKDAY, VAR_TEMP_4000, THURSDAY, 0, THURSDAY),
    (243, "Arthur's Hard Stone", GET_WEEKDAY, VAR_SPECIAL_RESULT, THURSDAY, 0, THURSDAY),
    (232, "Frieda shown (Route 32)", GET_WEEKDAY, VAR_TEMP_4000, FRIDAY, 0, FRIDAY),
    (232, "Frieda's Poison Barb", GET_WEEKDAY, VAR_SPECIAL_RESULT, FRIDAY, 0, FRIDAY),
    (941, "Santos shown (Blackthorn)", GET_WEEKDAY, VAR_TEMP_4000, SATURDAY, 0, SATURDAY),
    (941, "Santos's Soft Sand", GET_WEEKDAY, VAR_SPECIAL_RESULT, SATURDAY, 0, SATURDAY),
    (246, "Sunny shown (Route 37)", GET_WEEKDAY, VAR_TEMP_4000, SUNDAY, 0, SUNDAY),
    (246, "Sunny's Magnet", GET_WEEKDAY, VAR_SPECIAL_RESULT, SUNDAY, 0, SUNDAY),
    (800, "Celadon roof Spell Tag (night)", GET_TIME_OF_DAY, VAR_TEMP_4000, NIGHT, 0, NIGHT),
    (15, "Blaine in his gym on Tuesdays", GET_WEEKDAY, VAR_TEMP_4002, TUESDAY, 0, SUNDAY),
    (829, "Sabrina in her gym on Fridays", GET_WEEKDAY, VAR_TEMP_4000, FRIDAY, 0, SUNDAY),
    (829, "Sabrina in her gym on Mondays (phone registered)", GET_WEEKDAY, VAR_TEMP_4000, MONDAY, 0, SUNDAY),
    (58, "Union Cave Lapras (Fridays)", GET_WEEKDAY, VAR_TEMP_4000, FRIDAY, 0, FRIDAY),
    (859, "Falkner in his gym on Mondays", GET_WEEKDAY, VAR_TEMP_4001, MONDAY, 0, SUNDAY),
    (752, "Brock in his gym at 12:00-14:59", GET_HOUR, VAR_TEMP_4000, 12, 0, 0),
    (786, "Erika in her gym on weekends", GET_WEEKDAY, VAR_TEMP_4000, SATURDAY, 0, WEDNESDAY),
    (809, "Janine in her gym at 16:00-17:59", GET_HOUR, VAR_TEMP_4000, 16, 0, 0),
    (760, "Misty in her gym at 16:00-17:59", GET_HOUR, VAR_TEMP_4000, 16, 0, 0),
)


class TimedEventPatchError(Exception):
    pass


def _site_bytes(command: int, var: int, value: int) -> bytes:
    return struct.pack("<HH", command, var) + struct.pack("<HHH", _COMPARE_VAR_TO_VALUE, var, value)


def find_site(data: bytes, command: int, var: int, value: int, nth: int) -> int:
    pattern = _site_bytes(command, var, value)
    position = -1
    for _ in range(nth + 1):
        position = data.find(pattern, position + 1)
        if position < 0:
            raise TimedEventPatchError(f"no test #{nth} of var {var:#x} against {value}")
    return position


def patch_site(data: bytes, command: int, var: int, value: int, nth: int, forced: int) -> bytes:
    site = find_site(data, command, var, value, nth)
    out = bytearray(data)
    if len(out) % 2:
        out.append(0)
    routine = len(out)
    out += struct.pack("<HHH", _SET_VAR, var, forced)
    out += struct.pack("<HHH", _COMPARE_VAR_TO_VALUE, var, value)
    out += struct.pack("<H", _RETURN)
    out[site : site + 10] = struct.pack("<Hi", _CALL, routine - (site + 2) - 4) + struct.pack("<HH", _NOP, _NOP)
    return bytes(out)


def write_timed_events(rom: HeartGoldRom) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    for index, _what, command, var, value, nth, forced in SITES:
        narc.files[index] = patch_site(bytes(narc.files[index]), command, var, value, nth, forced)
    rom.write_narc(NITROFS_PATH, narc)
