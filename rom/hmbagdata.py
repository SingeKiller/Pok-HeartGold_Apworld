from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

FIELD_SCRIPT_FILE = 146
FIELD_SCRIPT_LENGTH = 3380
TERRAIN_OVERLAY = 1

MOVE_CUT = 15
MOVE_SURF = 57
MOVE_STRENGTH = 70
MOVE_WATERFALL = 127
MOVE_ROCK_SMASH = 249
MOVE_WHIRLPOOL = 250
MOVE_ROCK_CLIMB = 431

HM_CUT = 420
HM_SURF = 422
HM_STRENGTH = 423
HM_WHIRLPOOL = 424
HM_ROCK_SMASH = 425
HM_WATERFALL = 426
HM_ROCK_CLIMB = 427

HM_FOR_MOVE = {
    MOVE_CUT: HM_CUT,
    MOVE_ROCK_SMASH: HM_ROCK_SMASH,
    MOVE_STRENGTH: HM_STRENGTH,
    MOVE_ROCK_CLIMB: HM_ROCK_CLIMB,
    MOVE_SURF: HM_SURF,
    MOVE_WATERFALL: HM_WATERFALL,
    MOVE_WHIRLPOOL: HM_WHIRLPOOL,
}

PARTY_SLOT_SITES = (
    (0x56, MOVE_CUT),
    (0xAD, MOVE_CUT),
    (0x289, MOVE_ROCK_SMASH),
    (0x51C, MOVE_STRENGTH),
    (0x576, MOVE_STRENGTH),
    (0x73E, MOVE_ROCK_CLIMB),
    (0x7B5, MOVE_ROCK_CLIMB),
    (0x833, MOVE_SURF),
    (0x94F, MOVE_WATERFALL),
    (0x9A6, MOVE_WATERFALL),
    (0x9EC, MOVE_WHIRLPOOL),
    (0xA43, MOVE_WHIRLPOOL),
)

SURF_ENTRY = 0x7ED
SURF_ENTRY_VANILLA = bytes.fromhex("4900dc056000")
SURF_BODY = 0x7F3
SURF_BODY_FIRST_COMMAND = bytes.fromhex("2b01")

SURF_SCAN_SITE = 0x021E7544
SURF_SCAN_CONTEXT = (bytes.fromhex("3921"), bytes.fromhex("6cf6d0fe"), bytes.fromhex("ff2801d0"))
WATERFALL_SCAN_SITE = 0x021E6BBE
WATERFALL_SCAN_CONTEXT = (bytes.fromhex("7f21"), bytes.fromhex("6df693fb"), bytes.fromhex("ff2801d0"))
_FALSE_THEN_NOP = bytes.fromhex("0020c046")

_END = 2
_COMPARE = 17
_GOTO = 22
_CALL = 26
_RETURN = 27
_GOTO_IF = 28
_SET_VAR = 41
_PLAY_SE = 73
_LOCK_ALL = 96
_HAS_ITEM = 128
_GET_PARTY_SLOT_WITH_MOVE = 141
_GET_PARTY_LEAD_ALIVE = 529
_NOP = 0
_EQUAL = 1
_NOT_EQUAL = 5
_VAR_RESULT = 0x800C
_NO_SLOT = 6
_SURF_SOUND = 0x05DC

COMMAND_SIZES = {
    _END: 2,
    _COMPARE: 6,
    _GOTO: 6,
    _CALL: 6,
    _RETURN: 2,
    _GOTO_IF: 7,
    _SET_VAR: 6,
    _PLAY_SE: 4,
    _LOCK_ALL: 2,
    _HAS_ITEM: 8,
    _GET_PARTY_SLOT_WITH_MOVE: 6,
    _GET_PARTY_LEAD_ALIVE: 4,
}


class HmBagPatchError(Exception):
    pass


def _slot_with_move(move: int) -> bytes:
    return struct.pack("<HHH", _GET_PARTY_SLOT_WITH_MOVE, _VAR_RESULT, move)


def _compare_result(value: int) -> bytes:
    return struct.pack("<HHH", _COMPARE, _VAR_RESULT, value)


def _has_item(item: int) -> bytes:
    return struct.pack("<HHHH", _HAS_ITEM, item, 1, _VAR_RESULT)


def _append(out: bytearray, blob: bytes) -> int:
    if len(out) % 2:
        out.append(0)
    position = len(out)
    out += blob
    return position


def _call(out: bytearray, site: int, routine: int) -> None:
    out[site : site + 6] = struct.pack("<Hi", _CALL, routine - (site + 2) - 4)


