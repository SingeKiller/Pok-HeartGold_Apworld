# rom/starterdata.py
#
# *** LIVE-CONFIRMED (2026-08-12): the Pokémon actually received at the
# starter-choice scene is genuinely randomized (verified with the trio
# swapped to Bulbasaur/Charmander/Squirtle -- a real BizHawk boot test,
# not just a static byte-level match). One known cosmetic gap: the
# on-screen NAME TEXT during the selection scene still shows the vanilla
# name -- the species itself is correct, only the displayed label lags
# behind. Under investigation; likely choose_starter_app.c's UI layer
# reads the name through a separate path than the species field this
# module patches. Safe to wire into the normal patch path species-wise;
# do not advertise the selection-screen text as accurate until fixed. ***
#
# src/choose_starter.c has a plain, hardcoded `const int species[]` array
# inside CreateStarter's switch statement, copied into a local struct and
# passed to CreateMon in a loop. Unlike the old overlay 61 candidate
# (disconfirmed live, see git history), this one lives in the main ARM9
# image, decompressed: searching rom.read_main_code_decompressed() for
# the literal int[3] pattern (152, 155, 158 -- Chikorita/Cyndaquil/
# Totodile's raw species indices) finds exactly one match, at RAM address
# 0x02108514. A real Thumb LDR instruction at RAM 0x02096086 loads this
# exact address from its own literal pool, and the following bytes are a
# 3-word LDMIA/STMIA copy immediately followed by two BL calls with
# constants 5 and 0x20 (32) -- matching CreateMon(mon, species[i], 5, 32,
# ...)'s own level/personality arguments from the decomp source exactly.

from __future__ import annotations

import struct

from rom import HeartGoldRom

# RAM address of the species[3] array within the decompressed ARM9 main
# image (see this module's own docstring for the derivation).
_SPECIES_ARRAY_RAM_ADDRESS = 0x02108514
_SPECIES_COUNT = 3


def _species_array_file_offset(rom: HeartGoldRom) -> int:
    return _SPECIES_ARRAY_RAM_ADDRESS - rom.arm9_ram_address


def read_starters(rom: HeartGoldRom) -> tuple[int, int, int]:
    """Read the 3 raw species indices at the candidate address."""
    decompressed = rom.read_main_code_decompressed()
    offset = _species_array_file_offset(rom)
    return struct.unpack_from("<III", decompressed, offset)


def write_starters(rom: HeartGoldRom, species_raw_ids: tuple[int, int, int]) -> None:
    """Overwrite the 3 raw species indices at the candidate address,
    leaving every other byte of the ARM9 image untouched."""
    if len(species_raw_ids) != _SPECIES_COUNT:
        raise ValueError(f"expected exactly {_SPECIES_COUNT} species ids, got {len(species_raw_ids)}")
    offset = _species_array_file_offset(rom)
    data = struct.pack("<III", *species_raw_ids)
    rom.write_main_code_region(offset, data)
