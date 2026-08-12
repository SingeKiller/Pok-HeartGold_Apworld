# rom/trainerdata.py
#
# Read/write access to the trainer tables: trainer stats (class, AI
# flags, usable items, party size -- trdata) and trainer parties (species/
# level/moves per party slot -- trpoke). HGSS keeps these as two separate,
# index-aligned NARCs (trainer N's stats are trdata's Nth sub-file, its
# party is trpoke's Nth sub-file).
#
# NitroFS paths a/0/5/5 (stats) and a/0/5/6 (party), verified directly
# against the real US HeartGold ROM: both readable, both parse as NARCs
# with exactly 738 sub-files -- an exact match with data/trainers.py's
# TRAINERS table.

from __future__ import annotations

import struct
from collections.abc import Sequence

from rom import HeartGoldRom

STATS_NITROFS_PATH = "a/0/5/5"
PARTY_NITROFS_PATH = "a/0/5/6"
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


# TRPOKE is a union of 4 variants depending on whether a party slot has a
# custom held item and/or custom moves, but the fixed-size prefix is
# identical in every variant, so species is always at byte offset 4.
#
# IMPORTANT: the variant is a property of the *trainer* (its trainerType
# byte), never of any individual mon. A real corruption bug (found via
# Reviewer live-verification, see NOTES.md) came from deriving stride
# per-mon instead -- always read trainerType and derive one stride for
# the whole party from it.
_LEVEL_OFFSET_WITHIN_SLOT = 2
_SPECIES_OFFSET_WITHIN_SLOT = 4
_SPECIES_FORM_MASK = 0xFC00  # upper 6 bits of the species u16 (Platinum+)
_SPECIES_ID_MASK = 0x03FF

_TRPOKE_HAS_CUSTOM_MOVES_BIT = 0b01
_TRPOKE_HAS_HELD_ITEM_BIT = 0b10
_TRPOKE_BASE_SLOT_SIZE = 8  # difficulty(1) + genderAbilityOverride(1) + level(2) + species(2) + capsule(2)
_TRPOKE_ITEM_FIELD_SIZE = 2
_TRPOKE_MOVES_FIELD_SIZE = 8  # 4 x u16


def _slot_size_for_trainer_type(trainer_type: int) -> int:
    size = _TRPOKE_BASE_SLOT_SIZE
    if trainer_type & _TRPOKE_HAS_HELD_ITEM_BIT:
        size += _TRPOKE_ITEM_FIELD_SIZE
    if trainer_type & _TRPOKE_HAS_CUSTOM_MOVES_BIT:
        size += _TRPOKE_MOVES_FIELD_SIZE
    return size


def write_party_species(rom: HeartGoldRom, trainer_id: int, party: Sequence[dict]) -> None:
    """Overwrite one trainer's party species fields in place, leaving
    every other byte (level, difficulty, held item, moves, capsule) and
    each species' own form bits (upper 6 bits, Platinum+) untouched.
    Slot count/order must match the existing entry exactly; the slot
    stride is read from the trainer's own trainerType byte."""
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    trainer_type = read_stats_entry(rom, trainer_id)[0]
    slot_size = _slot_size_for_trainer_type(trainer_type)

    entry = bytearray(read_party_entry(rom, trainer_id))
    if slot_size * len(party) > len(entry):
        raise ValueError(
            f"trainer {trainer_id}: {len(party)} mons x {slot_size}-byte slots "
            f"({slot_size * len(party)} bytes) exceeds the {len(entry)}-byte party entry"
        )

    offset = 0
    for mon in party:
        species_id = SPECIES_KEY_TO_RAW_INDEX[mon["species"]]
        existing_species = struct.unpack_from("<H", entry, offset + _SPECIES_OFFSET_WITHIN_SLOT)[0]
        form = existing_species & _SPECIES_FORM_MASK
        struct.pack_into("<H", entry, offset + _SPECIES_OFFSET_WITHIN_SLOT, (species_id & _SPECIES_ID_MASK) | form)
        offset += slot_size

    write_party_entry(rom, trainer_id, bytes(entry))


def write_party_levels(rom: HeartGoldRom, trainer_id: int, party: Sequence[dict]) -> None:
    """Overwrite one trainer's party level fields in place -- same
    slot-stride/validation rules as write_party_species, just a
    different fixed offset within each slot."""
    trainer_type = read_stats_entry(rom, trainer_id)[0]
    slot_size = _slot_size_for_trainer_type(trainer_type)

    entry = bytearray(read_party_entry(rom, trainer_id))
    if slot_size * len(party) > len(entry):
        raise ValueError(
            f"trainer {trainer_id}: {len(party)} mons x {slot_size}-byte slots "
            f"({slot_size * len(party)} bytes) exceeds the {len(entry)}-byte party entry"
        )

    offset = 0
    for mon in party:
        struct.pack_into("<H", entry, offset + _LEVEL_OFFSET_WITHIN_SLOT, mon["level"])
        offset += slot_size

    write_party_entry(rom, trainer_id, bytes(entry))
