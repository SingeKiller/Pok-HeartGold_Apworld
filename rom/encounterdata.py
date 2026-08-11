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
# encounter table -- `HEARTGOLD_NITROFS_PATH` below. `s_enc_data.narc`
# (`ENC_SOULSILVER`) is SoulSilver's, `SOULSILVER_NITROFS_PATH` below. Both
# are present in every HGSS ROM regardless of version (the two games share
# one codebase, see docs/architecture.md) -- but *which one the compiled
# game code actually reads at runtime* is a compile-time choice, not a
# runtime one: `include/encounter_tables_narc.h` picks between the two
# NARCs with a plain `#ifdef HEARTGOLD`, so a HeartGold cartridge's own
# wild-encounter code only ever opens `g_enc_data.narc`, and a SoulSilver
# cartridge's only ever opens `s_enc_data.narc` -- the *other* file is
# present in that cartridge's own ROM image (dead weight) but never read by
# it. Live-verified 2026-08-11 against both real US ROMs: `a/0/3/7`
# decodes to HeartGold's Route 29 values (morning Sentret) and `a/1/3/6` to
# SoulSilver's (morning Rattata) in *both* ROMs identically -- confirming
# each ROM ships both tables, version-appropriate content baked in at
# build time regardless of which cartridge it ends up in. This is why
# every function below picks its NitroFS path from `rom.version` (see
# `_nitrofs_path_for` below) rather than hardcoding
# `HEARTGOLD_NITROFS_PATH`: writing wild-encounter randomization to the
# wrong path on a SoulSilver ROM would silently produce a patch that a
# real SoulSilver cartridge's own game code never reads, leaving vanilla
# (unrandomized, and version-mismatched pre-2026-08-11-fix) encounters in
# actual play regardless of what was written.
#
# `data/encounters.py`'s `ENCOUNTERS` table has 137 zones, fewer than
# either NARC's 142 sub-files -- some maps present in the raw encounter
# data were filtered out during `data_gen` extraction (see the C7 commit
# history). `tests/test_rom_access.py` asserts the NARC has at least as
# many entries as `ENCOUNTERS` (a loose but verifiable sanity check), not
# an index<->zone equivalence.
#
# Index question, RESOLVED for 134/137 zones (task M4.5, see
# docs/architecture.md's "## M4.5" section): `gs_enc_data.json`'s own
# array order is the real raw index (confirmed against the real ROM: index
# 0 == map code T20 == `data/encounters.py`'s `new_bark` zone, byte-for-
# byte -- its surf slots decode to Tentacool/Tentacruel exactly). Generated
# once, by matching each zone's own `map_code` against
# `gs_enc_data.json[i].map`, into `data/encounter_zone_index.py`'s
# `ENCOUNTER_ZONE_KEY_TO_RAW_INDEX` (see `data_gen/encounter_zone_index.
# toml`'s own header). The 3 unmatched zones (`route_16`/`pewter`/`azalea`)
# have a *headbutt* table only (a different NARC entirely, not read/
# written by this module) and no `gs_enc_data.json` entry at all -- not a
# gap in the mapping, there is genuinely no raw land/surf/rock_smash/
# fishing entry for them to patch.
#
# Struct (Decomposition `include/wild_encounter.h`, `EncounterData`, 0xC4 =
# 196 bytes, confirmed against the real ROM's entry size): see that
# header's own inline byte-offset comments (`/* 0x.. */`) -- reproduced by
# `_write_species_at_offsets` below rather than restated here in full.
# Species fields throughout are **raw species indices** (`data/
# species_index.py`'s `SPECIES_KEY_TO_RAW_INDEX`), confirmed against the
# real ROM the same way as the raw zone-index mapping above (Tentacool's
# raw index, 72, is exactly the u16 found at New Bark Town's first surf
# slot).

from __future__ import annotations

import struct
from collections.abc import Sequence

from rom import HeartGoldRom

