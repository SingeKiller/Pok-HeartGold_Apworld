from __future__ import annotations

import base64
import json
import logging
import os
import pkgutil
import struct
from typing import TYPE_CHECKING

import worlds._bizhawk as bizhawk
from NetUtils import ClientStatus
from worlds._bizhawk.client import BizHawkClient

from data.items import ITEMS
from data.rules import BADGES
from items import HEARTGOLD_ITEM_ID_BASE
from location_flags import (
    VAR_CHECKED_LOCATIONS,
    build_dexsanity_flag_to_ap_location_id,
    flag_id_for_location,
    build_flag_id_to_ap_location_id,
    build_locally_substituted_ap_location_ids,
)
from rom import HEARTGOLD_US_ID_CODE, SOULSILVER_US_ID_CODE
from rom.deathlinkdata import FLAG_AP_DEATHLINK, FLAG_AP_DEATHLINK_WHITEOUT, FLAG_AP_WHITED_OUT
from rom.startlocation import (
    REVOCATION_RECORD_ROM_OFFSET,
    REVOCATION_RECORD_SIZE,
    parse_revocation_record,
)
from rom.worldsignature import (
    DEATHLINK_SCRIPTS_ROM_OFFSET,
    DEATHLINK_SCRIPTS_TAG,
    SLOT_AUTH_ROM_OFFSET,
    SLOT_AUTH_SIZE,
    WORLD_SIGNATURE_ROM_OFFSET,
    WORLD_SIGNATURE_SIZE,
    has_world_signature,
)
from save_layout import (
    BAG_POCKET_OFFSETS,
    BAG_SIZE,
    BATTLE_SCENE_BIT,
    FLAGS_ARRAY_OFFSET,
    FLAGS_ARRAY_SIZE,
    POCKET_KEY_TO_BAG_FIELD,
    TEXT_SPEED_FAST_VALUE,
    TEXT_SPEED_MASK,
    flag_byte_and_bit,
    is_flag_set,
    plan_bag_item_write,
    stack_cap_for_pocket,
)
from universal_tracker import SLOT_DATA_OPTIONS_KEY

if TYPE_CHECKING:
    from worlds._bizhawk.context import BizHawkClientContext

HEARTGOLD_BAG_BASE_ADDRESS_ENV = "HEARTGOLD_BAG_BASE_ADDRESS"
HEARTGOLD_FLAGS_ARRAY_ADDRESS_ENV = "HEARTGOLD_FLAGS_ARRAY_ADDRESS"


def _resolve_address_override(env_var: str) -> int | None:
    raw = os.environ.get(env_var)
    if not raw:
        return None
    try:
        return int(raw, 0)
    except ValueError:
        return None


_SAVE_ARRAY_HEADER_SIZE = 16
_SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT = 5
_DYNAMIC_REGION_SIZE = 35 * 0x1000
_SAVE_COUNTER_SIZE = 4
_BAG_CHUNK_ID = 3
_FLAGS_CHUNK_ID = 4
_POKEDEX_CHUNK_ID = 6
_PARTY_CHUNK_ID = 2
_GAMESTATS_CHUNK_ID = 16

_GAMESTATS_SECURE_REGION_OFFSET = 8
_GAMESTATS_CHECKSUM_OFFSET = 444
_GAMESTATS_KEY_HIGH_OFFSET = 446
_GAMESTATS_LCRNG_MULTIPLIER = 1103515245
_GAMESTATS_LCRNG_INCREMENT = 24691

_GAME_STAT_BATTLE_STARTS_OFFSET = 32
_BATTLE_HOLD_TICKS = 90
_BATTLE_WATCH_TICKS = 1800
_PARTY_STRUCT_SIZE = 8 + 6 * 0xEC

_DEATHLINK_FLAGS_BYTE = flag_byte_and_bit(FLAG_AP_DEATHLINK)[0]
_FLAG_SYS_SAFARI = 0x967
_DEATHLINK_STALL_TICKS = 10
_ROAMER_CHUNK_ID = 21
_ROAMER_REPEL_STEPS_OFFSET = 8 + 8 + 4 * 20 + 4 + 1

_POKEDEX_CAUGHT_SPECIES_OFFSET = 4
_POKEDEX_CAUGHT_SPECIES_SIZE = 64

_POKEDEX_MAGIC_OFFSET = 0
_POKEDEX_MAGIC = 0xBEEFCAFE

_PLAYERDATA_CHUNK_ID = 1

_PLAYERDATA_PROFILE_OFFSET = 4

_PLAYERDATA_OPTIONS_OFFSET = 0
_PROFILE_MONEY_OFFSET = 20
_PROFILE_JOHTO_BADGES_OFFSET = 26
_PROFILE_KANTO_BADGES_OFFSET = 31
_MAX_MONEY = 999999

_ARRAY_HEADERS_SCAN_START = 0x02298000
_ARRAY_HEADERS_SCAN_LENGTH = 0x10000
_ARRAY_HEADERS_SCAN_READ_CHUNK = 0x4000


async def _read_chunked(ctx: BizHawkClientContext, address: int, length: int, domain: str) -> bytes:
    out = bytearray()
    offset = 0
    while offset < length:
        step = min(_ARRAY_HEADERS_SCAN_READ_CHUNK, length - offset)
        piece = (await bizhawk.read(ctx.bizhawk_ctx, [(address + offset, step, domain)]))[0]
        out.extend(piece)
        offset += step
    return bytes(out)


def _looks_like_array_headers(data: bytes, offset: int) -> bool:
    needed = _SAVE_ARRAY_HEADER_SIZE * _SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT
    if offset + needed > len(data):
        return False
    for chunk_id in range(_SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT):
        record_offset = offset + chunk_id * _SAVE_ARRAY_HEADER_SIZE
        (record_id,) = struct.unpack_from("<i", data, record_offset)
        if record_id != chunk_id:
            return False
    return True


def _find_array_headers_candidates(data: bytes) -> list[int]:
    needed = _SAVE_ARRAY_HEADER_SIZE * _SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT
    return [offset for offset in range(0, len(data) - needed, 4) if _looks_like_array_headers(data, offset)]


async def _find_array_headers_address(ctx: BizHawkClientContext) -> int | None:
    data = await _read_chunked(ctx, _ARRAY_HEADERS_SCAN_START, _ARRAY_HEADERS_SCAN_LENGTH, "ARM9 System Bus")
    candidates = _find_array_headers_candidates(data)
    return _ARRAY_HEADERS_SCAN_START + candidates[0] if candidates else None


async def _chunk_offset(ctx: BizHawkClientContext, array_headers_address: int, chunk_id: int) -> int:
    record_address = array_headers_address + chunk_id * _SAVE_ARRAY_HEADER_SIZE
    record_bytes = (
        await bizhawk.read(ctx.bizhawk_ctx, [(record_address, _SAVE_ARRAY_HEADER_SIZE, "ARM9 System Bus")])
    )[0]
    _record_id, _size, offset, _crc, _slot = struct.unpack("<iIIHH", bytes(record_bytes))
    return offset


_MAX_PLAUSIBLE_ITEM_ID = 536
_MAX_PLAUSIBLE_ITEM_QUANTITY = 999
_PLAUSIBILITY_CHECK_SLOT_COUNT = 8


async def _bag_looks_plausible(ctx: BizHawkClientContext, bag_address: int) -> bool:
    slot_bytes = (
        await bizhawk.read(ctx.bizhawk_ctx, [(bag_address, _PLAUSIBILITY_CHECK_SLOT_COUNT * 4, "ARM9 System Bus")])
    )[0]
    for i in range(_PLAUSIBILITY_CHECK_SLOT_COUNT):
        item_id, quantity = struct.unpack_from("<HH", bytes(slot_bytes), i * 4)
        if item_id == 0:
            continue
        if not (1 <= item_id <= _MAX_PLAUSIBLE_ITEM_ID and quantity <= _MAX_PLAUSIBLE_ITEM_QUANTITY):
            return False
    return True


async def _locate_save_addresses(
    ctx: BizHawkClientContext,
) -> tuple[int, int, int, int, int, int, int] | None:
    data = await _read_chunked(ctx, _ARRAY_HEADERS_SCAN_START, _ARRAY_HEADERS_SCAN_LENGTH, "ARM9 System Bus")

    candidates = [_ARRAY_HEADERS_SCAN_START + offset for offset in _find_array_headers_candidates(data)]
    with_magic = [address for address in candidates if await _pokedex_magic_ok(ctx, address)]
    for array_headers_address in with_magic + [address for address in candidates if address not in with_magic]:
        dynamic_region_base = array_headers_address - _SAVE_COUNTER_SIZE - _DYNAMIC_REGION_SIZE
        bag_chunk_offset = await _chunk_offset(ctx, array_headers_address, _BAG_CHUNK_ID)
        bag_address = dynamic_region_base + bag_chunk_offset

        if array_headers_address not in with_magic and not await _bag_looks_plausible(ctx, bag_address):
            continue

        flags_chunk_offset = await _chunk_offset(ctx, array_headers_address, _FLAGS_CHUNK_ID)
        flags_array_address = dynamic_region_base + flags_chunk_offset + FLAGS_ARRAY_OFFSET
        pokedex_chunk_offset = await _chunk_offset(ctx, array_headers_address, _POKEDEX_CHUNK_ID)
        pokedex_caught_species_address = dynamic_region_base + pokedex_chunk_offset + _POKEDEX_CAUGHT_SPECIES_OFFSET
        playerdata_chunk_offset = await _chunk_offset(ctx, array_headers_address, _PLAYERDATA_CHUNK_ID)
        playerdata_profile_address = dynamic_region_base + playerdata_chunk_offset + _PLAYERDATA_PROFILE_OFFSET
        party_chunk_offset = await _chunk_offset(ctx, array_headers_address, _PARTY_CHUNK_ID)
        party_address = dynamic_region_base + party_chunk_offset
        gamestats_chunk_offset = await _chunk_offset(ctx, array_headers_address, _GAMESTATS_CHUNK_ID)
        gamestats_address = dynamic_region_base + gamestats_chunk_offset
        return (
            bag_address,
            flags_array_address,
            pokedex_caught_species_address,
            playerdata_profile_address,
            array_headers_address,
            party_address,
            gamestats_address,
        )

    return None


async def _pokedex_magic_ok(ctx: BizHawkClientContext, array_headers_address: int) -> bool:
    dynamic_region_base = array_headers_address - _SAVE_COUNTER_SIZE - _DYNAMIC_REGION_SIZE
    try:
        pokedex_offset = await _chunk_offset(ctx, array_headers_address, _POKEDEX_CHUNK_ID)
        raw = (
            await bizhawk.read(
                ctx.bizhawk_ctx, [(dynamic_region_base + pokedex_offset + _POKEDEX_MAGIC_OFFSET, 4, "ARM9 System Bus")]
            )
        )[0]
    except bizhawk.RequestFailedError:
        return False
    return struct.unpack("<I", bytes(raw))[0] == _POKEDEX_MAGIC


async def _array_headers_still_valid(ctx: BizHawkClientContext, array_headers_address: int) -> bool:
    signature_size = _SAVE_ARRAY_HEADER_SIZE * _SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT
    try:
        data = (
            await bizhawk.read(ctx.bizhawk_ctx, [(array_headers_address, signature_size, "ARM9 System Bus")])
        )[0]
    except bizhawk.RequestFailedError:
        return False
    return _looks_like_array_headers(bytes(data), 0)


_APPLIED_ITEM_COUNT_KEY_TEMPLATE = "pokemon_heartgold_applied_item_count_{team}_{slot}_{trainer_id}"

_STARTING_MONEY_APPLIED_KEY_TEMPLATE = "pokemon_heartgold_starting_money_applied_{team}_{slot}_{trainer_id}"

_DELIVERED_AHEAD_KEY_TEMPLATE = "pokemon_heartgold_delivered_ahead_{team}_{slot}_{trainer_id}"


def _indices_from_mask(mask: int) -> set[int]:
    return {index for index in range(mask.bit_length()) if (mask >> index) & 1}


def _pack_item_count(count: int, ahead_mask: int) -> bytes:
    return struct.pack("<HHHH", count, _AP_ITEMS_MARKER, ahead_mask & 0xFFFF, ahead_mask >> 16 & 0xFFFF)


def _mask_from_indices(indices: set[int]) -> int:
    mask = 0
    for index in indices:
        mask |= 1 << index
    return mask

_START_LOCATION_FLAG_GOT_STARTER = 0x6A
_START_LOCATION_FLAGS_TO_SET = (
    0x6B,
    0x9C,
    0x190,
)
_START_LOCATION_FLAGS_TO_CLEAR = (0x19C,)

_START_LOCATION_MAP_NEW_BARK = 60
_START_LOCATION_MAP_ELMS_LAB = 61
_START_LOCATION_HOME_MAP_IDS = (_START_LOCATION_MAP_NEW_BARK, _START_LOCATION_MAP_ELMS_LAB)

_LOCAL_FIELD_DATA_CHUNK_ID = 5
_LOCAL_FIELD_DATA_CURRENT_MAP_ID_OFFSET = 0

_LOCAL_FIELD_DATA_LAST_SPAWN_OFFSET = 104
_LOCAL_FIELD_DATA_HAS_RUNNING_SHOES_OFFSET = 108

