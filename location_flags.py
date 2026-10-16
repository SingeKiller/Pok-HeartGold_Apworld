# location_flags.py
#
# Maps data/locations.py keys to the vanilla savedata flag id that fires
# when that location's check is triggered in-game (check detection: read
# the existing savedata flag bits directly, no ROM patch needed), and the
# reverse (flag id -> AP location id) map client.py's game_watcher polls.

from __future__ import annotations

from data.locations import LOCATIONS
from data.species import SPECIES
from data.trainers import TRAINERS
from locations import SHELVED_LOCATION_TYPES, create_location_label_to_code_map
from save_layout import HIDDEN_ITEMS_FLAG_BASE

# Location types whose data/locations.py `id` is already a real vanilla
# savedata flag id. `hidden_item` is excluded: its id is a small
# HIDDENITEM_* index, not a flag id directly.
_DIRECT_FLAG_ID_TYPES = {"ground_item", "npc_gift", "hm_tm"}

# include/constants/flags.h: FLAG_TRAINER(tr) = TRAINER_FLAG_BASE + tr,
# set automatically by the engine (script_manager.c's SetTrainerFlag/
# CheckTrainerFlag) the moment a TrainerBattle/std_trainer(...) fight is
# won -- same flags array as every other flag this module reads, no ROM
# patch needed (task M3.3, Trainersanity).
TRAINER_FLAG_BASE = 0x550

# include/constants/flags.h's own dedicated FLAG_CAUGHT_HO_OH/FLAG_CAUGHT_
# LUGIA constants -- decomp-confirmed to be set only on an actual
# successful catch, not merely winning the battle (see data_gen/
# locations.toml's own header / NOTES.md for the full derivation). Same
# SaveVarsFlags.flags[] array as every other flag this module reads.
_STATIC_POKEMON_FLAG_IDS: dict[str, int] = {
    "catch_ho_oh": 0x116,
    "catch_lugia": 0x117,
}

# npc_gift locations with no single-purpose FLAG_GOT_* constant get a
# synthetic id in this reserved band instead -- no real vanilla savedata
# flag to read, so check detection can't observe them via RAM by default.
_SYNTHETIC_ID_BASE = 9000

