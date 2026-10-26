from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

CHECKFLAG_OPCODE = 32
GOTOIF_OPCODE = 28
SETFLAG_OPCODE = 30
GOTO_OPCODE = 22
NOOP_OPCODE = 0
GOTOIF_TRUE = 1

GROUP_A: dict[str, tuple[int, int, int, int]] = {
    "goldenrod_radio_tower_2f_blue_card": (30, 362, 21, 437),
    "goldenrod_radio_tower_5f_basement_key": (33, 117, 19, 555),
    "goldenrod_tunnel_warehouse_card_key": (97, 49, 19, 91),
    "goldenrod_flower_shop_squirtbottle": (896, 397, 21, 464),
    "route_12_fishing_brother_house_super_rod": (200, 14, 19, 76),
    "celadon_condominiums_3f_gb_sounds": (798, 630, 19, 679),
    "route_36_hm06": (243, 1356, 19, 1394),
}

GROUP_B: dict[str, tuple[int, int, int, int, int]] = {
    "celadon_game_corner_coin_case": (806, 306, 21, 327, 388),
}

GATE_FLAGS: dict[str, int] = {
    "goldenrod_radio_tower_2f_blue_card": 0x52A,
    "goldenrod_radio_tower_5f_basement_key": 0x52B,
    "goldenrod_tunnel_warehouse_card_key": 0x52C,
    "goldenrod_flower_shop_squirtbottle": 0x52D,
    "route_12_fishing_brother_house_super_rod": 0x52E,
    "celadon_condominiums_3f_gb_sounds": 0x52F,
    "celadon_game_corner_coin_case": 0x530,
    "route_36_hm06": 0x539,
}

LEGACY_GATE_FLAGS: dict[str, int] = {
    "goldenrod_radio_tower_2f_blue_card": 0xB48,
    "goldenrod_radio_tower_5f_basement_key": 0xB49,
    "goldenrod_tunnel_warehouse_card_key": 0xB4A,
    "goldenrod_flower_shop_squirtbottle": 0xB4B,
    "route_12_fishing_brother_house_super_rod": 0xB4C,
    "celadon_condominiums_3f_gb_sounds": 0xB4D,
    "celadon_game_corner_coin_case": 0xB4F,
}

FLAG_SET_AT_GIVE = frozenset(
    {
        "route_12_fishing_brother_house_super_rod",
        "celadon_game_corner_coin_case",
        "goldenrod_radio_tower_5f_basement_key",
    }
)

FLAG_UNK_087 = 0x87

GROUP_C: dict[str, tuple[int, int, int, int, int]] = {
    "saffron_copycat_house_2f_pass": (841, 100, 19, 293, FLAG_UNK_087),
    "vermilion_pokemon_fan_club_lost_item": (782, 215, 19, 321, FLAG_UNK_087),
}


class NpcGiftGateDataError(Exception):
    pass


def _goto_word(dest: int, word_field_offset: int) -> int:
    return dest - word_field_offset - 4


