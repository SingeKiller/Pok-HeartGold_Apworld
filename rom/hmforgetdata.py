from __future__ import annotations

from rom import HeartGoldRom

SUMMARY_HM_CALLS = {
    0x020890A8: bytes.fromhex("eef7bcff"),
    0x0208917A: bytes.fromhex("eef753ff"),
}
BATTLE_OVERLAY = 8
BATTLE_HM_TAIL = 0x0221DB72
BATTLE_HM_TAIL_VANILLA = bytes.fromhex("014b1847")
_FALSE_THEN_NOP = bytes.fromhex("0020c046")
_RETURN_FALSE = bytes.fromhex("00207047")


class HmForgetPatchError(Exception):
    pass


def patch_summary(code: bytes, base: int) -> dict[int, bytes]:
    edits = {}
    for address, expected in SUMMARY_HM_CALLS.items():
        offset = address - base
        if code[offset : offset + len(expected)] != expected:
            raise HmForgetPatchError(f"summary screen: unexpected bytes for the HM check at {address:#010x}")
        edits[offset] = _FALSE_THEN_NOP
    return edits


def patch_battle_overlay(data: bytes, base: int) -> bytes:
    offset = BATTLE_HM_TAIL - base
    if data[offset : offset + len(BATTLE_HM_TAIL_VANILLA)] != BATTLE_HM_TAIL_VANILLA:
        raise HmForgetPatchError(f"battle overlay: unexpected bytes for the HM check at {BATTLE_HM_TAIL:#010x}")
    out = bytearray(data)
    out[offset : offset + len(_RETURN_FALSE)] = _RETURN_FALSE
    return bytes(out)


def write_hm_forget(rom: HeartGoldRom) -> None:
    code = rom.read_main_code_decompressed()
    rom.write_main_code_regions(list(patch_summary(code, rom.arm9_ram_address).items()))
    base = rom.overlay_ram_address(BATTLE_OVERLAY)
    rom.write_overlay(BATTLE_OVERLAY, patch_battle_overlay(rom.read_overlay(BATTLE_OVERLAY), base))