# Hand-verified overrides (task M1.6): specific synthetic-id locations
# whose own script does still set *some* real, unique, one-time vanilla
# savedata flag right alongside the GiveItemNoCheck call -- just not one
# named FLAG_GOT_*, which is why the C4/C5 extraction pass (see this
# module's docstring) didn't pick it up automatically. Found by manually
# reading each location's scr_seq/*.s source and confirming BOTH that the
# flag is set unconditionally right after the item grant AND that it is
# never set anywhere else in the entire scr_seq corpus for an unrelated
# reason (see the "real bug" note below for why the second half of that
# check is not optional).
_SYNTHETIC_ID_FLAG_OVERRIDES: dict[str, int] = {
    # scr_seq_0018_D15R0103.s (Sprout Tower 3F, Li): FLAG_UNK_076 is set
    # immediately after `GiveItemNoCheck ITEM_TM70, 1`, and a `GoToIfSet
    # FLAG_UNK_076` earlier in the same block is this exact interaction's
    # own re-entry guard. Confirmed the *only* SetFlag/reference to this
    # flag anywhere in the whole scr_seq corpus (2026-08-15, after the
    # real bug below was found) -- it cannot be set by anything else.
    "sprout_tower_3f_tm70": 0x76,
    # scr_seq_0090_D35R0103.s (Team Rocket HQ B2F, Lance/Wataru gives
    # HM05 after the 3-Electrode puzzle): FLAG_UNK_1E5 is set immediately
    # after `GiveItemNoCheck ITEM_HM05, 1` and `HidePerson
    # obj_D35R0103_wataru`, in the same unbranched block that also flips
    # FLAG_ROCKET_HIDEOUT_CLEARED right after. The only other reference
    # (scr_seq_0088_D35R0101.s) re-sets the same flag when
    # VAR_UNK_40AC == 8, a strictly-increasing story-progress counter
    # that scr_seq_0090_D35R0103.s's own HM05 scene is what first sets to
    # 8 (confirmed 2026-08-15, after the real bug below was found) -- a
    # redundant re-application on revisit, not an independent early
    # trigger, so this override is safe.
    "team_rocket_headquarters_b2f_hm05": 0x1E5,
    # scr_seq_0843_T20R0101.s (New Bark Town, Elm's Lab): FLAG_GOT_SS_
    # TICKET_FROM_ELM is set immediately after `SetVar VAR_SPECIAL_x8004,
    # ITEM_S_S__TICKET` / `CallStd std_give_item_verbose`, in the same
    # unbranched block. A semantically-named FLAG_GOT_* constant, and the
    # only SetFlag reference to it anywhere in the corpus (2026-08-15,
    # verified with the corpus-wide + scr_seq_0149.s cross-checks the
    # first live bug above made mandatory).
    "new_bark_elms_lab_1f_s_s_ticket": 0xF2,
    # scr_seq_0229_R30R0201.s (Route 30, Mr. Pokemon's assistant trades
    # Red Scale for Exp. Share): FLAG_EXCHANGED_RED_SCALE is set
    # immediately after `CallStd std_give_item_verbose` /
    # `TakeItemNoCheck ITEM_RED_SCALE, 1`, in the same unbranched block --
    # names the trade, not just the item, but is a real, one-time flag for
    # this exact interaction (only SetFlag reference anywhere).
    "route_30_mr_pokemon_house_exp_share": 0x6C,
    # scr_seq_0196_R10R0202.s (Route 10, the Power Plant director gives
    # TM57 once it's restored): FLAG_UNK_258 is set right after
    # `GiveItemNoCheck ITEM_TM57, 1` and its follow-up dialogue, in the
    # same unbranched block (which also flips several unrelated,
    # coincidentally-adjacent story flags for other locations entirely --
    # confirmed FLAG_UNK_258 itself is the only SetFlag reference to this
    # specific flag anywhere in the corpus).
    "route_10_power_plant_broken_tm57": 0x258,
    # scr_seq_0928_T27R0501.s (Ecruteak Dance Theater): two separate,
    # distinct one-time flags, each set immediately after its own item
    # grant in the same unbranched sequence -- FLAG_UNK_103 right after
    # `GiveItemNoCheck ITEM_CLEAR_BELL, 1`, FLAG_UNK_104 right after
    # `GiveItemNoCheck ITEM_TIDAL_BELL, 1`. Both confirmed as the only
    # SetFlag reference to their own flag id anywhere in the corpus.
    "ecruteak_dance_theater_clear_bell": 0x103,
    "ecruteak_dance_theater_tidal_bell": 0x104,
    # scr_seq_0251_R39R0201.s (Moomoo Farm Stable): FLAG_UNK_100 is set
    # immediately after `GiveItemNoCheck ITEM_SEAL_CASE, 1`, in the same
    # unbranched block. Only SetFlag reference to this flag anywhere.
    "route_39_moomoo_farm_stable_seal_case": 0x100,
    # scr_seq_0181_R05R0202.s (Route 5 Underground Path, trade Rage Candy
    # Bar for TM64/Explosion): FLAG_UNK_164 is set right after the trade's
    # own `SetVar VAR_SPECIAL_x8004, TM_EXPLOSION` / `CallStd std_obtain_
    # item_verbose` sequence and its follow-up dialogue, still unbranched.
    # Only SetFlag reference to this flag anywhere.
    "route_5_underground_path_tm64": 0x164,
    # scr_seq_0841_T11R0802.s (Saffron Copycat House 2F, the Pass):
    # FLAG_UNK_087 is set right after `GiveItemNoCheck ITEM_PASS, 1` and
    # its follow-up dialogue, still unbranched. Only SetFlag reference to
    # this flag anywhere (a coincidentally-nearby, unrelated flag with 12
    # occurrences elsewhere was ruled out by the same corpus-wide check).
    "saffron_copycat_house_2f_pass": 0x87,
    # scr_seq_0034_D23R0106.s (Goldenrod Radio Tower Observation Deck):
    # two separate, distinct flags, each set immediately after its own
    # item grant -- FLAG_UNK_093 for Rainbow Wing, FLAG_UNK_094 for Silver
    # Wing. FLAG_UNK_093 has a second reference (scr_seq_0750_T03.s,
    # Pewter City's own alternate Rainbow Wing NPC, see the matching
    # rom/npcgiftdata.py TABLE fix above) that is a real, redundant second
    # grant path for the same item, not an independent trigger. A third
    # reference (scr_seq_0019_D17R0101.s, Bell Tower) is a plain
    # `GoToIfSet` read, not a SetFlag. FLAG_UNK_094 has one other
    # reference (scr_seq_0103_D40R0104.s, Whirl Islands), also a plain
    # `GoToIfSet` read (gating the Lugia encounter's own dialogue branch).
    "goldenrod_radio_tower_observation_deck_rainbow_wing": 0x93,
    "goldenrod_radio_tower_observation_deck_silver_wing": 0x94,
    # scr_seq_0093_D37R0101.s (Goldenrod Tunnel 1F, the two-Pokemon-fan
    # NPC's Fashion Case): FLAG_UNK_14C is set immediately after
    # `GiveItemNoCheck ITEM_FASHION_CASE, 1`, in each of the location's own
    # 2 known TABLE sites (2 dialogue branches, both already covered) --
    # exactly 2 total occurrences, matching those same 2 sites, not a
    # third/different location.
    "goldenrod_tunnel_1f_fashion_case": 0x14C,
    # scr_seq_0243_R36.s (Route 36, the Flower Shop girl's Berry Pots):
    # FLAG_HIDE_ROUTE_36_FLOWERSHOP_GIRL is set right after `GiveItemNoCheck
    # ITEM_BERRY_POTS, 1` (and the two follow-up berry grants), once both
    # movement branches converge, still unbranched from there. Only
    # SetFlag reference to this flag anywhere, and confirmed NOT part of
    # scr_seq_0149.s's new-game mass-init batch despite the FLAG_HIDE_*
    # name (unlike route_29/route_42 above) -- the exact check that bug
    # made mandatory going forward.
    "route_36_berry_pots": 0x1CF,
    # scr_seq_0097_D37R0105.s (Goldenrod Tunnel Warehouse): FLAG_UNK_1C1 is
    # set right *before* `GiveItemNoCheck ITEM_CARD_KEY, 1`, but both sit in
    # the same unbranched block gated by the same `GetItemQuantity` re-entry
    # check -- the flag and the grant always fire together, order doesn't
    # matter for detection purposes. Only SetFlag reference to this flag
    # anywhere in the corpus.
    "goldenrod_tunnel_warehouse_card_key": 0x1C1,
    # scr_seq_0157_P01R0302.s (S.S. Aqua Captain's Room, the crew member who
    # hands over a Plate once you have the Earth Badge): FLAG_UNK_ABB is set
    # immediately after `CallStd std_obtain_item_verbose`, and a
    # `GoToIfSet FLAG_UNK_ABB` earlier in the same block is this exact
    # interaction's own re-entry guard. Only SetFlag reference to this flag
    # anywhere in the corpus (a second flag, FLAG_UNK_092, also fires here
    # but is referenced in 2 other S.S. Aqua rooms too and wasn't needed
    # once FLAG_UNK_ABB alone was confirmed unique).
    "ss_aqua_captain_room_flame_plate": 0xABB,
    # scr_seq_0890_T25R0201.s (Goldenrod Bike Shop): FLAG_UNK_089 is set
    # immediately after `GiveItemNoCheck ITEM_BICYCLE, 1`, and a
    # `GoToIfSet FLAG_UNK_089` at the very top of the script is this
    # exact interaction's own re-entry guard (skips the whole
    # conversation once already given). Only SetFlag/GoToIfSet reference
    # to this flag anywhere in the corpus (task "randomize_bicycle",
    # 2026-08-17).
    "goldenrod_bike_shop_bicycle": 0x89,
    # --- type = 'badge' overrides (real bug, found and fixed 2026-08-18) --
    #
    # Every one of the 16 gym Leaders is fought through a bespoke,
    # hand-authored `TrainerBattle TRAINER_LEADER_*` call embedded directly
    # in that gym's own scripted cutscene -- never routed through the
    # shared std_trainer/std_trainer_2 engine script (scr_seq_0953.s) that
    # every ordinary (type = 'trainer') Trainersanity trainer uses to
    # self-flag TRAINER_FLAG_BASE + their own trainer id after every win
    # (GetTrainerNum -> ScriptNumToTrainerNum -> SetTrainerFlag, decomp-
    # confirmed, src/script_manager.c). A gym Leader's own win branch never
    # calls SetTrainerFlag on themselves, so TRAINER_FLAG_BASE + their
    # trainer id is NEVER actually set in-game for any of them -- the old
    # `flag_id_for_location` badge branch that assumed otherwise was
    # simply wrong (found live, 2026-08-18: none of the 16 badge locations
    # could ever register as checked, and client.py's own
    # _apply_pending_badges deferred writing the received badge item's
    # PlayerProfile bit on that same always-false flag, so CheckBadge never
    # saw the Leader as beaten and the whole win cutscene -- including
    # Falkner's own `SetVar VAR_SCENE_ELMS_LAB, 6` that gates the Elm's Lab
    # egg-pickup call -- replayed on every single re-fight, the originally
    # reported 2026-08-17 player bug). Same fix pattern as every other
    # entry in this dict: a per-gym sentinel flag that fires unconditionally
    # in that Leader's own win branch, hand-verified corpus-unique.
    #
    # 6 of the 16 gym Leaders reuse a confirmed, safe pre-existing candidate
    # (see build_badge_index_to_sentinel_flag_id's own docstring for the
    # full derivation of why the other 10 had none):
    #
    # scr_seq_0859_T22GYM0101.s (Violet Gym, Falkner): FLAG_UNK_192 is set
    # right after `GiveBadge BADGE_ZEPHYR` (now NOP'd) and
    # `SetTrainerFlag` calls for 2 OTHER trainers' phone rematches, still
    # unconditional/unbranched. Only SetFlag reference to this flag
    # anywhere in the corpus.
    "violet_gym_badge": 0x192,
    # scr_seq_0886_T25GYM0101.s (Goldenrod Gym, Whitney): unlike every
    # other Leader, Whitney's own script gives the badge on a *separate*,
    # later revisit (`GoToIfSet FLAG_UNK_0B7, _01A0` at the very top routes
    # straight to the GiveBadge branch once a different, unrelated GS-Ball-
    # delivery cutscene elsewhere in the same narc file has already set
    # FLAG_UNK_0B7 -- confirmed NOT part of Whitney's own win branch, so
    # not usable). Her own win branch (CheckBattleWon -> SetTrainerFlag x4
    # for other trainers -> FLAG_UNK_084, unconditional) is what gates
    # entry into that later revisit path (`Compare VAR_UNK_410A, 1` is
    # only ever 1 after FLAG_UNK_084's own block sets it) -- i.e. FLAG_UNK_
    # 084 fires exactly once, the moment Whitney is actually beaten, and is
    # later ClearFlag'd only once the badge itself is finally handed over
    # (a harmless one-shot re-arm, not a re-trigger risk: client.py's
    # check-detection only needs to observe it true once while polling,
    # which is a long window here since the badge hand-over is a real
    # follow-up visit). Only SetFlag/ClearFlag reference to this flag
    # anywhere in the corpus.
    "goldenrod_gym_badge": 0x84,
    # scr_seq_0778_T06GYM0101.s (Vermilion Gym, Lt. Surge): FLAG_HIDE_
    # VERMILION_GYM_STOPS is set right after `GiveBadge BADGE_THUNDER` (now
    # NOP'd), still unconditional/unbranched, and hides the gym's own now-
    # pointless "bus stop" NPCs. Also used as a `GoToIfSet` re-entry guard
    # twice earlier in the same file (gym init logic) -- never as a SetFlag
    # anywhere else, and NOT part of scr_seq_0149.s's new-game mass-init
    # batch (the "real bug" class documented above), so it is a genuine
    # one-time "just won" signal, unlike that class of flag.
    "vermilion_gym_badge": 0x31A,
    # scr_seq_0943_T30GYM0101.s (Blackthorn Gym, Clair): Clair is the one
    # Leader whose `GiveBadge` site is NOT in her own TrainerBattle script
    # at all (she's fought here, but the badge itself is only granted later
    # by a separate Dragon's Den Shrine puzzle-completion cutscene,
    # scr_seq_0112_D44R0103.s -- see rom/badgedata.py's own TABLE comment).
    # FLAG_UNK_0D1 is set immediately after her win (past the other-
    # trainers' SetTrainerFlag calls), unconditional/unbranched, and is
    # this exact script's own re-entry guard (`GoToIfSet FLAG_UNK_0D1`,
    # both here and in the Blackthorn Town overworld script,
    # scr_seq_0941_T30.s) for "has Clair already been beaten". This is the
    # more reliable "just won" signal data_gen/locations.toml's own badge-
    # section header already pointed at (the TrainerBattle-adjacent script,
    # not the separate shrine cutscene) -- verified 2026-08-18. Only
    # SetFlag reference to this flag anywhere in the corpus.
    "dragons_den_shrine_badge": 0xD1,
    # scr_seq_0015_D11R0106.s (Seafoam Islands / Cinnabar Gym, Blaine):
    # FLAG_UNK_265 is set right after `GiveBadge BADGE_VOLCANO` (now
    # NOP'd), still unconditional/unbranched (several other, clearly-
    # unrelated story flags for Route 19 workmen etc. also fire further
    # down the same block, but FLAG_UNK_265 itself is the first and is the
    # only SetFlag reference to this specific flag anywhere in the corpus).
    "seafoam_islands_cinnabar_gym_badge": 0x265,
    # scr_seq_0743_T02GYM0101.s (Viridian Gym, Blue): FLAG_UNK_998 fires
    # right after `GiveBadge BADGE_EARTH` too, but is corpus-wide REUSED by
    # 11 other, completely unrelated scripts (Whitney/Morty/Sabrina's own
    # gym win branches among them, 2026-08-18) -- a real collision, not
    # usable. FLAG_UNK_97F, set right after (following the 4 SetTrainerFlag
    # calls for other trainers' rematches), is the only SetFlag reference
    # to this flag anywhere in the corpus and is genuinely unconditional in
    # this exact win branch.
    "viridian_gym_badge": 0x97F,
    #
    # The remaining 10 gym Leaders (task "Fix the remaining 10 gym badges",
    # 2026-08-18): unlike the 6 above, none of these 10 win branches has a
    # safe *pre-existing* flag to reuse -- every candidate found either
    # collides with another location's own check (e.g. FLAG_UNK_998,
    # corpus-wide reused by 12 unrelated scripts, including 3 of these
    # exact 10 gyms' own win branches) or is claimed by another trainer's
    # own phone-rematch SetTrainerFlag. So these 10 instead get a
    # brand-new, freshly-injected sentinel flag id (FLAG_UNK_B50 through
    # FLAG_UNK_B59, the unused tail of the flag array -- NUM_FLAGS = 2912,
    # confirmed unreferenced anywhere in the decomp source tree and not
    # claimed by any other id band in this project), written by rom.
    # badgedata.BADGE_SENTINEL_INJECTIONS/write_all_badges_neutralized
    # directly into that Leader's own `GiveBadge <badge>` instruction site
    # (same 4 bytes that instruction already occupies, overwritten with
    # `SetFlag <flag_id>` instead of NOP+NOP -- see that module's own
    # docstring for the full mechanism and why it's safe, plain-4-byte-
    # overwrite instead of an ARM hook). Each of the 10 GiveBadge sites was
    # hand-spot-checked in that Leader's own win branch (unconditional,
    # right after CheckBattleWon, same pattern as the 6 above) before being
    # trusted.
    "azalea_gym_badge": 0x520,  # Bugsy (hive)
    "ecruteak_gym_badge": 0x521,  # Morty (fog)
    "cianwood_gym_badge": 0x522,  # Chuck (storm)
    "olivine_gym_badge": 0x523,  # Jasmine (mineral)
    "mahogany_gym_leader_room_badge": 0x524,  # Pryce (glacier)
    "pewter_gym_badge": 0x525,  # Brock (boulder)
    "cerulean_gym_badge": 0x526,  # Misty (cascade)
    "celadon_gym_badge": 0x527,  # Erika (rainbow)
    "fuchsia_gym_badge": 0x528,  # Janine (soul)
    "saffron_gym_badge": 0x529,  # Sabrina (marsh)
}

