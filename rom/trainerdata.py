# rom/trainerdata.py
#
# Read/write access to the trainer tables (task C13): trainer stats
# (class, AI flags, usable items, party size -- `trdata`) and trainer
# parties (species/level/moves per party slot -- `trpoke`), the two tables
# `species.py`'s trainer-party randomization (task C11) will eventually
# need patched into the ROM. HGSS keeps these as two separate, index-
# aligned NARCs (trainer N's stats are `trdata`'s Nth sub-file, its party
# is `trpoke`'s Nth sub-file) rather than one combined table.
#
# NitroFS paths: like rom/itemdata.py's item table, neither table is
# reachable at its decomp source-tree path in the retail ROM
# (`poketool/trainer/trdata.narc` / `poketool/trainer/trpoke.narc` do not
# exist in the built ROM). `ressources/Decomposition/pokeheartgold/
# filesystem.mk`'s `arc_strip_name` calls map:
#   files/poketool/trainer/trdata.narc  -> files/a/0/5/5
#   files/poketool/trainer/trpoke.narc  -> files/a/0/5/6
# i.e. the real NitroFS paths are `a/0/5/5` (stats) and `a/0/5/6` (party),
# verified directly against the real US HeartGold ROM: both readable, both
# parse as NARCs with exactly 738 sub-files -- an exact match with
# `data/trainers.py`'s `TRAINERS` table (also 738 entries, ids 0-737, see
# docs/architecture.md Spike 3), unlike rom/itemdata.py's/
# rom/speciesdata.py's own open questions about their own index<->key
# mapping. `tests/test_rom_access.py` asserts this exact-count match for
# both tables.

from __future__ import annotations

from collections.abc import Sequence

from rom import HeartGoldRom

# See this module's docstring for how these numbered paths were derived
# and verified against the real ROM.
STATS_NITROFS_PATH = "a/0/5/5"
PARTY_NITROFS_PATH = "a/0/5/6"

# Sub-file count confirmed against the real US HeartGold ROM, and matching
# `data/trainers.py`'s `TRAINERS` table exactly (see this module's own
# docstring).
EXPECTED_ENTRY_COUNT = 738


def _read_all(rom: HeartGoldRom, path: str) -> list[bytes]:
    return rom.read_narc(path).files


def _write_all(rom: HeartGoldRom, path: str, entries: Sequence[bytes], table_name: str) -> None:
    narc = rom.read_narc(path)
    if len(entries) != len(narc.files):
        raise ValueError(
            f"trainer {table_name} table has {len(narc.files)} entries, got "
            f"{len(entries)} replacement entries -- entry count must match "
            "exactly (this layer never adds/removes NARC sub-files)."
        )
    narc.files = list(entries)
    rom.write_narc(path, narc)


def read_all_stats(rom: HeartGoldRom) -> list[bytes]:
    """Return every trainer's stats entry as a raw bytes blob, one per
    NARC sub-file, in trainer-id order (see `data/trainers.py`'s `id`
    field)."""
    return _read_all(rom, STATS_NITROFS_PATH)


def write_all_stats(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    """Replace every trainer's stats entry. `entries` must have exactly as
    many elements as the table currently has."""
    _write_all(rom, STATS_NITROFS_PATH, entries, "stats")


def read_all_parties(rom: HeartGoldRom) -> list[bytes]:
    """Return every trainer's party entry as a raw bytes blob, one per
    NARC sub-file, in trainer-id order (index-aligned with
    `read_all_stats`)."""
    return _read_all(rom, PARTY_NITROFS_PATH)


def write_all_parties(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    """Replace every trainer's party entry. `entries` must have exactly as
    many elements as the table currently has."""
    _write_all(rom, PARTY_NITROFS_PATH, entries, "party")


def read_stats_entry(rom: HeartGoldRom, trainer_id: int) -> bytes:
    """Read a single trainer's stats entry by trainer id (matches
    `data/trainers.py`'s `id` field: the real NARC is index-aligned with it
    exactly, see this module's docstring)."""
    return rom.read_narc(STATS_NITROFS_PATH).files[trainer_id]


def write_stats_entry(rom: HeartGoldRom, trainer_id: int, data: bytes) -> None:
    """Replace a single trainer's stats entry by trainer id."""
    narc = rom.read_narc(STATS_NITROFS_PATH)
    narc.files[trainer_id] = data
    rom.write_narc(STATS_NITROFS_PATH, narc)


def read_party_entry(rom: HeartGoldRom, trainer_id: int) -> bytes:
    """Read a single trainer's party entry by trainer id."""
    return rom.read_narc(PARTY_NITROFS_PATH).files[trainer_id]


def write_party_entry(rom: HeartGoldRom, trainer_id: int, data: bytes) -> None:
    """Replace a single trainer's party entry by trainer id."""
    narc = rom.read_narc(PARTY_NITROFS_PATH)
    narc.files[trainer_id] = data
    rom.write_narc(PARTY_NITROFS_PATH, narc)
