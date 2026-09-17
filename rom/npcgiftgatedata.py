# rom/npcgiftgatedata.py
#
# Fixes a real bug (player report, 2026-08-18): 8 npc_gift locations gate
# their own give-item script branch on possessing the *vanilla* original
# item (`HasItem`/`GetItemQuantity` against e.g. ITEM_BLUE_CARD), not on a
# savedata flag. rom/npcgiftdata.py's substitution only ever rewrites the
# item id/quantity operands of the actual `GiveItemNoCheck` call -- it never
# touches this separate gate check earlier in the same script. Once the
# item handed out here is a different, substituted AP item, the player
# never actually holds the vanilla item id the gate tests for, so the gate
# always reads "don't have it yet" and the NPC re-grants the item on every
# single interaction, forever (confirmed root cause, all 8 sites read below
# from the real decomp source).
#
# Fix: overwrite each gate's own `HasItem`/`GetItemQuantity` + `Compare` +
# `GoToIf*` instruction triple in place with a brand-new one-time flag gate
# (`CheckFlag`/`GoToIf`/`SetFlag`, the same primitives rom/badgedata.py
# already trusts for its own sentinel-flag injection), reusing the exact
# byte span the old triple occupied -- no script growth, so no other
# instruction's offset or jump target anywhere else in the file shifts.
# NitroFS path: same NARC as rom/eventscriptdata.py/rom/npcgiftdata.py,
# scr_seq.narc -> a/0/1/2.
#
# Three site shapes (asm/macros/script.inc's own macro definitions):
#
# Group A (6 sites since the Copycat moved to Group C): the *old* check jumps to `orig_target` when
# the player already has the vanilla item (skip-the-give branch); falling
# through means "don't have it yet, go on to actually give it". The new
# check preserves that exact shape: `CheckFlag`+`GoToIf(TRUE, orig_target)`
# (11 bytes, matches `GoToIfSet`'s own expansion) reproduces "already
# redeemed -> skip", then `SetFlag` (4 bytes) marks it redeemed right on
# the fall-through path (the one that's about to actually run the give
# sequence), padded out to the old triple's exact original byte length
# with `Noop` (opcode 0, 2 bytes each, asm/macros/script.inc's own
# `.macro Noop`) so nothing after this block moves.
#
# Group B (celadon_game_corner_coin_case only): the old check has the
# *opposite* polarity -- it jumps *into* the give branch when the player
# does NOT have the vanilla item, and falls through to an unrelated
# "you already have one" branch otherwise. Preserving that exact shape
# needs one more instruction than Group A's spare bytes allow, so this
# site instead uses `CheckFlag`+`GoToIf(TRUE, skip_target)` (jump to the
# original *fall-through* address when already redeemed) then `SetFlag`
# plus an explicit `GoTo(give_target)` (6 bytes, `.macro GoTo`) to reach
# the original *jump* target the first time -- still exactly the old
# triple's original byte length, just re-ordered instead of padded.
#
# Known accepted trade-off (both groups): `SetFlag` runs as soon as the
# gate decides to proceed to the give branch, before that branch's own
# `GoToIfNoItemSpace` bag-space check. A player whose Bag happens to be
# full on their first visit would still get flagged as "redeemed" even
# though nothing was actually granted, and making Bag space afterward
# would not re-open this gate. Same class of accepted minor trade-off as
# rom/startlocation.py's own "walk back out" note -- not solvable without
# growing the script (out of scope here, no real player report of it yet).
#
# Group C (the Pass chain, 2026-09-17): a Pass gate whose fall-through is
# NOT the give branch, so Group A's "SetFlag on fall-through" is wrong
# there. Both sites test `GetItemQuantity ITEM_PASS` to mean "the Copycat
# already traded", and the Pass is an AP item that can arrive at any time:
#
#   - Copycat (scr_seq_0841_T11R0802.s:41): the fall-through goes on to the
#     Lost Item test and to the first-talk dialogue that sets FLAG_UNK_119.
#     She was in Group A until this fix, which set 0xB4E on that first talk
#     (always before the Lost Item exists), so every later talk jumped to
#     `_0125` and the Pass location could never be checked.
#   - Fan Club chairman (scr_seq_0782_T06R0301.s:72): the fall-through goes
#     to FLAG_UNK_119 / FLAG_RESTORED_POWER dialogue, and only then to the
#     Lost Item give. A Pass received early made him refuse the Lost Item
#     forever. Not an AP location itself, but the only source of the Lost
#     Item the Copycat needs.
#
# The vanilla meaning of "holds the Pass" is exactly FLAG_UNK_087, set
# once in the Copycat's trade branch right after the give
# (scr_seq_0841_T11R0802.s:84), referenced nowhere else except a read in
# phone_scripts_juggler_irwin.c, never cleared, and already the Pass
# location's own check flag (location_flags.py). So Group C gates on that
# pre-existing flag with no SetFlag at all, the same shape as
# rom/badgegatedata.py's regate: `CheckFlag` + `GoToIf(TRUE, orig_target)`
# + `Noop` padding (4 + 7 + 8 = the old 19 bytes). Offsets verified byte for
# byte on both real HeartGold and SoulSilver US ROMs.

