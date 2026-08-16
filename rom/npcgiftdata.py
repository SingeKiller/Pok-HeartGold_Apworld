# rom/npcgiftdata.py
#
# Read/write access to npc_gift (and the NPC-delivered half of hm_tm)
# item grants: unlike ground_item's single shared script bank, each of
# these is a literal operand embedded directly in that NPC's own per-map
# script file -- no shared block layout to derive an offset formula from,
# so this module hardcodes one small (narc sub-file index, byte offset)
# table instead (TABLE below), derived once and cross-checked against the
# real ROM -- see NOTES.md for the full derivation methodology and the
# GiveItemNoCheck/SetVar byte shape this relies on.
#
# NitroFS path: same NARC as rom/eventscriptdata.py, scr_seq.narc ->
# a/0/1/2. TABLE's indices are sub-file indices into that same NARC.

from __future__ import annotations

import struct

from rom import HeartGoldRom
from rom.eventscriptdata import NITROFS_PATH

ITEM_ID_OPERAND_OFFSET = 4

# `GiveItemNoCheck item, quantity` compiles to two back-to-back 6-byte
# SetVar instructions (VAR_SPECIAL_x8004 = item id, then
# VAR_SPECIAL_x8005 = quantity, see NOTES.md's derivation) -- the
# quantity operand's value always sits exactly one 6-byte SetVar
# instruction after the item-id operand's own value.
QUANTITY_OPERAND_OFFSET_FROM_ITEM_ID = 6

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
    # scr_seq_0890_T25R0201.s (Goldenrod Bike Shop): found live against
    # the real ROM (task "randomize_bicycle", 2026-08-17) -- byte-pattern
    # search for item id 450 (Bicycle) in narc sub-file 890 found exactly
    # one match, with the quantity operand 6 bytes later reading 1,
    # matching GiveItemNoCheck ITEM_BICYCLE, 1 exactly (see
    # location_flags.py's own FLAG_UNK_089 note for this same script's
    # check-detection flag).
    'goldenrod_bike_shop_bicycle': [(890, 105)],
    'goldenrod_flower_shop_squirtbottle': [(896, 425)],
    'goldenrod_gym_tm45': [(886, 456)],
    'goldenrod_radio_tower_2f_blue_card': [(30, 392)],
    'goldenrod_radio_tower_3f_tm11': [(31, 274)],
    'goldenrod_radio_tower_4f_brightpowder': [(32, 258)],
    'goldenrod_radio_tower_5f_basement_key': [(33, 513)],
    # 2 real sites (found live 2026-08-15, same class of bug as
    # route_30_apricorn_house_apricorn_box above): scr_seq_0750_T03.s
    # (Pewter City) has a second, alternate NPC trigger for the same
    # Rainbow Wing, guarded by (and granting) the exact same FLAG_UNK_093
    # -- data_gen/locations.toml's own header already documented this as
    # "the same check" (correct, since only one of the two can ever fire,
    # the other's own GoToIfSet guard skips it), but the original C4/C5
    # extraction only ever recorded the Goldenrod Radio Tower site in
    # TABLE, leaving this one unsubstituted.
    'goldenrod_radio_tower_observation_deck_rainbow_wing': [(34, 307), (750, 234)],
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
    # 2 real sites, not 1 (real bug found live 2026-08-15, see NOTES.md):
    # scr_seq_0227_R30.s (the outdoor route, obj_R30_gsmiddleman1's own
    # cutscene) ALSO does `GiveItemNoCheck ITEM_APRICORN_BOX, 1` then
    # `SetFlag FLAG_GOT_APRICORN_BOX` -- the exact same flag as the indoor
    # site below, confirmed by decomp source cross-reference and a real
    # ROM byte scan (narc 227, value-offset 347, full SetVar-pair pattern
    # verified). The original C4/C5 extraction only ever found the indoor
    # site; the outdoor one is a real, live-reachable second grant path
    # for the same location that was never substituted before this fix.
    'route_30_apricorn_house_apricorn_box': [(227, 347), (228, 32)],
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
    """Read the native item id currently sitting at a given
    (scr_seq.narc sub-file index, byte offset) pair -- see TABLE."""
    narc = rom.read_narc(NITROFS_PATH)
    blob = narc.files[narc_index]
    return struct.unpack_from("<H", blob, offset)[0]


