# rom/speciesdata.py
#
# Read/write access to the species/personal stats table (task C13): base
# stats, types, catch rate, TM/HM compatibility etc. -- the table
# `species.py`'s evolution/starter/encounter randomization (task C11) will
# eventually need patched into the ROM to actually take effect in-game.
#
# NitroFS path: like rom/itemdata.py's item table, this table is not
# reachable at its decomp source-tree path in the retail ROM
# (`poketool/personal/personal.narc` does not exist in the built ROM).
# `ressources/Decomposition/pokeheartgold/filesystem.mk`'s
# `arc_strip_name` call maps `files/poketool/personal/personal.narc` ->
# `files/a/0/0/2`, i.e. the real NitroFS path is `a/0/0/2`, verified
# directly against the real US HeartGold ROM: readable, parses as a NARC
# with exactly 508 sub-files.
#
# Open question, deliberately left unresolved here (same reasoning as
# rom/itemdata.py's own docstring): `data/species.py`'s `SPECIES` table has
# 505 entries (493 real Pokedex species + 12 HGSS alternate forms, see
# species.py's own `real_species_pool` docstring), 3 fewer than this NARC's
# 508 sub-files. The extra slots are very likely a leading placeholder
# entry (index 0, "no species") plus a couple of additional
# engine-reserved/egg-related slots, but which raw index corresponds to
# which `data/species.py` key is not resolved here -- left to whichever
# later task writes species-stat patches. `tests/test_rom_access.py` only
# asserts the NARC has at least as many entries as `SPECIES` (a loose but
# verifiable sanity check), not an index<->species equivalence.

from __future__ import annotations

from collections.abc import Sequence

from rom import HeartGoldRom

# See this module's docstring for how this numbered path was derived and
# verified against the real ROM.
NITROFS_PATH = "a/0/0/2"

# Sub-file count confirmed against the real US HeartGold ROM.
EXPECTED_ENTRY_COUNT = 508


def read_all(rom: HeartGoldRom) -> list[bytes]:
    """Return every species stats entry as a raw bytes blob, one per NARC
    sub-file, in on-disk order."""
    return rom.read_narc(NITROFS_PATH).files


def write_all(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    """Replace every species stats entry. `entries` must have exactly as
    many elements as the table currently has -- this layer never adds or
    removes NARC sub-files, only replaces their contents."""
    narc = rom.read_narc(NITROFS_PATH)
    if len(entries) != len(narc.files):
        raise ValueError(
            f"species data table has {len(narc.files)} entries, got "
            f"{len(entries)} replacement entries -- entry count must match "
            "exactly (this layer never adds/removes NARC sub-files)."
        )
    narc.files = list(entries)
    rom.write_narc(NITROFS_PATH, narc)


def read_entry(rom: HeartGoldRom, index: int) -> bytes:
    """Read a single species stats entry by its raw NARC sub-file index."""
    return rom.read_narc(NITROFS_PATH).files[index]


def write_entry(rom: HeartGoldRom, index: int, data: bytes) -> None:
    """Replace a single species stats entry by its raw NARC sub-file
    index."""
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[index] = data
    rom.write_narc(NITROFS_PATH, narc)