_POKEGEAR_CHUNK_ID = 34
_POKEGEAR_CARDS_WORD_OFFSET = 4
_POKEGEAR_MAP_CARD_BIT = 1 << 25

_JOHTO_FLY_POINT_FLAGS = range(0x9BB, 0x9C6)

_START_GIFTS = {
    "running_shoes_at_start": (_LOCAL_FIELD_DATA_CHUNK_ID, _LOCAL_FIELD_DATA_HAS_RUNNING_SHOES_OFFSET, 1),
    "map_card_at_start": (_POKEGEAR_CHUNK_ID, _POKEGEAR_CARDS_WORD_OFFSET, _POKEGEAR_MAP_CARD_BIT),
}
_SPAWN_ID_NEW_BARK = 1
_START_LOCATION_TOWN_SPAWN_IDS: dict[str, int] = {
    "cherrygrove": 2,
    "violet": 3,
    "azalea": 4,
    "cianwood": 5,
    "goldenrod": 6,
    "olivine": 7,
    "ecruteak": 8,
    "mahogany": 9,
    "blackthorn": 11,
}
_BLACKOUT_SPAWN_LATCH_FLAG = 0x531

_FLAG_RESTORED_POWER = 0x118
_POWER_PLANT_FLAGS_TO_SET = (
    _FLAG_RESTORED_POWER,
    0x258,
)
_POWER_PLANT_FLAGS_TO_CLEAR = (0x259,)
_TM57_RESTORE_MARKER = 0x543
_COPYCAT_CHAIN_VAR = 0x40FF
_COPYCAT_CHAIN_FLAGS_TO_SET = (0x2FB,)
_COPYCAT_CHAIN_FLAGS_TO_CLEAR = (0x2FC,)
_CERULEAN_CHAIN_VAR = 0x411C
_CERULEAN_CHAIN_VAR_VALUE = 1
_CERULEAN_CHAIN_FLAGS_TO_CLEAR = (0x254,)
_VAR_BASE = 0x4000

_BADGE_THUNDER_INDEX = 10
_FLAG_HIDE_VERMILION_GYM_STOPS = 0x31A
_MAP_VERMILION = 54
_MAP_VERMILION_GYM = 365
_THUNDER_BADGE_WITHHELD_MAP_IDS = (_MAP_VERMILION, _MAP_VERMILION_GYM)

_GOAL_ELITE_FOUR = 0
_GOAL_CHAMPION_RED = 1
_GOAL_N_BADGES = 2
_JOHTO_BADGE_COUNT = 8
_FLAG_GAME_CLEAR = 0x964
_FLAG_RED_DEFEATED = 0x25F
_VAR_RED_DEFEATED = 0x40FD

_MAX_ITEMS_APPLIED_PER_TICK = 20
_RECEIVED_MESSAGES_PER_TICK = 3
_CHECK_RESEND_TICKS = 10

_BAG_WRITE_FAILURES_BEFORE_RELOCATE = 3

_VAR_SCENE_ROCKET_TAKEOVER = 0x4077
_VAR_MIDGAME_BADGES = 0x4134
_VAR_KIMONO_CHAIN = 0x4079
_VAR_DANCE_THEATER = 0x410C
_VAR_SCENE_ELMS_LAB = 0x4108
_VAR_SCENE_MR_POKEMONS_HOUSE = 0x4107
_FLAG_DRAGONS_DEN_SHRINE_DONE = 0xEA
_FLAG_ELMS_LAB_CLAIR_SCENE_DONE = 0x23B
_VAR_SCENE_LIGHTHOUSE_JASMINE = 0x40A5
_FLAG_GOT_SECRETPOTION = 0xB9
_FLAG_LIGHTHOUSE_BARRIER_OPEN = 0x1D8
_BOX_LEGENDARY_FLAGS = ((0x108, 0x116, 0x242), (0x109, 0x117, 0x243))
_BELL_GIVEN_FLAGS = (0x103, 0x104)
_VAR_AZALEA_ROCKET_SCENE = 0x4080
_FLAG_KURT_LEFT = 0x19E
_FLAG_HIDE_WELL_GUARD = 0x19F
_AZALEA_SCENE_NPC_FLAGS = (0x271, 0x272)
_STORY_FLAGS_SPAN = 0x50
_MIDGAME_LEADER_BADGE_KEYS = (
    "ecruteak_gym_badge", "cianwood_gym_badge", "olivine_gym_badge", "mahogany_gym_leader_room_badge",
)

_VAR_AP_ITEMS_APPLIED = 0x416C
_VAR_AP_ITEMS_MARKER = 0x416D
_AP_ITEMS_MARKER = 0xA7C5
_VAR_AP_ITEMS_AHEAD = 0x416E
_DELIVERED_AHEAD_WINDOW = 32
_ITEMS_POCKET_KEPT_FREE = 1

_WING_PASS_FLAGS = {"rainbow_wing": (0x532, 0xB5B), "silver_wing": (0x533, 0xB5C)}
_PEWTER_WING_LEGENDARY = {
    "heartgold": ("silver_wing", 0x243, 0x117),
    "soulsilver": ("rainbow_wing", 0x242, 0x116),
}


def _pocket_looks_plausible(pocket_bytes: bytes) -> bool:
    for offset in range(0, len(pocket_bytes), 4):
        item_id, quantity = struct.unpack_from("<HH", pocket_bytes, offset)
        if item_id == 0:
            continue
        if not (1 <= item_id <= _MAX_PLAUSIBLE_ITEM_ID and quantity <= _MAX_PLAUSIBLE_ITEM_QUANTITY):
            return False
    return True


def _build_ap_item_id_to_bag_write_info() -> dict[int, tuple[int, str]]:
    result: dict[int, tuple[int, str]] = {}
    for data in ITEMS.values():
        bag_field = POCKET_KEY_TO_BAG_FIELD.get(data["pocket"])
        if bag_field is None:
            continue
        result[HEARTGOLD_ITEM_ID_BASE + data["id"]] = (data["id"], bag_field)
    return result


_AP_ITEM_ID_TO_BAG_WRITE_INFO = _build_ap_item_id_to_bag_write_info()

_TAKEN_BY_SCRIPTS = frozenset(
    {"red_scale", "mystery_egg", "secretpotion", "ragecandybar", "machine_part", "lost_item", "enigma_stone"}
)
_KEPT_ITEM_AP_IDS = frozenset(
    HEARTGOLD_ITEM_ID_BASE + data["id"]
    for key, data in ITEMS.items()
    if (data["pocket"] == "key_items" and key not in _TAKEN_BY_SCRIPTS) or key.startswith("hm0")
)
_KEY_ITEM_CHECK_EVERY_TICKS = 10


def _build_ap_item_id_to_badge_index() -> dict[int, int]:
    result: dict[int, int] = {}
    for key, data in ITEMS.items():
        if data["pocket"] != "badge":
            continue
        badge_name = key.removeprefix("badge_")
        result[HEARTGOLD_ITEM_ID_BASE + data["id"]] = BADGES[badge_name]
    return result


_AP_ITEM_ID_TO_BADGE_INDEX = _build_ap_item_id_to_badge_index()


_FLAG_ID_TO_AP_LOCATION_ID = build_flag_id_to_ap_location_id()

_DEXSANITY_FLAG_ID_TO_AP_LOCATION_ID = build_dexsanity_flag_to_ap_location_id()
_DEXSANITY_AP_LOCATION_IDS = frozenset(_DEXSANITY_FLAG_ID_TO_AP_LOCATION_ID.values())


def _build_version_bound_checks() -> tuple[dict[int, int], int | None]:
    from locations import create_location_label_to_code_map

    ids = create_location_label_to_code_map()
    clear_bell = ids.get("ecruteak_dance_theater_clear_bell")
    tidal_bell = ids.get("ecruteak_dance_theater_tidal_bell")
    companions = {}
    if clear_bell is not None and tidal_bell is not None:
        companions = {clear_bell: tidal_bell, tidal_bell: clear_bell}
    return companions, ids.get("goldenrod_game_corner_jp_tm78")


_COMPANION_AP_LOCATION_IDS, _GAME_CORNER_JP_TM78_AP_ID = _build_version_bound_checks()
_MAP_GOLDENROD_GAME_CORNER = 536


def _build_flag_upkeep() -> tuple[dict[int, tuple[int, ...]], dict[int, int], dict[int, tuple[int, int]]]:
    from locations import create_location_label_to_code_map
    from rom import badgedata, giftflagdata, npcgiftgatedata

    ids = create_location_label_to_code_map()
    upkeep: dict[int, tuple[int, ...]] = {}
    new_to_badge = {flag: badge for badge, flag in badgedata.BADGE_SENTINEL_INJECTIONS.items()}
    for key in ids:
        try:
            flag = flag_id_for_location(key)
        except KeyError:
            continue
        if flag in new_to_badge:
            upkeep[ids[key]] = (flag, badgedata.LEGACY_BADGE_SENTINEL_INJECTIONS[new_to_badge[flag]])
    for key, flag in giftflagdata.GIFT_FLAGS.items():
        upkeep[ids[key]] = (flag,)

    aliases = {legacy: ids[key] for key, legacy in npcgiftgatedata.LEGACY_GATE_FLAGS.items()}
    aliases[0x9A] = ids["route_29_poke_ball"]

    var_checks = {
        ids["new_bark_elms_lab_1f_potion"]: (0x4108, 2),
        ids["pallet_town_oaks_lab_jade_orb"]: (0x40F9, 5),
        ids["ss_aqua_1f_northwest_rooms_metal_coat"]: (0x40CB, 6),
        **{ids[key]: check for key, check in VAR_CHECKED_LOCATIONS.items()},
        ids["ss_aqua_captain_room_flame_plate"]: (0x4101, 1),
        ids["goldenrod_gym_badge"]: (0x410A, 1),
    }
    return upkeep, aliases, var_checks


_UPKEEP_FLAGS_BY_AP_ID, _ALIAS_FLAG_TO_AP_ID, _VAR_CHECKS = _build_flag_upkeep()


def _build_location_key_to_ap_id() -> dict[str, int]:
    from locations import create_location_label_to_code_map

    return create_location_label_to_code_map()


_LOCATION_KEY_TO_AP_ID = _build_location_key_to_ap_id()
_TM57_AP_ID = _LOCATION_KEY_TO_AP_ID["route_10_power_plant_broken_tm57"]


def _build_never_given_in_game() -> dict[bool, frozenset[int]]:
    from locations import create_location_label_to_code_map

    ids = create_location_label_to_code_map()
    result = {}
    for soulsilver in (False, True):
        keys = ["goldenrod_game_corner_jp_tm78",
                "ecruteak_dance_theater_clear_bell" if soulsilver else "ecruteak_dance_theater_tidal_bell"]
        result[soulsilver] = frozenset(ids[key] for key in keys if key in ids)
    return result


_NEVER_GIVEN_IN_GAME = _build_never_given_in_game()


def _never_given_in_game(ctx: BizHawkClientContext) -> frozenset[int]:
    return _NEVER_GIVEN_IN_GAME[(ctx.slot_data.get("options") or {}).get("game_version") == 1]


_TAKEOVER_OVER = 5
_FLAG_SUDOWOODO_CLEARED = 0xB5
_MISSABLE_GIFTS = {
    "goldenrod_radio_tower_5f_basement_key": (0x53C, ("var", _VAR_SCENE_ROCKET_TAKEOVER, _TAKEOVER_OVER)),
    "goldenrod_tunnel_warehouse_card_key": (0x53D, ("var", _VAR_SCENE_ROCKET_TAKEOVER, _TAKEOVER_OVER)),
    "goldenrod_flower_shop_squirtbottle": (0x53E, ("flag", _FLAG_SUDOWOODO_CLEARED)),
    "cianwood_pharmacy_secretpotion": (0x53F, ("item", "secretpotion", (0xB9,))),
}
_VAR_BASEMENT_KEY_GIVEN = (0x40E7, 2)
_MISSABLE_TRAINER_GROUPS = (
    ("TAKEOVER_TRAINER_KEYS", ("var", _VAR_SCENE_ROCKET_TAKEOVER, _TAKEOVER_OVER)),
    ("LIGHTHOUSE_4F_TRAINER_KEYS", ("var", 0x40A5, 2)),
    ("HIDEOUT_TRAINER_KEYS", ("flag", 0x1F2)),
    ("SLOWPOKE_WELL_TRAINER_KEYS", ("flag", 0x1A9)),
    ("NEVER_PRESENT_TRAINER_KEYS", ("always",)),
)


def _build_missable_checks() -> tuple[tuple[tuple[frozenset[int], tuple], ...], dict[int, tuple[tuple[int, ...], int, tuple]]]:
    import locations
    from locations import create_location_label_to_code_map
    from rom import npcgiftgatedata

    ids = create_location_label_to_code_map()
    gifts = {}
    for key, (marker, trigger) in _MISSABLE_GIFTS.items():
        given = {
            flag_id_for_location(key), npcgiftgatedata.GATE_FLAGS.get(key), npcgiftgatedata.LEGACY_GATE_FLAGS.get(key)
        }
        gifts[ids[key]] = (tuple(sorted(flag for flag in given if flag is not None)), marker, trigger)
    trainers = tuple(
        (frozenset(ids[key] for key in getattr(locations, name)), trigger) for name, trigger in _MISSABLE_TRAINER_GROUPS
    )
    return trainers, gifts