# 2026-09-24 (player report: items found at these 14 spots never reached
# the server). Every one of them now has a check flag the ROM sets on the
# give path: the duplication gates of rom/npcgiftgatedata.py (their
# SetFlag runs right before the give) and the flags rom/giftflagdata.py
# injects. Only locations that had no readable flag at all are listed; the
# Card Key keeps its own.
from rom.giftflagdata import GIFT_FLAGS  # noqa: E402
from rom.npcgiftgatedata import GATE_FLAGS  # noqa: E402

_SYNTHETIC_ID_FLAG_OVERRIDES.update(GIFT_FLAGS)
_SYNTHETIC_ID_FLAG_OVERRIDES.update(
    {key: flag for key, flag in GATE_FLAGS.items() if key != "goldenrod_tunnel_warehouse_card_key"}
)

# Real bug, found and reverted live (2026-08-15, first live BizHawk test of
# task M1.6): route_29_poke_ball (FLAG_HIDE_ROUTE_29_FRIEND, 0x1A4) and
# route_42_hm04 (FLAG_HIDE_ROUTE_42_HIKER, 0x29D) both fired as "checked"
# on a brand new save, before the player had ever visited either route.
# Root cause: both flags are members of a ~150-flag batch of
# FLAG_HIDE_* NPC-visibility flags that scr_seq_0149.s (`_std_init`,
# include/constants/std_script.h's STD_INIT, run by RunInitScript() via
# CallFieldTask_NewGame(), src/field_warp_tasks.c) sets unconditionally at
# new-game creation, before the player can move at all -- the real
# interaction's own script then does ClearFlag then SetFlag again once the
# NPC is actually met, so "flag is set" is true almost always except
# during the brief window of the interaction itself, making it useless as
# a "have I done this" signal. The lesson generalizes: verifying a
# candidate flag is set once inside the target script is not enough --
# it must also be checked against every OTHER reference to that same flag
# name in the whole scr_seq corpus (which is exactly how the two
# overrides kept above were re-confirmed safe). Both are back in
# unsupported_location_keys() until/unless a real per-interaction flag is
# found for each.

