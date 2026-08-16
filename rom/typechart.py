# rom/typechart.py
#
# Read/write access to `sTypeEffectiveness`, the 112-row (attacker,
# defender, multiplier) sparse exception table the battle engine's damage
# calc walks linearly (src/battle/overlay_12_0224E4FC.c). Unlike
# rom/movedata.py's table (a NARC file) or rom/tmhmdata.py's array (the
# main ARM9 image), this one lives inside ARM9 **overlay 12** -- the
# battle-only code overlay, swapped in only during battles -- so this
# module uses rom.read_overlay(12)/write_overlay(12, ...) instead.
#
# Same reasoning as rom/tmhmdata.py for using a live byte-pattern search
# instead of a hardcoded offset. Live-verified against the real US
# HeartGold ROM (2026-08-17): the full 112-row vanilla pattern is found
# exactly once, at overlay-12 offset 218044 -- _find_table_offset still
# raises rather than guessing if it ever finds zero or more than one
# match on a different ROM revision.
#
# Row ORDER is load-bearing and this module never reorders anything: the
# `special = "foresight_marker"` row is a sentinel the Foresight/Odor
# Sleuth/Scrappy mechanic scans for and `break`s the scan on, relying on
# the two real matchups placed immediately after it (normal/ghost,
# fighting/ghost) being skipped whenever that break fires. write_type_chart
# only ever overwrites the 3rd byte (multiplier) of rows the caller marks
# randomizable -- attacker/defender bytes, row count and row order are
# always identical to vanilla.

from __future__ import annotations

import re

from rom import HeartGoldRom

OVERLAY_ID = 12
_ENTRY_COUNT = 112
_ENTRY_SIZE = 3  # u8 attacker, u8 defender, u8 multiplier

_ATTACKER_OFFSET = 0
_DEFENDER_OFFSET = 1
_MULTIPLIER_OFFSET = 2

# include/constants/pokemon.h's TYPE_MUL_* constants.
MULTIPLIER_NAME_TO_ID: dict[str, int] = {
    "no_effect": 0,
    "not_effective": 5,
    "normal": 10,
    "super_effective": 20,
}

# include/constants/pokemon.h's TYPE_FORESIGHT/TYPE_ENDTABLE sentinels --
# never real move/species types, only ever appear in this table's own
# attacker byte to mark the two special rows.
_SPECIAL_RAW_ID: dict[str, int] = {
    "foresight_marker": 0xFE,
    "end_table": 0xFF,
}


def _row_raw_bytes(row: dict) -> bytes:
    from rom.movedata import TYPE_NAME_TO_ID

    special = row.get("special")
    if special is not None:
        raw_id = _SPECIAL_RAW_ID[special]
        attacker = defender = raw_id
    else:
        attacker = TYPE_NAME_TO_ID[row["attacker"]]
        defender = TYPE_NAME_TO_ID[row["defender"]]
    multiplier = MULTIPLIER_NAME_TO_ID[row["multiplier"]]
    return bytes((attacker, defender, multiplier))


def _vanilla_pattern() -> bytes:
    from data.type_chart import TYPE_CHART

    if len(TYPE_CHART) != _ENTRY_COUNT:
        raise ValueError(f"data/type_chart.py has {len(TYPE_CHART)} entries, expected {_ENTRY_COUNT}")
    return b"".join(_row_raw_bytes(row) for row in TYPE_CHART)


def _locator_regex(vanilla_pattern: bytes) -> re.Pattern[bytes]:
    """A regex matching `vanilla_pattern` with every multiplier byte
    (every 3rd byte) treated as a wildcard -- write_type_chart only ever
    changes that byte, so locating the table this way works whether the
    ROM is pristine vanilla or was already randomized by an earlier call
    (unlike a plain, exact byte search, which can only ever match a
    still-untouched vanilla ROM)."""
    parts = [re.escape(vanilla_pattern[i : i + 2]) for i in range(0, len(vanilla_pattern), _ENTRY_SIZE)]
    return re.compile(b".".join(parts), re.DOTALL)


def _find_table_offset(overlay_data: bytes, vanilla_pattern: bytes) -> int:
    regex = _locator_regex(vanilla_pattern)
    matches = list(regex.finditer(overlay_data))
    if not matches:
        raise ValueError(
            "rom/typechart.py: could not locate sTypeEffectiveness in overlay "
            f"{OVERLAY_ID} -- vanilla attacker/defender pattern not found. The "
            "table may have moved (different ROM revision?) or data/"
            "type_chart.py no longer matches the real ROM."
        )
    if len(matches) > 1:
        raise ValueError(
            "rom/typechart.py: sTypeEffectiveness attacker/defender pattern "
            f"matched more than once in overlay {OVERLAY_ID} -- can't safely "
            "pick one without a real ROM to cross-check against."
        )
    return matches[0].start()


def read_type_chart(rom: HeartGoldRom) -> list[tuple[int, int, int]]:
    """Every row currently in the ROM, as raw (attacker, defender,
    multiplier) byte triples, in table order. Works whether the table is
    still pristine vanilla or was already randomized by a previous
    write_type_chart call."""
    overlay_data = rom.read_overlay(OVERLAY_ID)
    offset = _find_table_offset(overlay_data, _vanilla_pattern())
    return [
        tuple(overlay_data[offset + i * _ENTRY_SIZE : offset + (i + 1) * _ENTRY_SIZE])
        for i in range(_ENTRY_COUNT)
    ]


def write_type_chart(rom: HeartGoldRom, type_chart: list) -> None:
    """Apply species.py's randomize_type_chart output: overwrites only the
    multiplier byte of each `randomizable: True` row, at its own fixed row
    position. `type_chart` must have exactly _ENTRY_COUNT rows, same order
    as data/type_chart.py."""
    if len(type_chart) != _ENTRY_COUNT:
        raise ValueError(f"expected exactly {_ENTRY_COUNT} type_chart rows, got {len(type_chart)}")

    overlay_data = bytearray(rom.read_overlay(OVERLAY_ID))
    offset = _find_table_offset(bytes(overlay_data), _vanilla_pattern())

    for i, row in enumerate(type_chart):
        if not row["randomizable"]:
            continue
        multiplier_offset = offset + i * _ENTRY_SIZE + _MULTIPLIER_OFFSET
        overlay_data[multiplier_offset] = MULTIPLIER_NAME_TO_ID[row["multiplier"]]

    rom.write_overlay(OVERLAY_ID, bytes(overlay_data))
