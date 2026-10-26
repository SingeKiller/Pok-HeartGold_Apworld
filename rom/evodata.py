from __future__ import annotations

import struct
from collections.abc import Sequence

from rom import HeartGoldRom

NITROFS_PATH = "a/0/3/4"
EXPECTED_ENTRY_COUNT = 508
ENTRY_SIZE = 44
MAX_EVOS_PER_SPECIES = 7
_EVOLUTION_STRUCT_SIZE = 6


def read_all(rom: HeartGoldRom) -> list[bytes]:
    return rom.read_narc(NITROFS_PATH).files


def write_all(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    if len(entries) != len(narc.files):
        raise ValueError(
            f"evolution table has {len(narc.files)} entries, got "
            f"{len(entries)} replacement entries -- entry count must match "
            "exactly (this layer never adds/removes NARC sub-files)."
        )
    narc.files = list(entries)
    rom.write_narc(NITROFS_PATH, narc)


def read_entry(rom: HeartGoldRom, raw_index: int) -> bytes:
    return rom.read_narc(NITROFS_PATH).files[raw_index]


def write_entry(rom: HeartGoldRom, raw_index: int, data: bytes) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[raw_index] = data
    rom.write_narc(NITROFS_PATH, narc)


def encode_evolutions(evolutions: Sequence[tuple[int, int, int]]) -> bytes:
    if len(evolutions) > MAX_EVOS_PER_SPECIES:
        raise ValueError(f"{len(evolutions)} evolutions given, a species can have at most {MAX_EVOS_PER_SPECIES}")

    out = bytearray(MAX_EVOS_PER_SPECIES * _EVOLUTION_STRUCT_SIZE)
    for i, (method, param, target) in enumerate(evolutions):
        offset = i * _EVOLUTION_STRUCT_SIZE
        struct.pack_into("<HHH", out, offset, method, param, target)
    return bytes(out)


def write_species_evolutions(rom: HeartGoldRom, raw_index: int, evolutions: Sequence[tuple[int, int, int]]) -> None:
    existing = bytearray(read_entry(rom, raw_index))
    new_records = encode_evolutions(evolutions)
    existing[: len(new_records)] = new_records
    write_entry(rom, raw_index, bytes(existing))


def read_species_evolutions(rom: HeartGoldRom, raw_index: int) -> list[tuple[int, int, int]]:
    entry = read_entry(rom, raw_index)
    result = []
    for i in range(MAX_EVOS_PER_SPECIES):
        offset = i * _EVOLUTION_STRUCT_SIZE
        method, param, target = struct.unpack_from("<HHH", entry, offset)
        if method == 0 and param == 0 and target == 0:
            continue
        result.append((method, param, target))
    return result