# Known remaining gaps (task M1.6, exhaustively re-checked 2026-08-15 by
# reading each location's own full script, not just silently hidden):
#
# No SetFlag anywhere in the whole script, only a `GetItemQuantity`/
# `HasItem` Bag re-entry check (so no savedata flag bit exists to read at
# all): route_36_hm06 (scr_seq_0243_R36.s), celadon_condominiums_3f_
# gb_sounds (scr_seq_0798_T07R0203.s), celadon_game_corner_coin_case
# (scr_seq_0806_T07SP0101.s), goldenrod_flower_shop_squirtbottle
# (scr_seq_0896_T25R0601.s), route_12_fishing_brother_house_super_rod
# (scr_seq_0200_R12R0101.s), route_31_violet_gatehouse_vs_recorder
# (scr_seq_0231_R31R0101.s, confirmed zero SetFlag anywhere in the file).
# goldenrod_radio_tower_2f_blue_card (scr_seq_0030_D23R0102.s) is gated by
# a *counter* variable (VAR_NUM_TIMES_GIVEN_BLUE_CARD/VAR_BLUE_CARD_POINTS,
# the Buena's Password quiz reward), not a flag either.
#
# Gated by a *scene-progress counter variable*
# (SaveVarsFlags.vars[], a different array than the flags this module
# reads), not a boolean flag: new_bark_elms_lab_1f_potion
# (scr_seq_0843_T20R0101.s), pallet_town_oaks_lab_jade_orb and
# route_30_mr_pokemon_house_mystery_egg (both gated by
# VAR_SCENE_EMBEDDED_TOWER, scr_seq_0740_T01R0301.s /
# scr_seq_0229_R30R0201.s). Detecting these would need a new, separate
# vars-array read mechanism (comparing a u16 value, not testing a bit) --
# a real, larger follow-up task, not attempted here.
#
# route_29_poke_ball and route_42_hm04 (see the real bug note above) are
# back in the "no known flag" state pending a real fix. ss_aqua_1f_
# northwest_rooms_metal_coat's only nearby SetFlag (FLAG_UNK_22A) was
# checked and rejected: it is set at every S.S. Aqua departure/arrival
# regardless of item pickup (scr_seq_0152_P01R0101.s,
# scr_seq_0154_P01R0103.s -- a generic ferry-state flag, not per-item).
# goldenrod_radio_tower_5f_basement_key's only nearby SetFlag is part of
# the scr_seq_0149.s mass-init batch (same class as the real bug above).
#
# Local delivery (ROM substitution) still works for all of
# these; fixing check-detection would need either a genuine per-
# interaction flag (not yet found) or an ARM/script-bytecode edit to inject a
# new flag write, out of this task's scope.


