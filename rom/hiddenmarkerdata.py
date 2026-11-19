from __future__ import annotations

import struct

from rom import HeartGoldRom, eventdata
from rom.eventscriptdata import NITROFS_PATH as SCRIPT_NARC

MODEL_NARC = "a/0/8/1"
OBJECT_TABLE_OVERLAY = 1
ELEVATED_SPRITE = 281
ELEVATED_MODEL = 107
GROUND_SPRITE = 175
GROUND_MODEL = 55
BALL_MODEL = 94
TREE_MODEL = 93
ELEVATED_ATTRIBUTES = 0x020
GROUND_ATTRIBUTES = 0x020 | (1 << 10)
HIDDEN_SCRIPT_FILE = 145
HIDDEN_SCRIPT_BASE = 8000
HIDDEN_FLAG_BASE = 800
BG_TYPE_HIDDEN = 2
MARKER_FIRST_ID = 200
MAX_OBJECTS_PER_MAP = 64
MARKER_COLOURS = {3: 0x035F, 4: 0x01D6}
ARROW_ROWS = (
    "...5555555555...",
    "...5333333335...",
    "....53333335....",
    ".....533335.....",
    "......5335......",
    ".......55.......",
)
ELEVATED_TILES = frozenset({
    (8000, 682, 391), (8004, 475, 377), (8006, 421, 469), (8008, 381, 417), (8011, 391, 243),
    (8013, 379, 146), (8014, 12, 11), (8015, 59, 26), (8016, 14, 9), (8017, 9, 52), (8021, 15, 24),
    (8023, 309, 256), (8024, 252, 300), (8025, 170, 332), (8027, 17, 8), (8028, 38, 15),
    (8039, 80, 396), (8042, 480, 182), (8043, 27, 42), (8044, 58, 46), (8047, 53, 29),
    (8048, 34, 38), (8049, 33, 15), (8050, 17, 73), (8052, 1, 9), (8053, 13, 14), (8054, 20, 29),
    (8055, 48, 14), (8056, 28, 60), (8058, 7, 30), (8059, 16, 8), (8060, 38, 31), (8061, 38, 34),
    (8065, 10, 7), (8067, 20, 11), (8068, 12, 11), (8069, 27, 13), (8070, 17, 18), (8071, 26, 26),
    (8072, 48, 5), (8073, 47, 44), (8074, 63, 45), (8075, 29, 11), (8076, 45, 45), (8077, 10, 39),
    (8078, 2, 19), (8079, 18, 33), (8081, 14, 12), (8082, 8, 22), (8086, 23, 26), (8088, 56, 19),
    (8090, 5, 7), (8091, 42, 18), (8092, 38, 27), (8093, 4, 40), (8094, 60, 44), (8095, 24, 36),
    (8106, 1298, 110), (8111, 1386, 377), (8114, 1030, 481), (8114, 1033, 481), (8117, 55, 40),
    (8124, 39, 11), (8127, 23, 7), (8128, 14, 7), (8129, 17, 7), (8133, 365, 164), (8137, 285, 231),
    (8139, 1160, 105), (8140, 34, 74), (8141, 60, 37), (8142, 61, 71), (8143, 42, 48),
    (8144, 16, 18), (8146, 442, 296), (8147, 418, 314), (8149, 422, 263), (8150, 423, 311),
    (8151, 30, 58), (8152, 18, 76), (8153, 20, 43), (8154, 3, 74), (8155, 24, 15), (8156, 3, 81),
    (8165, 28, 41), (8166, 1044, 506), (8167, 1041, 493), (8168, 1318, 323), (8169, 25, 34),
    (8178, 1207, 467), (8180, 1210, 505), (8182, 882, 396), (8184, 923, 316), (8185, 15, 27),
    (8187, 59, 40), (8188, 43, 18), (8191, 67, 8), (8192, 28, 10), (8193, 72, 20), (8195, 24, 7),
    (8198, 1035, 101), (8201, 45, 17), (8202, 18, 1), (8203, 2, 1), (8204, 23, 12), (8206, 24, 2),
    (8208, 1209, 460), (8209, 40, 25), (8210, 10, 9), (8219, 32, 57), (8220, 50, 58), (8222, 38, 2),
    (8223, 27, 22), (8226, 9, 30), (8228, 15, 47),
})

