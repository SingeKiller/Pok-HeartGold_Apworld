from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

STD_SCRIPTS_FILE = 3

FLAG_AP_DEATHLINK = 0x540
FLAG_AP_WHITED_OUT = 0x541
FLAG_AP_DEATHLINK_WHITEOUT = 0x542

SCRDEF_WHITED_OUT_TO_MOM = 12
SCRDEF_WHITED_OUT_TO_POKECENTER = 13
SCRDEF_REPEL_WORE_OFF = 22
POISON_WHITEOUT_OFFSET = 0x5F5

_GOTO = 22
_GOTO_IF = 28
_CALL = 26
_RETURN = 27
_SETFLAG = 30
_CLEARFLAG = 31
_CHECKFLAG = 32
_TRUE = 1
_SCRCMD_609 = 609

_REPEL_START = bytes.fromhex("4900dc056000")
_MOM_FANFARE = bytes.fromhex("4e009f044f00")
_POKECENTER_COMPARE = bytes.fromhex("11000c800300")
_POKECENTER_COMPARE_SHIFT = 20
_POISON_WHITEOUT_START = bytes.fromhex("be0000")


class DeathLinkPatchError(Exception):
    pass


def scrdef_offsets(data: bytes) -> list[int]:
    offsets, position = [], 0
    while struct.unpack_from("<H", data, position)[0] != 0xFD13:
        offsets.append(position + 4 + struct.unpack_from("<i", data, position)[0])
        position += 4
    return offsets


def _expect(data: bytes, offset: int, expected: bytes, what: str) -> None:
    if data[offset : offset + len(expected)] != expected:
        raise DeathLinkPatchError(f"scr_seq_0003: unexpected bytes for {what} at {offset:#x}")


def _jump(opcode: int, source: int, target: int) -> bytes:
    return struct.pack("<Hi", opcode, target - (source + 2) - 4)


def _call_out(out: bytearray, site: int, moved: bytes, routine: bytes) -> None:
    start = len(out)
    out += moved + routine + struct.pack("<H", _RETURN)
    out[site : site + 6] = _jump(_CALL, site, start)


def patch_std_scripts(data: bytes) -> bytes:
    out = bytearray(data)
    scripts = scrdef_offsets(data)
    repel = scripts[SCRDEF_REPEL_WORE_OFF]
    mom = scripts[SCRDEF_WHITED_OUT_TO_MOM]
    pokecenter = scripts[SCRDEF_WHITED_OUT_TO_POKECENTER] + _POKECENTER_COMPARE_SHIFT
    _expect(data, repel, _REPEL_START, "std_repel_wore_off")
    _expect(data, pokecenter, _POKECENTER_COMPARE, "std_whited_out_to_pokecenter")
    _expect(data, POISON_WHITEOUT_OFFSET, _POISON_WHITEOUT_START, "the poison whiteout")
    fanfare = data.find(_MOM_FANFARE, mom, scripts[SCRDEF_WHITED_OUT_TO_POKECENTER])
    if fanfare < 0:
        raise DeathLinkPatchError("scr_seq_0003: no fanfare in std_whited_out_to_mom")

    set_whited_out = struct.pack("<HH", _SETFLAG, FLAG_AP_WHITED_OUT)
    _call_out(out, fanfare, _MOM_FANFARE, set_whited_out)
    _call_out(out, pokecenter, set_whited_out, _POKECENTER_COMPARE)

    start = len(out)
    out += _REPEL_START + struct.pack("<HH", _CHECKFLAG, FLAG_AP_DEATHLINK)
    goto_if = len(out)
    out += struct.pack("<HBi", _GOTO_IF, _TRUE, 0)
    out += struct.pack("<H", _RETURN)
    death = len(out)
    struct.pack_into("<i", out, goto_if + 3, death - (goto_if + 3) - 4)
    out += struct.pack("<HHHHH", _CLEARFLAG, FLAG_AP_DEATHLINK, _SETFLAG, FLAG_AP_DEATHLINK_WHITEOUT, _SCRCMD_609)
    out += _jump(_GOTO, len(out), POISON_WHITEOUT_OFFSET)
    out[repel : repel + 6] = _jump(_CALL, repel, start)
    return bytes(out)


def write_deathlink_scripts(rom: HeartGoldRom) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[STD_SCRIPTS_FILE] = patch_std_scripts(bytes(narc.files[STD_SCRIPTS_FILE]))
    rom.write_narc(NITROFS_PATH, narc)