def flag_id_for_location(location_key: str) -> int | None:
    """The vanilla savedata flag id that fires when `location_key`'s check
    is triggered in-game, or None if this client can't currently observe
    it (shelved types, synthetic-id npc_gift band with no confirmed
    override)."""
    data = LOCATIONS.get(location_key)
    if data is None:
        raise KeyError(f"unknown location key: {location_key!r}")

    override = _SYNTHETIC_ID_FLAG_OVERRIDES.get(location_key)
    if override is not None:
        return override

    location_type = data["type"]
    raw_id = data.get("id")

    if location_type in SHELVED_LOCATION_TYPES or raw_id is None:
        return None
    if location_type in _DIRECT_FLAG_ID_TYPES:
        return None if raw_id >= _SYNTHETIC_ID_BASE else raw_id
    if location_type == "hidden_item":
        return HIDDEN_ITEMS_FLAG_BASE + raw_id
    if location_type == "trainer":
        # Every type = 'trainer' Trainersanity location is fought through
        # the one shared engine script (std_trainer/std_trainer_2 ->
        # scr_seq_0953.s), which derives the current trainer's own id at
        # runtime and unconditionally self-flags TRAINER_FLAG_BASE + that
        # id after every win (src/script_manager.c's SetTrainerFlag) -- a
        # real, reliable engine primitive for these ~390 ordinary trainers.
        return TRAINER_FLAG_BASE + TRAINERS[data["trainer"]]["id"]
    if location_type == "badge":
        # type = 'badge' (real bug found and fixed 2026-08-18): unlike
        # ordinary trainers, each of the 16 gym Leaders is fought through a
        # bespoke, hand-authored `TrainerBattle` call embedded directly in
        # that gym's own scripted cutscene -- never routed through
        # scr_seq_0953.s -- and a Leader's own win branch never calls
        # SetTrainerFlag on themselves. TRAINER_FLAG_BASE + their trainer
        # id is therefore NEVER actually set in-game for any of them (the
        # previous version of this branch assumed it was, which meant none
        # of the 16 badge locations could ever register as checked). The
        # override lookup above is the only source of truth for badge
        # locations now: a hand-verified per-gym sentinel flag, same
        # pattern as _SYNTHETIC_ID_FLAG_OVERRIDES's other entries. All 16
        # of the 16 now have one (6 reuse a pre-existing flag already set
        # in that Leader's own win branch; the other 10, which had no safe
        # pre-existing candidate, get a brand-new sentinel flag injected
        # directly into that Leader's own GiveBadge instruction site by
        # rom.badgedata.BADGE_SENTINEL_INJECTIONS -- see that dict's own
        # badge-section comment and build_badge_index_to_sentinel_flag_id's
        # docstring for the full derivation) -- so unlike 'trainer',
        # falling through to here (no override matched) should never
        # actually happen for a real badge location any more.
        return None
    if location_type == "static_pokemon":
        return _STATIC_POKEMON_FLAG_IDS[location_key]
    return None


