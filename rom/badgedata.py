# rom/badgedata.py
#
# Neutralizes the vanilla `GiveBadge <badge>` script call at each of the 16
# gym scripts (task "Badges comme vrais items AP", 2026-08-15). Badges are
# now real, tradeable AP items (data_gen/items.toml's badge_* entries,
# data/locations.py's type = 'badge' locations) delivered exclusively
# through the normal remote-item mechanism (client.py writes the matching
# bit into PlayerProfile.johtoBadges/kantoBadges on receipt) -- so the
# vanilla local grant must be disabled everywhere, unconditionally, or
# defeating a gym Leader would *also* hand over that Leader's own vanilla
# badge for free, regardless of what the fill algorithm actually placed at
# that location (a real double-delivery bug, the same class already fixed
# for npc_gift in task M1.2/NOTES.md, just for a location type with no
# per-seed substitution of its own).
#
# `GiveBadge badge` compiles to a flat 4-byte instruction (asm/macros/
# script.inc): `.short 295` (opcode) + `.short badge` (badge.h's own
# BADGE_ZEPHYR=0..BADGE_EARTH=15 index) -- verified live against both the
# HeartGold and SoulSilver US ROMs (identical offsets on both; the 16 gym
# scripts do not differ between versions). Neutralized by overwriting both
# halves with opcode 0 (`ScrCmd_Nop`, gScriptCmdTable's own first entry,
# confirmed via the decomp to take no operand bytes and do nothing) --
# preserves the script's total byte length exactly, so no other
# instruction's offset/jump target shifts.
#
# The `CheckBadge <badge>, var` guard at the top of each gym script (used
# to skip the whole battle-and-dialogue sequence on a repeat visit) is
# deliberately left untouched: once GiveBadge no longer fires locally,
# CheckBadge naturally reflects whether the player has genuinely received
# that badge_* item yet (from this gym, from a different location, or from
# another player's game) -- exactly the semantics a randomized badge needs
# (re-battle the Leader on every revisit until the real badge_* item has
# actually been received), not something a separate patch has to force.
#
# NitroFS path: same NARC as rom/eventscriptdata.py, scr_seq.narc -> a/0/1/2.

from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

GIVEBADGE_OPCODE = 295
NOP_OPCODE = 0

# badge name (data_gen/rules.toml's own [badges] table key) -> (scr_seq.narc
# sub-file index, byte offset of the GiveBadge instruction's own opcode).
# One site each -- confirmed unique per narc sub-file by the derivation
# scan (searched for the GiveBadge opcode immediately followed by that
# exact badge's own index; every one of the 16 matched exactly once).
#
# rising (Clair) is the one badge whose GiveBadge site is NOT in the same
# script as her TrainerBattle: she is fought at Blackthorn Gym
# (scr_seq_0943_T30GYM0101.s, TRAINER_LEADER_CLAIR_CLAIR) but the badge
# itself is only granted later, after a separate puzzle-completion
# cutscene at Dragon's Den Shrine (scr_seq_0112_D44R0103.s) -- both
# decomp-confirmed; data_gen/locations.toml's badge-section header has the
# full writeup. TABLE below only needs the GiveBadge site (patch target);
# data_gen/locations.toml's own `trainer` field on dragons_den_shrine_badge
# points at the (different) TrainerBattle location for check detection.
TABLE: dict[str, tuple[int, int]] = {
    "zephyr": (859, 230),
    "hive": (869, 283),
    "plain": (886, 431),
    "fog": (922, 372),
    "storm": (877, 121),
    "mineral": (913, 426),
    "glacier": (932, 270),
    "rising": (112, 618),
    "boulder": (752, 314),
    "cascade": (760, 703),
    "thunder": (778, 827),
    "rainbow": (786, 326),
    "soul": (809, 1817),
    "marsh": (829, 200),
    "volcano": (15, 311),
    "earth": (743, 164),
}


class BadgeDataError(Exception):
    """Base class for every error this module raises."""


def read_givebadge_operand(rom: HeartGoldRom, narc_index: int, offset: int) -> tuple[int, int]:
    """Read the (opcode, badge index) pair currently sitting at a given
    (scr_seq.narc sub-file index, byte offset) pair -- see TABLE. Exposed
    for verification/testing, not used in the normal patch path."""
    narc = rom.read_narc(NITROFS_PATH)
    blob = narc.files[narc_index]
    return struct.unpack_from("<HH", blob, offset)


def write_badge_neutralized(rom: HeartGoldRom, narc_index: int, offset: int) -> None:
    """Overwrite a 4-byte `GiveBadge <badge>` instruction in place with two
    Nop (opcode 0) instructions -- see this module's own docstring."""
    narc = rom.read_narc(NITROFS_PATH)
    blob = bytearray(narc.files[narc_index])
    struct.pack_into("<HH", blob, offset, NOP_OPCODE, NOP_OPCODE)
    narc.files[narc_index] = bytes(blob)
    rom.write_narc(NITROFS_PATH, narc)


def write_all_badges_neutralized(rom: HeartGoldRom) -> None:
    """Neutralize every one of the 16 gym scripts' own GiveBadge call.
    Unconditional -- unlike ground_item/npc_gift substitution, this does
    not depend on this seed's fill result at all, so it always runs
    exactly the same way regardless of what item ends up at any given
    badge location."""
    for narc_index, offset in TABLE.values():
        write_badge_neutralized(rom, narc_index, offset)
