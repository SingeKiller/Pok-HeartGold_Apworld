# rom/npcgiftdata.py
#
# Read/write access to `npc_gift` (and the NPC-delivered half of `hm_tm`)
# item grants: unlike `ground_item`'s single shared script bank
# (rom/eventscriptdata.py's `scr_seq_0141.bin`), each of these is a literal
# operand embedded directly in that NPC's *own* per-map script file --
# there is no single shared block layout to derive an offset formula from,
# so this module hardcodes one small `(narc sub-file index, byte offset)`
# table instead (`TABLE` below), derived once and cross-checked against the
# real ROM (see this module's own docstring section below for exactly how),
# the same "derive once from the decomp + real ROM, hardcode the result"
# convention rom/eventscriptdata.py's `BLOCK_INDEX_BY_ITEMBALL_FLAG_ID`
# already uses.
#
# NitroFS path: same NARC as rom/eventscriptdata.py, `scr_seq.narc` ->
# `a/0/1/2` (see that module's docstring for the filesystem.mk mapping this
# was already verified against). `TABLE`'s indices are sub-file indices into
# that same NARC.
#
# -- How a vanilla npc_gift grant actually works (decomp investigation) --
#
# `asm/macros/script.inc`'s `GiveItemNoCheck item, quantity` macro (used by
# most npc_gift scripts, e.g.
# `files/fielddata/script/scr_seq/scr_seq_0228_R30R0101.s`'s
# `GiveItemNoCheck ITEM_APRICORN_BOX, 1`) expands, via the shared `ItemVars`
# macro, to two `SetVar` script commands (opcode 41, 6 bytes each: `.short
# 41`, `.short <var id>`, `.short <value>` -- same shape
# rom/eventscriptdata.py's docstring already documents for itemball blocks)
# followed by `CallStd std_give_item_verbose`:
#
#   SetVar VAR_SPECIAL_x8004, <item id>   -- the literal this module patches
#   SetVar VAR_SPECIAL_x8005, <quantity>
#   CallStd std_give_item_verbose         -- 4 bytes: .short 20, .short 2033
#
# (`ItemVars` only emits a literal `SetVar` when the operand is a compile-
# time constant, i.e. `\item < 0x4000` -- true for every real item id, which
# tops out at 536, so this holds for every location this module covers.)
# `GoToIfNoItemSpace`/`GoToIfNoItemSpace2` (used ahead of some grants, as an
# inventory-space precheck) expand through the very same `ItemVars` macro,
# so the same literal-`SetVar`-pair shape also shows up at a script's
# precheck site whenever one is used right before a bare `CallStd
# std_give_item_verbose` reuses those same vars instead of resetting them
# (confirmed against several locations, e.g.
# `scr_seq_0928_T27R0501.s`'s two `GoToIfNoItemSpace ITEM_HM03, 1, ...` /
# `CallStd std_give_item_verbose` pairs) -- this module's own derivation
# (below) does not need to tell the two shapes apart: both are a real,
# executable item-id operand feeding the same grant, so both get patched.
#
# The item-id operand this module patches is therefore the 2-byte
# unsigned-16-bit value at `SetVar`'s `+4` byte (2 bytes past the opcode+var
# id) -- `ITEM_ID_OPERAND_OFFSET` below, same offset convention as
# rom/eventscriptdata.py's own `ITEM_ID_OPERAND_OFFSET` (not reused
# directly to keep this module import-independent of that one).
#
# -- `TABLE` derivation methodology --
#
# For every `npc_gift` location, plus every `hm_tm` location whose flag id
# is *not* in rom/eventscriptdata.py's `BLOCK_INDEX_BY_ITEMBALL_FLAG_ID`
# (i.e. every `hm_tm` location that is *not* a plain item ball and so isn't
# already covered by `write_ground_item_substitution` -- see that module's
# own docstring; 36 of the 73 `hm_tm` locations fall in this NPC-delivered
# half):
#
#   1. Resolve the location's `data_gen/regions.toml` region to that
#      region's `map_code` (e.g. `route_30_apricorn_house` -> `R30R0101`).
#   2. Glob the decomp's `files/fielddata/script/scr_seq/` directory for
#      `scr_seq_<index>_<map_code>*.s` -- the per-map script source(s) for
#      that map (same "the numeric prefix is the compiled NARC sub-file
#      index" convention rom/eventscriptdata.py's docstring already
#      verified for `scr_seq_0141.bin`).
#   3. For each candidate sub-file index, read its *compiled* bytes from
#      the real ROM's `scr_seq.narc` and scan for the literal byte pattern
#      `SetVar VAR_SPECIAL_x8004, <original_item's numeric id>` (6 bytes)
#      immediately followed by another `SetVar VAR_SPECIAL_x8005, <...>`
#      (6 more bytes) -- i.e. the real, compiled operand shape above, not
#      just something that looks right in the decomp source.
#   4. Every such match is kept (not just the first): a handful of
#      locations have two independent, both-reachable script entry points
#      that each separately grant the same item under the same flag (two
#      NPC dialogue variants -- confirmed by reading the surrounding decomp
#      source for every one of these, see the 5 multi-entry `TABLE` values
#      below), so patching only one would leave the other vanilla.
#
# This resolved all 91 locations in scope unambiguously (every candidate
# match's immediately-following `SetVar VAR_SPECIAL_x8005` check held, and
# for locations with more than one match, reading the decomp source around
# each confirmed a real, independent grant site rather than a coincidental
# byte collision) -- no location in this task's scope was left unresolved,
# so `TABLE` has no "known gap" the way
# `BLOCK_INDEX_BY_ITEMBALL_FLAG_ID` has its block 58.