def dexsanity_pokedex_bit_for_species(species_id: int) -> int:
    """0-indexed bit position of `species_id` (data/species.py's own `id`
    field, which equals its national_dex number for every real species --
    see species.real_species_pool) within Pokedex.caughtSpecies, per
    pokedex.c's CheckDexFlag/SetDexFlag: `flagId--; array[flagId>>3] &
    (1<<(flagId&7))` -- a 1-indexed input, decremented once, then the exact
    same byte/bit split save_layout.flag_byte_and_bit already uses for the
    (unrelated, 0-indexed) SaveVarsFlags.flags[] array."""
    return species_id - 1


def build_dexsanity_flag_to_ap_location_id() -> dict[int, int]:
    """Pokedex.caughtSpecies bit position -> AP location id, for every
    `type = 'dexsanity'` entry (task M3.4). A genuinely different savedata
    array/address than SaveVarsFlags.flags[] (Pokedex is its own SAVE_
    POKEDEX chunk) -- deliberately kept out of build_flag_id_to_ap_
    location_id/flag_id_for_location, whose single int-key space is
    SaveVarsFlags.flags[]-relative and would collide with an unrelated
    real flag id (e.g. bit 0x76 here is not FLAG id 0x76). client.py reads
    Pokedex.caughtSpecies into its own separate byte buffer and polls this
    map against that, the same is_flag_set call, different bytes/dict."""
    ap_ids = create_location_label_to_code_map()
    result: dict[int, int] = {}
    for key, data in LOCATIONS.items():
        if data["type"] != "dexsanity":
            continue
        ap_id = ap_ids.get(key)
        if ap_id is None:
            continue
        bit = dexsanity_pokedex_bit_for_species(SPECIES[data["species"]]["id"])
        result[bit] = ap_id
    return result