_MISSABLE_TRAINERS, _MISSABLE_GIFTS_BY_AP_ID = _build_missable_checks()
_BASEMENT_KEY_AP_ID = _LOCATION_KEY_TO_AP_ID["goldenrod_radio_tower_5f_basement_key"]

_MAX_IMMEDIATE_CHECK_BATCH = 4

_MAX_PLAUSIBLE_FLAG_DENSITY = 0.85

_DEXSANITY_UNUSED_BITS = range(493, 504)


def _flags_read_looks_sane(flags_bytes: bytes) -> bool:
    if len(flags_bytes) != FLAGS_ARRAY_SIZE:
        return False
    if len(set(flags_bytes)) == 1 and flags_bytes[0] != 0:
        return False
    set_bits = sum(byte.bit_count() for byte in flags_bytes)
    return set_bits <= _MAX_PLAUSIBLE_FLAG_DENSITY * len(flags_bytes) * 8


def _pokedex_read_looks_sane(pokedex_bytes: bytes) -> bool:
    if len(pokedex_bytes) != _POKEDEX_CAUGHT_SPECIES_SIZE:
        return False
    return not any(is_flag_set(pokedex_bytes, bit) for bit in _DEXSANITY_UNUSED_BITS)


def _flag_in_byte(value: int, flag_id: int) -> bool:
    return bool(value & (1 << flag_byte_and_bit(flag_id)[1]))


def _decrypt_gamestats_halfword(raw_value: int, checksum: int, key_high: int, byte_offset: int) -> int:
    seed = (checksum + (key_high << 16)) & 0xFFFFFFFF
    word_index = (byte_offset - _GAMESTATS_SECURE_REGION_OFFSET) // 2
    for _ in range(word_index + 1):
        seed = (seed * _GAMESTATS_LCRNG_MULTIPLIER + _GAMESTATS_LCRNG_INCREMENT) & 0xFFFFFFFF
    return raw_value ^ ((seed >> 16) & 0xFFFF)


_LOCALLY_SUBSTITUTED_AP_LOCATION_IDS_NORMAL = build_locally_substituted_ap_location_ids(remote_items=False)
_LOCALLY_SUBSTITUTED_AP_LOCATION_IDS_REMOTE = build_locally_substituted_ap_location_ids(remote_items=True)


logger = logging.getLogger("Client")


async def _announce_received(ctx, received) -> None:
    if len(received) > _RECEIVED_MESSAGES_PER_TICK:
        messages = [f"Received {len(received)} items"]
    else:
        messages = [
            f"Received {_item_display_name(ctx, item.item)}"
            + ("" if item.player == ctx.slot else f" from {ctx.player_names.get(item.player, item.player)}")
            for item in received
        ]
    try:
        for message in messages:
            await bizhawk.display_message(ctx.bizhawk_ctx, message)
    except (bizhawk.RequestFailedError, bizhawk.SyncError):
        pass


def _item_display_name(ctx, item_id: int) -> str:
    try:
        return ctx.item_names.lookup_in_game(item_id)
    except Exception:
        return f"item {item_id}"


def cmd_pending(self) -> None:
    """List the items the server sent that are not in your game yet."""
    ctx = self.ctx
    handler = ctx.client_handler
    if ctx.game != HeartGoldClient.game or not isinstance(handler, HeartGoldClient):
        logger.warning("This command only works while playing Pokemon HGSS Singe.")
        return
    if not ctx.server or not ctx.slot:
        logger.warning("Connect to the server first.")
        return
    pending = handler.pending_item_indices(ctx)
    if not pending:
        logger.info(f"All {len(ctx.items_received)} received items are in your game.")
        return
    names = [_item_display_name(ctx, ctx.items_received[index].item) for index in pending]
    logger.info(f"{len(pending)} received item(s) not in your game yet: " + ", ".join(names))
    logger.info(
        "If this list does not shrink within a few seconds, close any open menu. "
        "A full Bag pocket also holds its items back until you make room."
    )


def _pocket_quantity(pocket_bytes: bytes, native_id: int) -> int:
    return sum(
        quantity
        for item_id, quantity in (struct.unpack_from("<HH", pocket_bytes, o) for o in range(0, len(pocket_bytes) - 3, 4))
        if item_id == native_id
    )


def _pocket_slice(bag_bytes: bytes, bag_field: str) -> bytes:
    offset, capacity = BAG_POCKET_OFFSETS[bag_field]
    return bag_bytes[offset : offset + capacity * 4]


def _installed_world_version() -> str | None:
    try:
        data = pkgutil.get_data(__name__, "archipelago.json")
    except (OSError, ValueError):
        return None
    return None if data is None else json.loads(data.decode("utf-8")).get("world_version")


def _normalized_item_name(name: str) -> str:
    plain = "".join(ch for ch in name.lower() if ch.isalnum())
    return _ITEM_NAME_ALIASES.get(plain, plain)


_ITEM_NAME_ALIASES = {"magnettrainpass": "pass"}


def cmd_resend(self, item_name: str = "") -> None:
    """Give you one more copy of an item the server sent you that never reached your Bag."""
    ctx = self.ctx
    handler = ctx.client_handler
    if ctx.game != HeartGoldClient.game or not isinstance(handler, HeartGoldClient):
        logger.warning("This command only works while playing Pokemon HGSS Singe.")
        return
    if not ctx.server or not ctx.slot:
        logger.warning("Connect to the server first.")
        return
    if not item_name.strip():
        logger.info(
            "Usage: /resend <item name>, e.g. /resend Expert Belt. Gives one copy of an item the server already "
            "sent you. Key items and HMs come back on their own; use this for others lost before this client "
            "version (game closed or reloaded right after they arrived)."
        )
        return
    received: dict[int, int] = {}
    for network_item in ctx.items_received:
        received[network_item.item] = received.get(network_item.item, 0) + 1
    wanted = _normalized_item_name(item_name)
    matches = [ap_id for ap_id in received if _normalized_item_name(_item_display_name(ctx, ap_id)) == wanted]
    if not matches:
        logger.warning(f"The server never sent you an item named {item_name.strip()!r}, nothing to resend.")
        return
    ap_id = matches[0]
    name = _item_display_name(ctx, ap_id)
    if ap_id not in _AP_ITEM_ID_TO_BAG_WRITE_INFO:
        logger.warning(f"{name} does not go in the Bag (badges are restored on their own).")
        return
    if ap_id in _KEPT_ITEM_AP_IDS:
        logger.info(f"{name} comes back on its own whenever it is missing from your Bag, nothing to resend.")
        return
    used = (
        handler._resent_counts.get(ap_id, 0)
        + handler._resend_queue.count(ap_id)
        - handler._wipe_resend_credits.get(ap_id, 0)
    )
    if used >= received[ap_id]:
        logger.warning(f"{name} was already resent as many times as the server sent it ({received[ap_id]}).")
        return
    handler._resend_queue.append(ap_id)
    logger.info(f"Resending one {name}. Save in-game afterwards to keep it.")


cmd_resend.raw_text = True


def cmd_restore_power(self) -> None:
    """Repair the Kanto Power Plant in your save (Magnet Train fallback)."""
    ctx = self.ctx
    if ctx.game != HeartGoldClient.game or not isinstance(ctx.client_handler, HeartGoldClient):
        logger.warning("This command only works while playing Pokemon HGSS Singe.")
        return
    if not ctx.server or not ctx.slot:
        logger.warning("Connect to the server first.")
        return
    if not ctx.client_handler._known_trainer_id:
        logger.warning("Load your save in the game first, then type /restore_power again.")
        return
    ctx.client_handler._power_restore_requested = True
    logger.info(
        "Restoring the Kanto Power Plant: the Magnet Train will run once you hold the Pass. "
        "Save in-game afterwards to keep it."
    )
    if not bool(ctx.slot_data.get("magnet_train", False)):
        logger.info("The Power Plant manager's TM57 check is sent too; its item arrives through the server.")


_OFFLINE_WARNING_TICKS = 5


