# rom/encounterdata.py
#
# Read/write access to the wild encounter tables (task C13): per-map
# grass/surf/rock-smash/fishing/headbutt species slots, the table
# `species.py`'s wild-encounter randomization (task C11) will eventually
# need patched into the ROM.
#
# NitroFS paths: like rom/itemdata.py's item table, neither table is
# reachable at its decomp source-tree path in the retail ROM
# (`fielddata/encountdata/g_enc_data.narc` /
# `fielddata/encountdata/s_enc_data.narc` do not exist in the built ROM).
# `ressources/Decomposition/pokeheartgold/filesystem.mk`'s
# `arc_strip_name` calls map:
#   files/fielddata/encountdata/g_enc_data.narc -> files/a/0/3/7
#   files/fielddata/encountdata/s_enc_data.narc -> files/a/1/3/6
# i.e. the real NitroFS paths are `a/0/3/7` and `a/1/3/6`, both verified
# directly against the real US HeartGold ROM: both readable, both parse as
# NARCs with exactly 142 sub-files (matching the decomp's own
# `gs_enc_data.json`'s 142 map entries, see docs/architecture.md Spike 3).
#
# `g_enc_data.narc` (`GAME_VERSION_S = ENC_HEARTGOLD` in the decomp's own
# `files/fielddata/encountdata/gs_enc_data.mk`) is HeartGold's own
# encounter table -- `HEARTGOLD_NITROFS_PATH` below, the one to patch for
# this project's wild-encounter randomization. `s_enc_data.narc`
# (`ENC_SOULSILVER`) is SoulSilver's encounter table; both are present in
# every HGSS ROM regardless of version (the two games share one codebase,
# see docs/architecture.md), but a HeartGold cartridge's own gameplay only
# ever reads `g_enc_data.narc` at runtime for its own wild encounters --
# `SOULSILVER_NITROFS_PATH` is exposed here for completeness/read access
# only, not intended as a patch target for this project.
#
# `data/encounters.py`'s `ENCOUNTERS` table has 137 zones, fewer than
# either NARC's 142 sub-files -- some maps present in the raw encounter
# data were filtered out during `data_gen` extraction (see the C7 commit
# history). `tests/test_rom_access.py` asserts the NARC has at least as
# many entries as `ENCOUNTERS` (a loose but verifiable sanity check), not
# an index<->zone equivalence -- resolving exactly which NARC sub-file
# index corresponds to which `data/encounters.py` zone key is left to
# whichever later task writes encounter patches.

from __future__ import annotations

from collections.abc import Sequence

from rom import HeartGoldRom

# See this module's docstring for how these numbered paths were derived
# and verified against the real ROM.
HEARTGOLD_NITROFS_PATH = "a/0/3/7"
SOULSILVER_NITROFS_PATH = "a/1/3/6"

# Sub-file count confirmed against the real US HeartGold ROM for both
# tables.
EXPECTED_ENTRY_COUNT = 142


def read_all(rom: HeartGoldRom) -> list[bytes]:
    """Return every HeartGold wild-encounter zone entry as a raw bytes
    blob, one per NARC sub-file, in on-disk order."""
    return rom.read_narc(HEARTGOLD_NITROFS_PATH).files


def write_all(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    """Replace every HeartGold wild-encounter zone entry. `entries` must
    have exactly as many elements as the table currently has -- this layer
    never adds or removes NARC sub-files, only replaces their contents."""
    narc = rom.read_narc(HEARTGOLD_NITROFS_PATH)
    if len(entries) != len(narc.files):
        raise ValueError(
            f"encounter data table has {len(narc.files)} entries, got "
            f"{len(entries)} replacement entries -- entry count must match "
            "exactly (this layer never adds/removes NARC sub-files)."
        )
    narc.files = list(entries)
    rom.write_narc(HEARTGOLD_NITROFS_PATH, narc)


def read_entry(rom: HeartGoldRom, index: int) -> bytes:
    """Read a single wild-encounter zone entry by its raw NARC sub-file
    index."""
    return rom.read_narc(HEARTGOLD_NITROFS_PATH).files[index]


def write_entry(rom: HeartGoldRom, index: int, data: bytes) -> None:
    """Replace a single wild-encounter zone entry by its raw NARC
    sub-file index."""
    narc = rom.read_narc(HEARTGOLD_NITROFS_PATH)
    narc.files[index] = data
    rom.write_narc(HEARTGOLD_NITROFS_PATH, narc)
