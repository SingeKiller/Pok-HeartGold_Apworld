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
    return _read_all(rom, STATS_NITROFS_PATH)


def write_all_stats(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    _write_all(rom, STATS_NITROFS_PATH, entries, "stats")


def read_all_parties(rom: HeartGoldRom) -> list[bytes]:
    return _read_all(rom, PARTY_NITROFS_PATH)


def write_all_parties(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    _write_all(rom, PARTY_NITROFS_PATH, entries, "party")


def read_stats_entry(rom: HeartGoldRom, trainer_id: int) -> bytes:
    return rom.read_narc(STATS_NITROFS_PATH).files[trainer_id]


def write_stats_entry(rom: HeartGoldRom, trainer_id: int, data: bytes) -> None:
    narc = rom.read_narc(STATS_NITROFS_PATH)
    narc.files[trainer_id] = data
    rom.write_narc(STATS_NITROFS_PATH, narc)


def read_party_entry(rom: HeartGoldRom, trainer_id: int) -> bytes:
    return rom.read_narc(PARTY_NITROFS_PATH).files[trainer_id]


def write_party_entry(rom: HeartGoldRom, trainer_id: int, data: bytes) -> None:
    narc = rom.read_narc(PARTY_NITROFS_PATH)
    narc.files[trainer_id] = data
    rom.write_narc(PARTY_NITROFS_PATH, narc)


_LEVEL_OFFSET_WITHIN_SLOT = 2
_SPECIES_OFFSET_WITHIN_SLOT = 4
_SPECIES_FORM_MASK = 0xFC00
_SPECIES_ID_MASK = 0x03FF

_TRPOKE_HAS_CUSTOM_MOVES_BIT = 0b01
_TRPOKE_HAS_HELD_ITEM_BIT = 0b10
_TRPOKE_BASE_SLOT_SIZE = 8
_TRPOKE_ITEM_FIELD_SIZE = 2
_TRPOKE_MOVES_FIELD_SIZE = 8


def _slot_size_for_trainer_type(trainer_type: int) -> int:
    size = _TRPOKE_BASE_SLOT_SIZE
    if trainer_type & _TRPOKE_HAS_HELD_ITEM_BIT:
        size += _TRPOKE_ITEM_FIELD_SIZE
    if trainer_type & _TRPOKE_HAS_CUSTOM_MOVES_BIT:
        size += _TRPOKE_MOVES_FIELD_SIZE
    return size


def write_party_species(rom: HeartGoldRom, trainer_id: int, party: Sequence[dict]) -> None:
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


def trainer_has_custom_moves(rom: HeartGoldRom, trainer_id: int) -> bool:
    return bool(read_stats_entry(rom, trainer_id)[0] & _TRPOKE_HAS_CUSTOM_MOVES_BIT)


def write_party_moves(rom: HeartGoldRom, trainer_id: int, movesets: Sequence[Sequence[int] | None]) -> None:
    trainer_type = read_stats_entry(rom, trainer_id)[0]
    if not trainer_type & _TRPOKE_HAS_CUSTOM_MOVES_BIT:
        raise ValueError(f"trainer {trainer_id} has no custom moves to write")
    slot_size = _slot_size_for_trainer_type(trainer_type)
    moves_offset = _SPECIES_OFFSET_WITHIN_SLOT + 2
    if trainer_type & _TRPOKE_HAS_HELD_ITEM_BIT:
        moves_offset += _TRPOKE_ITEM_FIELD_SIZE

    entry = bytearray(read_party_entry(rom, trainer_id))
    if slot_size * len(movesets) > len(entry):
        raise ValueError(
            f"trainer {trainer_id}: {len(movesets)} mons x {slot_size}-byte slots "
            f"({slot_size * len(movesets)} bytes) exceeds the {len(entry)}-byte party entry"
        )
    for index, moves in enumerate(movesets):
        if moves is None:
            continue
        if len(moves) > 4:
            raise ValueError(f"trainer {trainer_id} slot {index}: more than 4 moves")
        padded = list(moves) + [0] * (4 - len(moves))
        struct.pack_into("<4H", entry, index * slot_size + moves_offset, *padded)
    write_party_entry(rom, trainer_id, bytes(entry))


def write_party_levels(rom: HeartGoldRom, trainer_id: int, party: Sequence[dict]) -> None:
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
