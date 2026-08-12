# rom/movedata.py
#
# Read/write access to the move data table: power/accuracy/PP for the
# move-stat randomizer -- species.py's move-stat randomization writes
# here, keeping type/effect/category untouched.
#
# NitroFS path a/0/1/1 (waza_tbl.narc), verified directly against the
# real US HeartGold ROM: readable, parses as a NARC with exactly 471
# sub-files, 16 bytes each.
#
# data/moves.py's id field is directly usable as this NARC's raw sub-file
# index -- spot-checked four moves (tackle/thunderbolt/flamethrower/
# pound) against the real ROM, all matched exactly. The raw table has 471
# entries vs data/moves.py's 467 (index 0 is very likely a "no move"
# placeholder plus a few engine-reserved slots, not independently
# confirmed since no id-based write ever touches those).
#
# Struct (include/move.h, MoveTbl, 16 bytes, no padding ambiguity):
#   0x0 u16 effect
#   0x2 u8  category
#   0x3 u8  power
#   0x4 u8  type
#   0x5 u8  accuracy
#   0x6 u8  pp
#   0x7 u8  effectChance
#   0x8 u16 range
#   0xA s8  priority
#   0xB u8  unkB
#   0xC u8  unkC
#   0xD u8  contestType
#   0xE u16 unk_E

from __future__ import annotations

from collections.abc import Sequence

from rom import HeartGoldRom

NITROFS_PATH = "a/0/1/1"
EXPECTED_ENTRY_COUNT = 471
ENTRY_SIZE = 16

_EFFECT_OFFSET = 0
_POWER_OFFSET = 3
_TYPE_OFFSET = 4
_ACCURACY_OFFSET = 5
_PP_OFFSET = 6

# Live-verified against the real HeartGold ROM: Guillotine (id 12), Horn
# Drill (32), Fissure (90) and Sheer Cold (329) all read effect==38,
# power==1, accuracy==30 -- power is ignored by the battle engine for
# this effect (an instant KO check runs instead).
MOVE_EFFECT_ONE_HIT_KO = 38

# disable_ohko_moves's chosen neutralization recipe -- see NOTES.md.
_OHKO_NEUTRALIZED_POWER = 60
_OHKO_NEUTRALIZED_ACCURACY = 100

# include/constants/pokemon.h's TYPE_* constants -- the raw byte this
# table's type field (offset 4) uses. TYPE_NONE (255) is a species-table
# sentinel, never a real move type, not included.
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
    "mystery": 9,  # "???" -- Gen IV Curse's real vanilla type, never a randomization target
    "fire": 10,
    "water": 11,
    "grass": 12,
    "electric": 13,
    "psychic": 14,
    "ice": 15,
    "dragon": 16,
    "dark": 17,
}


def read_all(rom: HeartGoldRom) -> list[bytes]:
    """Every move's entry as a raw bytes blob, in on-disk order
    (index-usable directly as data/moves.py's id field)."""
    return rom.read_narc(NITROFS_PATH).files


def write_all(rom: HeartGoldRom, entries: Sequence[bytes]) -> None:
    """Replace every move's entry. `entries` must have exactly as many
    elements as the table currently has."""
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
    """Read a single move's entry by its raw NARC sub-file index
    (data/moves.py's id field)."""
    return rom.read_narc(NITROFS_PATH).files[move_id]


def write_entry(rom: HeartGoldRom, move_id: int, data: bytes) -> None:
    """Replace a single move's entry by its raw NARC sub-file index."""
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[move_id] = data
    rom.write_narc(NITROFS_PATH, narc)


def write_combat_stats(rom: HeartGoldRom, move_key: str, *, power: int, accuracy: int, pp: int) -> None:
    """Overwrite one move's power/accuracy/pp bytes in place, leaving
    every other byte (crucially type, at offset 4) untouched."""
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
    """Overwrite one move's type byte in place, leaving power/accuracy/pp
    and everything else untouched -- for randomize_move_types
    (species.py)."""
    from data.moves import MOVES

    move_id = MOVES[move_key]["id"]
    entry = bytearray(read_entry(rom, move_id))
    if len(entry) != ENTRY_SIZE:
        raise ValueError(f"move {move_key!r} (id {move_id}) entry is {len(entry)} bytes, expected {ENTRY_SIZE}")
    entry[_TYPE_OFFSET] = move_type
    write_entry(rom, move_id, bytes(entry))


def read_effect(rom: HeartGoldRom, move_key: str) -> int:
    """Read one move's raw effect u16 (offset 0) -- mainly for tests/
    verification; write_combat_stats/write_type never touch this field."""
    from data.moves import MOVES

    move_id = MOVES[move_key]["id"]
    entry = read_entry(rom, move_id)
    return int.from_bytes(entry[_EFFECT_OFFSET : _EFFECT_OFFSET + 2], "little")


def write_ohko_neutralization(rom: HeartGoldRom, move_key: str) -> None:
    """Neutralize one OHKO move (disable_ohko_moves, species.py) in
    place: effect=0 (drops the instant-KO check), power=60, accuracy=100.
    category/type/pp and every other byte are left exactly as vanilla.
    Clearing effect alone would leave a dead 1-power/30%-accuracy slot
    (both sentinels the battle engine ignores for this effect) -- 60/100
    makes it an ordinary move instead, no leftover RNG landmine."""
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
    """Read (power, type, accuracy, pp) for move_key directly from the
    ROM -- mainly for tests/verification."""
    from data.moves import MOVES

    move_id = MOVES[move_key]["id"]
    entry = read_entry(rom, move_id)
    power = entry[_POWER_OFFSET]
    move_type = entry[_TYPE_OFFSET]
    accuracy = entry[_ACCURACY_OFFSET]
    pp = entry[_PP_OFFSET]
    return power, move_type, accuracy, pp
