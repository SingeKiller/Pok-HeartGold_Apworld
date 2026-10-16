# rom/newbarkexitdata.py
#
# Keeps New Bark Town's east water open for the whole run (2026-09-23).
#
# Vanilla: two coordinate triggers on New Bark's east shore (x=700,
# z=398..402, zone_event T20) fire while VAR_SCENE_NEW_BARK_EAST_EXIT is 1
# or 2, and Mom walks the player back ("Prof. Elm wants to see you", then
# the Kimono Girl reminder). The var goes to 1 when Clair hands the badge
# over at the Dragon's Den Shrine (scr_seq_0112_D44R0103.s:192), to 2 after
# the Elm's Lab scene that follows (scr_seq_0843_T20R0101.s:949), and only
# to 3 (open again) after the Ho-Oh or Lugia battle
# (scr_seq_0021_D17R0110.s:84, scr_seq_0104_D40R0107.s:96).
#
# Archipelago logic cannot model a road that closes then reopens: Route 27
# is open from the start in logic (Surf only), so doing the Dragon's Den
# quiz before the box-art legendary would leave the player walled out of
# checks the logic considers reachable. Here both SetVar instructions write
# 3 instead, the value the legendary battle writes, so the triggers never
# fire. Nothing else reads the var (only the two triggers, whole decomp
# checked), and Mom's scripts have no side effect besides pushing the
# player back. Offsets verified byte for byte on both the HeartGold and
# SoulSilver US ROMs.

from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

SETVAR_OPCODE = 41
VAR_SCENE_NEW_BARK_EAST_EXIT = 0x4081
EAST_EXIT_OPEN = 3

# (scr_seq narc index, byte offset of the SetVar opcode, vanilla value)
SITES: tuple[tuple[int, int, int], ...] = (
    (112, 776, 1),  # Dragon's Den Shrine, after Clair's badge
    (843, 3175, 2),  # Elm's Lab, after the post-Clair scene
)


class NewBarkExitPatchError(Exception):
    """A script does not hold the expected vanilla instruction."""


def patch_script(data: bytes, offset: int, vanilla_value: int) -> bytes:
    expected = struct.pack("<HHH", SETVAR_OPCODE, VAR_SCENE_NEW_BARK_EAST_EXIT, vanilla_value)
    if data[offset : offset + len(expected)] != expected:
        raise NewBarkExitPatchError(
            f"no `SetVar VAR_SCENE_NEW_BARK_EAST_EXIT, {vanilla_value}` at offset {offset}"
        )
    out = bytearray(data)
    struct.pack_into("<H", out, offset + 4, EAST_EXIT_OPEN)
    return bytes(out)


def write_new_bark_east_exit_open(rom: HeartGoldRom) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    for index, offset, vanilla_value in SITES:
        narc.files[index] = patch_script(bytes(narc.files[index]), offset, vanilla_value)
    rom.write_narc(NITROFS_PATH, narc)