from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

ITEM_ID_OPERAND_OFFSET = 4

# location key (`data/locations.py`'s `LOCATIONS`, `npc_gift` or the
# NPC-delivered half of `hm_tm`) -> list of `(scr_seq.narc sub-file index,
# item-id byte offset)` pairs to patch. Almost every location has exactly
# one; see this module's docstring for the 5 that have two.
TABLE: dict[str, list[tuple[int, int]]] = {
    'azalea_charcoal_kiln_charcoal': [(873, 127)],
    'azalea_gym_tm89': [(869, 314)],
    'blackthorn_gym_tm59': [(943, 416)],
    'blackthorn_soft_sand': [(941, 346)],
    'celadon_condominiums_3f_gb_sounds': [(798, 656)],
    'celadon_condominiums_roof_room_spell_tag': [(800, 76)],
    'celadon_game_corner_coin_case': [(806, 447)],
    'celadon_gym_tm19': [(786, 384)],
    'cerulean_gym_tm03': [(760, 779)],
    'cianwood_gym_tm01': [(877, 179)],
    'cianwood_hm02': [(875, 107)],
    'cianwood_pharmacy_secretpotion': [(881, 98)],
    'dark_cave_route_45_side_blackglasses': [(108, 32)],
    'ecruteak_dance_theater_clear_bell': [(928, 2702)],
    'ecruteak_dance_theater_hm03': [(928, 1251), (928, 1340)],
    'ecruteak_dance_theater_tidal_bell': [(928, 2728)],
    'ecruteak_dowsing_machine_house_dowsing_mchn': [(929, 77)],
    'ecruteak_gym_tm30': [(922, 415)],
    'fuchsia_gym_tm84': [(809, 1875)],
    'goldenrod_flower_shop_squirtbottle': [(896, 425)],
    'goldenrod_gym_tm45': [(886, 456)],
    'goldenrod_radio_tower_2f_blue_card': [(30, 392)],
    'goldenrod_radio_tower_3f_tm11': [(31, 274)],
    'goldenrod_radio_tower_4f_brightpowder': [(32, 258)],
    'goldenrod_radio_tower_5f_basement_key': [(33, 513)],
    'goldenrod_radio_tower_observation_deck_rainbow_wing': [(34, 307)],
    'goldenrod_radio_tower_observation_deck_silver_wing': [(34, 338)],
    'goldenrod_tunnel_1f_fashion_case': [(93, 291), (93, 693)],
    'goldenrod_tunnel_warehouse_card_key': [(97, 79)],
    'ilex_forest_hm01': [(92, 4538), (92, 4718)],
    'lake_of_rage_black_belt': [(938, 748)],
    'lake_of_rage_hidden_power_house_tm10': [(939, 32)],
    'lake_of_rage_red_scale': [(938, 1063)],
    'mahogany_gym_leader_room_tm07': [(932, 322)],
    'mahogany_ragecandybar': [(930, 182), (930, 504)],
    'national_park_quick_claw': [(25, 859)],
    'new_bark_elms_lab_1f_everstone': [(843, 1526)],
    'new_bark_elms_lab_1f_potion': [(843, 1761), (843, 1794)],
    'new_bark_elms_lab_1f_s_s_ticket': [(843, 1329)],
    'olivine_gym_tm23': [(913, 466)],
    'olivine_northwest_house_good_rod': [(918, 68)],
    'pallet_town_oaks_lab_hm08': [(740, 660)],
    'pallet_town_oaks_lab_jade_orb': [(740, 1159)],
    'pewter_gym_tm80': [(752, 368)],
    'route_10_power_plant_broken_tm57': [(196, 200)],
    'route_12_fishing_brother_house_super_rod': [(200, 64)],
    'route_14_lucky_punch': [(202, 1566)],
    'route_25_nugget': [(216, 1301)],
    'route_27_house_tm37': [(222, 69)],
    'route_28_house_tm47': [(224, 261)],
    'route_29_poke_ball': [(225, 1303)],
    'route_29_twistedspoon': [(225, 219)],
    'route_2_house_nugget': [(171, 32)],
    'route_2_southeast_gatehouse_sacred_ash': [(172, 40)],
    'route_30_apricorn_house_apricorn_box': [(228, 32)],
    'route_30_mr_pokemon_house_exp_share': [(229, 330)],
    'route_30_mr_pokemon_house_mystery_egg': [(229, 143)],
    'route_31_violet_gatehouse_vs_recorder': [(231, 325)],
    'route_32_poison_barb': [(232, 293)],
    'route_32_pokecenter_1f_lure_ball': [(233, 231)],
    'route_32_pokecenter_1f_old_rod': [(233, 92)],
    'route_32_tm05': [(232, 534)],
    'route_34_ilex_forest_gatehouse_tm12': [(239, 42)],
    'route_36_berry_pots': [(243, 461)],
    'route_36_hard_stone': [(243, 1075)],
    'route_36_hm06': [(243, 1382)],
    'route_37_magnet': [(246, 170)],
    'route_39_moomoo_farm_house_tm83': [(250, 364)],
    'route_39_moomoo_farm_stable_seal_case': [(251, 133)],
    'route_40_sharp_beak': [(962, 194)],
    'route_42_hm04': [(252, 225)],
    'route_43_gatehouse_tm36': [(256, 481)],
    'route_5_house_cleanse_tag': [(183, 36)],
    'route_5_underground_path_tm64': [(181, 178)],
    'ruins_of_alph_underground_hall_unown_report': [(42, 272)],
    'saffron_copycat_house_2f_pass': [(841, 256)],
    'saffron_gym_tm48': [(829, 262)],
    'saffron_mr_psychic_house_tm29': [(833, 32)],
    'saffron_silph_co_hq_upgrade': [(837, 309)],
    'seafoam_islands_cinnabar_gym_tm50': [(15, 377)],
    'slowpoke_well_b2f_kings_rock': [(61, 36)],
    'sprout_tower_3f_tm70': [(18, 372)],
    'ss_aqua_1f_northwest_rooms_metal_coat': [(161, 193)],
    'ss_aqua_captain_room_flame_plate': [(157, 165)],
    'team_rocket_headquarters_b2f_hm05': [(90, 2325)],
    'vermilion_gym_tm34': [(778, 909)],
    'vermilion_pokemon_fan_club_rare_candy': [(782, 99)],
    'vermilion_pp_max': [(776, 529)],
    'violet_gym_tm51': [(859, 298)],
    'viridian_gym_tm92': [(743, 244)],
    'viridian_tm85': [(741, 290)],
}


