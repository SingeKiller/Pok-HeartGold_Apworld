# rom/badgegatedata.py
#
# Re-gates each gym Leader's own "have I already beaten them" check from
# `CheckBadge <badge>` onto that Leader's own per-gym sentinel flag (task
# "Decouple badge possession from gym-Leader re-battle", 2026-08-19).
#
# Why: with randomized badges (data_gen/items.toml's badge_* entries are
# real AP items placed anywhere in the multiworld), one single savedata bit
# -- PlayerProfile.johtoBadges/kantoBadges -- is asked to mean two
# incompatible things at once:
#
#   1. every gym script reads it via `CheckBadge` to decide "already
#      beaten, skip the fight and the whole win cutscene";
#   2. the field engine reads that SAME bit to authorize the out-of-battle
#      HM moves (Cut, Fly, Surf, Strength, Waterfall, Whirlpool, Rock
#      Smash, Rock Climb).
#
# Meaning (2) is what a randomizer needs a badge *item* to do, and it must
# apply the instant the item is received. Meaning (1) must instead track
# the player's own local progress. Serving both off one bit produced two
# real, decomp-confirmed bugs:
#
# Bug A -- because the client used to withhold the profile bit until the
# Leader's own sentinel flag was set (see client.py's
# _apply_pending_badges), a player who beat Falkner BEFORE the badge_zephyr
# item happened to arrive from the multiworld never got the bit written at
# all: `CheckBadge` stayed false, Falkner became re-fightable, and his
# whole win branch (including `SetVar VAR_SCENE_ELMS_LAB, 6`, which gates
# the Elm's Lab egg pickup and the Kimono Girl chain) replayed on every
# single revisit.
#
# Bug B (permanent softlock) -- Chuck, Jasmine, Morty and Pryce each run
# `AddVar VAR_MIDGAME_BADGES, 1` inside that same re-runnable win branch
# (scr_seq_0877_T24GYM0101.s:44, scr_seq_0913_T26GYM0101.s:136,
# scr_seq_0922_T27GYM0101.s:117, scr_seq_0932_T28GYM0101.s:89). The game
# then tests that counter for STRICT EQUALITY to fire the Team Rocket
# takeover of Mahogany Town and the Radio Tower (`Compare
# VAR_MIDGAME_BADGES, 3` at scr_seq_0877:47, scr_seq_0913:138,
# scr_seq_0932:91, plus `InitScriptGoToIfEqual VAR_MIDGAME_BADGES, 4` at
# scr_seq_0684_T26_hdr.s:14 and scr_seq_0703_T28_hdr.s:13). One extra
# re-win pushes the counter past 3, the equality can never be true again,
# and the mid-game story is permanently blocked.
#
# Fix: stop asking the profile bit meaning (1) at all. Each gym script's
# own battle gate is rewritten to test that Leader's per-gym sentinel flag
# instead -- the exact flag that already fires once, unconditionally, in
# that Leader's real win branch (rom/badgedata.py's own
# BADGE_SENTINEL_INJECTIONS for 10 of them, a hand-verified pre-existing
# flag from location_flags._SYNTHETIC_ID_FLAG_OVERRIDES for the other 4).
# Semantically this RESTORES vanilla: "sentinel set" is exactly what
# `CheckBadge` meant before badges were randomized. The profile bit is
# then free to be written the moment the badge_* item arrives (client.py),
# which is all the HM-move engine ever needed it for.
#
# Binary shape of the vanilla gate (19 bytes, byte-identical on 15 of the
# 16 gym scripts, verified live against both the real HeartGold and
# SoulSilver US ROMs -- same NitroFS layout on both, like rom/badgedata.py
# and rom/npcgiftgatedata.py):
#
#   26 01 <badge> 00 0C 80   CheckBadge badge, VAR_SPECIAL_RESULT  (6 bytes, opcode 294)
#   11 00 0C 80 01 00        Compare VAR_SPECIAL_RESULT, 1         (6 bytes, opcode 17)
#   1C 00 01 <word LE>       GoToIf cond=1 (eq), dest              (7 bytes, opcode 28)
#
# Only the first 12 bytes are overwritten; the trailing `GoToIf` -- and
# therefore its relative jump word -- is left byte-for-byte intact, so no
# jump target anywhere in the file shifts and the script keeps its exact
# original length:
#
#   20 00 <flag>             CheckFlag <sentinel>                  (4 bytes, opcode 32)
#   00 00 x4                 Noop x4                               (8 bytes, opcode 0)
#
# That this is equivalent to `GoToIfSet <sentinel>, dest` is decomp-proven,
# not assumed: `ScrCmd_CheckFlag` writes `ctx->comparisonResult`
# (src/scrcmd_c.c:481-489), `GoToIf` with cond=1 consults
# `sConditionTable[1] = { 0, 1, 0 }` (src/scrcmd_c.c:140-146) so it jumps
# exactly when the comparison result is "equal", i.e. when the flag reads
# 1/TRUE, and `Noop` (opcode 0, asm/macros/script.inc:18-20) consumes no
# operand bytes and touches nothing in between. `asm/macros/script.inc:
# 4798-4801` defines `GoToIfSet` as literally `CheckFlag` + `GoToIf TRUE`.
#
# Each of the 14 regated sentinels was re-verified to be set STRICTLY
# INSIDE the byte range the gate skips over (gate offset < SetFlag offset <
# GoToIf destination) and to have no `ClearFlag` anywhere in the same NARC
# sub-file, so the gate can never latch before the fight nor un-latch
# after it.
#
# Two gyms are deliberately not handled the generic way:
#
# Clair (rising, NARC 112 / her battle script NARC 943) has NO `CheckBadge`
# gate on her battle path at all -- she is already gated in vanilla on
# `GoToIfSet FLAG_UNK_0D1` (scr_seq_0943_T30GYM0101.s:87-105), i.e. on the
# very sentinel this module would have installed. Excluded entirely; the
# derivation scan confirms NARC 112 contains no matching 19-byte gate.
#
# Whitney (plain, NARC 886) has a `CheckBadge` at the top but it is NOT her
# battle gate. Her real battle gate is `Compare VAR_UNK_410A, 1`
# (scr_seq_0886_T25GYM0101.s:86-133), and her own sentinel FLAG_UNK_084 is
# `ClearFlag`'d by her own script at :128, so it cannot be used as a gate.
# See WHITNEY_VAR/WHITNEY_VAR_VALUE below for what her site gets instead
# and why plain NOPs would have been actively harmful there.
#
# VERSION COUPLING: this patch and rom/badgedata.py's
# `write_all_badges_neutralized` (which injects sentinels 0xB50-0xB59 at
# the GiveBadge sites) MUST be applied to the same ROM, in that order. A
# ROM regated here but built by an older patcher that never injected those
# sentinels would leave 10 Leaders infinitely re-fightable. patch_gen.py
# wires the two calls back to back for exactly that reason.
#
# NitroFS path: same NARC as rom/eventscriptdata.py, scr_seq.narc -> a/0/1/2.