# See this module's docstring for how these numbered paths were derived
# and verified against the real ROM.
HEARTGOLD_NITROFS_PATH = "a/0/3/7"
SOULSILVER_NITROFS_PATH = "a/1/3/6"

# Sub-file count confirmed against the real US HeartGold ROM for both
# tables.
EXPECTED_ENTRY_COUNT = 142


def _nitrofs_path_for(rom: HeartGoldRom) -> str:
    """The NitroFS path this `rom`'s own compiled game code actually reads
    at runtime for wild encounters (see this module's docstring):
    `SOULSILVER_NITROFS_PATH` for a SoulSilver ROM, `HEARTGOLD_NITROFS_PATH`
    otherwise -- including `rom.version is None` (an already-patched ROM
    re-opened with `expect_vanilla=False`, see `rom.HeartGoldRom`'s own
    docstring), where HeartGold is kept as the long-standing default rather
    than guessing."""
    if rom.version == "soulsilver":
        return SOULSILVER_NITROFS_PATH
    return HEARTGOLD_NITROFS_PATH


def read_all(rom: HeartGoldRom) -> list[bytes]:
    """Return every wild-encounter zone entry as a raw bytes blob, one per
    NARC sub-file, in on-disk order -- from `rom`'s own version-appropriate
    table (see `_nitrofs_path_for`)."""
    return rom.read_narc(_nitrofs_path_for(rom)).files


