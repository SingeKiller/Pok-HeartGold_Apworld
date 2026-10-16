# rom/giftflagdata.py
#
# Gives 7 npc_gift locations a check flag of their own (2026-09-24, player
# report: items found at these spots never reached the server, so neither
# the trackers nor the logic knew about them). Their scripts set nothing
# the client could read once the item is handed over: no flag, or a flag
# the game also sets elsewhere (FLAG_HIDE_ROUTE_29_FRIEND is set at new
# game, scr_seq_0149.s:13).
#
# Every gift here loads its item with `SetVar VAR_SPECIAL_x8004, item`
# (6 bytes, rom/npcgiftdata.py's TABLE points at its item operand). That
# instruction is replaced in place by `Call sub` (also 6 bytes) to a short
# routine appended at the end of the same script file:
#
#   SetVar VAR_SPECIAL_x8004, item    (the same item, substituted or not)
#   SetFlag <flag>
#   Return
#
# so the script goes on exactly as before, with the flag set. Nothing
# before the appended routine moves, so no other offset or jump target
# changes. Must run after the item substitution, which writes the item
# operand this copies. Offsets verified on both the HeartGold and
# SoulSilver US ROMs.

from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH
from rom.npcgiftdata import TABLE

SETVAR_OPCODE = 41
CALL_OPCODE = 26
SETFLAG_OPCODE = 30
RETURN_OPCODE = 27
VAR_SPECIAL_X8004 = 0x8004

# location key -> check flag (unused FLAG_UNK_ band 0x51F-0x54F, see
# rom/badgedata.py). Both of the Elm's lab Potion sites share one.
GIFT_FLAGS: dict[str, int] = {
    "new_bark_elms_lab_1f_potion": 0x534,
    "pallet_town_oaks_lab_jade_orb": 0x535,
    "route_29_poke_ball": 0x536,
    "route_30_mr_pokemon_house_mystery_egg": 0x537,
    "route_31_violet_gatehouse_vs_recorder": 0x538,
    "route_42_hm04": 0x53A,
    "ss_aqua_1f_northwest_rooms_metal_coat": 0x53B,
}


class GiftFlagError(Exception):
    """A gift site does not hold the expected `SetVar VAR_SPECIAL_x8004`."""


def patch_script(data: bytes, item_operand_offsets: list[int], flag: int) -> bytes:
    """`data` with each site's item SetVar turned into a Call to one
    appended routine per site."""
    out = bytearray(data)
    for operand in item_operand_offsets:
        start = operand - 4
        if struct.unpack_from("<HH", out, start) != (SETVAR_OPCODE, VAR_SPECIAL_X8004):
            raise GiftFlagError(f"no `SetVar VAR_SPECIAL_x8004` at offset {start}")
        item = struct.unpack_from("<H", out, operand)[0]
        if len(out) % 2:
            out.append(0)
        routine = len(out)
        out += struct.pack("<HHH", SETVAR_OPCODE, VAR_SPECIAL_X8004, item)
        out += struct.pack("<HH", SETFLAG_OPCODE, flag)
        out += struct.pack("<H", RETURN_OPCODE)
        # `.word \dest-.-4`, the word itself sitting right after the opcode.
        struct.pack_into("<Hi", out, start, CALL_OPCODE, routine - (start + 2) - 4)
    return bytes(out)


def write_gift_flags(rom: HeartGoldRom) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    by_file: dict[int, list[tuple[list[int], int]]] = {}
    for key, flag in GIFT_FLAGS.items():
        for index, operand in TABLE[key]:
            by_file.setdefault(index, []).append(([operand], flag))
    for index, sites in by_file.items():
        data = bytes(narc.files[index])
        for operands, flag in sites:
            data = patch_script(data, operands, flag)
        narc.files[index] = data
    rom.write_narc(NITROFS_PATH, narc)