from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

CHECKFLAG_OPCODE = 32
GOTOIF_OPCODE = 28
SETFLAG_OPCODE = 30
GOTO_OPCODE = 22
NOOP_OPCODE = 0
GOTOIF_TRUE = 1

# location key -> (scr_seq.narc sub-file index, gate block's own byte
# offset, gate block's own total byte length, `orig_target` -- the byte
# offset the old check jumps to when the player already has the vanilla
# item, i.e. the "skip the give branch" address). Every offset below was
# found live via an exact-bytes pattern search against both the real
# HeartGold and SoulSilver US ROMs (identical NitroFS layout on both, same
# as rom/badgedata.py's own TABLE) and cross-checked against the decomp's
# own scr_seq/*.s source for the surrounding script shape.
GROUP_A: dict[str, tuple[int, int, int, int]] = {
    # scr_seq_0030_D23R0102.s:128 -- HasItem ITEM_BLUE_CARD, 1, ...
    "goldenrod_radio_tower_2f_blue_card": (30, 362, 21, 437),
    # scr_seq_0033_D23R0105.s:38 -- GetItemQuantity ITEM_BASEMENT_KEY, ...
    "goldenrod_radio_tower_5f_basement_key": (33, 117, 19, 555),
    # scr_seq_0097_D37R0105.s:26 -- GetItemQuantity ITEM_CARD_KEY, ...
    "goldenrod_tunnel_warehouse_card_key": (97, 49, 19, 91),
    # scr_seq_0896_T25R0601.s:132 -- HasItem ITEM_SQUIRTBOTTLE, 1, ...
    "goldenrod_flower_shop_squirtbottle": (896, 397, 21, 464),
    # scr_seq_0200_R12R0101.s:15 -- GetItemQuantity ITEM_SUPER_ROD, ...
    "route_12_fishing_brother_house_super_rod": (200, 14, 19, 76),
    # scr_seq_0798_T07R0203.s:198 -- GetItemQuantity ITEM_GB_SOUNDS, ...
    "celadon_condominiums_3f_gb_sounds": (798, 630, 19, 679),
}

# celadon_game_corner_coin_case (scr_seq_0806_T07SP0101.s:104 -- HasItem
# ITEM_COIN_CASE, 1, ...): (narc index, block offset, block length,
# skip_target [old fall-through-once-redeemed address], give_target [old
# jump-to-the-give-branch address]). The bug report's own 4-site count for
# this file does not hold up against the real ROM/decomp source: the other
# 3 `HasItem ITEM_COIN_CASE` occurrences in this same narc sub-file
# (offsets 26, 195) are unrelated casino-table "can you play" gates that
# never call GiveItemNoCheck at all -- correctly checking real Bag
# possession forever, not part of this location's own give-branch, and
# deliberately left untouched.
GROUP_B: dict[str, tuple[int, int, int, int, int]] = {
    "celadon_game_corner_coin_case": (806, 306, 21, 327, 388),
}

