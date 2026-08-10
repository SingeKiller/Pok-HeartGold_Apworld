# rom/starterdata.py
#
# *** EXPERIMENTAL -- NOT LIVE-VERIFIED, read this whole docstring before
# enabling starter randomization by default anywhere ***
#
# Read/write access to the vanilla starter species list (task M4.5).
# Unlike every other table this project patches (ground items, NPC gifts,
# species/moves/trainers/encounters/evolutions), the starter choice is not
# NitroFS data -- it is 3 compiled `const int species[]` literal values
# baked into an ARM9 **overlay** (Decomposition `src/choose_starter.c`:
# `const int species[] = { SPECIES_CHIKORITA, SPECIES_CYNDAQUIL,
# SPECIES_TOTODILE };`, a local array inside `CreateStarter`'s task-state
# machine). This is the same general category of problem as C14's
# ground-item ARM hook (compiled code, not data) -- but narrower: this is
# an in-place *data* patch (3 existing literal values), not code injection
# (no new instructions, no call-site hooking), so the risk profile is
# closer to a NitroFS table edit than to C14's Blocker 1.
#
# How the address was found (task M4.5, no linked build available, same
# constraint as everywhere else in this project): the three raw species
# indices for Chikorita/Cyndaquil/Totodile (152, 155, 158 --
# `data/species_index.py`) were searched for as a literal `int[3]` (three
# consecutive little-endian `u32`s, matching C's `int` size and the
# array's declared type) across the ARM9 binary and all 129 ARM9
# overlays. Zero matches in the main ARM9 binary; exactly one match,
# total, across every overlay -- overlay 61, byte offset 0x1A98,
# `98 00 00 00 9b 00 00 00 9e 00 00 00` (152, 155, 158 as consecutive
# `<III`). A second, unrelated 16-bit pattern also turned up in overlays
# 80/99, but inspecting its surrounding bytes shows a long run of many
# sequential-looking species ids (consistent with a Pokédex-order table,
# not a 3-element starter list) -- not this array, discarded.
#
# **What was NOT done**: a live BizHawk test confirming that overwriting
# these 12 bytes actually changes which 3 Pokémon appear in the starter-
# choice scene in a running game. The uniqueness and exact type-match of
# the ARM9-wide search is strong circumstantial evidence, but per this
# project's own established policy (see docs/architecture.md's repeated
# "a single clean [result] is not sufficient evidence on its own" lesson
# from the client.py RAM-address saga), this must not be treated as
# confirmed until it is. `species.py`/`__init__.py`/`patch_gen.py` do
# not wire this module into the normal generation/patch path yet -- it
# is exposed here, tested for its own mechanical correctness (round-trips
# a ROM copy: write then read back correctly, real ROM), and left for
# whoever picks this up next to live-verify before enabling by default.

from __future__ import annotations

import struct

from rom import HeartGoldRom

OVERLAY_ID = 61
_SPECIES_ARRAY_OFFSET = 0x1A98
_SPECIES_COUNT = 3


def read_starters(rom: HeartGoldRom) -> tuple[int, int, int]:
    """Read the 3 raw species indices currently encoded at the candidate
    address (see this module's own docstring for why "candidate")."""
    data = rom.read_overlay(OVERLAY_ID)
    return struct.unpack_from("<III", data, _SPECIES_ARRAY_OFFSET)


def write_starters(rom: HeartGoldRom, species_raw_ids: tuple[int, int, int]) -> None:
    """Overwrite the 3 raw species indices at the candidate address,
    leaving every other byte of the overlay untouched. See this module's
    own docstring: NOT live-verified to actually change in-game starter
    selection yet."""
    if len(species_raw_ids) != _SPECIES_COUNT:
        raise ValueError(f"expected exactly {_SPECIES_COUNT} species ids, got {len(species_raw_ids)}")
    data = bytearray(rom.read_overlay(OVERLAY_ID))
    struct.pack_into("<III", data, _SPECIES_ARRAY_OFFSET, *species_raw_ids)
    rom.write_overlay(OVERLAY_ID, bytes(data))