from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

CHECKBADGE_OPCODE = 294
COMPARE_OPCODE = 17
GOTOIF_OPCODE = 28
CHECKFLAG_OPCODE = 32
NOOP_OPCODE = 0

VAR_SPECIAL_RESULT = 0x800C
GOTOIF_EQ = 1

# The 19-byte vanilla gate as a whole (CheckBadge + Compare + GoToIf); only
# the first 12 are ever rewritten, the trailing GoToIf is verified and then
# left alone.
GATE_SIGNATURE_SIZE = 19
GATE_PATCH_SIZE = 12

# badge name (data_gen/rules.toml's own [badges] table key) -> (scr_seq.narc
# sub-file index, byte offset of the gate's own `CheckBadge` opcode, that
# badge's own badge.h index BADGE_ZEPHYR=0..BADGE_EARTH=15).
#
# Derived by scanning both real ROMs for the CheckBadge opcode and keeping
# only occurrences whose following 13 bytes match the full signature above.
# Several gym scripts contain MORE than one matching site (ordinary NPC
# dialogue branches, and the gym-init logic that decides whether the Leader
# is even present at this time of day), so the site is pinned by exact
# offset, never by "first occurrence" -- `_verify_gate_signature` re-checks
# opcode, badge index and comparison var before writing anything.
#
# `rising` (Clair) is absent on purpose: no matching site exists in NARC
# 112 or in her battle script NARC 943, she is already flag-gated in
# vanilla. See this module's own docstring.
TABLE: dict[str, tuple[int, int, int]] = {
    "zephyr": (859, 181, 0),
    "hive": (869, 219, 1),
    "plain": (886, 276, 2),
    "fog": (922, 320, 3),
    "storm": (877, 47, 4),
    "mineral": (913, 362, 5),
    "glacier": (932, 198, 6),
    "boulder": (752, 265, 8),
    "cascade": (760, 654, 9),
    "thunder": (778, 778, 10),
    "rainbow": (786, 277, 11),
    "soul": (809, 1756, 12),
    "marsh": (829, 151, 13),
    "volcano": (15, 262, 14),
    "earth": (743, 115, 15),
}

# badge names with no gate to patch at all, and why -- kept explicit so a
# future reader does not "fix" the 15/16 asymmetry by guessing.
EXCLUDED: dict[str, str] = {
    "rising": (
        "Clair has no CheckBadge gate on her battle path; "
        "scr_seq_0943_T30GYM0101.s:87-105 already gates her on "
        "GoToIfSet FLAG_UNK_0D1, the same sentinel this module would install"
    ),
}

