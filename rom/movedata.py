# rom/movedata.py
#
# Read/write access to the move data table (task M4.5): power/accuracy/PP
# for the move-stat randomizer -- `species.py`'s move-stat randomization
# writes here, keeping `type`/`effect`/`category` untouched (see this
# module's own `write_combat_stats` docstring for why).
#
# NitroFS path: `ressources/Decomposition/pokeheartgold/filesystem.mk`'s
# `arc_strip_name` maps `files/poketool/waza/waza_tbl.narc` ->
# `files/a/0/1/1`, verified directly against the real US HeartGold ROM:
# readable, parses as a NARC with exactly 471 sub-files, 16 bytes each.
#
# `data/moves.py`'s `id` field is directly usable as this NARC's raw
# sub-file index -- unlike `data/species.py` (see
# `data/species_index.py`'s own generation, `docs/architecture.md`'s
# "## M4.5" section), no separate index-mapping table was needed here:
# spot-checked four moves (tackle/thunderbolt/flamethrower/pound) by
# reading `waza_tbl.narc[MOVES[key]["id"]]` directly against the real ROM
# and comparing power/accuracy/pp/type -- all four matched exactly. The
# raw table has 471 entries vs `data/moves.py`'s 467 (index 0 is very
# likely a "no move" placeholder plus a few engine-reserved slots at the
# tail, mirroring the species table's own shape, but this was not
# independently confirmed since no id-based write ever needs to touch
# those unused indices).
#
# Struct (Decomposition `include/move.h`, `MoveTbl`, 16 bytes, no padding
# ambiguity -- every member is 2-byte-or-smaller):
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

_POWER_OFFSET = 3
_TYPE_OFFSET = 4
_ACCURACY_OFFSET = 5
_PP_OFFSET = 6


def read_all(rom: HeartGoldRom) -> list[bytes]:
    """Return every move's entry as a raw bytes blob, one per NARC
    sub-file, in on-disk order (index-usable directly as `data/moves.py`'s
    `id` field, see this module's own docstring)."""
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
    """Read a single move's entry by its raw NARC sub-file index (`data/
    moves.py`'s `id` field)."""
    return rom.read_narc(NITROFS_PATH).files[move_id]


def write_entry(rom: HeartGoldRom, move_id: int, data: bytes) -> None:
    """Replace a single move's entry by its raw NARC sub-file index."""
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[move_id] = data
    rom.write_narc(NITROFS_PATH, narc)


def write_combat_stats(rom: HeartGoldRom, move_key: str, *, power: int, accuracy: int, pp: int) -> None:
    """Overwrite one move's `power`/`accuracy`/`pp` bytes in place, leaving
    every other byte of its entry (crucially `type`, at offset 4) untouched
    -- the move-stat randomizer's own documented contract ("conservation
    du Type"): only power/PP/accuracy are randomized, the move's type
    never changes."""
    from data.moves import MOVES

    move_id = MOVES[move_key]["id"]
    entry = bytearray(read_entry(rom, move_id))
    if len(entry) != ENTRY_SIZE:
        raise ValueError(f"move {move_key!r} (id {move_id}) entry is {len(entry)} bytes, expected {ENTRY_SIZE}")
    entry[_POWER_OFFSET] = power
    entry[_ACCURACY_OFFSET] = accuracy
    entry[_PP_OFFSET] = pp
    write_entry(rom, move_id, bytes(entry))


def read_combat_stats(rom: HeartGoldRom, move_key: str) -> tuple[int, int, int, int]:
    """Read `(power, type, accuracy, pp)` for `move_key` directly from the
    ROM -- mainly for tests/verification, `write_combat_stats` is the
    normal write path."""
    from data.moves import MOVES

    move_id = MOVES[move_key]["id"]
    entry = read_entry(rom, move_id)
    power = entry[_POWER_OFFSET]
    move_type = entry[_TYPE_OFFSET]
    accuracy = entry[_ACCURACY_OFFSET]
    pp = entry[_PP_OFFSET]
    return power, move_type, accuracy, pp
