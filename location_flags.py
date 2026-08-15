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
}

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
    if location_type in ("trainer", "badge"):
        # type = 'badge' (task "Badges comme vrais items AP", 2026-08-15):
        # defeating the gym Leader is itself a std_trainer-class battle
        # (TrainerBattle scrcmd, engine-auto-flagged the exact same way as
        # any other trainer -- see data_gen/locations.toml's badge-section
        # header for why it was never one of the 390 Trainersanity
        # locations despite using the same underlying flag mechanism).
        return TRAINER_FLAG_BASE + TRAINERS[data["trainer"]]["id"]
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


def build_locally_substituted_ap_location_ids() -> set[int]:
    """AP location ids of every ground_item/npc_gift/hm_tm/hidden_item
    location (the same set output_patch.build_item_substitutions can
    ROM-substitute) -- used by client.py to recognize a received item
    that was already physically delivered by ROM substitution, so it
    never gets written into the Bag a second time. See NOTES.md for the
    real double-delivery bug this fixes."""
    ap_ids = create_location_label_to_code_map()
    result: set[int] = set()
    for key, data in LOCATIONS.items():
        if data["type"] not in ("ground_item", "npc_gift", "hm_tm", "hidden_item"):
            continue
        ap_id = ap_ids.get(key)
        if ap_id is not None:
            result.add(ap_id)
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
    `badge` locations need no such exclusion: flag_id_for_location has a
    real 'badge' branch (TRAINER_FLAG_BASE, same as 'trainer'), so they
    are never unsupported in the first place."""
    return sorted(
        key
        for key in LOCATIONS
        if LOCATIONS[key]["type"] not in ("event", "dexsanity")
        and LOCATIONS[key]["type"] not in SHELVED_LOCATION_TYPES
        and flag_id_for_location(key) is None
    )
