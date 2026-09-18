# rom/expshare.py
#
# Global Exp. Share and Exp. multiplier (v0.2.5): an in-place code patch of
# ARM9 overlay 12, the battle engine. The source is patches/exp_share.s;
# the bytes below are its armips output, embedded so that patching never
# needs armips on the player's machine. Regenerate them with armips
# whenever the .s file changes (tests/test_expshare.py re-assembles and
# compares when armips is available).
#
# Two variants, picked by `global_exp_share`:
#   - False: vanilla Exp. distribution, only scaled by the multiplier
#     (BtlCmd_CalcExpGain only).
#   - True: participants split the full (scaled) amount and every other
#     party member that is not fainted and not an Egg gets half of it, as
#     in the modern games (BtlCmd_CalcExpGain plus two sites in
#     Task_GetExp).
# The multiplier (a percentage) is a 4-byte literal inside the
# BtlCmd_CalcExpGain patch, written separately.
#
# Overlay 12 is byte-identical between HeartGold and SoulSilver US except
# for 7 bytes outside every range here, so one table serves both. Each
# range is checked against its vanilla bytes before writing: a mismatch
# (another ROM revision, or a patch applied twice) is a hard error rather
# than a corrupted battle engine.

from __future__ import annotations

import struct

OVERLAY_ID = 12
OVERLAY_LOAD_ADDRESS = 0x022378C0

MULTIPLIER_MIN = 10
MULTIPLIER_MAX = 1000

# (address, vanilla hex, patched hex)
_CALC_EXP_GAIN_VANILLA = (
    "002920d044080199201cb4f6f8e8291c9c310860281c9c300068002803d1281c01219c30"
    "01600099201cb4f6e8e8291ca0310860281ca0300068002819d10120a035286015e00199"
    "b4f6d8e8291c9c310860281c9c300068002803d1281c01219c3001600020a035286002e0"
)

_REGIONS_VANILLA_SPLIT: tuple[tuple[int, str, str], ...] = (
    (
        0x0223E79C,
        _CALC_EXP_GAIN_VANILLA,
        "134948436421b4f6fae8041c009900290fd06408201c0199b4f6f0e89c2100f012f8201c"
        "0099b4f6eae8a02100f00bf81fe00199b4f6e2e89c2100f004f80020a021685015e00028"
        "00d1012068507047443322119c300068002803d1281c01219c3001600020a035286002e0",
    ),
)
_MULTIPLIER_LITERAL_VANILLA_SPLIT = 0x0223E7EC

_REGIONS_GLOBAL: tuple[tuple[int, str, str], ...] = (
    (
        0x0223E79C,
        _CALC_EXP_GAIN_VANILLA,
        "0a4948436421b4f6fae8041c0199b4f6f6e89c2100f005f86008a02100f001f827e00028"
        "00d101206850704744332211a0310860281ca0300068002819d10120a035286015e00199"
        "b4f6d8e8291c9c310860281c9c300068002803d1281c01219c3001600020a035286002e0",
    ),
    (0x022458F4, "11d0", "11e0"),
    (
        0x02245A36,
        "281c2cf642fe11998a0009998918a4310968084203d009989c3000680e90069833280"
        "6d10998a030099001680e9840180e90",
        "281c2cf642fe11998a0009998a18a4321268104201d09c2208e0301c4c21002228f673"
        "fd00286fd10999a02288580e90ffe7",
    ),
)
_MULTIPLIER_LITERAL_GLOBAL = 0x0223E7C8


class ExpSharePatchError(Exception):
    """The overlay does not hold the vanilla bytes this patch expects."""


def patch_overlay_data(data: bytes, global_exp_share: bool, multiplier: int) -> bytes:
    """Return a copy of decompressed overlay 12 with the Exp. patch applied."""
    if not MULTIPLIER_MIN <= multiplier <= MULTIPLIER_MAX:
        raise ValueError(f"exp multiplier {multiplier} outside {MULTIPLIER_MIN}..{MULTIPLIER_MAX}")
    regions = _REGIONS_GLOBAL if global_exp_share else _REGIONS_VANILLA_SPLIT
    literal = _MULTIPLIER_LITERAL_GLOBAL if global_exp_share else _MULTIPLIER_LITERAL_VANILLA_SPLIT
    out = bytearray(data)
    for address, vanilla_hex, patched_hex in regions:
        vanilla, patched = bytes.fromhex(vanilla_hex), bytes.fromhex(patched_hex)
        assert len(vanilla) == len(patched)
        offset = address - OVERLAY_LOAD_ADDRESS
        if bytes(out[offset : offset + len(vanilla)]) != vanilla:
            raise ExpSharePatchError(
                f"overlay {OVERLAY_ID} at {address:#010x} does not hold the expected vanilla code -- "
                "unsupported ROM revision, or the Exp. patch was already applied"
            )
        out[offset : offset + len(patched)] = patched
    struct.pack_into("<I", out, literal - OVERLAY_LOAD_ADDRESS, multiplier)
    return bytes(out)


def is_vanilla_setting(global_exp_share: bool, multiplier: int) -> bool:
    """True when the options ask for vanilla behavior, so no patch is needed."""
    return not global_exp_share and multiplier == 100