def _build_group_a_patch(
    block_offset: int, block_size: int, orig_target: int, flag_id: int, set_flag: bool = True
) -> bytes:
    checkflag = struct.pack("<HH", CHECKFLAG_OPCODE, flag_id)
    goto_word_field_offset = block_offset + 4 + 2 + 1
    gotoif = struct.pack("<HB", GOTOIF_OPCODE, GOTOIF_TRUE) + struct.pack(
        "<i", _goto_word(orig_target, goto_word_field_offset)
    )
    setflag = struct.pack("<HH", SETFLAG_OPCODE, flag_id) if set_flag else b""
    used = len(checkflag) + len(gotoif) + len(setflag)
    remaining = block_size - used
    if remaining < 0 or remaining % 2 != 0:
        raise NpcGiftGateDataError(
            f"Group A patch does not fit block_size {block_size} (used {used}, remaining {remaining})"
        )
    noop_pad = struct.pack("<H", NOOP_OPCODE) * (remaining // 2)
    return checkflag + gotoif + setflag + noop_pad


def _build_group_b_patch(
    block_offset: int, block_size: int, skip_target: int, give_target: int, flag_id: int, set_flag: bool = True
) -> bytes:
    checkflag = struct.pack("<HH", CHECKFLAG_OPCODE, flag_id)
    gotoif_word_field_offset = block_offset + 4 + 2 + 1
    gotoif = struct.pack("<HB", GOTOIF_OPCODE, GOTOIF_TRUE) + struct.pack(
        "<i", _goto_word(skip_target, gotoif_word_field_offset)
    )
    setflag = struct.pack("<HH", SETFLAG_OPCODE, flag_id) if set_flag else b""
    goto_word_field_offset = block_offset + 4 + 7 + len(setflag) + 2
    goto = struct.pack("<H", GOTO_OPCODE) + struct.pack("<i", _goto_word(give_target, goto_word_field_offset))
    patch = checkflag + gotoif + setflag + goto
    if not set_flag:
        patch += struct.pack("<H", NOOP_OPCODE) * ((block_size - len(patch)) // 2)
    if len(patch) != block_size:
        raise NpcGiftGateDataError(f"Group B patch length {len(patch)} != block_size {block_size}")
    return patch


def _build_group_c_patch(block_offset: int, block_size: int, orig_target: int, flag_id: int) -> bytes:
    checkflag = struct.pack("<HH", CHECKFLAG_OPCODE, flag_id)
    goto_word_field_offset = block_offset + 4 + 2 + 1
    gotoif = struct.pack("<HB", GOTOIF_OPCODE, GOTOIF_TRUE) + struct.pack(
        "<i", _goto_word(orig_target, goto_word_field_offset)
    )
    used = len(checkflag) + len(gotoif)
    remaining = block_size - used
    if remaining < 0 or remaining % 2 != 0:
        raise NpcGiftGateDataError(
            f"Group C patch does not fit block_size {block_size} (used {used}, remaining {remaining})"
        )
    return checkflag + gotoif + struct.pack("<H", NOOP_OPCODE) * (remaining // 2)


def read_gate_bytes(rom: HeartGoldRom, narc_index: int, offset: int, size: int) -> bytes:
    narc = rom.read_narc(NITROFS_PATH)
    return bytes(narc.files[narc_index][offset : offset + size])


def write_npc_gift_duplication_gate(rom: HeartGoldRom, location_key: str) -> None:
    if location_key in GROUP_C:
        narc_index, block_offset, block_size, orig_target, flag_id = GROUP_C[location_key]
        patch = _build_group_c_patch(block_offset, block_size, orig_target, flag_id)
        narc = rom.read_narc(NITROFS_PATH)
        blob = bytearray(narc.files[narc_index])
        blob[block_offset : block_offset + block_size] = patch
        narc.files[narc_index] = bytes(blob)
        rom.write_narc(NITROFS_PATH, narc)
        return

    flag_id = GATE_FLAGS.get(location_key)
    if flag_id is None:
        raise KeyError(f"unknown npc_gift duplication-gate location key: {location_key!r}")

    set_flag = location_key not in FLAG_SET_AT_GIVE
    if location_key in GROUP_A:
        narc_index, block_offset, block_size, orig_target = GROUP_A[location_key]
        patch = _build_group_a_patch(block_offset, block_size, orig_target, flag_id, set_flag)
    else:
        narc_index, block_offset, block_size, skip_target, give_target = GROUP_B[location_key]
        patch = _build_group_b_patch(block_offset, block_size, skip_target, give_target, flag_id, set_flag)

    narc = rom.read_narc(NITROFS_PATH)
    blob = bytearray(narc.files[narc_index])
    blob[block_offset : block_offset + block_size] = patch
    narc.files[narc_index] = bytes(blob)
    rom.write_narc(NITROFS_PATH, narc)


def write_all_npc_gift_duplication_gates(rom: HeartGoldRom) -> None:
    for location_key in (*GATE_FLAGS, *GROUP_C):
        write_npc_gift_duplication_gate(rom, location_key)
