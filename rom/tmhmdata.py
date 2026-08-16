# rom/tmhmdata.py
#
# Read/write access to `sTMHMMoves`, the 100-entry (92 TM + 8 HM) u16
# move-id array that decides what move each TM/HM item teaches
# (src/item.c, TMHMGetMove). It's a plain `static const u16[]` compiled
# into the decompressed ARM9 main image (not a NARC file) -- same class of
# target as rom/starterdata.py's species[3] array, but unlike that module
# this one locates it with a live byte-pattern search instead of a
# hardcoded RAM address. Live-verified against the real US HeartGold ROM
# (2026-08-17): the full 100-entry vanilla pattern is found exactly once,
# at decompressed-main-image offset 1048780 -- `_find_array_offset` still
# raises rather than guessing if it ever finds zero or more than one
# match on a different ROM revision.
#
# HM01-HM08 are deliberately never randomized (see write_tm_hm_moves) --
# only TM01-TM92 are eligible. That also makes HM01-HM08's own 8 raw move
# ids (16 bytes) a stable anchor for relocating the table after a write --
# confirmed unique on their own in the real ROM's decompressed main image
# (not just as part of the full 100-entry vanilla pattern), so read_tm_hm_
# moves can find the table again even once every TM slot has already been
# randomized away from vanilla.

from __future__ import annotations

import re
import struct

from rom import HeartGoldRom

TM_COUNT = 92
HM_COUNT = 8
_ENTRY_COUNT = TM_COUNT + HM_COUNT
_ENTRY_SIZE = 2  # u16

# Machine order must match src/item.c's sTMHMMoves[] exactly (also the
# order data_gen/moves.toml's own [tm_hm] section was extracted in).
MACHINE_ORDER: tuple[str, ...] = tuple(f"tm{i:02d}" for i in range(1, TM_COUNT + 1)) + tuple(
    f"hm{i:02d}" for i in range(1, HM_COUNT + 1)
)


def _vanilla_ids_in_order() -> list[int]:
    from data.moves import MOVES, TM_HM_MOVES

    return [MOVES[TM_HM_MOVES[machine]]["id"] for machine in MACHINE_ORDER]


def _locator_regex(vanilla_ids: list[int]) -> re.Pattern[bytes]:
    """A regex matching the full `_ENTRY_COUNT`-entry array with every TM
    slot (index < TM_COUNT) treated as a 2-byte wildcard -- write_tm_hm_
    moves only ever changes those, never the 8 HM slots. Locating the
    table this way works whether the ROM is pristine vanilla or was
    already randomized by an earlier call, unlike a plain exact-byte
    search (which can only ever match a still-untouched vanilla ROM)."""
    parts = []
    for index, move_id in enumerate(vanilla_ids):
        if index < TM_COUNT:
            parts.append(b"..")
        else:
            parts.append(re.escape(struct.pack("<H", move_id)))
    return re.compile(b"".join(parts), re.DOTALL)


def _find_array_offset(decompressed: bytes, vanilla_ids: list[int]) -> int:
    regex = _locator_regex(vanilla_ids)
    matches = list(regex.finditer(decompressed))
    if not matches:
        raise ValueError(
            "rom/tmhmdata.py: could not locate sTMHMMoves in the decompressed "
            "ARM9 main image -- vanilla HM move-id anchor not found. The table "
            "may have moved (different ROM revision?) or data/moves.py's "
            "TM_HM_MOVES no longer matches the real ROM."
        )
    if len(matches) > 1:
        raise ValueError(
            "rom/tmhmdata.py: sTMHMMoves vanilla HM move-id anchor matched more "
            "than once in the decompressed ARM9 main image -- can't safely "
            "pick one without a real ROM to cross-check against (see this "
            "module's own header comment)."
        )
    return matches[0].start()


def read_tm_hm_moves(rom: HeartGoldRom) -> dict[str, int]:
    """Every TM/HM's currently-taught move, as {machine: raw_move_id}.
    Works whether the table is still pristine vanilla or was already
    randomized by a previous write_tm_hm_moves call."""
    decompressed = rom.read_main_code_decompressed()
    offset = _find_array_offset(decompressed, _vanilla_ids_in_order())
    raw_ids = struct.unpack_from(f"<{_ENTRY_COUNT}H", decompressed, offset)
    return dict(zip(MACHINE_ORDER, raw_ids))


def write_tm_hm_moves(rom: HeartGoldRom, machine_to_move_id: dict[str, int]) -> None:
    """Overwrite TM01-TM92's taught move. `machine_to_move_id` must have
    an entry for every one of MACHINE_ORDER, but HM01-HM08's entries are
    silently ignored (always rewritten back to their own vanilla value) --
    HM-taught moves must stay vanilla, since this project's region-access
    rules (`hms = ["surf"]` etc. in data_gen/rules.toml) mean "the player
    owns this HM item," not "the player's HM item currently teaches this
    move": if HM03 ever taught something other than Surf, a player who
    logically has Surf per the rules would be unable to actually use it in
    the field -- a silent, un-recoverable soft-lock."""
    decompressed = bytearray(rom.read_main_code_decompressed())
    vanilla_ids = _vanilla_ids_in_order()
    offset = _find_array_offset(bytes(decompressed), vanilla_ids)

    missing = [machine for machine in MACHINE_ORDER if machine not in machine_to_move_id]
    if missing:
        raise ValueError(f"write_tm_hm_moves: missing entries for {missing!r}")

    new_ids = list(vanilla_ids)  # HM slots start (and stay) vanilla
    for index, machine in enumerate(MACHINE_ORDER):
        if machine.startswith("tm"):
            new_ids[index] = machine_to_move_id[machine]

    data = struct.pack(f"<{_ENTRY_COUNT}H", *new_ids)
    rom.write_main_code_region(offset, data)