class NpcGiftDataError(Exception):
    """Base class for every error this module raises."""


def read_npc_gift_item_id(rom: HeartGoldRom, narc_index: int, offset: int) -> int:
    """Read the native item id currently sitting at a given `(scr_seq.narc
    sub-file index, byte offset)` pair -- see `TABLE`."""
    narc = rom.read_narc(NITROFS_PATH)
    blob = narc.files[narc_index]
    return struct.unpack_from("<H", blob, offset)[0]


def write_npc_gift_item_id(rom: HeartGoldRom, narc_index: int, offset: int, item_id: int) -> None:
    """Overwrite a single `SetVar VAR_SPECIAL_x8004, <item id>` operand in
    place (see `TABLE`/this module's docstring), leaving every other byte
    -- including that same sub-file's own quantity operand, and every other
    sub-file -- byte-identical."""
    if not (0 <= item_id <= 0xFFFF):
        raise ValueError(
            f"item id {item_id} does not fit this script's SetVar operand "
            "(an unsigned 16-bit value, 0-65535)."
        )
    narc = rom.read_narc(NITROFS_PATH)
    blob = bytearray(narc.files[narc_index])
    struct.pack_into("<H", blob, offset, item_id)
    narc.files[narc_index] = bytes(blob)
    rom.write_narc(NITROFS_PATH, narc)


