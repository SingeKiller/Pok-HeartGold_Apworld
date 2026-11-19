from __future__ import annotations

import struct

from rom import HeartGoldRom

BATTLE_SCRIPTS_NARC = "a/0/0/1"
BATTLE_WIN_SUBSCRIPT = 4
WILD_BATTLE_MONEY = 20
WILD_TEST_WORD = 16
WILD_JUMP_WORD = 20
PAY_DAY_PICKUP_WORD = 148
SCRIPT_SIZE_LIMIT = 1600

_COMPARE_VAR_TO_VALUE = 32
_UPDATE_VAR = 50
_GOTO = 59
_OPCODE_FLAG_NOT = 5
_OPCODE_ADD = 8
_VAR_BATTLE_TYPE = 0
_VAR_PAY_DAY_COUNT = 23
_BATTLE_TYPE_TRAINER = 1


class WildMoneyPatchError(Exception):
    pass


def money_block(start: int) -> list[int]:
    block = [_UPDATE_VAR, _OPCODE_ADD, _VAR_PAY_DAY_COUNT, WILD_BATTLE_MONEY, _GOTO]
    return [*block, (PAY_DAY_PICKUP_WORD - (start + len(block)) - 1) & 0xFFFFFFFF]


def patch_script(data: bytes) -> bytes:
    words = list(struct.unpack(f"<{len(data) // 4}I", data))
    test = (
        _COMPARE_VAR_TO_VALUE, _OPCODE_FLAG_NOT, _VAR_BATTLE_TYPE, _BATTLE_TYPE_TRAINER,
        PAY_DAY_PICKUP_WORD - WILD_JUMP_WORD - 1,
    )
    if tuple(words[WILD_TEST_WORD : WILD_JUMP_WORD + 1]) != test:
        raise WildMoneyPatchError("battle win script: unexpected words for the wild battle test")
    start = len(words)
    words[WILD_JUMP_WORD] = start - WILD_JUMP_WORD - 1
    words += money_block(start)
    patched = struct.pack(f"<{len(words)}I", *words)
    if len(patched) >= SCRIPT_SIZE_LIMIT:
        raise WildMoneyPatchError("battle win script: too long for the battle script buffer")
    return patched


def write_wild_battle_money(rom: HeartGoldRom) -> None:
    narc = rom.read_narc(BATTLE_SCRIPTS_NARC)
    narc.files[BATTLE_WIN_SUBSCRIPT] = patch_script(bytes(narc.files[BATTLE_WIN_SUBSCRIPT]))
    rom.write_narc(BATTLE_SCRIPTS_NARC, narc)
