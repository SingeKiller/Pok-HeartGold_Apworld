from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH
from rom.npcgiftdata import TABLE
from rom.npcgiftgatedata import FLAG_SET_AT_GIVE, GATE_FLAGS

SETVAR_OPCODE = 41
CALL_OPCODE = 26
SETFLAG_OPCODE = 30
RETURN_OPCODE = 27
VAR_SPECIAL_X8004 = 0x8004

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
    pass


def patch_script(data: bytes, item_operand_offsets: list[int], flag: int) -> bytes:
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
        struct.pack_into("<Hi", out, start, CALL_OPCODE, routine - (start + 2) - 4)
    return bytes(out)


def write_gift_flags(rom: HeartGoldRom) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    by_file: dict[int, list[tuple[list[int], int]]] = {}
    at_give = {key: GATE_FLAGS[key] for key in FLAG_SET_AT_GIVE}
    for key, flag in {**GIFT_FLAGS, **at_give}.items():
        for index, operand in TABLE[key]:
            by_file.setdefault(index, []).append(([operand], flag))
    for index, sites in by_file.items():
        data = bytes(narc.files[index])
        for operands, flag in sites:
            data = patch_script(data, operands, flag)
        narc.files[index] = data
    rom.write_narc(NITROFS_PATH, narc)
