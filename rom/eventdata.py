from __future__ import annotations

from collections.abc import Sequence

from rom import HeartGoldRom

NITROFS_PATH = "a/0/3/2"
EXPECTED_ENTRY_COUNT = 491


def read_all(rom: HeartGoldRom) -> list[bytes]:
    return rom.read_narc(NITROFS_PATH).files


def write_all(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    if len(entries) != len(narc.files):
        raise ValueError(
            f"event data table has {len(narc.files)} entries, got "
            f"{len(entries)} replacement entries -- entry count must match "
            "exactly (this layer never adds/removes NARC sub-files)."
        )
    narc.files = list(entries)
    rom.write_narc(NITROFS_PATH, narc)


def read_entry(rom: HeartGoldRom, index: int) -> bytes:
    return rom.read_narc(NITROFS_PATH).files[index]


def write_entry(rom: HeartGoldRom, index: int, data: bytes) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[index] = data
    rom.write_narc(NITROFS_PATH, narc)


def entry_rom_offset(packed: bytes, index: int) -> int:
    narc_start, narc_end = HeartGoldRom.nitrofs_file_span(packed, NITROFS_PATH)
    entry_start, _entry_end = HeartGoldRom.narc_subfile_span(packed[narc_start:narc_end], index)
    return narc_start + entry_start
