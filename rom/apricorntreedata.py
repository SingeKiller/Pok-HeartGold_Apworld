from __future__ import annotations

import struct
from collections.abc import Iterable

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

SCRIPT_INDEX = 150
FLAG_BASE = 0x83C

TREE_POSITIONS: tuple[tuple[int, int], ...] = (
    (1027, 302), (1052, 157), (1397, 232), (1378, 305), (920, 342), (596, 392), (553, 355), (562, 293),
    (538, 271), (471, 474), (472, 474), (358, 293), (382, 233), (401, 202), (406, 202), (404, 204),
    (315, 172), (269, 163), (464, 184), (465, 184), (466, 184), (513, 125), (557, 171), (666, 332),
    (617, 331), (616, 332), (1072, 77), (1074, 77), (1206, 421), (472, 275), (396, 453),
)

TREE_COUNT = len(TREE_POSITIONS)

APRICORN_TREE_FLAGS: dict[int, int] = {index: FLAG_BASE + index for index in range(TREE_COUNT)}

STD_SCRIPT_ID = 2800
OBJECT_ENTRY_SIZE = 32

VANILLA_SCRIPT = bytes.fromhex(
    "0200000013fd4900dc05600068002d000035008000d40101000c8011000c8000001c0001710000006f020c80"
    "11000c8000001c00014f00000070020080290005800100be000072020100802d000135004e00a1042d000"
    "34f007102008001000c800302010011000c8000001c00010b0000002d000432003500610002002d000632"
    "0035006100020003000f000c802d000232003500610002002d00073200350061000200"
)

INSERT_AT = 57
HAS_ITEM_JUMP_AT = 33
ANIM_JUMP_AT = 50

_COMPARE = 17
_GOTO = 22
_GOTO_IF = 28
_SET_FLAG = 30
_ADD_VAR = 39
_SUB_VAR = 40
_GET_PLAYER_COORDS = 105
_GET_PLAYER_FACING = 386
_NOT_EQUAL = 5

_X = 0x8001
_Z = 0x8002
_DIRECTION = 0x8003

_DIR_NORTH = 0
_DIR_SOUTH = 1
_DIR_WEST = 2


class ApricornTreeDataError(Exception):
    pass


def check_script(data: bytes) -> None:
    if bytes(data) != VANILLA_SCRIPT:
        raise ApricornTreeDataError("the Apricorn tree script does not match the vanilla bytes")


def _compare(var: int, value: int) -> bytes:
    return struct.pack("<HHH", _COMPARE, var, value)


def _var_op(opcode: int, var: int, value: int) -> bytes:
    return struct.pack("<HHH", opcode, var, value)


def _build_dispatch(trees: list[int]) -> bytes:
    steps: list[tuple] = [
        ("raw", struct.pack("<HHH", _GET_PLAYER_COORDS, _X, _Z)),
        ("raw", struct.pack("<HH", _GET_PLAYER_FACING, _DIRECTION)),
        ("raw", _compare(_DIRECTION, _DIR_NORTH)),
        ("if_ne", "south"),
        ("raw", _var_op(_SUB_VAR, _Z, 1)),
        ("goto", "trees"),
        ("label", "south"),
        ("raw", _compare(_DIRECTION, _DIR_SOUTH)),
        ("if_ne", "west"),
        ("raw", _var_op(_ADD_VAR, _Z, 1)),
        ("goto", "trees"),
        ("label", "west"),
        ("raw", _compare(_DIRECTION, _DIR_WEST)),
        ("if_ne", "east"),
        ("raw", _var_op(_SUB_VAR, _X, 1)),
        ("goto", "trees"),
        ("label", "east"),
        ("raw", _var_op(_ADD_VAR, _X, 1)),
        ("label", "trees"),
    ]
    for position, index in enumerate(trees):
        x, z = TREE_POSITIONS[index]
        following = f"tree_{position + 1}" if position + 1 < len(trees) else "end"
        steps += [
            ("label", f"tree_{position}"),
            ("raw", _compare(_X, x)),
            ("if_ne", following),
            ("raw", _compare(_Z, z)),
            ("if_ne", following),
            ("raw", struct.pack("<HH", _SET_FLAG, APRICORN_TREE_FLAGS[index])),
            ("goto", "end"),
        ]
    steps.append(("label", "end"))
    sizes = {"raw": None, "if_ne": 7, "goto": 6, "label": 0}
    labels: dict[str, int] = {}
    cursor = 0
    for step in steps:
        if step[0] == "label":
            labels[step[1]] = cursor
        elif step[0] == "raw":
            cursor += len(step[1])
        else:
            cursor += sizes[step[0]]
    out = bytearray()
    for step in steps:
        kind = step[0]
        if kind == "raw":
            out += step[1]
        elif kind == "if_ne":
            end = len(out) + 7
            out += struct.pack("<HBi", _GOTO_IF, _NOT_EQUAL, labels[step[1]] - end)
        elif kind == "goto":
            end = len(out) + 6
            out += struct.pack("<Hi", _GOTO, labels[step[1]] - end)
    return bytes(out)


def build_script(trees: Iterable[int]) -> bytes:
    chosen = sorted(set(trees))
    if not chosen:
        raise ApricornTreeDataError("no Apricorn tree to patch")
    if chosen[0] < 0 or chosen[-1] >= TREE_COUNT:
        raise ApricornTreeDataError(f"Apricorn tree index out of range: {chosen}")
    block = _build_dispatch(chosen)
    script = bytearray(VANILLA_SCRIPT)
    for at in (HAS_ITEM_JUMP_AT, ANIM_JUMP_AT):
        (rel,) = struct.unpack_from("<i", script, at + 3)
        struct.pack_into("<i", script, at + 3, rel + len(block))
    script[INSERT_AT:INSERT_AT] = block
    return bytes(script)


def read_tree_objects(zone_events: list[bytes]) -> dict[int, tuple[int, int]]:
    found: dict[int, tuple[int, int]] = {}
    for data in zone_events:
        data = bytes(data)
        (background_count,) = struct.unpack_from("<I", data, 0)
        offset = 4 + background_count * 20
        (object_count,) = struct.unpack_from("<I", data, offset)
        offset += 4
        for slot in range(object_count):
            fields = struct.unpack_from("<HHHHHHHHHHhhHHi", data, offset + OBJECT_ENTRY_SIZE * slot)
            if fields[5] == STD_SCRIPT_ID:
                found[fields[7]] = (fields[12], fields[13])
    return found


def apply_apricorn_trees(rom: HeartGoldRom, trees: Iterable[int]) -> None:
    chosen = sorted(set(trees))
    if not chosen:
        return
    narc = rom.read_narc(NITROFS_PATH)
    check_script(narc.files[SCRIPT_INDEX])
    narc.files[SCRIPT_INDEX] = build_script(chosen)
    rom.write_narc(NITROFS_PATH, narc)