def write_all(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    """Replace every wild-encounter zone entry in `rom`'s own version-
    appropriate table (see `_nitrofs_path_for`). `entries` must have
    exactly as many elements as the table currently has -- this layer
    never adds or removes NARC sub-files, only replaces their contents."""
    path = _nitrofs_path_for(rom)
    narc = rom.read_narc(path)
    if len(entries) != len(narc.files):
        raise ValueError(
            f"encounter data table has {len(narc.files)} entries, got "
            f"{len(entries)} replacement entries -- entry count must match "
            "exactly (this layer never adds/removes NARC sub-files)."
        )
    narc.files = list(entries)
    rom.write_narc(path, narc)


def read_entry(rom: HeartGoldRom, index: int) -> bytes:
    """Read a single wild-encounter zone entry by its raw NARC sub-file
    index, from `rom`'s own version-appropriate table (see
    `_nitrofs_path_for`)."""
    return rom.read_narc(_nitrofs_path_for(rom)).files[index]


def write_entry(rom: HeartGoldRom, index: int, data: bytes) -> None:
    """Replace a single wild-encounter zone entry by its raw NARC
    sub-file index, in `rom`'s own version-appropriate table (see
    `_nitrofs_path_for`)."""
    path = _nitrofs_path_for(rom)
    narc = rom.read_narc(path)
    narc.files[index] = data
    rom.write_narc(path, narc)


# Byte offsets within one 196-byte `EncounterData` entry (Decomposition
# `include/wild_encounter.h`, see this module's own docstring).
_LAND_SPECIES_MORN_OFFSET = 0x14
_LAND_SPECIES_DAY_OFFSET = 0x2C
_LAND_SPECIES_NITE_OFFSET = 0x44
_LAND_SLOT_COUNT = 12
_SURF_SLOTS_OFFSET = 0x64
_ROCK_SMASH_SLOTS_OFFSET = 0x78
_OLD_ROD_SLOTS_OFFSET = 0x80
_GOOD_ROD_SLOTS_OFFSET = 0x94
_SUPER_ROD_SLOTS_OFFSET = 0xA8
_ENCOUNTER_DATA_SLOT_SIZE = 4  # EncounterDataSlot{u8 min; u8 max; u16 species;}
_ENCOUNTER_DATA_SLOT_SPECIES_OFFSET = 2

# Capacity of each slot array -- the distance to the *next* field in
# `EncounterData` (see this module's own docstring's byte-offset list),
# divided by `_ENCOUNTER_DATA_SLOT_SIZE`. Writing past these would land in
# the next field entirely, silently -- every write path below checks
# against these rather than trusting `zone`'s own slot counts.
_SURF_SLOT_CAPACITY = 5
_ROCK_SMASH_SLOT_CAPACITY = 2
_FISHING_SLOT_CAPACITY = 5


def _write_land_species(entry: bytearray, land: dict, species_index: dict[str, int]) -> None:
    slots = land["slots"]
    if not slots:
        return
    if len(slots) != _LAND_SLOT_COUNT:
        raise ValueError(f"land encounter data has {len(slots)} slots, expected exactly {_LAND_SLOT_COUNT}")
    for time_key, offset in (
        ("morn", _LAND_SPECIES_MORN_OFFSET),
        ("day", _LAND_SPECIES_DAY_OFFSET),
        ("nite", _LAND_SPECIES_NITE_OFFSET),
    ):
        for i in range(_LAND_SLOT_COUNT):
            species_id = species_index[slots[i][time_key]]
            struct.pack_into("<H", entry, offset + i * 2, species_id)


def _write_slot_array_species(
    entry: bytearray, slots: Sequence[dict], base_offset: int, species_index: dict[str, int], capacity: int
) -> None:
    if len(slots) > capacity:
        raise ValueError(f"{len(slots)} slots given for a {capacity}-slot array at offset {base_offset:#x}")
    for i, slot in enumerate(slots):
        offset = base_offset + i * _ENCOUNTER_DATA_SLOT_SIZE + _ENCOUNTER_DATA_SLOT_SPECIES_OFFSET
        struct.pack_into("<H", entry, offset, species_index[slot["species"]])


def write_zone_encounters(rom: HeartGoldRom, zone_key: str, zone: dict) -> None:
    """Overwrite one zone's species fields in place (land morn/day/nite,
    surf, rock_smash, and old/good/super rod fishing), leaving every rate/
    level byte untouched -- `species.py`'s `randomize_wild_encounters`
    only ever reassigns species references (see that function's own
    docstring), so `zone` is expected to be `data/encounters.py`'s own
    per-zone dict shape with only `species`/`morn`/`day`/`nite` values
    possibly changed from vanilla. Headbutt encounters are not covered
    (see this module's own docstring: `route_16`/`pewter`/`azalea` have no
    raw entry here at all, and no other zone's headbutt table has been
    wired up to a ROM location yet)."""
    from data.encounter_zone_index import ENCOUNTER_ZONE_KEY_TO_RAW_INDEX
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw_index = ENCOUNTER_ZONE_KEY_TO_RAW_INDEX[zone_key]
    entry = bytearray(read_entry(rom, raw_index))

    _write_land_species(entry, zone["land"], SPECIES_KEY_TO_RAW_INDEX)
    _write_slot_array_species(
        entry, zone["surf"]["slots"], _SURF_SLOTS_OFFSET, SPECIES_KEY_TO_RAW_INDEX, _SURF_SLOT_CAPACITY
    )
    _write_slot_array_species(
        entry,
        zone["rock_smash"]["slots"],
        _ROCK_SMASH_SLOTS_OFFSET,
        SPECIES_KEY_TO_RAW_INDEX,
        _ROCK_SMASH_SLOT_CAPACITY,
    )
    _write_slot_array_species(
        entry,
        zone["fishing"]["old_rod"]["slots"],
        _OLD_ROD_SLOTS_OFFSET,
        SPECIES_KEY_TO_RAW_INDEX,
        _FISHING_SLOT_CAPACITY,
    )
    _write_slot_array_species(
        entry,
        zone["fishing"]["good_rod"]["slots"],
        _GOOD_ROD_SLOTS_OFFSET,
        SPECIES_KEY_TO_RAW_INDEX,
        _FISHING_SLOT_CAPACITY,
    )
    _write_slot_array_species(
        entry,
        zone["fishing"]["super_rod"]["slots"],
        _SUPER_ROD_SLOTS_OFFSET,
        SPECIES_KEY_TO_RAW_INDEX,
        _FISHING_SLOT_CAPACITY,
    )

    write_entry(rom, raw_index, bytes(entry))