def hm_routine(move: int, item: int) -> bytes:
    blob = _slot_with_move(move) + _compare_result(_NO_SLOT)
    found_at = len(blob)
    blob += bytes(7)
    blob += _has_item(item) + _compare_result(0)
    none_at = len(blob)
    blob += bytes(7)
    blob += struct.pack("<HH", _GET_PARTY_LEAD_ALIVE, _VAR_RESULT) + struct.pack("<H", _RETURN)
    none = len(blob)
    blob += struct.pack("<HHH", _SET_VAR, _VAR_RESULT, _NO_SLOT)
    done = len(blob)
    blob += struct.pack("<H", _RETURN)
    blob = bytearray(blob)
    blob[found_at : found_at + 7] = struct.pack("<HBi", _GOTO_IF, _NOT_EQUAL, done - (found_at + 7))
    blob[none_at : none_at + 7] = struct.pack("<HBi", _GOTO_IF, _EQUAL, none - (none_at + 7))
    return bytes(blob)


def surf_guard(start: int, body: int) -> bytes:
    blob = _slot_with_move(MOVE_SURF) + _compare_result(_NO_SLOT)
    first_at = len(blob)
    blob += bytes(7)
    blob += _has_item(HM_SURF) + _compare_result(0)
    second_at = len(blob)
    blob += bytes(7)
    blob += struct.pack("<H", _END)
    entry = len(blob)
    blob += struct.pack("<HH", _PLAY_SE, _SURF_SOUND) + struct.pack("<H", _LOCK_ALL)
    return_at = len(blob)
    blob += bytes(6)
    blob = bytearray(blob)
    blob[first_at : first_at + 7] = struct.pack("<HBi", _GOTO_IF, _NOT_EQUAL, entry - (first_at + 7))
    blob[second_at : second_at + 7] = struct.pack("<HBi", _GOTO_IF, _NOT_EQUAL, entry - (second_at + 7))
    blob[return_at : return_at + 6] = struct.pack("<Hi", _GOTO, body - (start + return_at + 6))
    return bytes(blob)


def patch_script(data: bytes) -> bytes:
    if len(data) != FIELD_SCRIPT_LENGTH:
        raise HmBagPatchError(f"field move script file is {len(data)} bytes, expected {FIELD_SCRIPT_LENGTH}")
    for site, move in PARTY_SLOT_SITES:
        if data[site : site + 6] != _slot_with_move(move):
            raise HmBagPatchError(f"field move script: unexpected bytes for the move {move} search at {site:#x}")
    if data[SURF_ENTRY : SURF_ENTRY + 6] != SURF_ENTRY_VANILLA:
        raise HmBagPatchError(f"field move script: unexpected bytes at the Surf entry {SURF_ENTRY:#x}")
    if data[SURF_BODY : SURF_BODY + 2] != SURF_BODY_FIRST_COMMAND:
        raise HmBagPatchError(f"field move script: unexpected bytes at the Surf body {SURF_BODY:#x}")
    out = bytearray(data)
    routines = {}
    for move, item in sorted(HM_FOR_MOVE.items()):
        routines[move] = _append(out, hm_routine(move, item))
    for site, move in PARTY_SLOT_SITES:
        _call(out, site, routines[move])
    if len(out) % 2:
        out.append(0)
    guard = len(out)
    out += surf_guard(guard, SURF_BODY)
    out[SURF_ENTRY : SURF_ENTRY + 6] = struct.pack("<Hi", _GOTO, guard - (SURF_ENTRY + 2) - 4)
    return bytes(out)


def _check_scan(code: bytes, base: int, address: int, context: tuple[bytes, bytes, bytes], what: str) -> int:
    before, call, after = context
    offset = address - base
    if (
        code[offset - len(before) : offset] != before
        or code[offset : offset + len(call)] != call
        or code[offset + len(call) : offset + len(call) + len(after)] != after
    ):
        raise HmBagPatchError(f"terrain overlay: unexpected bytes for the {what} at {address:#010x}")
    return offset


def patch_terrain_overlay(code: bytes, base: int) -> bytes:
    out = bytearray(code)
    for address, context, what in (
        (SURF_SCAN_SITE, SURF_SCAN_CONTEXT, "Surf party search"),
        (WATERFALL_SCAN_SITE, WATERFALL_SCAN_CONTEXT, "waterfall descent check"),
    ):
        offset = _check_scan(code, base, address, context, what)
        out[offset : offset + 4] = _FALSE_THEN_NOP
    return bytes(out)


def write_hms_without_teaching(rom: HeartGoldRom) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[FIELD_SCRIPT_FILE] = patch_script(bytes(narc.files[FIELD_SCRIPT_FILE]))
    base = rom.overlay_ram_address(TERRAIN_OVERLAY)
    patched = patch_terrain_overlay(rom.read_overlay(TERRAIN_OVERLAY), base)
    rom.write_narc(NITROFS_PATH, narc)
    rom.write_overlay(TERRAIN_OVERLAY, patched)