# badge name -> that Leader's own per-gym sentinel flag id, i.e. the flag
# that fires exactly once inside their real win branch. The 10 hex-0xB5x
# ids are the ones rom/badgedata.BADGE_SENTINEL_INJECTIONS writes into that
# Leader's own (now neutralized) `GiveBadge` instruction; the other 4 are
# pre-existing, hand-verified corpus-unique flags reused from
# location_flags._SYNTHETIC_ID_FLAG_OVERRIDES. Both halves are the exact
# same flags location_flags.build_badge_index_to_sentinel_flag_id returns
# and the badge locations' own AP check-detection already reads, so a gym
# is "gate closed" precisely when its badge location reads as checked --
# tests/test_badge_gate_regating.py pins that agreement to catch drift.
#
# `plain` (Whitney) is absent: her gate is a var comparison, not a flag
# (see WHITNEY_VAR below).
SENTINEL_FLAGS: dict[str, int] = {
    "zephyr": 0x192,  # violet_gym_badge (Falkner), pre-existing
    "hive": 0x520,  # azalea_gym_badge (Bugsy), injected
    "fog": 0x521,  # ecruteak_gym_badge (Morty), injected
    "storm": 0x522,  # cianwood_gym_badge (Chuck), injected
    "mineral": 0x523,  # olivine_gym_badge (Jasmine), injected
    "glacier": 0x524,  # mahogany_gym_leader_room_badge (Pryce), injected
    "boulder": 0x525,  # pewter_gym_badge (Brock), injected
    "cascade": 0x526,  # cerulean_gym_badge (Misty), injected
    "thunder": 0x31A,  # vermilion_gym_badge (Lt. Surge), pre-existing
    "rainbow": 0x527,  # celadon_gym_badge (Erika), injected
    "soul": 0x528,  # fuchsia_gym_badge (Janine), injected
    "marsh": 0x529,  # saffron_gym_badge (Sabrina), injected
    "volcano": 0x265,  # seafoam_islands_cinnabar_gym_badge (Blaine), pre-existing
    "earth": 0x97F,  # viridian_gym_badge (Blue), pre-existing
}

# Whitney (plain) only. Her script's top-level `CheckBadge BADGE_PLAIN`
# does NOT guard her TrainerBattle: the vanilla shape is
# (scr_seq_0886_T25GYM0101.s:86-133, cross-checked byte for byte against
# both real ROMs)
#
#   CheckBadge BADGE_PLAIN / Compare / GoToIfEq _0202   -> post-badge chat
#   GoToIfSet FLAG_UNK_0B7, _01A0                       -> hand over the badge
#   Compare VAR_UNK_410A, 1 / GoToIfEq _017D            -> beaten, crying, no badge yet
#   TrainerBattle TRAINER_LEADER_WHITNEY
#   _01A0: GiveBadge ; SetVar VAR_UNK_410A, 2 ; ClearFlag FLAG_UNK_084 ; give TM45
#
# So her battle is already one-shot via VAR_UNK_410A, and her own sentinel
# FLAG_UNK_084 is cleared at :128 -- unusable as a gate. Plain NOPs here
# would be actively harmful too: once VAR_UNK_410A == 2 no branch would
# match any more and control would fall straight through to
# `TrainerBattle`, re-opening a fight vanilla had closed.
#
# Her site is therefore rewritten as `Compare VAR_UNK_410A, 2` (opcode 17,
# also exactly 6 bytes, asm/macros/script.inc:147-151's own
# CompareVarToValue, which `Compare` resolves to for a plain literal --
# :4785-4791) plus 3 Noops, keeping the same untouched `GoToIf` -- i.e.
# "Whitney has already personally handed you her badge -> skip to the
# post-badge chat".
#
# Side effect, deliberate: this also closes a pre-existing duplication bug.
# With GiveBadge neutralized, `CheckBadge` never became true, so every
# revisit after FLAG_UNK_0B7 got set re-entered `_01A0` and re-ran the
# unconditional `_01C4` TM45 hand-out (`GoToIfNoItemSpace` + `CallStd
# std_give_item_verbose`; the FLAG_GOT_TM45_FROM_WHITNEY guard lives on the
# `_0202` path only, at :148, which was unreachable). The new gate reaches
# `_0202` again as soon as VAR_UNK_410A is 2, so `_01A0` stops replaying.
WHITNEY_BADGE_NAME = "plain"
WHITNEY_VAR = 0x410A  # VAR_UNK_410A, include/constants/vars.h:281
WHITNEY_VAR_VALUE = 2  # set by scr_seq_0886_T25GYM0101.s:127, right after GiveBadge