# Freshly reserved sentinel flag ids, one per site -- same reserved-tail
# methodology as rom/badgedata.py's BADGE_SENTINEL_INJECTIONS (include/
# constants/flags.h's NUM_FLAGS = 2912, ids 0-2911 / 0x0-0xB5F), the band
# immediately below the 10 ids BADGE_SENTINEL_INJECTIONS already claims
# (0xB50-0xB59). Confirmed completely unreferenced anywhere in the entire
# decomp source tree (scripts AND C code) and not claimed anywhere else in
# this project's own code (checked against BADGE_SENTINEL_INJECTIONS,
# `_SYNTHETIC_ID_FLAG_OVERRIDES`, the TRAINER_FLAG_BASE/HIDDEN_ITEMS_
# FLAG_BASE reserved bands, and each other -- no overlap).
GATE_FLAGS: dict[str, int] = {
    "goldenrod_radio_tower_2f_blue_card": 0xB48,
    "goldenrod_radio_tower_5f_basement_key": 0xB49,
    "goldenrod_tunnel_warehouse_card_key": 0xB4A,
    "goldenrod_flower_shop_squirtbottle": 0xB4B,
    "route_12_fishing_brother_house_super_rod": 0xB4C,
    "celadon_condominiums_3f_gb_sounds": 0xB4D,
    # 0xB4E belonged to saffron_copycat_house_2f_pass, now in GROUP_C. Left
    # unassigned rather than reused: ROMs patched before the move already
    # set it on their saves.
    "celadon_game_corner_coin_case": 0xB4F,
}

FLAG_UNK_087 = 0x87  # Copycat traded the Lost Item for the Pass

# Group C, see this module's docstring: key -> (narc index, gate block
# offset, block length, orig_target, pre-existing flag to test). The Fan
# Club key is not an AP location key (the Lost Item is not randomized).
GROUP_C: dict[str, tuple[int, int, int, int, int]] = {
    # scr_seq_0841_T11R0802.s:41 -- GetItemQuantity ITEM_PASS, ... -> _0125
    "saffron_copycat_house_2f_pass": (841, 100, 19, 293, FLAG_UNK_087),
    # scr_seq_0782_T06R0301.s:72 -- GetItemQuantity ITEM_PASS, ... -> _0141
    "vermilion_pokemon_fan_club_lost_item": (782, 215, 19, 321, FLAG_UNK_087),
}


class NpcGiftGateDataError(Exception):
    """Base class for every error this module raises."""


def _goto_word(dest: int, word_field_offset: int) -> int:
    """`.word \\dest-.-4`'s own relative-encoding formula: the word field
    itself sits 4 bytes before the position it's relative to."""
    return dest - word_field_offset - 4