def write_npc_gift_item_id(rom: HeartGoldRom, narc_index: int, offset: int, item_id: int) -> None:
    """Overwrite a single SetVar VAR_SPECIAL_x8004 operand in place,
    leaving every other byte byte-identical."""
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


def write_npc_gift_item_quantity(rom: HeartGoldRom, narc_index: int, item_id_offset: int, quantity: int) -> None:
    """Overwrite the SetVar VAR_SPECIAL_x8005 operand paired with the
    item-id operand at `item_id_offset` (see
    QUANTITY_OPERAND_OFFSET_FROM_ITEM_ID). Must be paired with
    write_npc_gift_item_id whenever the item id changes -- the vanilla
    quantity left in place otherwise still gets granted alongside the new
    item id (task M1.3)."""
    if not (0 <= quantity <= 0xFFFF):
        raise ValueError(
            f"quantity {quantity} does not fit this script's SetVar operand "
            "(an unsigned 16-bit value, 0-65535)."
        )
    narc = rom.read_narc(NITROFS_PATH)
    blob = bytearray(narc.files[narc_index])
    struct.pack_into("<H", blob, item_id_offset + QUANTITY_OPERAND_OFFSET_FROM_ITEM_ID, quantity)
    narc.files[narc_index] = bytes(blob)
    rom.write_narc(NITROFS_PATH, narc)


def _resolve_npc_gift_sites(location_key: str) -> list[tuple[int, int]]:
    """Shared validation for write_npc_gift_substitution/
    write_npc_gift_empty: resolve location_key to its TABLE script sites,
    or raise."""
    from data.locations import LOCATIONS

    location = LOCATIONS.get(location_key)
    if location is None:
        raise KeyError(f"unknown location key: {location_key!r}")
    if location["type"] not in ("npc_gift", "hm_tm"):
        raise NpcGiftDataError(
            f"location {location_key!r} is type {location['type']!r}, not "
            "'npc_gift'/'hm_tm' -- itemball-shaped hm_tm locations belong "
            "to rom/eventscriptdata.py's write_ground_item_substitution."
        )
    sites = TABLE.get(location_key)
    if sites is None:
        raise NpcGiftDataError(f"location {location_key!r} has no known npc_gift script site.")
    return sites


def write_npc_gift_substitution(rom: HeartGoldRom, location_key: str, item_key: str) -> None:
    """Patch every script site that grants a npc_gift location (or the
    NPC-delivered half of an hm_tm location) so it grants a different
    item instead of its vanilla original_item. Also pins each site's
    quantity operand to 1 -- an AP location grants exactly one of its
    placed item regardless of what quantity vanilla happened to give at
    that same spot (task M1.3; leaving the vanilla quantity in place
    would hand over e.g. 5 Master Balls if the original gift there was a
    5-Potion stack)."""
    from data.items import ITEMS

    sites = _resolve_npc_gift_sites(location_key)
    item = ITEMS.get(item_key)
    if item is None:
        raise KeyError(f"unknown item key: {item_key!r}")

    for narc_index, offset in sites:
        write_npc_gift_item_id(rom, narc_index, offset, item["id"])
        write_npc_gift_item_quantity(rom, narc_index, offset, 1)


def write_npc_gift_empty(rom: HeartGoldRom, location_key: str) -> None:
    """Patch every script site that grants location_key so it grants item
    id 0 instead of its vanilla original_item -- for locations whose
    placed item belongs to another multiworld player. Live-verified: an
    item-id-0 npc_gift shows a garbled "Obtained ???!" message but adds
    nothing real to the Bag, same outcome as the itemball case. Also
    zeroes each site's quantity operand (task M1.3): leaving the vanilla
    quantity in place produces a real, visible {id: 0, quantity: N} Bag
    slot once granted (src/bag.c's Pocket_GetItemSlotForAdd matches the
    first id-0 slot and does `slot->quantity += N` unconditionally), a
    blank-named stack the player can see and move around -- this is the
    confirmed root cause of the "blank name x5" tester report (route_29's
    Poke Ball site, see NOTES.md)."""
    sites = _resolve_npc_gift_sites(location_key)
    for narc_index, offset in sites:
        write_npc_gift_item_id(rom, narc_index, offset, 0)
        write_npc_gift_item_quantity(rom, narc_index, offset, 0)
