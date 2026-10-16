# rom/deathlinkdata.py
#
# DeathLink through the game's own whiteout (2026-10-16, player report: "I
# enabled DeathLink but it doesn't work"). A death in this game is the
# whiteout, "<player> is out of usable Pokemon! ... whited out!", back to
# the last Pokemon Center. Zeroing the party's HP is not one: outside a
# battle the field code assumes a living party
# (GetFirstAliveMonInParty_CrashIfNone in the follower, Repel and fishing
# code, src/script_pokemon_util.c:109), and the party HP sits in the
# PID-encrypted part of each Pokemon anyway.
#
# Three edits to scr_seq_0003, the std_* scripts (std id 2000 + n is its
# ScrDef n, include/constants/std_script.h), all byte-identical on the
# HeartGold and SoulSilver US ROMs:
#
#   - Receive: std_repel_wore_off (n = 22) runs on the step where the Repel
#     counter reaches 0 (PlayerStepEvent_RepelCounterDecrement,
#     asm/overlay_02_02248728.s:6963). Its first two instructions become a
#     Call to an appended routine that, when FLAG_AP_DEATHLINK is set,
#     clears it, sets FLAG_AP_DEATHLINK_WHITEOUT and jumps to the overworld
#     whiteout the poison script ends with (`_05F5` in scr_seq_0003_003:
#     the "out of usable Pokemon" message, ScrCmd_436, OverworldWhiteOut). The client sets the flag and
#     the Repel counter to 1, so the death lands on the player's next step,
#     the same way a poison whiteout would.
#   - Send: std_whited_out_to_mom (n = 12) and std_whited_out_to_pokecenter
#     (n = 13) are queued by every whiteout and by nothing else
#     (src/blackout.c:230-232). Each sets FLAG_AP_WHITED_OUT, which the
#     client reads and clears; it sends a death to everyone else unless
#     FLAG_AP_DEATHLINK_WHITEOUT says this whiteout was a received one. Both
#     live in the save, so a reload never confuses the two.
#
# Every replaced instruction is checked against its vanilla bytes and moved
# into the appended routine, so the scripts go on exactly as before.

from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

STD_SCRIPTS_FILE = 3

# Unused FLAG_UNK_ band 0x51F-0x54F (no vanilla script or code reads them,
# include/constants/flags.h), see rom/badgedata.py.
FLAG_AP_DEATHLINK = 0x540  # set by the client: a received death is waiting
FLAG_AP_WHITED_OUT = 0x541  # set by every whiteout, cleared by the client
FLAG_AP_DEATHLINK_WHITEOUT = 0x542  # set when the whiteout is a received death

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
_SCRCMD_609 = 609  # settles the following Pokemon before the whiteout

# Vanilla bytes at each site, the length of the instructions moved out.
_REPEL_START = bytes.fromhex("4900dc056000")  # PlaySE SEQ_SE_DP_SELECT; LockAll
_MOM_FANFARE = bytes.fromhex("4e009f044f00")  # PlayFanfare SEQ_ME_ASA; WaitFanfare
_POKECENTER_COMPARE = bytes.fromhex("11000c800300")  # CompareVarToValue VAR_SPECIAL_RESULT, 3
_POKECENTER_COMPARE_SHIFT = 20  # after ScrCmd_609, LockAll, FadeScreen, WaitFade, GetPlayerState
_POISON_WHITEOUT_START = bytes.fromhex("be0000")  # BufferPlayersName 0


class DeathLinkPatchError(Exception):
    """A script does not hold the expected vanilla instructions."""


def scrdef_offsets(data: bytes) -> list[int]:
    """Absolute offset of each script in a scr_seq file (`ScrDef` header:
    `.word label - . - 4` per script, then SCRDEF_END)."""
    offsets, position = [], 0
    while struct.unpack_from("<H", data, position)[0] != 0xFD13:
        offsets.append(position + 4 + struct.unpack_from("<i", data, position)[0])
        position += 4
    return offsets


def _expect(data: bytes, offset: int, expected: bytes, what: str) -> None:
    if data[offset : offset + len(expected)] != expected:
        raise DeathLinkPatchError(f"scr_seq_0003: unexpected bytes for {what} at {offset:#x}")


def _jump(opcode: int, source: int, target: int) -> bytes:
    """GoTo/Call at `source`: `.word dest - . - 4`, the word right after
    the 2-byte opcode."""
    return struct.pack("<Hi", opcode, target - (source + 2) - 4)


def _call_out(out: bytearray, site: int, moved: bytes, routine: bytes) -> None:
    """Replace the 6 bytes at `site` with a Call to `moved` + `routine` +
    Return, appended at the end of the file."""
    start = len(out)
    out += moved + routine + struct.pack("<H", _RETURN)
    out[site : site + 6] = _jump(_CALL, site, start)


def patch_std_scripts(data: bytes) -> bytes:
    """scr_seq_0003 with the three DeathLink edits (see module header)."""
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

    # Repel: PlaySE; LockAll; CheckFlag; GoToIf TRUE, death; Return, then
    # death: ClearFlag; SetFlag; ScrCmd_609; GoTo the poison whiteout.
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