def build_flag_id_to_ap_location_id() -> dict[int, int]:
    """flag id -> AP location id, for every location this client can
    actually detect via a savedata flag read. Uses `locations.py`'s own id
    assignment (`create_location_label_to_code_map`) so the ids returned
    always match what `HeartGoldWorld.location_name_to_id` hands out."""
    ap_ids = create_location_label_to_code_map()
    result: dict[int, int] = {}
    for key in LOCATIONS:
        flag_id = flag_id_for_location(key)
        if flag_id is None:
            continue
        ap_id = ap_ids.get(key)
        if ap_id is None:
            raise KeyError(f"location {key!r} has a flag id but no AP location id")
        result[flag_id] = ap_id
    return result


def build_locally_substituted_ap_location_ids(*, remote_items: bool = False) -> set[int]:
    """AP location ids of every ground_item/npc_gift/hm_tm/hidden_item
    location that gets ROM-substituted with this player's own real item
    (the same set output_patch.build_item_substitutions can write a real
    item_key into) -- used by client.py to recognize a received item
    that was already physically delivered by ROM substitution, so it
    never gets written into the Bag a second time. See NOTES.md for the
    real double-delivery bug this fixes.

    `remote_items` (options.RemoteItems, off by default): when on,
    output_patch.build_item_substitutions stops embedding this player's
    own items into the ROM at all (always writes the "empty" sentinel,
    same as another player's item) -- delivery goes through the normal
    network path (_apply_received_items) instead, same as any other
    remote item. This function must mirror that decision exactly, or
    `_apply_received_items` would wrongly skip writing an item that was
    never actually placed in the ROM. The exception is
    `unsupported_location_keys()` (~30 locations with no real savedata
    flag this client can read at all): ROM substitution is their *only*
    possible delivery path regardless of remote_items (no check-detection
    means no network delivery path either), so they always stay in this
    set."""
    ap_ids = create_location_label_to_code_map()
    always_local_keys = frozenset(unsupported_location_keys()) if remote_items else None
    result: set[int] = set()
    for key, data in LOCATIONS.items():
        if data["type"] not in ("ground_item", "npc_gift", "hm_tm", "hidden_item"):
            continue
        if remote_items and key not in always_local_keys:
            continue
        ap_id = ap_ids.get(key)
        if ap_id is not None:
            result.add(ap_id)
    return result