_TEXTURE_OFFSET = 0xA4
_BALL_SIZE = 16
_BALL_FIRST_ROW = 5
_TREE_SIZE = 32
_PALETTE_SIZE = 16
_BG_SIZE = 20
_OBJECT_SIZE = 32
_COUNT_SIZE = 4
_VAR_HIDDEN_FLAG = 0x8006
_VAR_LAST_TALKED = 0x800D
_MSG_FOUND_ITEM = 9
_GOTO = 22
_GOTO_IF = 28
_COMPARE_VAR_TO_VALUE = 17
_SET_FLAG_VAR = 33
_SET_VAR = 41
_NPC_MSG = 45
_HIDE_PERSON = 101
_LESS_THAN = 0


class HiddenMarkerPatchError(Exception):
    pass


def _marker_palette(ball: bytes) -> bytes:
    start = _TEXTURE_OFFSET + _BALL_SIZE * _BALL_SIZE // 2
    palette = bytearray(ball[start : start + _PALETTE_SIZE])
    for index, colour in MARKER_COLOURS.items():
        struct.pack_into("<H", palette, index * 2, colour)
    return bytes(palette)


def build_ground_model(ball: bytes) -> bytes:
    start = _TEXTURE_OFFSET + _BALL_SIZE * _BALL_SIZE // 2
    return ball[:start] + _marker_palette(ball) + ball[start + _PALETTE_SIZE :]


