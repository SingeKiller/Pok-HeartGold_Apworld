from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

CHECKBADGE_OPCODE = 294
COMPARE_OPCODE = 17
GOTOIF_OPCODE = 28
CHECKFLAG_OPCODE = 32
NOOP_OPCODE = 0

VAR_SPECIAL_RESULT = 0x800C
GOTOIF_EQ = 1

GATE_SIGNATURE_SIZE = 19
GATE_PATCH_SIZE = 12

TABLE: dict[str, tuple[int, int, int]] = {
    "zephyr": (859, 181, 0),
    "hive": (869, 219, 1),
    "plain": (886, 276, 2),
    "fog": (922, 320, 3),
    "storm": (877, 47, 4),
    "mineral": (913, 362, 5),
    "glacier": (932, 198, 6),
    "boulder": (752, 265, 8),
    "cascade": (760, 654, 9),
    "thunder": (778, 778, 10),
    "rainbow": (786, 277, 11),
    "soul": (809, 1756, 12),
    "marsh": (829, 151, 13),
    "volcano": (15, 262, 14),
    "earth": (743, 115, 15),
}

EXCLUDED: dict[str, str] = {
    "rising": (
        "Clair has no CheckBadge gate on her battle path; her gym script "
        "already gates her on the same sentinel flag this module would install"
    ),
}

SENTINEL_FLAGS: dict[str, int] = {
    "zephyr": 0x192,
    "hive": 0x520,
    "fog": 0x521,
    "storm": 0x522,
    "mineral": 0x523,
    "glacier": 0x524,
    "boulder": 0x525,
    "cascade": 0x526,
    "thunder": 0x31A,
    "rainbow": 0x527,
    "soul": 0x528,
    "marsh": 0x529,
    "volcano": 0x265,
    "earth": 0x97F,
}

WHITNEY_BADGE_NAME = "plain"
WHITNEY_VAR = 0x410A
WHITNEY_VAR_VALUE = 2


class BadgeGateDataError(Exception):
    pass


def read_gate_bytes(rom: HeartGoldRom, narc_index: int, offset: int, size: int = GATE_SIGNATURE_SIZE) -> bytes:
    narc = rom.read_narc(NITROFS_PATH)
    return bytes(narc.files[narc_index][offset : offset + size])


def _verify_gate_signature(blob: bytes, badge_name: str, offset: int, badge_index: int) -> None:
    signature = blob[offset : offset + GATE_SIGNATURE_SIZE]
    if len(signature) != GATE_SIGNATURE_SIZE:
        raise BadgeGateDataError(f"{badge_name}: gate at offset {offset} runs past the end of NARC sub-file")

    check_opcode, check_badge, check_var = struct.unpack_from("<HHH", signature, 0)
    cmp_opcode, cmp_var, cmp_value = struct.unpack_from("<HHH", signature, 6)
    goto_opcode = struct.unpack_from("<H", signature, 12)[0]
    goto_cond = signature[14]

    expected = (
        CHECKBADGE_OPCODE,
        badge_index,
        VAR_SPECIAL_RESULT,
        COMPARE_OPCODE,
        VAR_SPECIAL_RESULT,
        1,
        GOTOIF_OPCODE,
        GOTOIF_EQ,
    )
    actual = (check_opcode, check_badge, check_var, cmp_opcode, cmp_var, cmp_value, goto_opcode, goto_cond)
    if actual != expected:
        raise BadgeGateDataError(
            f"{badge_name}: gate signature mismatch at offset {offset} -- expected {expected}, got {actual} "
            f"(raw {signature.hex(' ')})"
        )


def build_gate_patch(badge_name: str) -> bytes:
    if badge_name == WHITNEY_BADGE_NAME:
        head = struct.pack("<HHH", COMPARE_OPCODE, WHITNEY_VAR, WHITNEY_VAR_VALUE)
    else:
        flag_id = SENTINEL_FLAGS.get(badge_name)
        if flag_id is None:
            raise KeyError(f"no sentinel flag known for badge {badge_name!r}")
        head = struct.pack("<HH", CHECKFLAG_OPCODE, flag_id)

    remaining = GATE_PATCH_SIZE - len(head)
    if remaining < 0 or remaining % 2 != 0:
        raise BadgeGateDataError(
            f"{badge_name}: replacement head is {len(head)} bytes, does not pad to {GATE_PATCH_SIZE}"
        )
    return head + struct.pack("<H", NOOP_OPCODE) * (remaining // 2)


def write_badge_gate_regated(rom: HeartGoldRom, badge_name: str) -> None:
    site = TABLE.get(badge_name)
    if site is None:
        raise KeyError(f"unknown badge gate: {badge_name!r} (excluded: {sorted(EXCLUDED)})")
    narc_index, offset, badge_index = site

    narc = rom.read_narc(NITROFS_PATH)
    blob = bytearray(narc.files[narc_index])
    _verify_gate_signature(bytes(blob), badge_name, offset, badge_index)

    blob[offset : offset + GATE_PATCH_SIZE] = build_gate_patch(badge_name)
    narc.files[narc_index] = bytes(blob)
    rom.write_narc(NITROFS_PATH, narc)


def write_all_badge_gates_regated(rom: HeartGoldRom) -> None:
    for badge_name in TABLE:
        write_badge_gate_regated(rom, badge_name)