def _resolve_npc_gift_sites(location_key: str) -> list[tuple[int, int]]:
    """Shared validation for `write_npc_gift_substitution`/
    `write_npc_gift_empty`: resolve `location_key` (a `data/locations.py`
    key) to its `TABLE` script sites, or raise. Lazily imports
    `data.locations` (same reason as rom/eventscriptdata.py's own
    `_resolve_ground_item_block_index`)."""
    from data.locations import LOCATIONS

    location = LOCATIONS.get(location_key)
    if location is None:
        raise KeyError(f"unknown location key: {location_key!r}")
    if location["type"] not in ("npc_gift", "hm_tm"):
        raise NpcGiftDataError(
            f"location {location_key!r} is type {location['type']!r}, not "
            "'npc_gift'/'hm_tm' -- this module only patches NPC-delivered "
            "item grants (ground_item/hidden_item/badge are out of scope, "
            "see this task's own brief; itemball-shaped hm_tm locations "
            "belong to rom/eventscriptdata.py's write_ground_item_substitution)."
        )
    sites = TABLE.get(location_key)
    if sites is None:
        raise NpcGiftDataError(
            f"location {location_key!r} has no known npc_gift script site "
            "-- see this module's docstring for how TABLE was derived (it "
            "covers every npc_gift/NPC-delivered hm_tm location as of this "
            "task, so this should not happen for a real location key)."
        )
    return sites


def write_npc_gift_substitution(rom: HeartGoldRom, location_key: str, item_key: str) -> None:
    """Patch every script site that grants a `npc_gift` location (or the
    NPC-delivered half of a `hm_tm` location -- see this module's
    docstring) so it grants a different item instead of its vanilla
    `original_item`. Lazily imports `data.items` (same reason as
    rom/eventscriptdata.py's own `write_ground_item_substitution`)."""
    from data.items import ITEMS

    sites = _resolve_npc_gift_sites(location_key)
    item = ITEMS.get(item_key)
    if item is None:
        raise KeyError(f"unknown item key: {item_key!r}")

    for narc_index, offset in sites:
        write_npc_gift_item_id(rom, narc_index, offset, item["id"])


def write_npc_gift_empty(rom: HeartGoldRom, location_key: str) -> None:
    """Patch every script site that grants `location_key` so it grants item
    id 0 instead of its vanilla `original_item` -- used for locations whose
    placed item belongs to *another* multiworld player (see
    `output_patch.build_item_substitutions`'s own docstring): live-verified
    (2026-08-11, see docs/architecture.md) that an item-id-0 npc_gift shows
    a garbled "Obtained ???!" message but adds nothing real to the Bag
    (confirmed empty afterwards), same outcome as the itemball case in
    `rom/eventscriptdata.write_ground_item_empty`."""
    sites = _resolve_npc_gift_sites(location_key)
    for narc_index, offset in sites:
        write_npc_gift_item_id(rom, narc_index, offset, 0)
