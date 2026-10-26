from __future__ import annotations

import re
import struct

from rom import HeartGoldRom

TM_COUNT = 92
HM_COUNT = 8
_ENTRY_COUNT = TM_COUNT + HM_COUNT
_ENTRY_SIZE = 2

MACHINE_ORDER: tuple[str, ...] = tuple(f"tm{i:02d}" for i in range(1, TM_COUNT + 1)) + tuple(
    f"hm{i:02d}" for i in range(1, HM_COUNT + 1)
)


def _vanilla_ids_in_order() -> list[int]:
    from data.moves import MOVES, TM_HM_MOVES

    return [MOVES[TM_HM_MOVES[machine]]["id"] for machine in MACHINE_ORDER]


def _locator_regex(vanilla_ids: list[int]) -> re.Pattern[bytes]:
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
    decompressed = rom.read_main_code_decompressed()
    offset = _find_array_offset(decompressed, _vanilla_ids_in_order())
    raw_ids = struct.unpack_from(f"<{_ENTRY_COUNT}H", decompressed, offset)
    return dict(zip(MACHINE_ORDER, raw_ids))


def write_tm_hm_moves(rom: HeartGoldRom, machine_to_move_id: dict[str, int]) -> None:
    decompressed = bytearray(rom.read_main_code_decompressed())
    vanilla_ids = _vanilla_ids_in_order()
    offset = _find_array_offset(bytes(decompressed), vanilla_ids)

    missing = [machine for machine in MACHINE_ORDER if machine not in machine_to_move_id]
    if missing:
        raise ValueError(f"write_tm_hm_moves: missing entries for {missing!r}")

    new_ids = list(vanilla_ids)
    for index, machine in enumerate(MACHINE_ORDER):
        if machine.startswith("tm"):
            new_ids[index] = machine_to_move_id[machine]

    data = struct.pack(f"<{_ENTRY_COUNT}H", *new_ids)
    rom.write_main_code_region(offset, data)
