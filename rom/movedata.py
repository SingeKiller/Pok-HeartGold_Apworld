from __future__ import annotations

from collections.abc import Sequence

from rom import HeartGoldRom

NITROFS_PATH = "a/0/1/1"
EXPECTED_ENTRY_COUNT = 471
ENTRY_SIZE = 16

_EFFECT_OFFSET = 0
_CATEGORY_OFFSET = 2
_POWER_OFFSET = 3
_TYPE_OFFSET = 4
_ACCURACY_OFFSET = 5
_PP_OFFSET = 6

MOVE_EFFECT_ONE_HIT_KO = 38

_OHKO_NEUTRALIZED_POWER = 60
_OHKO_NEUTRALIZED_ACCURACY = 100

TYPE_NAME_TO_ID: dict[str, int] = {
    "normal": 0,
    "fighting": 1,
    "flying": 2,
    "poison": 3,
    "ground": 4,
    "rock": 5,
    "bug": 6,
    "ghost": 7,
    "steel": 8,
    "mystery": 9,
    "fire": 10,
    "water": 11,
    "grass": 12,
    "electric": 13,
    "psychic": 14,
    "ice": 15,
    "dragon": 16,
    "dark": 17,
}

CATEGORY_NAME_TO_ID: dict[str, int] = {
    "physical": 0,
    "special": 1,
    "status": 2,
}


def read_all(rom: HeartGoldRom) -> list[bytes]:
    return rom.read_narc(NITROFS_PATH).files


def write_all(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    if len(entries) != len(narc.files):
        raise ValueError(
            f"move data table has {len(narc.files)} entries, got "
            f"{len(entries)} replacement entries -- entry count must match "
            "exactly (this layer never adds/removes NARC sub-files)."
        )
    narc.files = list(entries)
    rom.write_narc(NITROFS_PATH, narc)


def read_entry(rom: HeartGoldRom, move_id: int) -> bytes:
    return rom.read_narc(NITROFS_PATH).files[move_id]


def write_entry(rom: HeartGoldRom, move_id: int, data: bytes) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[move_id] = data
    rom.write_narc(NITROFS_PATH, narc)


def write_combat_stats(rom: HeartGoldRom, move_key: str, *, power: int, accuracy: int, pp: int) -> None:
    from data.moves import MOVES

    move_id = MOVES[move_key]["id"]
    entry = bytearray(read_entry(rom, move_id))
    if len(entry) != ENTRY_SIZE:
        raise ValueError(f"move {move_key!r} (id {move_id}) entry is {len(entry)} bytes, expected {ENTRY_SIZE}")
    entry[_POWER_OFFSET] = power
    entry[_ACCURACY_OFFSET] = accuracy
    entry[_PP_OFFSET] = pp
    write_entry(rom, move_id, bytes(entry))


def write_type(rom: HeartGoldRom, move_key: str, move_type: int) -> None:
    from data.moves import MOVES

    move_id = MOVES[move_key]["id"]
    entry = bytearray(read_entry(rom, move_id))
    if len(entry) != ENTRY_SIZE:
        raise ValueError(f"move {move_key!r} (id {move_id}) entry is {len(entry)} bytes, expected {ENTRY_SIZE}")
    entry[_TYPE_OFFSET] = move_type
    write_entry(rom, move_id, bytes(entry))


def write_category(rom: HeartGoldRom, move_key: str, category: int) -> None:
    from data.moves import MOVES

    move_id = MOVES[move_key]["id"]
    entry = bytearray(read_entry(rom, move_id))
    if len(entry) != ENTRY_SIZE:
        raise ValueError(f"move {move_key!r} (id {move_id}) entry is {len(entry)} bytes, expected {ENTRY_SIZE}")
    entry[_CATEGORY_OFFSET] = category
    write_entry(rom, move_id, bytes(entry))


def read_category(rom: HeartGoldRom, move_key: str) -> int:
    from data.moves import MOVES

    move_id = MOVES[move_key]["id"]
    entry = read_entry(rom, move_id)
    return entry[_CATEGORY_OFFSET]


def read_effect(rom: HeartGoldRom, move_key: str) -> int:
    from data.moves import MOVES

    move_id = MOVES[move_key]["id"]
    entry = read_entry(rom, move_id)
    return int.from_bytes(entry[_EFFECT_OFFSET : _EFFECT_OFFSET + 2], "little")


def write_ohko_neutralization(rom: HeartGoldRom, move_key: str) -> None:
    from data.moves import MOVES

    move_id = MOVES[move_key]["id"]
    entry = bytearray(read_entry(rom, move_id))
    if len(entry) != ENTRY_SIZE:
        raise ValueError(f"move {move_key!r} (id {move_id}) entry is {len(entry)} bytes, expected {ENTRY_SIZE}")
    entry[_EFFECT_OFFSET : _EFFECT_OFFSET + 2] = (0).to_bytes(2, "little")
    entry[_POWER_OFFSET] = _OHKO_NEUTRALIZED_POWER
    entry[_ACCURACY_OFFSET] = _OHKO_NEUTRALIZED_ACCURACY
    write_entry(rom, move_id, bytes(entry))


def read_combat_stats(rom: HeartGoldRom, move_key: str) -> tuple[int, int, int, int]:
    from data.moves import MOVES

    move_id = MOVES[move_key]["id"]
    entry = read_entry(rom, move_id)
    power = entry[_POWER_OFFSET]
    move_type = entry[_TYPE_OFFSET]
    accuracy = entry[_ACCURACY_OFFSET]
    pp = entry[_PP_OFFSET]
    return power, move_type, accuracy, pp
