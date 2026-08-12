# rom/starterdata.py
#
# *** DISCONFIRMED CANDIDATE -- do not wire this into the normal patch
# path. A live BizHawk test showed overlay 61 / offset 0x1A98 does NOT
# change the starter-choice scene (still vanilla Chikorita/Cyndaquil/
# Totodile). Kept for its own mechanical correctness (round-trips a ROM
# copy). A more promising lead was found 2026-08-12: src/choose_starter.c
# has a plain, hardcoded `const int species[]` array in decompiled C
# source -- see the heartgold-next-session-priorities memory / NOTES.md
# before resuming this investigation. ***
#
# Unlike every other table this project patches, the starter choice is
# not NitroFS data -- this candidate was a compiled `const int species[]`
# literal in an ARM9 overlay, found by searching for the three raw
# species indices for Chikorita/Cyndaquil/Totodile (152, 155, 158) as a
# literal int[3] across the ARM9 binary and all 129 overlays. See
# NOTES.md for the full search methodology.

from __future__ import annotations

import struct

from rom import HeartGoldRom

OVERLAY_ID = 61
_SPECIES_ARRAY_OFFSET = 0x1A98
_SPECIES_COUNT = 3


def read_starters(rom: HeartGoldRom) -> tuple[int, int, int]:
    """Read the 3 raw species indices at the (disconfirmed) candidate
    address."""
    data = rom.read_overlay(OVERLAY_ID)
    return struct.unpack_from("<III", data, _SPECIES_ARRAY_OFFSET)


def write_starters(rom: HeartGoldRom, species_raw_ids: tuple[int, int, int]) -> None:
    """Overwrite the 3 raw species indices at the (disconfirmed) candidate
    address, leaving every other byte of the overlay untouched."""
    if len(species_raw_ids) != _SPECIES_COUNT:
        raise ValueError(f"expected exactly {_SPECIES_COUNT} species ids, got {len(species_raw_ids)}")
    data = bytearray(rom.read_overlay(OVERLAY_ID))
    struct.pack_into("<III", data, _SPECIES_ARRAY_OFFSET, *species_raw_ids)
    rom.write_overlay(OVERLAY_ID, bytes(data))
