from __future__ import annotations

import struct

from rom import HeartGoldRom

_SPECIES_ARRAY_RAM_ADDRESS = 0x02108514
_SPECIES_COUNT = 3


def _species_array_file_offset(rom: HeartGoldRom) -> int:
    return _SPECIES_ARRAY_RAM_ADDRESS - rom.arm9_ram_address


def read_starters(rom: HeartGoldRom) -> tuple[int, int, int]:
    decompressed = rom.read_main_code_decompressed()
    offset = _species_array_file_offset(rom)
    return struct.unpack_from("<III", decompressed, offset)


def write_starters(rom: HeartGoldRom, species_raw_ids: tuple[int, int, int]) -> None:
    if len(species_raw_ids) != _SPECIES_COUNT:
        raise ValueError(f"expected exactly {_SPECIES_COUNT} species ids, got {len(species_raw_ids)}")
    offset = _species_array_file_offset(rom)
    data = struct.pack("<III", *species_raw_ids)
    rom.write_main_code_region(offset, data)