class HeartGoldClient(BizHawkClient):
    game = "Pokemon HGSS Singe"
    system = "NDS"
    patch_suffix = ".appokehgss"

    local_checked_locations: set[int]
    _pending_check_batch: set[int] | None
    bag_base_address: int | None
    flags_array_address: int | None
    pokedex_caught_species_address: int | None
    playerdata_profile_address: int | None
    party_address: int | None
    gamestats_address: int | None
    _array_headers_address: int | None
    _manual_bag_base_override: int | None
    _manual_flags_array_override: int | None
    _applied_item_count: int
    _delivered_ahead: set[int]
    _qol_applied: bool
    _start_gifts_done: set[str]
    _fly_points_done: bool
    _known_tm_quantities: dict[int, int] | None
    _previous_death_link: float | None
    _ignore_next_death_link: bool
    _death_link_tag_set: bool
    _starting_money_applied: bool
    _known_trainer_id: int | None
    _pending_trainer_id: int | None
    _start_location_revocation_target: tuple[int, int] | None
    _start_location_revocation_probed: bool
    _goal_pending: bool

    def __init__(self) -> None:
        super().__init__()
        self.local_checked_locations = set()
        self._pending_check_batch = None
        self.bag_base_address = None
        self.flags_array_address = None
        self.pokedex_caught_species_address = None
        self.playerdata_profile_address = None
        self.party_address = None
        self.gamestats_address = None
        self._array_headers_address = None
        self._manual_bag_base_override = None
        self._manual_flags_array_override = None
        self._previous_death_link = None
        self._ignore_next_death_link = False
        self._death_link_tag_set = False
        self._death_link_queued = False
        self._death_link_stalled_ticks = 0
        self._rom_has_deathlink_scripts = False
        self._reported_deathlink_old_rom = False
        self._known_trainer_id = None
        self._pending_trainer_id = None
        self._start_location_revocation_target = None
        self._start_location_revocation_probed = False
        self._offline_ticks = 0
        self._reset_save_scoped_progress()

    def _warn_if_offline(self, ctx: BizHawkClientContext) -> None:
        self._offline_ticks += 1
        if self._offline_ticks == _OFFLINE_WARNING_TICKS:
            logger.warning(
                "Connected to the emulator, but not to an Archipelago server: your checks are not being sent. "
                "Enter the server address at the top of this window (or /connect <address>). "
                "The slot name is read from your ROM."
            )

    async def set_auth(self, ctx: BizHawkClientContext) -> None:
        try:
            raw = (await bizhawk.read(ctx.bizhawk_ctx, [(SLOT_AUTH_ROM_OFFSET, SLOT_AUTH_SIZE, "ROM")]))[0]
        except bizhawk.RequestFailedError:
            return
        if any(raw):
            ctx.auth = base64.b64encode(bytes(raw)).decode("ascii")

    async def validate_rom(self, ctx: BizHawkClientContext) -> bool:
        try:
            id_code, signature, deathlink_tag = await bizhawk.read(
                ctx.bizhawk_ctx,
                [
                    (0x0C, 4, "ROM"),
                    (WORLD_SIGNATURE_ROM_OFFSET, WORLD_SIGNATURE_SIZE, "ROM"),
                    (DEATHLINK_SCRIPTS_ROM_OFFSET, len(DEATHLINK_SCRIPTS_TAG), "ROM"),
                ],
            )
        except bizhawk.RequestFailedError:
            return False

        if bytes(id_code) not in (HEARTGOLD_US_ID_CODE, SOULSILVER_US_ID_CODE):
            return False
        if not has_world_signature(bytes(signature)):
            return False

        if "restore_power" not in ctx.command_processor.commands:
            ctx.command_processor.commands["restore_power"] = cmd_restore_power
        if "pending" not in ctx.command_processor.commands:
            ctx.command_processor.commands["pending"] = cmd_pending
        if "resend" not in ctx.command_processor.commands:
            ctx.command_processor.commands["resend"] = cmd_resend

        ctx.game = self.game
        ctx.items_handling = 0b111
        ctx.want_slot_data = True
        ctx.watcher_timeout = 1.0

        self.local_checked_locations = set()
        self._pending_check_batch = None
        self._manual_bag_base_override = _resolve_address_override(HEARTGOLD_BAG_BASE_ADDRESS_ENV)
        self._manual_flags_array_override = _resolve_address_override(HEARTGOLD_FLAGS_ARRAY_ADDRESS_ENV)
        self.bag_base_address = self._manual_bag_base_override
        self.flags_array_address = self._manual_flags_array_override
        self.pokedex_caught_species_address = None
        self.playerdata_profile_address = None
        self.party_address = None
        self.gamestats_address = None
        self._array_headers_address = None
        self._previous_death_link = None
        self._ignore_next_death_link = False
        self._death_link_tag_set = False
        self._death_link_queued = False
        self._rom_has_deathlink_scripts = bytes(deathlink_tag) == DEATHLINK_SCRIPTS_TAG
        self._reported_deathlink_old_rom = False
        self._known_trainer_id = None
        self._pending_trainer_id = None
        self._start_location_revocation_target = None
        self._start_location_revocation_probed = False
        self._offline_ticks = 0
        self._reset_save_scoped_progress()

        return True

    def _reset_save_scoped_progress(self) -> None:
        self._applied_item_count = 0
        self._delivered_ahead = set()
        self._save_anchored = False
        self._save_item_count_address: int | None = None
        self._key_item_check_countdown = 0
        self._gifts_never_given: frozenset[int] = frozenset()
        self._resend_queue: list[int] = []
        self._wipe_resend_credits: dict[int, int] = {}
        self._resent_counts: dict[int, int] = {}
        self._battle_counter: int | None = None
        self._battle: dict | None = None
        self._battle_receipts: list[tuple[int, str, int, int]] = []
        self._tick_receipts: list[tuple[int, str, int, int]] = []
        self._tick = 0
        self._last_check_send_tick = 0
        self._version_checked = False
        self._reported_stuck_items: set[int] = set()
        self._reported_odd_slots: set[tuple[str, int, int, int]] = set()
        self._reported_bag_relocation = False
        self._bag_write_failures = 0
        self._power_restore_requested = False
        self._starting_money_applied = False
        self._qol_applied = False
        self._start_gifts_done = set()
        self._fly_points_done = False
        self._known_tm_quantities = None
        self._goal_pending = False

    async def _ensure_addresses_located(self, ctx: BizHawkClientContext) -> bool:
        if self._manual_bag_base_override is not None and self._manual_flags_array_override is not None:
            return True

        if self._array_headers_address is not None and await _array_headers_still_valid(
            ctx, self._array_headers_address
        ):
            return True

        located = await _locate_save_addresses(ctx)
        if located is None:
            self.bag_base_address = self._manual_bag_base_override
            self.flags_array_address = self._manual_flags_array_override
            self.pokedex_caught_species_address = None
            self.playerdata_profile_address = None
            self.party_address = None
            self.gamestats_address = None
            self._array_headers_address = None
            return False

        (
            bag_address,
            flags_array_address,
            pokedex_caught_species_address,
            playerdata_profile_address,
            array_headers_address,
            party_address,
            gamestats_address,
        ) = located
        self.bag_base_address = (
            bag_address if self._manual_bag_base_override is None else self._manual_bag_base_override
        )
        self.flags_array_address = (
            flags_array_address if self._manual_flags_array_override is None else self._manual_flags_array_override
        )
        self.pokedex_caught_species_address = pokedex_caught_species_address
        self.playerdata_profile_address = playerdata_profile_address
        self.party_address = party_address
        self.gamestats_address = gamestats_address
        self._array_headers_address = array_headers_address
        return True

    async def _apply_qol_options(self, ctx: BizHawkClientContext) -> None:
        if self._qol_applied or self.playerdata_profile_address is None:
            return

        fast_text_speed = bool(ctx.slot_data.get("fast_text_speed", False))
        skip_battle_animations = bool(ctx.slot_data.get("skip_battle_animations", False))
        if not fast_text_speed and not skip_battle_animations:
            self._qol_applied = True
            return

        playerdata_base_address = self.playerdata_profile_address - _PLAYERDATA_PROFILE_OFFSET
        options_address = playerdata_base_address + _PLAYERDATA_OPTIONS_OFFSET
        current = (await bizhawk.read(ctx.bizhawk_ctx, [(options_address, 2, "ARM9 System Bus")]))[0]
        (value,) = struct.unpack("<H", bytes(current))

        new_value = value
        if fast_text_speed:
            new_value = (new_value & ~TEXT_SPEED_MASK) | TEXT_SPEED_FAST_VALUE
        if skip_battle_animations:
            new_value |= BATTLE_SCENE_BIT

        if new_value != value:
            await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(options_address, struct.pack("<H", new_value), "ARM9 System Bus")],
                [(options_address, bytes(current), "ARM9 System Bus")],
            )
        self._qol_applied = True

    async def _apply_start_gifts(self, ctx: BizHawkClientContext) -> None:
        if self._array_headers_address is None:
            return
        dynamic_region_base = self._array_headers_address - _SAVE_COUNTER_SIZE - _DYNAMIC_REGION_SIZE
        for option, (chunk_id, offset, bits) in _START_GIFTS.items():
            if option in self._start_gifts_done:
                continue
            if not bool(ctx.slot_data.get(option, False)):
                self._start_gifts_done.add(option)
                continue
            address = dynamic_region_base + await _chunk_offset(ctx, self._array_headers_address, chunk_id) + offset
            current = (await bizhawk.read(ctx.bizhawk_ctx, [(address, 4, "ARM9 System Bus")]))[0]
            (value,) = struct.unpack("<I", bytes(current))
            if value & bits == bits:
                self._start_gifts_done.add(option)
                continue
            await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(address, struct.pack("<I", value | bits), "ARM9 System Bus")],
                [(address, bytes(current), "ARM9 System Bus")],
            )

    async def _apply_fly_points(self, ctx: BizHawkClientContext) -> None:
        if self._fly_points_done or self.flags_array_address is None:
            return
        if not bool(ctx.slot_data.get("fly_points_at_start", False)):
            self._fly_points_done = True
            return
        first = flag_byte_and_bit(_JOHTO_FLY_POINT_FLAGS[0])[0]
        last = flag_byte_and_bit(_JOHTO_FLY_POINT_FLAGS[-1])[0]
        address = self.flags_array_address + first
        current = bytes((await bizhawk.read(ctx.bizhawk_ctx, [(address, last - first + 1, "ARM9 System Bus")]))[0])
        wanted = bytearray(current)
        for flag in _JOHTO_FLY_POINT_FLAGS:
            byte_index, bit_index = flag_byte_and_bit(flag)
            wanted[byte_index - first] |= 1 << bit_index
        if bytes(wanted) == current:
            self._fly_points_done = True
            return
        await bizhawk.guarded_write(
            ctx.bizhawk_ctx,
            [(address, bytes(wanted), "ARM9 System Bus")],
            [(address, current, "ARM9 System Bus")],
        )

    async def _apply_starting_money(self, ctx: BizHawkClientContext, money_applied_key: str) -> None:
        if self._starting_money_applied or self.playerdata_profile_address is None:
            return

        starting_money = ctx.slot_data.get("starting_money")
        if starting_money is None:
            self._starting_money_applied = True
            return

        money_address = self.playerdata_profile_address + _PROFILE_MONEY_OFFSET
        current = (await bizhawk.read(ctx.bizhawk_ctx, [(money_address, 4, "ARM9 System Bus")]))[0]
        new_value = min(int(starting_money), _MAX_MONEY)

        write_succeeded = await bizhawk.guarded_write(
            ctx.bizhawk_ctx,
            [(money_address, struct.pack("<I", new_value), "ARM9 System Bus")],
            [(money_address, bytes(current), "ARM9 System Bus")],
        )
        if not write_succeeded:
            return

        self._starting_money_applied = True
        ctx.stored_data[money_applied_key] = 1
        await ctx.send_msgs(
            [
                {
                    "cmd": "Set",
                    "key": money_applied_key,
                    "default": 0,
                    "want_reply": False,
                    "operations": [{"operation": "max", "value": 1}],
                }
            ]
        )

    async def _apply_start_location_flags(self, ctx: BizHawkClientContext) -> None:
        if self.flags_array_address is None:
            return

        if not bool(ctx.slot_data.get("randomize_start_location", False)):
            return

        starter_byte_index, starter_bit_index = flag_byte_and_bit(_START_LOCATION_FLAG_GOT_STARTER)
        starter_byte_address = self.flags_array_address + starter_byte_index
        starter_byte = (await bizhawk.read(ctx.bizhawk_ctx, [(starter_byte_address, 1, "ARM9 System Bus")]))[0]
        if not (starter_byte[0] & (1 << starter_bit_index)):
            return

        touched_bytes: dict[int, int] = {}
        original_bytes: dict[int, int] = {}

        async def _byte_at(byte_index: int) -> int:
            if byte_index not in touched_bytes:
                address = self.flags_array_address + byte_index
                current = (await bizhawk.read(ctx.bizhawk_ctx, [(address, 1, "ARM9 System Bus")]))[0]
                touched_bytes[byte_index] = current[0]
                original_bytes[byte_index] = current[0]
            return touched_bytes[byte_index]

        for flag_id in _START_LOCATION_FLAGS_TO_SET:
            byte_index, bit_index = flag_byte_and_bit(flag_id)
            touched_bytes[byte_index] = (await _byte_at(byte_index)) | (1 << bit_index)

        vars_array_address = self.flags_array_address - 736
        var_scene_cherrygrove_index = 0x73
        var_address = vars_array_address + var_scene_cherrygrove_index * 2
        var_bytes = (await bizhawk.read(ctx.bizhawk_ctx, [(var_address, 2, "ARM9 System Bus")]))[0]
        (var_scene_cherrygrove,) = struct.unpack("<H", bytes(var_bytes))

        if var_scene_cherrygrove < 3:
            for flag_id in _START_LOCATION_FLAGS_TO_CLEAR:
                byte_index, bit_index = flag_byte_and_bit(flag_id)
                touched_bytes[byte_index] = (await _byte_at(byte_index)) & ~(1 << bit_index)

        if all(touched_bytes[byte_index] == original_bytes[byte_index] for byte_index in touched_bytes):
            return

        writes = [
            (self.flags_array_address + byte_index, bytes([new_value]), "ARM9 System Bus")
            for byte_index, new_value in touched_bytes.items()
            if new_value != original_bytes[byte_index]
        ]
        guards = [
            (self.flags_array_address + byte_index, bytes([original_bytes[byte_index]]), "ARM9 System Bus")
            for byte_index in touched_bytes
            if touched_bytes[byte_index] != original_bytes[byte_index]
        ]

        await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, guards)

    async def _read_start_location_revocation_target(
        self, ctx: BizHawkClientContext
    ) -> tuple[int, int] | None:
        if self._start_location_revocation_probed:
            return self._start_location_revocation_target

        try:
            record = (
                await bizhawk.read(
                    ctx.bizhawk_ctx, [(REVOCATION_RECORD_ROM_OFFSET, REVOCATION_RECORD_SIZE, "ROM")]
                )
            )[0]
        except bizhawk.RequestFailedError:
            return None

        self._start_location_revocation_probed = True
        self._start_location_revocation_target = parse_revocation_record(bytes(record))
        return self._start_location_revocation_target

    async def _current_map_id(self, ctx: BizHawkClientContext) -> int | None:
        position = await self._current_position(ctx)
        return None if position is None else struct.unpack_from("<i", position)[0]

    async def _current_position(self, ctx: BizHawkClientContext) -> bytes | None:
        if self._array_headers_address is None:
            return None
        dynamic_region_base = self._array_headers_address - _SAVE_COUNTER_SIZE - _DYNAMIC_REGION_SIZE
        chunk_offset = await _chunk_offset(ctx, self._array_headers_address, _LOCAL_FIELD_DATA_CHUNK_ID)
        address = dynamic_region_base + chunk_offset + _LOCAL_FIELD_DATA_CURRENT_MAP_ID_OFFSET
        return bytes((await bizhawk.read(ctx.bizhawk_ctx, [(address, 16, "ARM9 System Bus")]))[0])

    async def _revoke_start_location_redirect(self, ctx: BizHawkClientContext) -> None:
        if not bool(ctx.slot_data.get("randomize_start_location", False)):
            return
        if self.flags_array_address is None:
            return

        target = await self._read_start_location_revocation_target(ctx)
        if target is None:
            return
        rom_offset, vanilla_value = target

        try:
            current = (await bizhawk.read(ctx.bizhawk_ctx, [(rom_offset, 4, "ROM")]))[0]
        except bizhawk.RequestFailedError:
            return
        if struct.unpack("<I", bytes(current))[0] == vanilla_value:
            return

        starter_byte_index, starter_bit_index = flag_byte_and_bit(_START_LOCATION_FLAG_GOT_STARTER)
        starter_byte = (
            await bizhawk.read(
                ctx.bizhawk_ctx, [(self.flags_array_address + starter_byte_index, 1, "ARM9 System Bus")]
            )
        )[0]
        if not (starter_byte[0] & (1 << starter_bit_index)):
            return

        map_id = await self._current_map_id(ctx)
        if map_id is None or map_id in _START_LOCATION_HOME_MAP_IDS:
            return

        try:
            await bizhawk.write(ctx.bizhawk_ctx, [(rom_offset, struct.pack("<I", vanilla_value), "ROM")])
        except bizhawk.RequestFailedError:
            pass

    async def _apply_start_location_blackout_spawn(self, ctx: BizHawkClientContext) -> None:
        if not bool(ctx.slot_data.get("randomize_start_location", False)):
            return
        spawn_id = _START_LOCATION_TOWN_SPAWN_IDS.get(ctx.slot_data.get("starting_town"))
        if spawn_id is None or self.flags_array_address is None or self._array_headers_address is None:
            return

        starter_byte_index, starter_bit_index = flag_byte_and_bit(_START_LOCATION_FLAG_GOT_STARTER)
        latch_byte_index, latch_bit_index = flag_byte_and_bit(_BLACKOUT_SPAWN_LATCH_FLAG)
        latch_address = self.flags_array_address + latch_byte_index
        starter_byte, latch_byte = (
            await bizhawk.read(
                ctx.bizhawk_ctx,
                [
                    (self.flags_array_address + starter_byte_index, 1, "ARM9 System Bus"),
                    (latch_address, 1, "ARM9 System Bus"),
                ],
            )
        )
        if latch_byte[0] & (1 << latch_bit_index):
            return
        if not (starter_byte[0] & (1 << starter_bit_index)):
            return

        map_id = await self._current_map_id(ctx)
        if map_id is None or map_id in _START_LOCATION_HOME_MAP_IDS:
            return

        dynamic_region_base = self._array_headers_address - _SAVE_COUNTER_SIZE - _DYNAMIC_REGION_SIZE
        chunk_offset = await _chunk_offset(ctx, self._array_headers_address, _LOCAL_FIELD_DATA_CHUNK_ID)
        spawn_address = dynamic_region_base + chunk_offset + _LOCAL_FIELD_DATA_LAST_SPAWN_OFFSET
        current_spawn = (await bizhawk.read(ctx.bizhawk_ctx, [(spawn_address, 2, "ARM9 System Bus")]))[0]

        latched = latch_byte[0] | (1 << latch_bit_index)
        writes = [(latch_address, bytes([latched]), "ARM9 System Bus")]
        guards = [
            (latch_address, bytes(latch_byte), "ARM9 System Bus"),
            (spawn_address, bytes(current_spawn), "ARM9 System Bus"),
        ]
        if struct.unpack("<H", bytes(current_spawn))[0] == _SPAWN_ID_NEW_BARK:
            writes.append((spawn_address, struct.pack("<H", spawn_id), "ARM9 System Bus"))
        await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, guards)

    async def _apply_power_plant_prerestored(self, ctx: BizHawkClientContext) -> None:
        if not (bool(ctx.slot_data.get("magnet_train", False)) or self._power_restore_requested):
            return
        if self.flags_array_address is None:
            return

        flags_address = self.flags_array_address
        starter_byte_index, starter_bit_index = flag_byte_and_bit(_START_LOCATION_FLAG_GOT_STARTER)
        power_byte_index, power_bit_index = flag_byte_and_bit(_FLAG_RESTORED_POWER)
        starter_byte, power_byte = await bizhawk.read(
            ctx.bizhawk_ctx,
            [
                (flags_address + starter_byte_index, 1, "ARM9 System Bus"),
                (flags_address + power_byte_index, 1, "ARM9 System Bus"),
            ],
        )
        if power_byte[0] & (1 << power_bit_index):
            return
        if not (starter_byte[0] & (1 << starter_bit_index)):
            return

        vars_address = flags_address - FLAGS_ARRAY_OFFSET
        copycat_address = vars_address + (_COPYCAT_CHAIN_VAR - _VAR_BASE) * 2
        cerulean_address = vars_address + (_CERULEAN_CHAIN_VAR - _VAR_BASE) * 2
        flags, copycat_raw, cerulean_raw = await bizhawk.read(
            ctx.bizhawk_ctx,
            [
                (flags_address, FLAGS_ARRAY_SIZE, "ARM9 System Bus"),
                (copycat_address, 2, "ARM9 System Bus"),
                (cerulean_address, 2, "ARM9 System Bus"),
            ],
        )
        flags = bytes(flags)

        to_set = list(_POWER_PLANT_FLAGS_TO_SET)
        if not bool(ctx.slot_data.get("magnet_train", False)):
            to_set.append(_TM57_RESTORE_MARKER)
        to_clear = list(_POWER_PLANT_FLAGS_TO_CLEAR)
        writes: list[tuple[int, bytes, str]] = []
        guards: list[tuple[int, bytes, str]] = []
        if struct.unpack("<H", bytes(copycat_raw))[0] == 0:
            to_set += _COPYCAT_CHAIN_FLAGS_TO_SET
            to_clear += _COPYCAT_CHAIN_FLAGS_TO_CLEAR
            writes.append((copycat_address, struct.pack("<H", 1), "ARM9 System Bus"))
            guards.append((copycat_address, bytes(copycat_raw), "ARM9 System Bus"))
        if struct.unpack("<H", bytes(cerulean_raw))[0] == 0:
            to_clear += _CERULEAN_CHAIN_FLAGS_TO_CLEAR
            writes.append(
                (cerulean_address, struct.pack("<H", _CERULEAN_CHAIN_VAR_VALUE), "ARM9 System Bus")
            )
            guards.append((cerulean_address, bytes(cerulean_raw), "ARM9 System Bus"))

        new_flags = bytearray(flags)
        for flag_id in to_set:
            byte_index, bit_index = flag_byte_and_bit(flag_id)
            new_flags[byte_index] |= 1 << bit_index
        for flag_id in to_clear:
            byte_index, bit_index = flag_byte_and_bit(flag_id)
            new_flags[byte_index] &= ~(1 << bit_index) & 0xFF
        for byte_index, (old, new) in enumerate(zip(flags, new_flags)):
            if old != new:
                writes.append((flags_address + byte_index, bytes([new]), "ARM9 System Bus"))
                guards.append((flags_address + byte_index, bytes([old]), "ARM9 System Bus"))

        if await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, guards) and self._power_restore_requested:
            logger.info("Kanto Power Plant restored in your save. Save in-game to keep it.")

    async def _apply_wing_passes(self, ctx: BizHawkClientContext) -> None:
        if self.flags_array_address is None:
            return
        received = {item.item for item in ctx.items_received}
        wanted = [
            (key, flag) for key, flag in _WING_PASS_FLAGS.items()
            if HEARTGOLD_ITEM_ID_BASE + ITEMS[key]["id"] in received
        ]
        if not wanted:
            return
        flags_address = self.flags_array_address
        flags = bytes((await bizhawk.read(ctx.bizhawk_ctx, [(flags_address, FLAGS_ARRAY_SIZE, "ARM9 System Bus")]))[0])

        def is_set(flag_id: int) -> bool:
            byte_index, bit_index = flag_byte_and_bit(flag_id)
            return bool(flags[byte_index] & (1 << bit_index))

        if not is_set(_START_LOCATION_FLAG_GOT_STARTER):
            return
        soulsilver = (ctx.slot_data.get("options") or {}).get("game_version") == 1
        pewter_wing, hide_flag, caught_flag = _PEWTER_WING_LEGENDARY["soulsilver" if soulsilver else "heartgold"]
        new_flags = bytearray(flags)
        for key, (pass_flag, legacy_flag) in wanted:
            if is_set(pass_flag) and is_set(legacy_flag):
                continue
            first_time = not is_set(pass_flag)
            for flag_id in (pass_flag, legacy_flag):
                byte_index, bit_index = flag_byte_and_bit(flag_id)
                new_flags[byte_index] |= 1 << bit_index
            if first_time and key == pewter_wing and not is_set(caught_flag):
                byte_index, bit_index = flag_byte_and_bit(hide_flag)
                new_flags[byte_index] &= ~(1 << bit_index) & 0xFF
        writes, guards = [], []
        for byte_index, (old, new) in enumerate(zip(flags, new_flags)):
            if old != new:
                writes.append((flags_address + byte_index, bytes([new]), "ARM9 System Bus"))
                guards.append((flags_address + byte_index, bytes([old]), "ARM9 System Bus"))
        if writes:
            await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, guards)

    async def _restore_reusable_tms(self, ctx: BizHawkClientContext) -> None:
        if not bool(ctx.slot_data.get("reusable_tms", False)) or self.bag_base_address is None:
            return

        pocket_offset, pocket_capacity = BAG_POCKET_OFFSETS["TMsHMs"]
        pocket_address = self.bag_base_address + pocket_offset
        pocket_bytes = bytearray(
            (await bizhawk.read(ctx.bizhawk_ctx, [(pocket_address, pocket_capacity * 4, "ARM9 System Bus")]))[0]
        )

        current_quantities: dict[int, int] = {}
        for offset in range(0, len(pocket_bytes), 4):
            item_id, quantity = struct.unpack_from("<HH", bytes(pocket_bytes), offset)
            if item_id != 0:
                current_quantities[item_id] = current_quantities.get(item_id, 0) + quantity

        if self._known_tm_quantities is not None:
            stack_cap = stack_cap_for_pocket("TMsHMs")
            for item_id, known_quantity in self._known_tm_quantities.items():
                missing = known_quantity - current_quantities.get(item_id, 0)
                if missing <= 0:
                    continue
                plan = plan_bag_item_write(bytes(pocket_bytes), item_id, missing, stack_cap)
                if plan is None:
                    continue
                slot_offset, slot_bytes = plan
                write_succeeded = await bizhawk.guarded_write(
                    ctx.bizhawk_ctx,
                    [(pocket_address + slot_offset, slot_bytes, "ARM9 System Bus")],
                    [(pocket_address + slot_offset, bytes(pocket_bytes[slot_offset : slot_offset + 4]), "ARM9 System Bus")],
                )
                if write_succeeded:
                    pocket_bytes[slot_offset : slot_offset + 4] = slot_bytes
                    current_quantities[item_id] = current_quantities.get(item_id, 0) + missing

        self._known_tm_quantities = current_quantities

    async def _update_death_link_tag(self, ctx: BizHawkClientContext) -> None:
        if self._death_link_tag_set:
            return
        await ctx.update_death_link(bool(ctx.slot_data.get("death_link", False)))
        self._death_link_tag_set = True

    async def _send_death_link_on_whiteout(self, ctx: BizHawkClientContext) -> None:
        if not bool(ctx.slot_data.get("death_link", False)) or self.flags_array_address is None:
            return
        address = self.flags_array_address + _DEATHLINK_FLAGS_BYTE
        value = (await bizhawk.read(ctx.bizhawk_ctx, [(address, 1, "ARM9 System Bus")]))[0][0]
        if not _flag_in_byte(value, FLAG_AP_WHITED_OUT):
            return
        cleared = value
        for flag_id in (FLAG_AP_DEATHLINK, FLAG_AP_WHITED_OUT, FLAG_AP_DEATHLINK_WHITEOUT):
            cleared &= ~(1 << flag_byte_and_bit(flag_id)[1])
        if not await bizhawk.guarded_write(
            ctx.bizhawk_ctx,
            [(address, bytes([cleared]), "ARM9 System Bus")],
            [(address, bytes([value]), "ARM9 System Bus")],
        ):
            return
        if _flag_in_byte(value, FLAG_AP_DEATHLINK_WHITEOUT):
            return
        self._ignore_next_death_link = True
        await ctx.send_death(f"{ctx.player_names[ctx.slot]} whited out!")

    async def _receive_death_link(self, ctx: BizHawkClientContext) -> None:
        if not bool(ctx.slot_data.get("death_link", False)) or self.flags_array_address is None:
            return

        if self._previous_death_link is None:
            self._previous_death_link = ctx.last_death_link
        elif ctx.last_death_link != self._previous_death_link:
            self._previous_death_link = ctx.last_death_link
            if self._ignore_next_death_link:
                self._ignore_next_death_link = False
            else:
                self._death_link_queued = True

        if self._death_link_queued and not self._rom_has_deathlink_scripts:
            self._death_link_queued = False
            if not self._reported_deathlink_old_rom:
                self._reported_deathlink_old_rom = True
                logger.warning(
                    "DeathLink: this ROM was patched by an older version of the APWorld, which cannot make you "
                    "white out. Patch your .appokehgss again with this APWorld (your save keeps working)."
                )
            return

        repel_address = await self._roamer_repel_address(ctx)
        if repel_address is None:
            return
        address = self.flags_array_address + _DEATHLINK_FLAGS_BYTE
        safari_byte, safari_bit = flag_byte_and_bit(_FLAG_SYS_SAFARI)
        raw_flags, raw_safari, raw_repel = await bizhawk.read(
            ctx.bizhawk_ctx,
            [
                (address, 1, "ARM9 System Bus"),
                (self.flags_array_address + safari_byte, 1, "ARM9 System Bus"),
                (repel_address, 1, "ARM9 System Bus"),
            ],
        )
        value, repel_steps = raw_flags[0], raw_repel[0]
        writes, guards = [], []
        arming = self._death_link_queued and not raw_safari[0] & (1 << safari_bit)
        if arming:
            flag_set = value | (1 << flag_byte_and_bit(FLAG_AP_DEATHLINK)[1])
            writes.append((address, bytes([flag_set]), "ARM9 System Bus"))
            guards.append((address, bytes([value]), "ARM9 System Bus"))
            value = flag_set
        pending = _flag_in_byte(value, FLAG_AP_DEATHLINK)
        self._death_link_stalled_ticks = self._death_link_stalled_ticks + 1 if pending and repel_steps == 0 else 0
        stalled = self._death_link_stalled_ticks >= _DEATHLINK_STALL_TICKS
        if pending and (repel_steps > 1 or (repel_steps == 0 and (arming or stalled))):
            writes.append((repel_address, b"\x01", "ARM9 System Bus"))
            guards.append((repel_address, bytes([repel_steps]), "ARM9 System Bus"))
        if not writes or not await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, guards):
            return
        if self._death_link_queued and _flag_in_byte(value, FLAG_AP_DEATHLINK):
            self._death_link_queued = False
            logger.info("DeathLink: you will white out on your next step.")

    async def _roamer_repel_address(self, ctx: BizHawkClientContext) -> int | None:
        if self._array_headers_address is None:
            return None
        dynamic_region_base = self._array_headers_address - _SAVE_COUNTER_SIZE - _DYNAMIC_REGION_SIZE
        chunk_offset = await _chunk_offset(ctx, self._array_headers_address, _ROAMER_CHUNK_ID)
        return dynamic_region_base + chunk_offset + _ROAMER_REPEL_STEPS_OFFSET

    async def game_watcher(self, ctx: BizHawkClientContext) -> None:
        if ctx.server is None or ctx.server.socket.closed:
            self._warn_if_offline(ctx)
            return
        self._offline_ticks = 0
        if ctx.slot_data is None:
            return
        self._warn_on_version_mismatch(ctx)

        try:
            if not await self._ensure_addresses_located(ctx):
                return

            trainer_id_bytes = (
                await bizhawk.read(ctx.bizhawk_ctx, [(self.playerdata_profile_address + 16, 4, "ARM9 System Bus")])
            )[0]
            (trainer_id,) = struct.unpack("<I", bytes(trainer_id_bytes))

            if not self._accept_trainer_id(trainer_id):
                return

            if trainer_id == 0:
                return

            applied_key = _APPLIED_ITEM_COUNT_KEY_TEMPLATE.format(team=ctx.team, slot=ctx.slot, trainer_id=trainer_id)
            delivered_ahead_key = _DELIVERED_AHEAD_KEY_TEMPLATE.format(
                team=ctx.team, slot=ctx.slot, trainer_id=trainer_id
            )
            money_applied_key = _STARTING_MONEY_APPLIED_KEY_TEMPLATE.format(
                team=ctx.team, slot=ctx.slot, trainer_id=trainer_id
            )
            ctx.set_notify(money_applied_key)
            self._starting_money_applied = self._starting_money_applied or bool(
                int(ctx.stored_data.get(money_applied_key, 0) or 0)
            )
            self._restore_item_delivery_progress(ctx, applied_key, delivered_ahead_key)

            await self._apply_qol_options(ctx)
            await self._apply_start_gifts(ctx)
            await self._apply_fly_points(ctx)
            await self._apply_starting_money(ctx, money_applied_key)
            await self._apply_start_location_flags(ctx)
            await self._revoke_start_location_redirect(ctx)
            await self._apply_start_location_blackout_spawn(ctx)
            await self._apply_power_plant_prerestored(ctx)
            await self._apply_wing_passes(ctx)
            await self._restore_reusable_tms(ctx)
            await self._update_death_link_tag(ctx)
            await self._send_death_link_on_whiteout(ctx)
            await self._receive_death_link(ctx)
            await self._check_locations(ctx)
            await self._repair_story_vars(ctx)
            await self._track_battles(ctx)
            if await self._sync_item_count_with_save(ctx, applied_key):
                await self._apply_received_items(ctx, applied_key, delivered_ahead_key)
                await self._ensure_key_items(ctx)
                await self._process_resends(ctx)
                await self._catch_battle_started_mid_tick(ctx)
            await self._apply_pending_badges(ctx)
        except bizhawk.RequestFailedError:
            pass

    def _warn_on_version_mismatch(self, ctx: BizHawkClientContext) -> None:
        generated = ctx.slot_data.get("world_version")
        if self._version_checked or generated is None:
            return
        self._version_checked = True
        installed = _installed_world_version()
        if installed is not None and generated != installed:
            logger.warning(
                f"This seed was generated with Pokemon HGSS Singe {generated}, but this client is {installed}. "
                "Use the same version as the seed to avoid lost or repeated items."
            )

    def _accept_trainer_id(self, trainer_id: int) -> bool:
        if trainer_id == self._known_trainer_id:
            self._pending_trainer_id = trainer_id
            return True

        if trainer_id != self._pending_trainer_id:
            self._pending_trainer_id = trainer_id
            return False

        self._known_trainer_id = trainer_id
        self._reset_save_scoped_progress()
        return True

    async def _pocket_usable(self, ctx: BizHawkClientContext, pocket_bytes: bytes, bag_field: str) -> bool:
        if _pocket_looks_plausible(pocket_bytes):
            return True
        if self.pokedex_caught_species_address is not None and await self._save_block_signature_valid(ctx):
            for offset in range(0, len(pocket_bytes) - 3, 4):
                item_id, quantity = struct.unpack_from("<HH", pocket_bytes, offset)
                if item_id and not (item_id <= _MAX_PLAUSIBLE_ITEM_ID and quantity <= _MAX_PLAUSIBLE_ITEM_QUANTITY):
                    key = (bag_field, offset // 4, item_id, quantity)
                    if key not in self._reported_odd_slots:
                        self._reported_odd_slots.add(key)
                        logger.warning(
                            f"Your Bag's {bag_field} pocket holds an unexpected entry (slot {offset // 4 + 1}: item "
                            f"{item_id}, quantity {quantity}). Items keep arriving; please report this entry."
                        )
            return True
        self._array_headers_address = None
        if not self._reported_bag_relocation:
            self._reported_bag_relocation = True
            logger.warning("Bag data looks wrong, searching for your save data again.")
        return False

    async def _save_block_signature_valid(self, ctx: BizHawkClientContext) -> bool:
        if self.pokedex_caught_species_address is None:
            return True

        magic_address = (
            self.pokedex_caught_species_address - _POKEDEX_CAUGHT_SPECIES_OFFSET + _POKEDEX_MAGIC_OFFSET
        )
        raw = (await bizhawk.read(ctx.bizhawk_ctx, [(magic_address, 4, "ARM9 System Bus")]))[0]
        (magic,) = struct.unpack("<I", bytes(raw))
        if magic == _POKEDEX_MAGIC:
            return True

        self._array_headers_address = None
        return False

    async def _check_locations(self, ctx: BizHawkClientContext) -> None:
        goal_seen_last_tick = self._goal_pending
        self._goal_pending = False
        if not await self._save_block_signature_valid(ctx):
            self._pending_check_batch = None
            return

        flags_address = self.flags_array_address
        flags_bytes = bytes(
            (await bizhawk.read(ctx.bizhawk_ctx, [(flags_address, FLAGS_ARRAY_SIZE, "ARM9 System Bus")]))[0]
        )
        if not _flags_read_looks_sane(flags_bytes):
            self._pending_check_batch = None
            return

        flagged = {
            ap_location_id
            for flag_id, ap_location_id in (*_FLAG_ID_TO_AP_LOCATION_ID.items(), *_ALIAS_FLAG_TO_AP_ID.items())
            if is_flag_set(bytes(flags_bytes), flag_id)
        }
        missing = set(ctx.missing_locations)
        checked = set(getattr(ctx, "checked_locations", None) or ())
        unmarked = {
            ap_id: (marker, trigger)
            for ap_id, (given_flags, marker, trigger) in _MISSABLE_GIFTS_BY_AP_ID.items()
            if (ap_id in missing or ap_id in checked)
            and not is_flag_set(flags_bytes, marker)
            and not any(is_flag_set(flags_bytes, f) for f in given_flags)
        }
        vars_bytes = None
        if (
            missing & _VAR_CHECKS.keys()
            or any(trigger[0] == "var" for _, trigger in unmarked.values())
            or any(trigger[0] == "var" and missing & ap_ids for ap_ids, trigger in _MISSABLE_TRAINERS)
        ):
            vars_bytes = bytes(
                (
                    await bizhawk.read(
                        ctx.bizhawk_ctx, [(flags_address - FLAGS_ARRAY_OFFSET, FLAGS_ARRAY_OFFSET, "ARM9 System Bus")]
                    )
                )[0]
            )

        def var(var_id: int) -> int:
            assert vars_bytes is not None
            return struct.unpack_from("<H", vars_bytes, (var_id - _VAR_BASE) * 2)[0]

        received_ids = {network_item.item for network_item in getattr(ctx, "items_received", ())}

        def triggered(trigger: tuple) -> bool:
            if trigger[0] == "always":
                return True
            if trigger[0] == "flag":
                return is_flag_set(flags_bytes, trigger[1])
            if trigger[0] == "item":
                return HEARTGOLD_ITEM_ID_BASE + ITEMS[trigger[1]]["id"] in received_ids
            return vars_bytes is not None and var(trigger[1]) >= trigger[2]

        if vars_bytes is not None:
            for ap_id, (var_id, minimum) in _VAR_CHECKS.items():
                if var(var_id) >= minimum:
                    flagged.add(ap_id)
        for ap_ids, trigger in _MISSABLE_TRAINERS:
            if missing & ap_ids and triggered(trigger):
                flagged |= ap_ids
        new_markers = {ap_id: marker for ap_id, (marker, trigger) in unmarked.items() if triggered(trigger)}
        if vars_bytes is not None and var(_VAR_BASEMENT_KEY_GIVEN[0]) >= _VAR_BASEMENT_KEY_GIVEN[1]:
            new_markers.pop(_BASEMENT_KEY_AP_ID, None)
        unlock_flags = tuple(
            flag
            for ap_id in new_markers
            if unmarked[ap_id][1][0] == "item"
            for flag in unmarked[ap_id][1][2]
        )
        if not await self._keep_check_flags_set(
            ctx, flags_address, flags_bytes, tuple(new_markers.values()) + unlock_flags
        ):
            new_markers = {}
        self._gifts_never_given = frozenset(
            ap_id for ap_id, (_, marker, _) in _MISSABLE_GIFTS_BY_AP_ID.items() if is_flag_set(flags_bytes, marker)
        ) | new_markers.keys()
        if is_flag_set(flags_bytes, _TM57_RESTORE_MARKER):
            self._gifts_never_given |= {_TM57_AP_ID}
        flagged |= self._gifts_never_given
        flagged |= {_COMPANION_AP_LOCATION_IDS[i] for i in flagged if i in _COMPANION_AP_LOCATION_IDS}
        newly_checked = flagged & set(ctx.missing_locations)
        if _GAME_CORNER_JP_TM78_AP_ID in ctx.missing_locations:
            if await self._current_map_id(ctx) == _MAP_GOLDENROD_GAME_CORNER:
                newly_checked.add(_GAME_CORNER_JP_TM78_AP_ID)

        if self.pokedex_caught_species_address is not None and not _DEXSANITY_AP_LOCATION_IDS.isdisjoint(
            ctx.missing_locations
        ):
            pokedex_address = self.pokedex_caught_species_address
            if ctx.slot_data.get("dexsanity_trigger") == "encounter":
                pokedex_address += _POKEDEX_CAUGHT_SPECIES_SIZE
            pokedex_bytes = bytes(
                (
                    await bizhawk.read(
                        ctx.bizhawk_ctx,
                        [(pokedex_address, _POKEDEX_CAUGHT_SPECIES_SIZE, "ARM9 System Bus")],
                    )
                )[0]
            )
            if not _pokedex_read_looks_sane(pokedex_bytes):
                self._pending_check_batch = None
                return
            newly_checked |= {
                ap_location_id
                for bit, ap_location_id in _DEXSANITY_FLAG_ID_TO_AP_LOCATION_ID.items()
                if ap_location_id in ctx.missing_locations and is_flag_set(bytes(pokedex_bytes), bit)
            }

        await self._report_goal(ctx, flags_bytes, goal_seen_last_tick)

        if not newly_checked:
            self._pending_check_batch = None
            return

        if len(newly_checked) > _MAX_IMMEDIATE_CHECK_BATCH and newly_checked != self._pending_check_batch:
            self._pending_check_batch = newly_checked
            return

        self._pending_check_batch = newly_checked
        stale = self._tick - self._last_check_send_tick >= _CHECK_RESEND_TICKS
        if newly_checked != self.local_checked_locations or stale:
            self.local_checked_locations = newly_checked
            self._last_check_send_tick = self._tick
            await ctx.check_locations(newly_checked)

    async def _repair_story_vars(self, ctx: BizHawkClientContext) -> None:
        if self.flags_array_address is None:
            return
        vars_address = self.flags_array_address - FLAGS_ARRAY_OFFSET
        vars_bytes = bytes(
            (await bizhawk.read(ctx.bizhawk_ctx, [(vars_address, FLAGS_ARRAY_OFFSET, "ARM9 System Bus")]))[0]
        )

        def var(var_id: int) -> int:
            return struct.unpack_from("<H", vars_bytes, (var_id - _VAR_BASE) * 2)[0]

        flags_bytes = bytes(
            (await bizhawk.read(ctx.bizhawk_ctx, [(self.flags_array_address, _STORY_FLAGS_SPAN, "ARM9 System Bus")]))[0]
        )

        def flag(flag_id: int) -> bool:
            byte_index, bit_index = flag_byte_and_bit(flag_id)
            return bool(flags_bytes[byte_index] & (1 << bit_index))

        writes = []
        clair_scene_done = flag(_FLAG_ELMS_LAB_CLAIR_SCENE_DONE)
        if var(_VAR_SCENE_MR_POKEMONS_HOUSE) == 1:
            if var(_VAR_SCENE_ELMS_LAB) != 3:
                writes.append((_VAR_SCENE_ELMS_LAB, 3))
        elif flag(_FLAG_DRAGONS_DEN_SHRINE_DONE) and not clair_scene_done and var(_VAR_SCENE_ELMS_LAB) != 8:
            writes.append((_VAR_SCENE_ELMS_LAB, 8))
        if var(_VAR_SCENE_ROCKET_TAKEOVER) < 2 and var(_VAR_MIDGAME_BADGES) > 4:
            ids = _LOCATION_KEY_TO_AP_ID
            checked = getattr(ctx, "checked_locations", None) or set()
            beaten = sum(1 for key in _MIDGAME_LEADER_BADGE_KEYS if ids.get(key) in checked)
            writes.append((_VAR_MIDGAME_BADGES, beaten))
        if (
            (var(_VAR_SCENE_ELMS_LAB) >= 9 or clair_scene_done)
            and var(_VAR_DANCE_THEATER) < 4
            and var(_VAR_KIMONO_CHAIN) in (0, 1, 2)
        ):
            writes.append((_VAR_KIMONO_CHAIN, 3))
        for var_id, value in writes:
            address = vars_address + (var_id - _VAR_BASE) * 2
            await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(address, struct.pack("<H", value), "ARM9 System Bus")],
                [(address, struct.pack("<H", var(var_id)), "ARM9 System Bus")],
            )

        to_set: list[int] = []
        to_clear: list[int] = []
        if (flag(_FLAG_GOT_SECRETPOTION) or var(_VAR_SCENE_LIGHTHOUSE_JASMINE) >= 2) and not flag(
            _FLAG_LIGHTHOUSE_BARRIER_OPEN
        ):
            to_set.append(_FLAG_LIGHTHOUSE_BARRIER_OPEN)
        for fought, caught, hidden in _BOX_LEGENDARY_FLAGS:
            if flag(fought) and not flag(caught) and flag(hidden):
                to_clear.append(hidden)
        if flag(_FLAG_KURT_LEFT) and var(_VAR_AZALEA_ROCKET_SCENE) == 0:
            address = vars_address + (_VAR_AZALEA_ROCKET_SCENE - _VAR_BASE) * 2
            await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(address, struct.pack("<H", 1), "ARM9 System Bus")],
                [(address, struct.pack("<H", 0), "ARM9 System Bus")],
            )
            to_set.extend(_AZALEA_SCENE_NPC_FLAGS)
        if flag(_FLAG_KURT_LEFT) and var(_VAR_AZALEA_ROCKET_SCENE) == 1 and not flag(_FLAG_HIDE_WELL_GUARD):
            to_set.append(_FLAG_HIDE_WELL_GUARD)
        if (
            var(_VAR_DANCE_THEATER) == 5
            and not any(flag(bell) for bell in _BELL_GIVEN_FLAGS)
            and any(flag(fought) for fought, _caught, _hidden in _BOX_LEGENDARY_FLAGS)
        ):
            address = vars_address + (_VAR_DANCE_THEATER - _VAR_BASE) * 2
            await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(address, struct.pack("<H", 4), "ARM9 System Bus")],
                [(address, struct.pack("<H", 5), "ARM9 System Bus")],
            )
        new_flags = bytearray(flags_bytes)
        for flag_id in to_set:
            byte_index, bit_index = flag_byte_and_bit(flag_id)
            new_flags[byte_index] |= 1 << bit_index
        for flag_id in to_clear:
            byte_index, bit_index = flag_byte_and_bit(flag_id)
            new_flags[byte_index] &= ~(1 << bit_index)
        for byte_index, (old, new) in enumerate(zip(flags_bytes, new_flags)):
            if old != new:
                address = self.flags_array_address + byte_index
                await bizhawk.guarded_write(
                    ctx.bizhawk_ctx,
                    [(address, bytes([new]), "ARM9 System Bus")],
                    [(address, bytes([old]), "ARM9 System Bus")],
                )

    async def _keep_check_flags_set(
        self, ctx: BizHawkClientContext, flags_address: int, flags_bytes: bytes, extra_flags: tuple[int, ...] = ()
    ) -> bool:
        checked = getattr(ctx, "checked_locations", None) or set()
        new_flags = bytearray(flags_bytes)
        wanted = [flag for ap_id, flag_ids in _UPKEEP_FLAGS_BY_AP_ID.items() if ap_id in checked for flag in flag_ids]
        for flag_id in (*wanted, *extra_flags):
            byte_index, bit_index = flag_byte_and_bit(flag_id)
            new_flags[byte_index] |= 1 << bit_index
        writes, guards = [], []
        for byte_index, (old, new) in enumerate(zip(flags_bytes, new_flags)):
            if old != new:
                writes.append((flags_address + byte_index, bytes([new]), "ARM9 System Bus"))
                guards.append((flags_address + byte_index, bytes([old]), "ARM9 System Bus"))
        if not writes:
            return True
        return bool(await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, guards))

    async def _report_goal(self, ctx: BizHawkClientContext, flags_bytes: bytes, goal_seen_last_tick: bool) -> None:
        if ctx.finished_game:
            return

        goal = int(ctx.slot_data.get("goal", _GOAL_ELITE_FOUR))
        if goal == _GOAL_N_BADGES:
            required = int(ctx.slot_data.get("goal_badge_count", 16))
            if ctx.slot_data.get(SLOT_DATA_OPTIONS_KEY, {}).get("johto_only"):
                required = min(required, _JOHTO_BADGE_COUNT)
            received = {item.item for item in ctx.items_received if item.item in _AP_ITEM_ID_TO_BADGE_INDEX}
            reached = len(received) >= required
        elif goal == _GOAL_CHAMPION_RED:
            reached = False
            if is_flag_set(flags_bytes, _FLAG_RED_DEFEATED):
                vars_address = self.flags_array_address - FLAGS_ARRAY_OFFSET
                var_address = vars_address + (_VAR_RED_DEFEATED - _VAR_BASE) * 2
                raw = (await bizhawk.read(ctx.bizhawk_ctx, [(var_address, 2, "ARM9 System Bus")]))[0]
                reached = struct.unpack("<H", bytes(raw))[0] == 1
            if reached and not goal_seen_last_tick:
                self._goal_pending = True
                return
        elif goal == _GOAL_ELITE_FOUR:
            reached = is_flag_set(flags_bytes, _FLAG_GAME_CLEAR)
            if reached and not goal_seen_last_tick:
                self._goal_pending = True
                return
        else:
            return

        if not reached:
            return
        ctx.finished_game = True
        await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])

    def _restore_item_delivery_progress(
        self, ctx: BizHawkClientContext, applied_key: str, delivered_ahead_key: str
    ) -> None:
        ctx.set_notify(applied_key, delivered_ahead_key)
        if self._save_anchored:
            return
        self._applied_item_count = max(self._applied_item_count, int(ctx.stored_data.get(applied_key, 0) or 0))
        self._delivered_ahead |= _indices_from_mask(int(ctx.stored_data.get(delivered_ahead_key, 0) or 0))
        self._compact_delivery_progress()

    async def _sync_item_count_with_save(self, ctx: BizHawkClientContext, applied_key: str) -> bool:
        if self.flags_array_address is None:
            return False
        address = self.flags_array_address - FLAGS_ARRAY_OFFSET + (_VAR_AP_ITEMS_APPLIED - _VAR_BASE) * 2
        raw = bytes((await bizhawk.read(ctx.bizhawk_ctx, [(address, 8, "ARM9 System Bus")]))[0])
        count, marker, ahead_low, ahead_high = struct.unpack("<HHHH", raw)
        ahead_mask = ahead_low | ahead_high << 16
        if marker != _AP_ITEMS_MARKER:
            if applied_key not in ctx.stored_data:
                return False
            count = min(self._applied_item_count, 0xFFFF)
            ahead_mask = self._ahead_mask(count)
            await bizhawk.write(
                ctx.bizhawk_ctx,
                [(address, _pack_item_count(count, ahead_mask), "ARM9 System Bus")],
            )
        self._save_anchored = True
        self._applied_item_count = count
        self._delivered_ahead = {count + 1 + bit for bit in range(_DELIVERED_AHEAD_WINDOW) if ahead_mask >> bit & 1}
        self._save_item_count_address = address
        return True

    def _ahead_mask(self, count: int) -> int:
        return sum(
            1 << (index - count - 1)
            for index in self._delivered_ahead
            if count < index <= count + _DELIVERED_AHEAD_WINDOW
        )

    def pending_item_indices(self, ctx: BizHawkClientContext) -> list[int]:
        return [
            index
            for index in range(self._applied_item_count, len(ctx.items_received))
            if index not in self._delivered_ahead
        ]

    def _save_progress_with(self, index: int) -> bytes:
        ahead = {i for i in (*self._delivered_ahead, index) if i >= self._applied_item_count}
        count = self._applied_item_count
        while count in ahead:
            ahead.remove(count)
            count += 1
        count = min(count, 0xFFFF)
        mask = sum(1 << (i - count - 1) for i in ahead if count < i <= count + _DELIVERED_AHEAD_WINDOW)
        return _pack_item_count(count, mask)

    def _compact_delivery_progress(self) -> None:
        self._delivered_ahead = {index for index in self._delivered_ahead if index >= self._applied_item_count}
        while self._applied_item_count in self._delivered_ahead:
            self._delivered_ahead.remove(self._applied_item_count)
            self._applied_item_count += 1

    async def _apply_received_items(
        self, ctx: BizHawkClientContext, applied_key: str, delivered_ahead_key: str
    ) -> None:
        if self._deliveries_held():
            return
        locally_substituted = (
            _LOCALLY_SUBSTITUTED_AP_LOCATION_IDS_REMOTE
            if bool(ctx.slot_data.get("remote_items", False))
            else _LOCALLY_SUBSTITUTED_AP_LOCATION_IDS_NORMAL
        ) - _never_given_in_game(ctx) - self._gifts_never_given

        applied_this_tick = 0
        index = self._applied_item_count
        received = []
        full_bag_fields: set[str] = set()
        held_back: int | None = None
        while applied_this_tick < _MAX_ITEMS_APPLIED_PER_TICK and index < len(ctx.items_received):
            if index in self._delivered_ahead:
                index += 1
                continue
            if held_back is not None and index - held_back > _DELIVERED_AHEAD_WINDOW:
                break

            next_item = ctx.items_received[index]

            already_delivered_locally = (
                next_item.player == ctx.slot and next_item.location in locally_substituted
            )

            badge_index = None if already_delivered_locally else _AP_ITEM_ID_TO_BADGE_INDEX.get(next_item.item)
            if badge_index is not None:
                self._delivered_ahead.add(index)
                received.append(next_item)
                index += 1
                applied_this_tick += 1
                continue

            write_info = None if already_delivered_locally else _AP_ITEM_ID_TO_BAG_WRITE_INFO.get(next_item.item)
            if write_info is None:
                self._delivered_ahead.add(index)
                index += 1
                applied_this_tick += 1
                continue

            native_item_id, bag_field = write_info
            if bag_field in full_bag_fields:
                held_back = index if held_back is None else held_back
                index += 1
                continue

            pocket_offset, pocket_capacity = BAG_POCKET_OFFSETS[bag_field]
            pocket_address = self.bag_base_address + pocket_offset
            pocket_size = pocket_capacity * 4

            pocket_bytes = (
                await bizhawk.read(ctx.bizhawk_ctx, [(pocket_address, pocket_size, "ARM9 System Bus")])
            )[0]

            if not await self._pocket_usable(ctx, bytes(pocket_bytes), bag_field):
                break

            keep_free = _ITEMS_POCKET_KEPT_FREE if bag_field == "items" else 0
            plan = plan_bag_item_write(
                bytes(pocket_bytes), native_item_id, 1, stack_cap_for_pocket(bag_field), keep_free
            )
            if plan is None:
                if index not in self._reported_stuck_items:
                    self._reported_stuck_items.add(index)
                    name = _item_display_name(ctx, next_item.item)
                    logger.warning(
                        f"Could not add {name} to your Bag: that pocket is full (or already holds the "
                        "maximum). Toss, sell or store items in the PC and it will arrive on its own; "
                        f"past {_DELIVERED_AHEAD_WINDOW} more items, later ones wait for it too."
                    )
                full_bag_fields.add(bag_field)
                held_back = index if held_back is None else held_back
                index += 1
                continue

            slot_offset, slot_bytes = plan
            writes = [(pocket_address + slot_offset, slot_bytes, "ARM9 System Bus")]
            if self._save_item_count_address is not None:
                writes.append((self._save_item_count_address, self._save_progress_with(index), "ARM9 System Bus"))
            write_succeeded = await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                writes,
                [(pocket_address + slot_offset, bytes(pocket_bytes[slot_offset : slot_offset + 4]), "ARM9 System Bus")],
            )
            if not write_succeeded:
                self._bag_write_failures += 1
                if self._bag_write_failures >= _BAG_WRITE_FAILURES_BEFORE_RELOCATE:
                    logger.warning("Items could not be written to your Bag, searching for your save data again.")
                    self._array_headers_address = None
                    self._bag_write_failures = 0
                break

            self._bag_write_failures = 0
            self._reported_stuck_items.discard(index)
            self._delivered_ahead.add(index)
            received.append(next_item)
            self._note_delivery(
                next_item.item,
                bag_field,
                native_item_id,
                bytes(pocket_bytes[:slot_offset]) + slot_bytes + bytes(pocket_bytes[slot_offset + 4 :]),
            )
            index += 1
            applied_this_tick += 1

        self._compact_delivery_progress()
        if applied_this_tick > 0:
            await self._store_applied_item_count(ctx, applied_key, delivered_ahead_key)
        if received and bool(ctx.slot_data.get("item_received_messages", False)):
            await _announce_received(ctx, received)

    async def _read_battle_starts(self, ctx: BizHawkClientContext) -> int | None:
        if self.gamestats_address is None:
            return None
        raw_stats, raw_crypt = await bizhawk.read(
            ctx.bizhawk_ctx,
            [
                (self.gamestats_address + _GAME_STAT_BATTLE_STARTS_OFFSET, 8, "ARM9 System Bus"),
                (self.gamestats_address + _GAMESTATS_CHECKSUM_OFFSET, 4, "ARM9 System Bus"),
            ],
        )
        checksum, key_high = struct.unpack("<HH", bytes(raw_crypt))
        halves = [
            _decrypt_gamestats_halfword(value, checksum, key_high, _GAME_STAT_BATTLE_STARTS_OFFSET + 2 * i)
            for i, value in enumerate(struct.unpack("<4H", bytes(raw_stats)))
        ]
        return (halves[0] | halves[1] << 16) + (halves[2] | halves[3] << 16)

    async def _read_party_and_bag(self, ctx: BizHawkClientContext) -> tuple[bytes, bytes]:
        party, bag = await bizhawk.read(
            ctx.bizhawk_ctx,
            [
                (self.party_address, _PARTY_STRUCT_SIZE, "ARM9 System Bus"),
                (self.bag_base_address, BAG_SIZE, "ARM9 System Bus"),
            ],
        )
        return bytes(party), bytes(bag)

    def _deliveries_held(self) -> bool:
        return self._battle is not None and self._tick < self._battle["hold_until"]

    def _note_delivery(self, ap_id: int, bag_field: str, native_id: int, pocket_bytes: bytes) -> None:
        receipt = (ap_id, bag_field, native_id, _pocket_quantity(pocket_bytes, native_id))
        self._tick_receipts.append(receipt)
        if self._battle is not None:
            self._battle_receipts.append(receipt)

    async def _catch_battle_started_mid_tick(self, ctx: BizHawkClientContext) -> None:
        if not self._tick_receipts or self._battle is not None or self._battle_counter is None:
            return
        starts = await self._read_battle_starts(ctx)
        if starts is None or starts <= self._battle_counter:
            return
        party, bag = await self._read_party_and_bag(ctx)
        self._battle_counter = starts
        self._battle = {
            "party": party,
            "bag": bag,
            "hold_until": self._tick + _BATTLE_HOLD_TICKS,
            "watch_until": self._tick + _BATTLE_WATCH_TICKS,
        }
        self._battle_receipts = list(self._tick_receipts)

    async def _track_battles(self, ctx: BizHawkClientContext) -> None:
        self._tick += 1
        self._tick_receipts = []
        if self.party_address is None or self.bag_base_address is None:
            return
        starts = await self._read_battle_starts(ctx)
        if starts is None:
            return
        previous, self._battle_counter = self._battle_counter, starts
        if previous is not None and starts > previous:
            party, bag = await self._read_party_and_bag(ctx)
            self._battle = {
                "party": party,
                "bag": bag,
                "hold_until": self._tick + _BATTLE_HOLD_TICKS,
                "watch_until": self._tick + _BATTLE_WATCH_TICKS,
            }
            self._battle_receipts = []
            return
        if previous is not None and starts < previous:
            self._battle = None
            self._battle_receipts = []
            return
        if self._battle is None:
            return
        party, bag = await self._read_party_and_bag(ctx)
        wiped = [
            receipt
            for receipt in self._battle_receipts
            if _pocket_quantity(_pocket_slice(bag, receipt[1]), receipt[2]) < receipt[3]
        ]
        for ap_id, *_rest in wiped:
            self._resend_queue.append(ap_id)
            self._wipe_resend_credits[ap_id] = self._wipe_resend_credits.get(ap_id, 0) + 1
            logger.info(
                f"{_item_display_name(ctx, ap_id)} arrived during a battle and was undone when it ended: "
                "delivering it again."
            )
        ended = bool(wiped) or party != self._battle["party"] or (
            not self._battle_receipts and bag != self._battle["bag"]
        )
        if not ended and self._tick >= self._battle["hold_until"]:
            where = await self._current_position(ctx)
            if where is not None:
                if self._battle.get("where") is None:
                    self._battle["where"] = where
                elif where != self._battle["where"]:
                    ended = True
        if ended or self._tick >= self._battle["watch_until"]:
            self._battle = None
            self._battle_receipts = []

    async def _process_resends(self, ctx: BizHawkClientContext) -> None:
        while self._resend_queue and self.bag_base_address is not None and not self._deliveries_held():
            ap_id = self._resend_queue[0]
            native_id, bag_field = _AP_ITEM_ID_TO_BAG_WRITE_INFO[ap_id]
            pocket_offset, pocket_capacity = BAG_POCKET_OFFSETS[bag_field]
            pocket_address = self.bag_base_address + pocket_offset
            pocket_bytes = bytes(
                (await bizhawk.read(ctx.bizhawk_ctx, [(pocket_address, pocket_capacity * 4, "ARM9 System Bus")]))[0]
            )
            if not await self._pocket_usable(ctx, pocket_bytes, bag_field):
                return
            if ap_id in _KEPT_ITEM_AP_IDS and _pocket_quantity(pocket_bytes, native_id) > 0:
                self._resend_queue.pop(0)
                self._spend_wipe_credit(ap_id)
                continue
            plan = plan_bag_item_write(pocket_bytes, native_id, 1, stack_cap_for_pocket(bag_field))
            if plan is None:
                return
            slot_offset, slot_bytes = plan
            if not await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(pocket_address + slot_offset, slot_bytes, "ARM9 System Bus")],
                [(pocket_address + slot_offset, pocket_bytes[slot_offset : slot_offset + 4], "ARM9 System Bus")],
            ):
                return
            self._resend_queue.pop(0)
            if not self._spend_wipe_credit(ap_id):
                self._resent_counts[ap_id] = self._resent_counts.get(ap_id, 0) + 1
            pocket_bytes = pocket_bytes[:slot_offset] + slot_bytes + pocket_bytes[slot_offset + 4 :]
            self._note_delivery(ap_id, bag_field, native_id, pocket_bytes)
            logger.info(f"Resent {_item_display_name(ctx, ap_id)}.")

    def _spend_wipe_credit(self, ap_id: int) -> bool:
        credits = self._wipe_resend_credits.get(ap_id, 0)
        if credits <= 0:
            return False
        if credits == 1:
            del self._wipe_resend_credits[ap_id]
        else:
            self._wipe_resend_credits[ap_id] = credits - 1
        return True

    async def _ensure_key_items(self, ctx: BizHawkClientContext) -> None:
        self._key_item_check_countdown -= 1
        if self._key_item_check_countdown > 0 or self.bag_base_address is None or self._deliveries_held():
            return
        self._key_item_check_countdown = _KEY_ITEM_CHECK_EVERY_TICKS
        wanted: dict[str, set[int]] = {}
        for index, item in enumerate(ctx.items_received):
            if index >= self._applied_item_count and index not in self._delivered_ahead:
                continue
            if item.item not in _KEPT_ITEM_AP_IDS:
                continue
            write_info = _AP_ITEM_ID_TO_BAG_WRITE_INFO.get(item.item)
            if write_info is not None:
                wanted.setdefault(write_info[1], set()).add(write_info[0])
        for bag_field, native_ids in wanted.items():
            pocket_offset, pocket_capacity = BAG_POCKET_OFFSETS[bag_field]
            pocket_address = self.bag_base_address + pocket_offset
            pocket_bytes = bytes(
                (await bizhawk.read(ctx.bizhawk_ctx, [(pocket_address, pocket_capacity * 4, "ARM9 System Bus")]))[0]
            )
            if not await self._pocket_usable(ctx, pocket_bytes, bag_field):
                return
            held = {struct.unpack_from("<H", pocket_bytes, o)[0] for o in range(0, len(pocket_bytes), 4)}
            for native_id in sorted(native_ids - held):
                plan = plan_bag_item_write(pocket_bytes, native_id, 1, stack_cap_for_pocket(bag_field))
                if plan is None:
                    continue
                slot_offset, slot_bytes = plan
                if await bizhawk.guarded_write(
                    ctx.bizhawk_ctx,
                    [(pocket_address + slot_offset, slot_bytes, "ARM9 System Bus")],
                    [(pocket_address + slot_offset, pocket_bytes[slot_offset : slot_offset + 4], "ARM9 System Bus")],
                ):
                    pocket_bytes = pocket_bytes[:slot_offset] + slot_bytes + pocket_bytes[slot_offset + 4 :]
                    logger.info(f"Gave back {_item_display_name(ctx, HEARTGOLD_ITEM_ID_BASE + native_id)}.")

    async def _store_applied_item_count(
        self, ctx: BizHawkClientContext, applied_key: str, delivered_ahead_key: str
    ) -> None:
        if self._save_item_count_address is not None:
            count = min(self._applied_item_count, 0xFFFF)
            await bizhawk.write(
                ctx.bizhawk_ctx,
                [(
                    self._save_item_count_address,
                    _pack_item_count(count, self._ahead_mask(count)),
                    "ARM9 System Bus",
                )],
            )
        delivered_ahead_mask = _mask_from_indices(self._delivered_ahead)
        ctx.stored_data[delivered_ahead_key] = delivered_ahead_mask
        ctx.stored_data[applied_key] = self._applied_item_count
        await ctx.send_msgs(
            [
                {
                    "cmd": "Set",
                    "key": delivered_ahead_key,
                    "default": 0,
                    "want_reply": False,
                    "operations": [{"operation": "or", "value": delivered_ahead_mask}],
                },
                {
                    "cmd": "Set",
                    "key": applied_key,
                    "default": 0,
                    "want_reply": False,
                    "operations": [{"operation": "max", "value": self._applied_item_count}],
                },
            ]
        )

    async def _apply_pending_badges(self, ctx: BizHawkClientContext) -> None:
        if self.playerdata_profile_address is None:
            return

        thunder_withheld = await self._thunder_badge_withheld(ctx)
        if thunder_withheld:
            await self._clear_badge_bit(ctx, _BADGE_THUNDER_INDEX)

        seen_badge_indices = {
            _AP_ITEM_ID_TO_BADGE_INDEX[item.item] for item in ctx.items_received if item.item in _AP_ITEM_ID_TO_BADGE_INDEX
        }
        for badge_index in seen_badge_indices:
            if badge_index == _BADGE_THUNDER_INDEX and thunder_withheld is not False:
                continue
            byte_offset = _PROFILE_JOHTO_BADGES_OFFSET if badge_index < 8 else _PROFILE_KANTO_BADGES_OFFSET
            bit = badge_index if badge_index < 8 else badge_index - 8
            badge_byte_address = self.playerdata_profile_address + byte_offset
            current_byte = (await bizhawk.read(ctx.bizhawk_ctx, [(badge_byte_address, 1, "ARM9 System Bus")]))[0]
            if current_byte[0] & (1 << bit):
                continue

            new_byte = bytes([current_byte[0] | (1 << bit)])
            await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(badge_byte_address, new_byte, "ARM9 System Bus")],
                [(badge_byte_address, bytes(current_byte), "ARM9 System Bus")],
            )

    async def _thunder_badge_withheld(self, ctx: BizHawkClientContext) -> bool | None:
        if self.flags_array_address is None:
            return False
        try:
            byte_index, bit_index = flag_byte_and_bit(_FLAG_HIDE_VERMILION_GYM_STOPS)
            stops_byte = (
                await bizhawk.read(
                    ctx.bizhawk_ctx, [(self.flags_array_address + byte_index, 1, "ARM9 System Bus")]
                )
            )[0]
            if stops_byte[0] & (1 << bit_index):
                return False
            map_id = await self._current_map_id(ctx)
        except bizhawk.RequestFailedError:
            return None
        if map_id is None:
            return False
        return map_id in _THUNDER_BADGE_WITHHELD_MAP_IDS

    async def _clear_badge_bit(self, ctx: BizHawkClientContext, badge_index: int) -> None:
        byte_offset = _PROFILE_JOHTO_BADGES_OFFSET if badge_index < 8 else _PROFILE_KANTO_BADGES_OFFSET
        bit = badge_index if badge_index < 8 else badge_index - 8
        badge_byte_address = self.playerdata_profile_address + byte_offset
        try:
            current_byte = (await bizhawk.read(ctx.bizhawk_ctx, [(badge_byte_address, 1, "ARM9 System Bus")]))[0]
            if not (current_byte[0] & (1 << bit)):
                return
            await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(badge_byte_address, bytes([current_byte[0] & ~(1 << bit) & 0xFF]), "ARM9 System Bus")],
                [(badge_byte_address, bytes(current_byte), "ARM9 System Bus")],
            )
        except bizhawk.RequestFailedError:
            pass