def _build_group_a_patch(block_offset: int, block_size: int, orig_target: int, flag_id: int) -> bytes:
    checkflag = struct.pack("<HH", CHECKFLAG_OPCODE, flag_id)
    goto_word_field_offset = block_offset + 4 + 2 + 1  # after CheckFlag(4) + GoToIf's own opcode(2)+cond(1)
    gotoif = struct.pack("<HB", GOTOIF_OPCODE, GOTOIF_TRUE) + struct.pack(
        "<i", _goto_word(orig_target, goto_word_field_offset)
    )
    setflag = struct.pack("<HH", SETFLAG_OPCODE, flag_id)
    used = len(checkflag) + len(gotoif) + len(setflag)
    remaining = block_size - used
    if remaining < 0 or remaining % 2 != 0:
        raise NpcGiftGateDataError(
            f"Group A patch does not fit block_size {block_size} (used {used}, remaining {remaining})"
        )
    noop_pad = struct.pack("<H", NOOP_OPCODE) * (remaining // 2)
    return checkflag + gotoif + setflag + noop_pad


def _build_group_b_patch(block_offset: int, block_size: int, skip_target: int, give_target: int, flag_id: int) -> bytes:
    checkflag = struct.pack("<HH", CHECKFLAG_OPCODE, flag_id)
    gotoif_word_field_offset = block_offset + 4 + 2 + 1
    gotoif = struct.pack("<HB", GOTOIF_OPCODE, GOTOIF_TRUE) + struct.pack(
        "<i", _goto_word(skip_target, gotoif_word_field_offset)
    )
    setflag = struct.pack("<HH", SETFLAG_OPCODE, flag_id)
    goto_word_field_offset = block_offset + 4 + 7 + 4 + 2
    goto = struct.pack("<H", GOTO_OPCODE) + struct.pack("<i", _goto_word(give_target, goto_word_field_offset))
    patch = checkflag + gotoif + setflag + goto
    if len(patch) != block_size:
        raise NpcGiftGateDataError(f"Group B patch length {len(patch)} != block_size {block_size}")
    return patch


def _build_group_c_patch(block_offset: int, block_size: int, orig_target: int, flag_id: int) -> bytes:
    checkflag = struct.pack("<HH", CHECKFLAG_OPCODE, flag_id)
    goto_word_field_offset = block_offset + 4 + 2 + 1
    gotoif = struct.pack("<HB", GOTOIF_OPCODE, GOTOIF_TRUE) + struct.pack(
        "<i", _goto_word(orig_target, goto_word_field_offset)
    )
    used = len(checkflag) + len(gotoif)
    remaining = block_size - used
    if remaining < 0 or remaining % 2 != 0:
        raise NpcGiftGateDataError(
            f"Group C patch does not fit block_size {block_size} (used {used}, remaining {remaining})"
        )
    return checkflag + gotoif + struct.pack("<H", NOOP_OPCODE) * (remaining // 2)


def read_gate_bytes(rom: HeartGoldRom, narc_index: int, offset: int, size: int) -> bytes:
    """Read `size` raw bytes at (narc_index, offset) -- exposed for
    verification/testing, not used in the normal patch path."""
    narc = rom.read_narc(NITROFS_PATH)
    return bytes(narc.files[narc_index][offset : offset + size])


def write_npc_gift_duplication_gate(rom: HeartGoldRom, location_key: str) -> None:
    """Patch location_key's own broken vanilla-item-possession gate in
    place with a fresh one-time savedata-flag gate -- see this module's own
    docstring for the three block shapes."""
    if location_key in GROUP_C:
        narc_index, block_offset, block_size, orig_target, flag_id = GROUP_C[location_key]
        patch = _build_group_c_patch(block_offset, block_size, orig_target, flag_id)
        narc = rom.read_narc(NITROFS_PATH)
        blob = bytearray(narc.files[narc_index])
        blob[block_offset : block_offset + block_size] = patch
        narc.files[narc_index] = bytes(blob)
        rom.write_narc(NITROFS_PATH, narc)
        return

    flag_id = GATE_FLAGS.get(location_key)
    if flag_id is None:
        raise KeyError(f"unknown npc_gift duplication-gate location key: {location_key!r}")

    if location_key in GROUP_A:
        narc_index, block_offset, block_size, orig_target = GROUP_A[location_key]
        patch = _build_group_a_patch(block_offset, block_size, orig_target, flag_id)
    else:
        narc_index, block_offset, block_size, skip_target, give_target = GROUP_B[location_key]
        patch = _build_group_b_patch(block_offset, block_size, skip_target, give_target, flag_id)

    narc = rom.read_narc(NITROFS_PATH)
    blob = bytearray(narc.files[narc_index])
    blob[block_offset : block_offset + block_size] = patch
    narc.files[narc_index] = bytes(blob)
    rom.write_narc(NITROFS_PATH, narc)


def write_all_npc_gift_duplication_gates(rom: HeartGoldRom) -> None:
    """Patch every known broken vanilla-item gate (GATE_FLAGS, then
    GROUP_C). Unconditional -- like rom/badgedata.py's own
    write_all_badges_neutralized, this does not depend on this seed's fill
    result, so it always runs exactly the same way regardless of what item
    ends up at any of these locations."""
    for location_key in (*GATE_FLAGS, *GROUP_C):
        write_npc_gift_duplication_gate(rom, location_key)