def build_elevated_model(tree: bytes, ball: bytes) -> bytes:
    tree_bytes = _TREE_SIZE * _TREE_SIZE // 2
    ball_row = _BALL_SIZE // 2
    tree_row = _TREE_SIZE // 2
    side = (tree_row - ball_row) // 2
    texture = bytearray(tree_bytes)
    for y in range(_BALL_FIRST_ROW, _BALL_SIZE):
        start = _TEXTURE_OFFSET + y * ball_row
        target = (y - _BALL_FIRST_ROW) * tree_row + side
        texture[target : target + ball_row] = ball[start : start + ball_row]
    for y, row in enumerate(ARROW_ROWS, _BALL_SIZE - _BALL_FIRST_ROW):
        for x, char in enumerate(row, side * 2):
            if char != ".":
                texture[y * tree_row + x // 2] |= int(char) << (4 if x & 1 else 0)
    palette = _marker_palette(ball)
    out = bytearray(tree)
    out[_TEXTURE_OFFSET : _TEXTURE_OFFSET + tree_bytes] = texture
    out[_TEXTURE_OFFSET + tree_bytes : _TEXTURE_OFFSET + tree_bytes + _PALETTE_SIZE] = palette
    return bytes(out)


def add_markers(data: bytes) -> bytes:
    (bg_count,) = struct.unpack_from("<I", data, 0)
    objects_at = _COUNT_SIZE + bg_count * _BG_SIZE
    (object_count,) = struct.unpack_from("<I", data, objects_at)
    objects_end = objects_at + _COUNT_SIZE + object_count * _OBJECT_SIZE
    markers = []
    for index in range(bg_count):
        script, kind, x, z, _y, _direction = struct.unpack_from("<HHIIII", data, _COUNT_SIZE + index * _BG_SIZE)
        if kind != BG_TYPE_HIDDEN:
            continue
        if script < HIDDEN_SCRIPT_BASE:
            raise HiddenMarkerPatchError(f"hidden item event with script {script} below the hidden item scripts")
        sprite = ELEVATED_SPRITE if (script, x, z) in ELEVATED_TILES else GROUND_SPRITE
        markers.append(
            struct.pack(
                "<14HI",
                MARKER_FIRST_ID + len(markers), sprite, 0, 0,
                script - HIDDEN_SCRIPT_BASE + HIDDEN_FLAG_BASE, script,
                0, 0, 0, 0, 0, 0, x, z, 0,
            )
        )
    if not markers:
        return data
    if object_count + len(markers) > MAX_OBJECTS_PER_MAP:
        raise HiddenMarkerPatchError(f"{object_count + len(markers)} objects do not fit in one map")
    return (
        data[:objects_at]
        + struct.pack("<I", object_count + len(markers))
        + data[objects_at + _COUNT_SIZE : objects_end]
        + b"".join(markers)
        + data[objects_end:]
    )


def _found_item_site() -> bytes:
    return struct.pack("<HH", _SET_FLAG_VAR, _VAR_HIDDEN_FLAG) + struct.pack("<HB", _NPC_MSG, _MSG_FOUND_ITEM)


def patch_hidden_script(data: bytes) -> bytes:
    pattern = _found_item_site()
    if data.count(pattern) != 1:
        raise HiddenMarkerPatchError(f"scr_seq_0145: expected one found item sequence, got {data.count(pattern)}")
    site = data.index(pattern)
    start = len(data)
    head = struct.pack("<HH", _SET_FLAG_VAR, _VAR_HIDDEN_FLAG)
    head += struct.pack("<HHH", _COMPARE_VAR_TO_VALUE, _VAR_LAST_TALKED, MARKER_FIRST_ID)
    jump_at = start + len(head)
    hide = struct.pack("<HH", _HIDE_PERSON, _VAR_LAST_TALKED) + struct.pack("<HHH", _SET_VAR, _VAR_LAST_TALKED, 0)
    skip = jump_at + 7 + len(hide)
    routine = head + struct.pack("<HBi", _GOTO_IF, _LESS_THAN, skip - (jump_at + 3) - 4) + hide
    routine += struct.pack("<HB", _NPC_MSG, _MSG_FOUND_ITEM)
    back_at = start + len(routine)
    routine += struct.pack("<Hi", _GOTO, (site + len(pattern)) - (back_at + 2) - 4)
    out = bytearray(data)
    out[site : site + 6] = struct.pack("<Hi", _GOTO, start - (site + 2) - 4)
    return bytes(out) + routine


def patch_object_table(code: bytes) -> bytes:
    for sprite, model, attributes in (
        (ELEVATED_SPRITE, ELEVATED_MODEL, ELEVATED_ATTRIBUTES),
        (GROUND_SPRITE, GROUND_MODEL, GROUND_ATTRIBUTES),
    ):
        row = struct.pack("<3H", sprite, model, 0)
        if code.count(row) != 1:
            raise HiddenMarkerPatchError(f"overlay 1: expected one object row for sprite {sprite}, got {code.count(row)}")
        code = code.replace(row, struct.pack("<3H", sprite, model, attributes))
    return code


def write_hidden_item_markers(rom: HeartGoldRom) -> None:
    models = rom.read_narc(MODEL_NARC)
    ball = bytes(models.files[BALL_MODEL])
    models.files[ELEVATED_MODEL] = build_elevated_model(bytes(models.files[TREE_MODEL]), ball)
    models.files[GROUND_MODEL] = build_ground_model(ball)
    rom.write_narc(MODEL_NARC, models)
    rom.write_overlay(OBJECT_TABLE_OVERLAY, patch_object_table(rom.read_overlay(OBJECT_TABLE_OVERLAY)))
    eventdata.write_all(rom, [add_markers(bytes(entry)) for entry in eventdata.read_all(rom)])
    scripts = rom.read_narc(SCRIPT_NARC)
    scripts.files[HIDDEN_SCRIPT_FILE] = patch_hidden_script(bytes(scripts.files[HIDDEN_SCRIPT_FILE]))
    rom.write_narc(SCRIPT_NARC, scripts)
