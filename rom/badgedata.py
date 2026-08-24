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
# scripts do not differ between versions). For the 6 badges NOT in
# BADGE_SENTINEL_INJECTIONS below (their check-detection instead reuses a
# hand-verified, corpus-unique flag already present elsewhere in that same
# Leader's win branch -- see location_flags.py's `_SYNTHETIC_ID_FLAG_
# OVERRIDES`, "type = 'badge' overrides" section), this GiveBadge site is
# simply neutralized: both halves overwritten with opcode 0 (`ScrCmd_Nop`,
# gScriptCmdTable's own first entry, confirmed via the decomp to take no
# operand bytes and do nothing). For the other 10 (BADGE_SENTINEL_
# INJECTIONS), the same 4 bytes are instead overwritten with a brand-new
# `SetFlag <flag_id>` instruction (opcode 30, also exactly 4 bytes --
# asm/macros/script.inc's own `.macro SetFlag`) -- see BADGE_SENTINEL_
# INJECTIONS's own docstring for why. Either way, the instruction's total
# byte length is unchanged (4 bytes in, 4 bytes out), so no other
# instruction's offset/jump target shifts.
#
# The `CheckBadge <badge>, var` guard at the top of each gym script (used
# to skip the whole battle-and-dialogue sequence on a repeat visit) used to
# be left untouched here, on the theory that it would then naturally read
# "has this player received that badge_* item yet". That was wrong in a
# multiworld and is fixed by a separate module as of 2026-08-19: see
# rom/badgegatedata.py, which rewrites each of those guards to test the
# very sentinel flag BADGE_SENTINEL_INJECTIONS below writes. The two
# patches are VERSION-COUPLED and must be applied to the same ROM, in that
# order -- patch_gen.py wires them back to back.
#
# NitroFS path: same NARC as rom/eventscriptdata.py, scr_seq.narc -> a/0/1/2.

from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

GIVEBADGE_OPCODE = 295
NOP_OPCODE = 0
SETFLAG_OPCODE = 30

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


