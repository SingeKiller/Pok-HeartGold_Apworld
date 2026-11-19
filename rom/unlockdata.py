from __future__ import annotations

from rom import HeartGoldRom, msgdata

OPTIONS_OVERLAY = 54
OPTIONS_TEXT_BANK = 45
LABELS = {4: "UNLOCK", 16: "OFF", 17: "ON"}
MONO_FLAG_CALLS = {
    0x1EC: bytes.fromhex("1ff646ff"),
    0xBEC: bytes.fromhex("1ff646fa"),
}
_THUMB_NOPS = bytes.fromhex("c046c046")


class UnlockPatchError(Exception):
    pass


def patch_overlay(data: bytes) -> bytes:
    out = bytearray(data)
    for site, expected in MONO_FLAG_CALLS.items():
        if data[site : site + len(expected)] != expected:
            raise UnlockPatchError(f"options overlay: unexpected bytes for the mono flag call at {site:#x}")
        out[site : site + len(expected)] = _THUMB_NOPS
    return bytes(out)


def write_unlock_button(rom: HeartGoldRom) -> None:
    rom.write_overlay(OPTIONS_OVERLAY, patch_overlay(rom.read_overlay(OPTIONS_OVERLAY)))
    msgdata.replace_messages(rom, OPTIONS_TEXT_BANK, LABELS)