def build_badge_index_to_sentinel_flag_id() -> dict[int, int]:
    """badge.h's own BADGE_* index (0-15) -> that gym Leader's own per-gym
    sentinel savedata flag id (a _SYNTHETIC_ID_FLAG_OVERRIDES entry) -- the
    *real* "have you actually beaten them" flag, as opposed to
    PlayerProfile's badge bit (which a multiworld can set from receiving
    the badge item at any location, independent of whether this player has
    personally fought that Leader yet).

    Originally (2026-08-17/18) this drove client.py, which deferred writing
    a received badge_* item's PlayerProfile bit until the Leader was
    actually beaten, because every gym Leader's own field script gated its
    `TrainerBattle` call behind `CheckBadge`. That deferral is gone as of
    2026-08-19: rom/badgegatedata.py rewrites those gates to test these
    sentinel flags directly, so the bit can be written on receipt and the
    two meanings stop fighting over one savedata bit. This function now
    serves as the canonical badge index -> sentinel map that
    rom.badgegatedata.SENTINEL_FLAGS is cross-checked against (see
    tests/test_badge_gate_regating.py), on top of the badge locations' own
    check detection, which reads the same flags through
    _SYNTHETIC_ID_FLAG_OVERRIDES.

    Replaces build_badge_index_to_trainer_flag_id (removed 2026-08-18):
    that function's entire premise -- that TRAINER_FLAG_BASE + a gym
    Leader's own trainer id gets engine-auto-flagged "the exact same way
    as any other trainer" -- was false. Every gym Leader is fought through
    a bespoke, hand-authored `TrainerBattle` call embedded directly in that
    gym's own scripted cutscene, never routed through the shared engine
    script (scr_seq_0953.s) that actually does the auto-flagging for
    ordinary Trainersanity trainers, and a Leader's own win branch never
    calls SetTrainerFlag on themselves -- so that flag was never actually
    set in-game for any of the 16, and neither this deferred-write
    mechanism nor the badge location's own check-detection
    (flag_id_for_location) could ever fire. Same class of fix as
    _SYNTHETIC_ID_FLAG_OVERRIDES's other entries: a hand-verified,
    corpus-unique sentinel flag straight from that Leader's own win branch,
    instead.

    All 16 gym Leaders now have a confirmed sentinel (task "Fix the
    remaining 10 gym badges", 2026-08-18). 6 reuse a confirmed, safe
    pre-existing flag (zephyr, plain, thunder, rising, volcano, earth --
    see _SYNTHETIC_ID_FLAG_OVERRIDES's own badge-section comment for the
    full per-gym citation). The other 10's own win branches were checked
    and every *pre-existing* candidate rejected: each only sets (a)
    SetTrainerFlag calls for *other* trainers' phone rematches (already
    claimed by those trainers' own Trainersanity locations, reusing one
    would falsely complete two locations at once), (b) a FLAG_GOT_TM<xx>_
    FROM_<leader> flag that is itself already claimed by that same gym's
    own separate hm_tm Trainersanity location for the TM the Leader also
    hands over (same collision risk, plus it is gated behind a
    `GoToIfNoItemSpace` bag-space check so it is not even truly
    unconditional), or (c) FLAG_HIDE_* room/NPC-visibility flags that get
    set *and cleared* several times through the script for ordinary
    movement/room-state reasons, not a reliable one-shot "just won"
    signal. Four of these ten (Whitney/Morty/Sabrina/Blue's own hm_tm-free
    candidate, FLAG_UNK_998) looked plausible in isolation but is
    corpus-wide reused by 12 different scripts -- a real collision, ruled
    out. Rather than force one of these unsafe candidates, these 10 get a
    brand-new sentinel flag instead (FLAG_UNK_B50..FLAG_UNK_B59, the
    unused tail of the flag array) injected directly into that Leader's
    own GiveBadge instruction site by rom.badgedata.
    BADGE_SENTINEL_INJECTIONS/write_all_badges_neutralized (a plain 4-byte
    instruction overwrite, `SetFlag <flag_id>` in place of `GiveBadge
    <badge>` -- see that module's own docstring for the full mechanism and
    why it's safe compared to an ARM hook). See _SYNTHETIC_ID_FLAG_
    OVERRIDES's own badge-section comment for the full per-gym citation of
    these 10 too."""
    from data.rules import BADGES

    result: dict[int, int] = {}
    for key, data in LOCATIONS.items():
        if data["type"] != "badge":
            continue
        flag_id = flag_id_for_location(key)
        if flag_id is None:
            continue
        badge_name = data["original_item"].removeprefix("badge_")
        result[BADGES[badge_name]] = flag_id
    return result


def unsupported_location_keys() -> list[str]:
    """Location keys with a real AP location that this client cannot
    detect via a savedata flag read. Exposed for diagnostics/logging, not
    used in the hot polling path. `event` locations are excluded: they are
    locked progression items granted directly by AP once their region is
    reachable, never polled for via a live RAM flag read at all (see
    locations.py's create_locations). `dexsanity` locations are also
    excluded: they ARE detectable, just through Pokedex.caughtSpecies (a
    separate savedata array/client.py code path, build_dexsanity_flag_to_
    ap_location_id above) rather than flag_id_for_location's SaveVarsFlags.
    flags[]-relative int, which is why flag_id_for_location itself has no
    'dexsanity' branch and would otherwise misreport them as unsupported.
    `badge` locations need no exclusion the way `dexsanity` does (they use
    the same SaveVarsFlags.flags[]-relative int as everything else here),
    and unlike the 2026-08-15 state, all 16 are now supported: every gym
    Leader has a confirmed sentinel flag in _SYNTHETIC_ID_FLAG_OVERRIDES
    (6 reuse a pre-existing flag, the other 10 get a freshly-injected one
    -- see that dict's own badge-section comment and build_badge_index_to_
    sentinel_flag_id's docstring for the full derivation)."""
    return sorted(
        key
        for key in LOCATIONS
        if LOCATIONS[key]["type"] not in ("event", "dexsanity")
        and LOCATIONS[key]["type"] not in SHELVED_LOCATION_TYPES
        and flag_id_for_location(key) is None
    )