# badge name -> brand-new sentinel flag id, for the 10 gym Leaders whose
# win branch has no safe *pre-existing* flag to reuse (task "Fix the
# remaining 10 gym badges", 2026-08-18 -- see location_flags.py's
# `_SYNTHETIC_ID_FLAG_OVERRIDES` "type = 'badge' overrides" section and
# `build_badge_index_to_sentinel_flag_id`'s own docstring for the full
# archaeology on why: every candidate in these 10 scripts either collides
# with another location's own check, e.g. FLAG_UNK_998, corpus-wide reused
# by 12 unrelated scripts, or is claimed by another trainer's own phone-
# rematch SetTrainerFlag).
#
# Instead of searching for a pre-existing flag, this injects a brand new
# one directly into that Leader's own `GiveBadge <badge>` instruction
# (TABLE above): the exact same 4 bytes `write_all_badges_neutralized`
# already overwrites with NOP+NOP for the other 6 gyms get overwritten with
# `SetFlag <flag_id>` (opcode 30, asm/macros/script.inc's own `.macro
# SetFlag`, also exactly 4 bytes: `.short 30; .short flag`) instead. This
# simultaneously (a) still neutralizes the vanilla local GiveBadge call --
# it's no longer a GiveBadge instruction at all, same double-delivery fix
# as every other badge -- and (b) writes a brand-new, guaranteed one-shot
# "this Leader was just genuinely beaten" signal, at the exact same
# trigger point (that Leader's own real win branch, unconditional) GiveBadge
# itself used to fire at.
#
# Deliberately NOT an ARM-hook/jump injection: docs/scope.md's "Shop
# randomization" section documents that approach as having crashed live
# twice and been abandoned there. This is a plain 4-byte overwrite of one
# existing script instruction with another existing, common opcode
# (SetFlag is used 63+ times elsewhere in the game already), using the
# exact same `struct.pack_into("<HH", blob, offset, opcode, operand)`
# mechanism `write_badge_neutralized` below already uses safely today --
# no ARM code append, no jump/hook, no script size change at all.
#
# The 10 flag ids themselves sit at the very top of the valid flag range
# (include/constants/flags.h's NUM_FLAGS = 2912, i.e. ids 0-2911 /
# 0x0-0xB5F) -- FLAG_UNK_B50 through FLAG_UNK_B59, the last 10 ids in the
# whole array, an unused tail block. Confirmed completely unreferenced
# anywhere in the entire decomp source tree (scripts AND C code -- 0 hits
# for any of the 10 outside their own #define in flags.h) and not claimed
# anywhere in this project's own code (checked against
# `_SYNTHETIC_ID_FLAG_OVERRIDES`, `_STATIC_POKEMON_FLAG_IDS`, the full
# TRAINER_FLAG_BASE..TRAINER_FLAG_BASE+max_trainer_id reserved band, and
# the HIDDEN_ITEMS_FLAG_BASE band -- and against each other, no overlap).
BADGE_SENTINEL_INJECTIONS: dict[str, int] = {
    "hive": 0xB50,  # azalea_gym_badge (Bugsy)
    "fog": 0xB51,  # ecruteak_gym_badge (Morty)
    "storm": 0xB52,  # cianwood_gym_badge (Chuck)
    "mineral": 0xB53,  # olivine_gym_badge (Jasmine)
    "glacier": 0xB54,  # mahogany_gym_leader_room_badge (Pryce)
    "boulder": 0xB55,  # pewter_gym_badge (Brock)
    "cascade": 0xB56,  # cerulean_gym_badge (Misty)
    "rainbow": 0xB57,  # celadon_gym_badge (Erika)
    "soul": 0xB58,  # fuchsia_gym_badge (Janine)
    "marsh": 0xB59,  # saffron_gym_badge (Sabrina)
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


def write_badge_sentinel_injected(rom: HeartGoldRom, narc_index: int, offset: int, flag_id: int) -> None:
    """Overwrite a 4-byte `GiveBadge <badge>` instruction in place with a
    `SetFlag <flag_id>` instruction (opcode 30) -- see BADGE_SENTINEL_
    INJECTIONS's own docstring. Neutralizes the vanilla local grant (same
    as write_badge_neutralized) while also injecting a brand-new one-shot
    "just beaten" sentinel at the exact same trigger point."""
    narc = rom.read_narc(NITROFS_PATH)
    blob = bytearray(narc.files[narc_index])
    struct.pack_into("<HH", blob, offset, SETFLAG_OPCODE, flag_id)
    narc.files[narc_index] = bytes(blob)
    rom.write_narc(NITROFS_PATH, narc)


def write_all_badges_neutralized(rom: HeartGoldRom) -> None:
    """Neutralize every one of the 16 gym scripts' own GiveBadge call.
    Unconditional -- unlike ground_item/npc_gift substitution, this does
    not depend on this seed's fill result at all, so it always runs
    exactly the same way regardless of what item ends up at any given
    badge location.

    The 6 badges with a reused pre-existing sentinel flag (not in
    BADGE_SENTINEL_INJECTIONS) get the plain NOP+NOP neutralization; the
    10 badges in BADGE_SENTINEL_INJECTIONS get a `SetFlag <flag_id>`
    instruction instead, which neutralizes the vanilla grant AND injects
    that badge's new sentinel flag in the same 4-byte write -- see
    BADGE_SENTINEL_INJECTIONS's own docstring."""
    for badge_name, (narc_index, offset) in TABLE.items():
        flag_id = BADGE_SENTINEL_INJECTIONS.get(badge_name)
        if flag_id is not None:
            write_badge_sentinel_injected(rom, narc_index, offset, flag_id)
        else:
            write_badge_neutralized(rom, narc_index, offset)