class BadgeGateDataError(Exception):
    """Base class for every error this module raises."""


def read_gate_bytes(rom: HeartGoldRom, narc_index: int, offset: int, size: int = GATE_SIGNATURE_SIZE) -> bytes:
    """Read `size` raw bytes at (narc_index, offset) -- exposed for
    verification/testing, not used in the normal patch path."""
    narc = rom.read_narc(NITROFS_PATH)
    return bytes(narc.files[narc_index][offset : offset + size])


def _verify_gate_signature(blob: bytes, badge_name: str, offset: int, badge_index: int) -> None:
    """Refuse to patch anything that is not the exact 19-byte vanilla gate
    documented in this module's own docstring. Guards against a stale TABLE
    offset silently corrupting an unrelated instruction (the failure mode
    that would be hardest to notice: the ROM still builds, the script just
    misbehaves live)."""
    signature = blob[offset : offset + GATE_SIGNATURE_SIZE]
    if len(signature) != GATE_SIGNATURE_SIZE:
        raise BadgeGateDataError(f"{badge_name}: gate at offset {offset} runs past the end of NARC sub-file")

    check_opcode, check_badge, check_var = struct.unpack_from("<HHH", signature, 0)
    cmp_opcode, cmp_var, cmp_value = struct.unpack_from("<HHH", signature, 6)
    goto_opcode = struct.unpack_from("<H", signature, 12)[0]
    goto_cond = signature[14]

    expected = (
        CHECKBADGE_OPCODE,
        badge_index,
        VAR_SPECIAL_RESULT,
        COMPARE_OPCODE,
        VAR_SPECIAL_RESULT,
        1,
        GOTOIF_OPCODE,
        GOTOIF_EQ,
    )
    actual = (check_opcode, check_badge, check_var, cmp_opcode, cmp_var, cmp_value, goto_opcode, goto_cond)
    if actual != expected:
        raise BadgeGateDataError(
            f"{badge_name}: gate signature mismatch at offset {offset} -- expected {expected}, got {actual} "
            f"(raw {signature.hex(' ')})"
        )


def build_gate_patch(badge_name: str) -> bytes:
    """The GATE_PATCH_SIZE replacement bytes for one badge's gate. Never
    includes the trailing `GoToIf`: that instruction (and its relative jump
    word) is deliberately left untouched, which is what keeps the script's
    total length and every other jump target in the file unchanged."""
    if badge_name == WHITNEY_BADGE_NAME:
        head = struct.pack("<HHH", COMPARE_OPCODE, WHITNEY_VAR, WHITNEY_VAR_VALUE)
    else:
        flag_id = SENTINEL_FLAGS.get(badge_name)
        if flag_id is None:
            raise KeyError(f"no sentinel flag known for badge {badge_name!r}")
        head = struct.pack("<HH", CHECKFLAG_OPCODE, flag_id)

    remaining = GATE_PATCH_SIZE - len(head)
    if remaining < 0 or remaining % 2 != 0:
        raise BadgeGateDataError(
            f"{badge_name}: replacement head is {len(head)} bytes, does not pad to {GATE_PATCH_SIZE}"
        )
    return head + struct.pack("<H", NOOP_OPCODE) * (remaining // 2)


def write_badge_gate_regated(rom: HeartGoldRom, badge_name: str) -> None:
    """Re-gate one gym script's battle guard off `CheckBadge` -- see this
    module's own docstring. Verifies the vanilla signature first and raises
    BadgeGateDataError rather than writing over anything unexpected."""
    site = TABLE.get(badge_name)
    if site is None:
        raise KeyError(f"unknown badge gate: {badge_name!r} (excluded: {sorted(EXCLUDED)})")
    narc_index, offset, badge_index = site

    narc = rom.read_narc(NITROFS_PATH)
    blob = bytearray(narc.files[narc_index])
    _verify_gate_signature(bytes(blob), badge_name, offset, badge_index)

    blob[offset : offset + GATE_PATCH_SIZE] = build_gate_patch(badge_name)
    narc.files[narc_index] = bytes(blob)
    rom.write_narc(NITROFS_PATH, narc)


def write_all_badge_gates_regated(rom: HeartGoldRom) -> None:
    """Re-gate all 15 patchable gym battle guards (every badge but
    `rising`, see EXCLUDED). Unconditional -- like rom/badgedata.py's own
    write_all_badges_neutralized, this never depends on this seed's fill
    result, since the bug is in the gate itself, not in what item ends up
    placed at any badge location.

    MUST run on a ROM that also went through write_all_badges_neutralized
    (see this module's own VERSION COUPLING note): 10 of these 15 gates now
    depend on a sentinel flag that only that function injects."""
    for badge_name in TABLE:
        write_badge_gate_regated(rom, badge_name)
