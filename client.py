# client.py
#
# BizHawk in-game connector. Two jobs:
#   - Check detection: read the vanilla savedata flag bits directly (see
#     location_flags.py) -- no ROM patch needed.
#   - Remote items: write them into the running game's Bag savedata via
#     RAM once ctx.items_received reports them.
#
# Every read/write here is relative to the RAM address of the running
# game's SaveData struct, relocated fresh every session (see "Dynamic
# SaveData location" below) since HGSS double-buffers save data across two
# physical slots. See NOTES.md for the full derivation and history.
#
# HEARTGOLD_BAG_BASE_ADDRESS/HEARTGOLD_FLAGS_ARRAY_ADDRESS env vars are a
# manual override (skips the scan) for troubleshooting -- unset by
# default.

from __future__ import annotations

import os
import struct
from typing import TYPE_CHECKING

import worlds._bizhawk as bizhawk
from worlds._bizhawk.client import BizHawkClient

from data.items import ITEMS
from data.rules import BADGES
from items import HEARTGOLD_ITEM_ID_BASE
from location_flags import (
    build_badge_index_to_trainer_flag_id,
    build_dexsanity_flag_to_ap_location_id,
    build_flag_id_to_ap_location_id,
    build_locally_substituted_ap_location_ids,
    menu_unlock_flag_id_by_item_key,
)
from rom import HEARTGOLD_US_ID_CODE, SOULSILVER_US_ID_CODE
from save_layout import (
    BAG_POCKET_OFFSETS,
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

if TYPE_CHECKING:
    from worlds._bizhawk.context import BizHawkClientContext

# Manual override env vars -- unset by default, so the automatic scan below
# is what actually runs for players. ARM9 System Bus addresses (Main RAM
# domain + 0x02000000).
HEARTGOLD_BAG_BASE_ADDRESS_ENV = "HEARTGOLD_BAG_BASE_ADDRESS"
HEARTGOLD_FLAGS_ARRAY_ADDRESS_ENV = "HEARTGOLD_FLAGS_ARRAY_ADDRESS"


def _resolve_address_override(env_var: str) -> int | None:
    """`None` (the default) unless `env_var` is set to a parseable int
    (hex or decimal)."""
    raw = os.environ.get(env_var)
    if not raw:
        return None
    try:
        return int(raw, 0)
    except ValueError:
        return None


# -- Dynamic SaveData location -----------------------------------------------
#
# Locate SaveData fresh every session by scanning for SaveData.
# arrayHeaders[]'s own signature instead of trusting a fixed address --
# see NOTES.md for the full struct derivation.

_SAVE_ARRAY_HEADER_SIZE = 16  # include/save.h: SaveArrayHeader, 4+4+4+2+2
_SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT = 5  # SysInfo..SaveVarsFlags
_DYNAMIC_REGION_SIZE = 35 * 0x1000  # SAVE_PAGE_MAX * SAVE_SECTOR_SIZE
_SAVE_COUNTER_SIZE = 4
_BAG_CHUNK_ID = 3  # SAVE_BAG
_FLAGS_CHUNK_ID = 4  # SAVE_FLAGS
_POKEDEX_CHUNK_ID = 6  # SAVE_POKEDEX
_PARTY_CHUNK_ID = 2  # SAVE_PARTY
_GAMESTATS_CHUNK_ID = 16  # SAVE_GAMESTATS

# DeathLink send: GAME_STAT_PLAYER_MON_FAINTED counter, a real vanilla
# savedata field -- see NOTES.md for the struct derivation.
_GAME_STAT_PLAYER_MON_FAINTED_OFFSET = 338

# DeathLink receive: PartyCore/PartyPokemon layout for zeroing current HP,
# a plain unencrypted savedata field -- see NOTES.md for the derivation.
_PARTY_CUR_COUNT_OFFSET = 4
_PARTY_MONS_OFFSET = 8
_PARTY_POKEMON_STRUCT_SIZE = 0xEC
_PARTY_POKEMON_HP_OFFSET = 0x96
_PARTY_MAX_SIZE = 6

# Pokedex.caughtSpecies -- see location_flags.dexsanity_pokedex_bit_for_species.
_POKEDEX_CAUGHT_SPECIES_OFFSET = 4
_POKEDEX_CAUGHT_SPECIES_SIZE = 64

_PLAYERDATA_CHUNK_ID = 1  # SAVE_PLAYERDATA

# include/player_data.h PLAYERDATA/PlayerProfile layout -- see NOTES.md
# for the full field-offset derivation, including the badge-flag bit
# split (johtoBadges for badge_no < 8, kantoBadges otherwise).
_PLAYERDATA_PROFILE_OFFSET = 4

# Options sits at the start of PLAYERDATA (offset 0) -- see save_layout.py
# for the live-verified bit layout.
_PLAYERDATA_OPTIONS_OFFSET = 0
_PROFILE_MONEY_OFFSET = 20
_PROFILE_JOHTO_BADGES_OFFSET = 26
_PROFILE_KANTO_BADGES_OFFSET = 31
_MAX_MONEY = 999999  # include/player_data.h: MAX_MONEY

# Scan window for arrayHeaders -- generous but bounded (EWRAM is 4 MiB
# total). See NOTES.md for how this range was chosen.
_ARRAY_HEADERS_SCAN_START = 0x02298000
_ARRAY_HEADERS_SCAN_LENGTH = 0x10000
# Larger single reads have been observed to fail against the BizHawk
# connector -- read in bounded chunks instead.
_ARRAY_HEADERS_SCAN_READ_CHUNK = 0x4000


async def _read_chunked(ctx: BizHawkClientContext, address: int, length: int, domain: str) -> bytes:
    """Read `length` bytes starting at `address`, splitting into
    _ARRAY_HEADERS_SCAN_READ_CHUNK-sized requests."""
    out = bytearray()
    offset = 0
    while offset < length:
        step = min(_ARRAY_HEADERS_SCAN_READ_CHUNK, length - offset)
        piece = (await bizhawk.read(ctx.bizhawk_ctx, [(address + offset, step, domain)]))[0]
        out.extend(piece)
        offset += step
    return bytes(out)


def _looks_like_array_headers(data: bytes, offset: int) -> bool:
    """True if data[offset:] starts with _SAVE_ARRAY_HEADER_SIGNATURE_
    CHUNK_COUNT consecutive SaveArrayHeader records whose id fields are
    exactly 0, 1, 2, ... in order."""
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
    """Every offset into `data` where `_looks_like_array_headers` matches.
    Returns every candidate (not just the first), so `_locate_save_
    addresses` can verify each against real Bag contents."""
    needed = _SAVE_ARRAY_HEADER_SIZE * _SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT
    return [offset for offset in range(0, len(data) - needed, 4) if _looks_like_array_headers(data, offset)]


async def _find_array_headers_address(ctx: BizHawkClientContext) -> int | None:
    """First plausible arrayHeaders candidate address, unverified against
    real Bag contents. `_locate_save_addresses` (the real session-start/
    reload path) uses `_find_array_headers_candidates` plus a
    plausibility check instead."""
    data = await _read_chunked(ctx, _ARRAY_HEADERS_SCAN_START, _ARRAY_HEADERS_SCAN_LENGTH, "ARM9 System Bus")
    candidates = _find_array_headers_candidates(data)
    return _ARRAY_HEADERS_SCAN_START + candidates[0] if candidates else None


async def _chunk_offset(ctx: BizHawkClientContext, array_headers_address: int, chunk_id: int) -> int:
    """Read arrayHeaders[chunk_id].offset directly (ground truth, exactly
    what the game itself uses internally)."""
    record_address = array_headers_address + chunk_id * _SAVE_ARRAY_HEADER_SIZE
    record_bytes = (
        await bizhawk.read(ctx.bizhawk_ctx, [(record_address, _SAVE_ARRAY_HEADER_SIZE, "ARM9 System Bus")])
    )[0]
    _record_id, _size, offset, _crc, _slot = struct.unpack("<iIIHH", bytes(record_bytes))
    return offset


# A real Bag "items" pocket slot (u16 id, u16 quantity) is either empty
# (id 0) or a real item id in a small stack.
_MAX_PLAUSIBLE_ITEM_ID = 536
_MAX_PLAUSIBLE_ITEM_QUANTITY = 999
_PLAUSIBILITY_CHECK_SLOT_COUNT = 8


async def _bag_looks_plausible(ctx: BizHawkClientContext, bag_address: int) -> bool:
    """Read the first _PLAUSIBILITY_CHECK_SLOT_COUNT "items"-pocket slots
    at a candidate bag_address and check every one looks like a real
    ItemSlot -- the verification step the arrayHeaders signature alone
    doesn't provide."""
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
    """Locate this session's real Bag/SaveVarsFlags.flags[]/Pokedex.
    caughtSpecies/PlayerProfile/Party/GameStats addresses fresh. Tries
    every scan candidate, accepting the first whose derived Bag address
    passes `_bag_looks_plausible`. Returns None if nothing plausible was
    found (caller retries next tick)."""
    data = await _read_chunked(ctx, _ARRAY_HEADERS_SCAN_START, _ARRAY_HEADERS_SCAN_LENGTH, "ARM9 System Bus")

    for candidate_offset in _find_array_headers_candidates(data):
        array_headers_address = _ARRAY_HEADERS_SCAN_START + candidate_offset
        dynamic_region_base = array_headers_address - _SAVE_COUNTER_SIZE - _DYNAMIC_REGION_SIZE
        bag_chunk_offset = await _chunk_offset(ctx, array_headers_address, _BAG_CHUNK_ID)
        bag_address = dynamic_region_base + bag_chunk_offset

        if not await _bag_looks_plausible(ctx, bag_address):
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


async def _array_headers_still_valid(ctx: BizHawkClientContext, array_headers_address: int) -> bool:
    """Cheap per-tick check: re-read the signature bytes at a previously-
    found arrayHeaders address and confirm they still match. If this
    fails (e.g. a save reload), the caller re-runs the full scan."""
    signature_size = _SAVE_ARRAY_HEADER_SIZE * _SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT
    try:
        data = (
            await bizhawk.read(ctx.bizhawk_ctx, [(array_headers_address, signature_size, "ARM9 System Bus")])
        )[0]
    except bizhawk.RequestFailedError:
        return False
    return _looks_like_array_headers(bytes(data), 0)


# Server data-storage key remembering, across client restarts, how many
# of ctx.items_received have already been written into the bag (no in-
# ROM/in-save counter exists to read this from). Known limitation: a save
# reload from before some already-applied remote items were written does
# not roll this counter back, so those items are not re-granted -- fixing
# that needs ROM/ARM-hook cooperation, out of scope for this client-only
# v1.
_APPLIED_ITEM_COUNT_KEY_TEMPLATE = "pokemon_heartgold_applied_item_count_{team}_{slot}"
_STARTING_MONEY_APPLIED_KEY_TEMPLATE = "pokemon_heartgold_starting_money_applied_{team}_{slot}"
_START_LOCATION_FLAGS_APPLIED_KEY_TEMPLATE = "pokemon_heartgold_start_location_flags_applied_{team}_{slot}"

# randomize_start_location: FLAG_GOT_STARTER (include/constants/flags.h,
# 0x6A) is already set by the vanilla ChooseStarter scene itself (that
# scene runs completely unmodified -- see rom/startlocation.py) -- these
# are only the OTHER menu-unlock flags vanilla would normally set via
# New Bark content this feature skips entirely (Mom, walking through
# town, meeting the rival), plus advancing the rival's own flag chain so
# he still eventually appears at his next real checkpoint instead of
# never again.
_START_LOCATION_FLAG_GOT_STARTER = 0x6A
_START_LOCATION_FLAGS_TO_SET = (
    0x11B,  # FLAG_GOT_BAG
    0x11C,  # FLAG_GOT_TRAINER_CARD
    0x11D,  # FLAG_GOT_SAVE_BUTTON
    0x11E,  # FLAG_GOT_OPTIONS_BUTTON
    0x6B,  # FLAG_GOT_POKEDEX
    0x9C,  # FLAG_GOT_POKEGEAR
    0x190,  # FLAG_HIDE_NEW_BARK_RIVAL
)
_START_LOCATION_FLAGS_TO_CLEAR = (0x19C,)  # FLAG_HIDE_CHERRYGROVE_RIVAL

# task M1.5: cap on how many pending items _apply_received_items will write
# in a single game_watcher tick -- batches a large backlog (e.g. right
# after connecting, or catching up after a big multiworld fill) down to a
# handful of ticks instead of one item per tick (roughly one per second on
# a real BizHawk session), while still bounding how long any one tick's
# run of Bag read/write RPC round trips can take.
_MAX_ITEMS_APPLIED_PER_TICK = 20


# -- Item id <-> Bag pocket mapping ------------------------------------------


def _build_ap_item_id_to_bag_write_info() -> dict[int, tuple[int, str]]:
    """AP item id -> (native HG/SS item id, Bag field name to write it
    into)."""
    result: dict[int, tuple[int, str]] = {}
    for data in ITEMS.values():
        bag_field = POCKET_KEY_TO_BAG_FIELD.get(data["pocket"])
        if bag_field is None:
            continue
        result[HEARTGOLD_ITEM_ID_BASE + data["id"]] = (data["id"], bag_field)
    return result


_AP_ITEM_ID_TO_BAG_WRITE_INFO = _build_ap_item_id_to_bag_write_info()


def _build_ap_item_id_to_badge_index() -> dict[int, int]:
    """AP item id -> badge.h's own BADGE_* index (0-15), for the 16
    badge_<name> synthetic items. pocket = "badge" is deliberately absent
    from POCKET_KEY_TO_BAG_FIELD, so these never appear in
    _AP_ITEM_ID_TO_BAG_WRITE_INFO above -- receiving one instead sets the
    matching bit in PlayerProfile.johtoBadges/kantoBadges."""
    result: dict[int, int] = {}
    for key, data in ITEMS.items():
        if data["pocket"] != "badge":
            continue
        badge_name = key.removeprefix("badge_")
        result[HEARTGOLD_ITEM_ID_BASE + data["id"]] = BADGES[badge_name]
    return result


_AP_ITEM_ID_TO_BADGE_INDEX = _build_ap_item_id_to_badge_index()

# badge index -> TRAINER_FLAG_BASE + that gym Leader's trainer id -- see
# _apply_pending_badges's own docstring for why a received badge item's
# PlayerProfile bit can't just be written immediately.
_BADGE_INDEX_TO_TRAINER_FLAG_ID = build_badge_index_to_trainer_flag_id()


def _build_menu_unlock_maps() -> tuple[dict[int, int], dict[int, str]]:
    """(AP item id -> SaveVarsFlags flag id, flag id -> `options.
    RandomizeMenuUnlocks` option key) for the 6 `menu_unlock_*` synthetic
    items -- see `_apply_menu_unlock_gating`. The option key is always the
    item/location key with its `menu_unlock_` prefix stripped, by
    construction (data_gen/locations.toml)."""
    flag_id_by_item_key = menu_unlock_flag_id_by_item_key()
    ap_item_id_to_flag_id: dict[int, int] = {}
    flag_id_to_option_key: dict[int, str] = {}
    for key, flag_id in flag_id_by_item_key.items():
        ap_item_id_to_flag_id[HEARTGOLD_ITEM_ID_BASE + ITEMS[key]["id"]] = flag_id
        flag_id_to_option_key[flag_id] = key.removeprefix("menu_unlock_")
    return ap_item_id_to_flag_id, flag_id_to_option_key


_AP_ITEM_ID_TO_MENU_UNLOCK_FLAG_ID, _MENU_UNLOCK_FLAG_ID_TO_OPTION_KEY = _build_menu_unlock_maps()

# menu_unlock flag ids are deliberately kept OUT of _FLAG_ID_TO_AP_LOCATION_ID
# (the generic check-detection map _check_locations polls every tick) --
# real bug found by code review, 2026-08-17: these 6 flags are the *same*
# bits _apply_menu_unlock_gating also writes (1 once the matching item is
# owned, 0 otherwise), so generic detection would report the location as
# checked the moment the player *received* the item, not when they
# actually reached the vanilla trigger point -- releasing whatever item
# was placed there without the corresponding real-game action, and (worse)
# racing _apply_menu_unlock_gating's own suppression: a vanilla SetFlag
# landing between _check_locations's read and the gating write later in
# the same tick would be cleared before ever being observed, silently and
# permanently losing that location's check (5 of the 6 flags are set by a
# script that never replays -- see rom/startlocation.py's scr_seq_
# T20R0201_000/scr_seq_0229_R30R0201.s notes). _apply_menu_unlock_gating
# now owns detection AND gating together, atomically, from one single read
# -- see its own docstring.
_ALL_FLAG_ID_TO_AP_LOCATION_ID = build_flag_id_to_ap_location_id()
_MENU_UNLOCK_FLAG_ID_TO_AP_LOCATION_ID = {
    flag_id: _ALL_FLAG_ID_TO_AP_LOCATION_ID[flag_id]
    for flag_id in _MENU_UNLOCK_FLAG_ID_TO_OPTION_KEY
    if flag_id in _ALL_FLAG_ID_TO_AP_LOCATION_ID
}
_FLAG_ID_TO_AP_LOCATION_ID = {
    flag_id: ap_location_id
    for flag_id, ap_location_id in _ALL_FLAG_ID_TO_AP_LOCATION_ID.items()
    if flag_id not in _MENU_UNLOCK_FLAG_ID_TO_OPTION_KEY
}

# Pokedex.caughtSpecies bit -> AP location id (task M3.4, Dexsanity) -- a
# separate savedata array from SaveVarsFlags.flags[] above, so a separate
# dict and a separate read/check path (see location_flags.build_dexsanity_
# flag_to_ap_location_id's own docstring for why these can't share one map).
_DEXSANITY_FLAG_ID_TO_AP_LOCATION_ID = build_dexsanity_flag_to_ap_location_id()

# AP location ids already covered by ROM substitution -- see NOTES.md for
# the double-delivery bug this prevents.
_LOCALLY_SUBSTITUTED_AP_LOCATION_IDS = build_locally_substituted_ap_location_ids()


class HeartGoldClient(BizHawkClient):
    game = "Pokemon HGSS"
    system = "NDS"
    # Must match output_patch.HeartGoldProcedurePatch.patch_file_ending --
    # this is what makes the Launcher's "Open Patch" dialog recognize a
    # real .apheartgold file.
    patch_suffix = ".apheartgold"

    local_checked_locations: set[int]
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
    _qol_applied: bool
    _known_tm_quantities: dict[int, int] | None
    _known_player_mon_fainted: int | None
    _previous_death_link: float | None
    _ignore_next_death_link: bool
    _death_link_tag_set: bool

    def __init__(self) -> None:
        super().__init__()
        self.local_checked_locations = set()
        self.bag_base_address = None
        self.flags_array_address = None
        self.pokedex_caught_species_address = None
        self.playerdata_profile_address = None
        self.party_address = None
        self.gamestats_address = None
        self._array_headers_address = None
        self._manual_bag_base_override = None
        self._manual_flags_array_override = None
        self._applied_item_count = 0
        self._qol_applied = False
        self._known_tm_quantities = None
        self._known_player_mon_fainted = None
        self._previous_death_link = None
        self._ignore_next_death_link = False
        self._death_link_tag_set = False
        self._starting_money_applied = False
        self._start_location_flags_applied = False

    async def validate_rom(self, ctx: BizHawkClientContext) -> bool:
        try:
            id_code = (await bizhawk.read(ctx.bizhawk_ctx, [(0x0C, 4, "ROM")]))[0]
        except bizhawk.RequestFailedError:
            return False

        if bytes(id_code) not in (HEARTGOLD_US_ID_CODE, SOULSILVER_US_ID_CODE):
            return False

        ctx.game = self.game
        ctx.items_handling = 0b111  # locations + remote items + start inventory
        ctx.want_slot_data = True
        ctx.watcher_timeout = 1.0

        self.local_checked_locations = set()
        self._manual_bag_base_override = _resolve_address_override(HEARTGOLD_BAG_BASE_ADDRESS_ENV)
        self._manual_flags_array_override = _resolve_address_override(HEARTGOLD_FLAGS_ARRAY_ADDRESS_ENV)
        self.bag_base_address = self._manual_bag_base_override
        self.flags_array_address = self._manual_flags_array_override
        self.pokedex_caught_species_address = None
        self.playerdata_profile_address = None
        self.party_address = None
        self.gamestats_address = None
        self._array_headers_address = None
        self._applied_item_count = 0
        self._qol_applied = False
        self._known_tm_quantities = None
        self._known_player_mon_fainted = None
        self._previous_death_link = None
        self._ignore_next_death_link = False
        self._death_link_tag_set = False
        self._starting_money_applied = False
        self._start_location_flags_applied = False

        return True

    async def _ensure_addresses_located(self, ctx: BizHawkClientContext) -> bool:
        """Make sure bag_base_address/flags_array_address are current,
        relocating via SaveData.arrayHeaders[] if needed. Returns whether
        both addresses are currently usable. pokedex_caught_species_address/
        playerdata_profile_address are best-effort: the manual bag/flags
        override env vars predate Dexsanity/badges and skip the scan
        entirely, so that override combination leaves them None forever
        (_check_locations/_apply_received_items skip the Dexsanity check
        and badge delivery respectively in that case, rather than failing
        the whole tick)."""
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
        """Set Text Speed/Battle Scene from this player's `fast_text_
        speed`/`skip_battle_animations` options, once per connection. A
        plain read-modify-write of the Options word -- other bits are
        preserved untouched, and the player can still change either
        setting freely afterward from the in-game Options menu."""
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

    async def _apply_starting_money(self, ctx: BizHawkClientContext, money_applied_key: str) -> None:
        """Set PlayerProfile.money from this player's `starting_money`
        option, exactly once ever for this slot. Guarded by a flag this
        world stores server-side (money_applied_key, set via the same
        "Set"+"max" Datastorage pattern _store_applied_item_count uses) --
        deliberately not a "money still looks vanilla" heuristic, since
        the player's money changes constantly during play and could
        coincidentally pass back through any fixed value later, which
        would make a value-based guard misfire and wipe out money the
        player has since earned or spent."""
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
            return  # retry next tick

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

    async def _apply_start_location_flags(self, ctx: BizHawkClientContext, applied_key: str) -> None:
        """randomize_start_location: once FLAG_GOT_STARTER is observed
        set (the vanilla ChooseStarter scene, itself untouched, sets it
        the moment the player picks a starter -- see rom/startlocation.
        py), set the other menu-unlock flags vanilla would otherwise set
        via New Bark content this feature skips (Bag/Trainer Card/Save
        button/Options button/Pokedex/Pokegear), and advance the rival's
        own flag chain so he still eventually appears at his next real
        checkpoint instead of never again (see docs/scope.md). Exactly
        once ever per slot, guarded by a server-stored flag -- same
        durable "Set"+"max" Datastorage pattern _apply_starting_money
        uses, not a live-only guard, so a reconnect never re-fires this
        once it has already applied."""
        if self._start_location_flags_applied or self.flags_array_address is None:
            return

        if not bool(ctx.slot_data.get("randomize_start_location", False)):
            self._start_location_flags_applied = True
            return

        starter_byte_index, starter_bit_index = flag_byte_and_bit(_START_LOCATION_FLAG_GOT_STARTER)
        starter_byte_address = self.flags_array_address + starter_byte_index
        starter_byte = (await bizhawk.read(ctx.bizhawk_ctx, [(starter_byte_address, 1, "ARM9 System Bus")]))[0]
        if not (starter_byte[0] & (1 << starter_bit_index)):
            return  # hasn't picked a starter yet -- retry next tick

        touched_bytes: dict[int, int] = {}
        original_bytes: dict[int, int] = {}

        async def _byte_at(byte_index: int) -> int:
            if byte_index not in touched_bytes:
                address = self.flags_array_address + byte_index
                current = (await bizhawk.read(ctx.bizhawk_ctx, [(address, 1, "ARM9 System Bus")]))[0]
                touched_bytes[byte_index] = current[0]
                original_bytes[byte_index] = current[0]
            return touched_bytes[byte_index]

        # randomize_menu_unlocks: whichever of Bag/Trainer Card/Save
        # button/Options button/Pokedex/Pokegear that option turned into a
        # real, independently-gated item is excluded from this automatic
        # grant -- _apply_menu_unlock_gating owns those flags instead,
        # gated on actually receiving the matching menu_unlock_* item.
        enabled_menu_unlocks = set(ctx.slot_data.get("randomize_menu_unlocks", []))
        for flag_id in _START_LOCATION_FLAGS_TO_SET:
            option_key = _MENU_UNLOCK_FLAG_ID_TO_OPTION_KEY.get(flag_id)
            if option_key is not None and option_key in enabled_menu_unlocks:
                continue
            byte_index, bit_index = flag_byte_and_bit(flag_id)
            touched_bytes[byte_index] = (await _byte_at(byte_index)) | (1 << bit_index)
        for flag_id in _START_LOCATION_FLAGS_TO_CLEAR:
            byte_index, bit_index = flag_byte_and_bit(flag_id)
            touched_bytes[byte_index] = (await _byte_at(byte_index)) & ~(1 << bit_index)

        # Guard against the exact same snapshot the new values were
        # computed from (original_bytes), not a fresh re-read -- a flag
        # the game sets in the gap between the two would otherwise pass a
        # fresh guard while still getting clobbered by a new_value
        # computed from stale data (real bug, found by code review,
        # 2026-08-17; byte 13 holds both FLAG_GOT_STARTER and
        # FLAG_GOT_POKEDEX, so this window is not purely theoretical).
        writes = [
            (self.flags_array_address + byte_index, bytes([new_value]), "ARM9 System Bus")
            for byte_index, new_value in touched_bytes.items()
        ]
        guards = [
            (self.flags_array_address + byte_index, bytes([original_bytes[byte_index]]), "ARM9 System Bus")
            for byte_index in touched_bytes
        ]

        write_succeeded = await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, guards)
        if not write_succeeded:
            return  # retry next tick

        self._start_location_flags_applied = True
        ctx.stored_data[applied_key] = 1
        await ctx.send_msgs(
            [
                {
                    "cmd": "Set",
                    "key": applied_key,
                    "default": 0,
                    "want_reply": False,
                    "operations": [{"operation": "max", "value": 1}],
                }
            ]
        )

    async def _restore_reusable_tms(self, ctx: BizHawkClientContext) -> None:
        """Reusable TMs: no ROM patch (see NOTES.md for why the ARM hook
        approach was abandoned). Every tick, compare each TM/HM pocket
        item's total quantity (summed across slots) against the last
        tick's count and write back any decrease via the same
        plan_bag_item_write/guarded_write path _apply_received_items uses
        -- a consumed TM/HM simply reappears next poll. The first tick
        after (re)connecting only records a baseline."""
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
                    continue  # pocket full, or stack cap reached -- retry next tick
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
        """Set/clear the "DeathLink" connection tag once per connection to
        match this player's own `death_link` option -- CommonContext's own
        `update_death_link` helper (also used to send the initial
        ConnectUpdate)."""
        if self._death_link_tag_set:
            return
        await ctx.update_death_link(bool(ctx.slot_data.get("death_link", False)))
        self._death_link_tag_set = True

    async def _send_death_link_on_faint(self, ctx: BizHawkClientContext) -> None:
        """DeathLink send side: poll GAME_STAT_PLAYER_MON_FAINTED (see
        NOTES.md) and send a death the moment it increases. The first
        tick after (re)connecting only records a baseline."""
        if not bool(ctx.slot_data.get("death_link", False)) or self.gamestats_address is None:
            return

        stat_address = self.gamestats_address + _GAME_STAT_PLAYER_MON_FAINTED_OFFSET
        raw = (await bizhawk.read(ctx.bizhawk_ctx, [(stat_address, 2, "ARM9 System Bus")]))[0]
        (fainted_count,) = struct.unpack("<H", bytes(raw))

        if self._known_player_mon_fainted is not None and fainted_count > self._known_player_mon_fainted:
            self._ignore_next_death_link = True
            await ctx.send_death(f"{ctx.player_names[ctx.slot]}'s Pokémon fainted!")

        self._known_player_mon_fainted = fainted_count

    async def _receive_death_link(self, ctx: BizHawkClientContext) -> None:
        """DeathLink receive side: notice `ctx.last_death_link` changing
        (CommonContext's own DeathLink bookkeeping) and zero every real
        party Pokemon's current HP, matching a vanilla blackout.
        `_ignore_next_death_link` skips the echo of this player's own
        just-sent death (Bounce rebroadcasts to the sender too)."""
        if not bool(ctx.slot_data.get("death_link", False)) or self.party_address is None:
            return

        if self._previous_death_link is None:
            self._previous_death_link = ctx.last_death_link
            return

        if ctx.last_death_link == self._previous_death_link:
            return
        self._previous_death_link = ctx.last_death_link

        if self._ignore_next_death_link:
            self._ignore_next_death_link = False
            return

        cur_count_raw = (
            await bizhawk.read(ctx.bizhawk_ctx, [(self.party_address + _PARTY_CUR_COUNT_OFFSET, 4, "ARM9 System Bus")])
        )[0]
        (cur_count,) = struct.unpack("<i", bytes(cur_count_raw))
        cur_count = max(0, min(cur_count, _PARTY_MAX_SIZE))

        mons_address = self.party_address + _PARTY_MONS_OFFSET
        writes = [
            (
                mons_address + i * _PARTY_POKEMON_STRUCT_SIZE + _PARTY_POKEMON_HP_OFFSET,
                struct.pack("<H", 0),
                "ARM9 System Bus",
            )
            for i in range(cur_count)
        ]
        if writes:
            await bizhawk.write(ctx.bizhawk_ctx, writes)

    async def game_watcher(self, ctx: BizHawkClientContext) -> None:
        if ctx.server is None or ctx.server.socket.closed or ctx.slot_data is None:
            return

        if not await self._ensure_addresses_located(ctx):
            return  # retried automatically next tick

        applied_key = _APPLIED_ITEM_COUNT_KEY_TEMPLATE.format(team=ctx.team, slot=ctx.slot)
        ctx.set_notify(applied_key)
        self._applied_item_count = max(self._applied_item_count, int(ctx.stored_data.get(applied_key, 0) or 0))

        money_applied_key = _STARTING_MONEY_APPLIED_KEY_TEMPLATE.format(team=ctx.team, slot=ctx.slot)
        ctx.set_notify(money_applied_key)
        self._starting_money_applied = self._starting_money_applied or bool(
            int(ctx.stored_data.get(money_applied_key, 0) or 0)
        )

        start_location_flags_applied_key = _START_LOCATION_FLAGS_APPLIED_KEY_TEMPLATE.format(
            team=ctx.team, slot=ctx.slot
        )
        ctx.set_notify(start_location_flags_applied_key)
        self._start_location_flags_applied = self._start_location_flags_applied or bool(
            int(ctx.stored_data.get(start_location_flags_applied_key, 0) or 0)
        )

        try:
            await self._apply_qol_options(ctx)
            await self._apply_starting_money(ctx, money_applied_key)
            await self._apply_start_location_flags(ctx, start_location_flags_applied_key)
            await self._restore_reusable_tms(ctx)
            await self._update_death_link_tag(ctx)
            await self._send_death_link_on_faint(ctx)
            await self._receive_death_link(ctx)
            await self._check_locations(ctx)
            await self._apply_received_items(ctx, applied_key)
            await self._apply_pending_badges(ctx)
            await self._apply_menu_unlock_gating(ctx)
        except bizhawk.RequestFailedError:
            pass  # exit handler, return to main loop to reconnect

    async def _check_locations(self, ctx: BizHawkClientContext) -> None:
        flags_address = self.flags_array_address
        flags_bytes = (await bizhawk.read(ctx.bizhawk_ctx, [(flags_address, FLAGS_ARRAY_SIZE, "ARM9 System Bus")]))[0]

        newly_checked = {
            ap_location_id
            for flag_id, ap_location_id in _FLAG_ID_TO_AP_LOCATION_ID.items()
            if ap_location_id in ctx.missing_locations and is_flag_set(bytes(flags_bytes), flag_id)
        }

        # Dexsanity (task M3.4): Pokedex.caughtSpecies is its own savedata
        # array, not SaveVarsFlags.flags[] -- a separate read, separate map,
        # unioned into the same newly_checked set so one ctx.check_locations
        # call covers both. Best-effort: pokedex_caught_species_address can
        # be None under the manual bag/flags override env vars (see
        # _ensure_addresses_located), in which case Dexsanity checks are
        # simply skipped this tick rather than failing the whole thing.
        #
        # dexsanity_trigger ("catch"/"encounter"): Pokedex.seenSpecies is
        # the exact same shape as caughtSpecies (same size, same bit
        # formula) and sits immediately after it in the struct
        # (include/pokedex.h), so this is just a fixed +64 byte offset --
        # no separate address needs to be located.
        if self.pokedex_caught_species_address is not None:
            pokedex_address = self.pokedex_caught_species_address
            if ctx.slot_data.get("dexsanity_trigger") == "encounter":
                pokedex_address += _POKEDEX_CAUGHT_SPECIES_SIZE
            pokedex_bytes = (
                await bizhawk.read(
                    ctx.bizhawk_ctx,
                    [(pokedex_address, _POKEDEX_CAUGHT_SPECIES_SIZE, "ARM9 System Bus")],
                )
            )[0]
            newly_checked |= {
                ap_location_id
                for bit, ap_location_id in _DEXSANITY_FLAG_ID_TO_AP_LOCATION_ID.items()
                if ap_location_id in ctx.missing_locations and is_flag_set(bytes(pokedex_bytes), bit)
            }

        if newly_checked and newly_checked != self.local_checked_locations:
            self.local_checked_locations = newly_checked
            await ctx.check_locations(newly_checked)

    async def _apply_received_items(self, ctx: BizHawkClientContext, applied_key: str) -> None:
        """Apply as many pending items as possible in this single tick (up
        to _MAX_ITEMS_APPLIED_PER_TICK), instead of just one -- otherwise a
        large backlog trickles in at roughly one item per second. Stops
        early (retried next tick) the moment a real Bag write is needed
        and genuinely can't proceed yet."""
        applied_this_tick = 0
        while (
            applied_this_tick < _MAX_ITEMS_APPLIED_PER_TICK
            and self._applied_item_count < len(ctx.items_received)
        ):
            next_item = ctx.items_received[self._applied_item_count]

            # Archipelago's server sends every item belonging to this
            # player through items_received once its location is checked
            # -- including this player's own locations, which this client
            # already delivered via ROM substitution. Writing it into the
            # Bag again would double it -- see NOTES.md.
            already_delivered_locally = (
                next_item.player == ctx.slot and next_item.location in _LOCALLY_SUBSTITUTED_AP_LOCATION_IDS
            )

            # Badges never go through the Bag at all -- receiving one sets
            # the matching bit in PlayerProfile.johtoBadges/kantoBadges
            # instead (see rom/badgedata.py for how the vanilla local
            # grant is neutralized so it can't also set this bit). That
            # write itself is deferred to _apply_pending_badges (see its
            # own docstring) -- here we only advance the resume counter.
            badge_index = None if already_delivered_locally else _AP_ITEM_ID_TO_BADGE_INDEX.get(next_item.item)
            if badge_index is not None:
                self._applied_item_count += 1
                applied_this_tick += 1
                continue

            write_info = None if already_delivered_locally else _AP_ITEM_ID_TO_BAG_WRITE_INFO.get(next_item.item)
            if write_info is None:
                # Not one of this world's own bag items, or already
                # delivered locally -- count it as "applied" so the queue
                # doesn't stall, no RPC round trip needed, keep looping.
                self._applied_item_count += 1
                applied_this_tick += 1
                continue

            native_item_id, bag_field = write_info
            pocket_offset, pocket_capacity = BAG_POCKET_OFFSETS[bag_field]
            pocket_address = self.bag_base_address + pocket_offset
            pocket_size = pocket_capacity * 4

            pocket_bytes = (
                await bizhawk.read(ctx.bizhawk_ctx, [(pocket_address, pocket_size, "ARM9 System Bus")])
            )[0]

            plan = plan_bag_item_write(bytes(pocket_bytes), native_item_id, 1, stack_cap_for_pocket(bag_field))
            if plan is None:
                # Pocket genuinely full -- try again next tick (e.g. once
                # the player has made room); do not advance the counter.
                break

            slot_offset, slot_bytes = plan
            write_succeeded = await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(pocket_address + slot_offset, slot_bytes, "ARM9 System Bus")],
                [(pocket_address + slot_offset, bytes(pocket_bytes[slot_offset : slot_offset + 4]), "ARM9 System Bus")],
            )
            if not write_succeeded:
                # Pocket contents changed between the read and the write
                # (e.g. the player used/moved an item at the same time) --
                # retry next tick rather than writing over stale data.
                break

            self._applied_item_count += 1
            applied_this_tick += 1

        if applied_this_tick > 0:
            await self._store_applied_item_count(ctx, applied_key)

    async def _store_applied_item_count(self, ctx: BizHawkClientContext, applied_key: str) -> None:
        ctx.stored_data[applied_key] = self._applied_item_count
        await ctx.send_msgs(
            [
                {
                    "cmd": "Set",
                    "key": applied_key,
                    "default": 0,
                    "want_reply": False,
                    "operations": [{"operation": "max", "value": self._applied_item_count}],
                }
            ]
        )

    async def _apply_pending_badges(self, ctx: BizHawkClientContext) -> None:
        """Set PlayerProfile.johtoBadges/kantoBadges's bit for every
        badge_* item this player has ever received, but only once this
        player has actually beaten that gym Leader in a real battle
        (TRAINER_FLAG_BASE + their trainer id, the same flag the badge
        location's own check detection already reads) -- not immediately
        on receipt, unlike every other item. Every gym Leader's own field
        script gates its `TrainerBattle` call behind `CheckBadge`, so
        setting the bit early makes the Leader think the fight already
        happened and skip it entirely: a real bug (reported by a player,
        2026-08-17) that also silently stalls whatever story progression
        or chained trainer unlocks only fire inside that same battle-won
        branch (e.g. Falkner's own script only advances
        VAR_SCENE_ELMS_LAB, which gates Elm's Lab's egg-pickup call,
        inside the real fight).

        Re-derives the pending set from ctx.items_received fresh every
        tick rather than tracking it in instance state, so a client
        restart mid-seed can't lose track of a badge still waiting on
        its real fight -- nothing here depends on anything but live
        savedata and the server's own items_received list."""
        if self.playerdata_profile_address is None or self.flags_array_address is None:
            return

        seen_badge_indices = {
            _AP_ITEM_ID_TO_BADGE_INDEX[item.item] for item in ctx.items_received if item.item in _AP_ITEM_ID_TO_BADGE_INDEX
        }
        for badge_index in seen_badge_indices:
            trainer_flag_id = _BADGE_INDEX_TO_TRAINER_FLAG_ID.get(badge_index)
            if trainer_flag_id is None:
                continue

            byte_offset = _PROFILE_JOHTO_BADGES_OFFSET if badge_index < 8 else _PROFILE_KANTO_BADGES_OFFSET
            bit = badge_index if badge_index < 8 else badge_index - 8
            badge_byte_address = self.playerdata_profile_address + byte_offset
            current_byte = (await bizhawk.read(ctx.bizhawk_ctx, [(badge_byte_address, 1, "ARM9 System Bus")]))[0]
            if current_byte[0] & (1 << bit):
                continue  # already applied

            flag_byte_index, flag_bit_index = flag_byte_and_bit(trainer_flag_id)
            flags_byte = (
                await bizhawk.read(ctx.bizhawk_ctx, [(self.flags_array_address + flag_byte_index, 1, "ARM9 System Bus")])
            )[0]
            if not (flags_byte[0] & (1 << flag_bit_index)):
                continue  # hasn't actually beaten this Leader yet -- retry next tick

            new_byte = bytes([current_byte[0] | (1 << bit)])
            await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(badge_byte_address, new_byte, "ARM9 System Bus")],
                [(badge_byte_address, bytes(current_byte), "ARM9 System Bus")],
            )

    async def _apply_menu_unlock_gating(self, ctx: BizHawkClientContext) -> None:
        """randomize_menu_unlocks: for each of Bag/Trainer Card/Save
        button/Options button/Pokedex/Pokegear the player enabled, force
        its FLAG_GOT_* bit to match whether they've actually received the
        matching menu_unlock_* item yet -- 1 if owned, 0 (suppressed) if
        not, overriding whatever vanilla story progression would
        otherwise have set it to for free. Also owns that same location's
        own check detection, atomically, from the exact same read --
        deliberately NOT delegated to the generic _check_locations/
        _FLAG_ID_TO_AP_LOCATION_ID polling (menu_unlock flag ids are kept
        out of that map on purpose, see its own comment).

        Real bug fixed here (code review, 2026-08-17): the old design let
        _check_locations poll this same bit generically. Since this
        function also *writes* 1 to that bit the moment the item is
        owned, receiving the item from anywhere in the multiworld made
        the player's own location report itself as checked on the very
        next tick -- with no real in-game action at all. Worse, running
        after _check_locations (as the old design required, to let
        detection see a vanilla SetFlag before suppression cleared it)
        left an intra-tick race: a vanilla SetFlag landing in the gap
        between _check_locations's read and this function's later
        read/clear was lost forever (5 of the 6 flags are set by a
        script with its own no-replay guard, so a missed transition is
        gone for the rest of the seed, permanently stranding whatever
        item was placed there).

        Fixed by making this function the *sole* reader of these 6 bits,
        and by keying "did the check fire" off `currently_set and not
        owned` -- since gating only ever writes 1 when owned, a bit
        observed as 1 while *not yet* owned can only mean vanilla set it,
        never this function. That is deliberately still true when
        randomize_start_location is also on, in which case vanilla can
        never set these bits at all (New Bark's own scripts never run,
        see rom/startlocation.py) -- FLAG_GOT_STARTER (this project's own
        established substitute "game has begun" checkpoint, already used
        by _apply_start_location_flags for the *other* menu-unlock flags)
        is used as the check-fire signal instead in that case, exactly
        once the location is still missing.

        Same real, documented gap as _apply_start_location_flags's own
        grant: this only gates the pause-menu icon (src/sys_flags.c's
        CheckGotMenuIconI), not whatever else the vanilla scene also does
        alongside it (e.g. GivePokedex's own separate struct bit) -- see
        options.RandomizeBag's own docstring (shared by all 6 of the
        per-icon toggles)."""
        if self.flags_array_address is None:
            return

        enabled_menu_unlocks = set(ctx.slot_data.get("randomize_menu_unlocks", []))
        if not enabled_menu_unlocks:
            return

        owned_flag_ids = {
            flag_id
            for item in ctx.items_received
            if (flag_id := _AP_ITEM_ID_TO_MENU_UNLOCK_FLAG_ID.get(item.item)) is not None
        }

        start_location_on = bool(ctx.slot_data.get("randomize_start_location", False))
        starter_chosen = False
        if start_location_on:
            starter_byte_index, starter_bit_index = flag_byte_and_bit(_START_LOCATION_FLAG_GOT_STARTER)
            starter_byte = (
                await bizhawk.read(ctx.bizhawk_ctx, [(self.flags_array_address + starter_byte_index, 1, "ARM9 System Bus")])
            )[0]
            starter_chosen = bool(starter_byte[0] & (1 << starter_bit_index))

        touched_bytes: dict[int, int] = {}
        original_bytes: dict[int, int] = {}
        to_check: set[int] = set()

        async def _byte_at(byte_index: int) -> int:
            if byte_index not in touched_bytes:
                address = self.flags_array_address + byte_index
                current = (await bizhawk.read(ctx.bizhawk_ctx, [(address, 1, "ARM9 System Bus")]))[0]
                touched_bytes[byte_index] = current[0]
                original_bytes[byte_index] = current[0]
            return touched_bytes[byte_index]

        for flag_id, option_key in _MENU_UNLOCK_FLAG_ID_TO_OPTION_KEY.items():
            if option_key not in enabled_menu_unlocks:
                continue
            byte_index, bit_index = flag_byte_and_bit(flag_id)
            current_value = await _byte_at(byte_index)
            currently_set = bool(current_value & (1 << bit_index))
            owned = flag_id in owned_flag_ids

            ap_location_id = _MENU_UNLOCK_FLAG_ID_TO_AP_LOCATION_ID.get(flag_id)
            if ap_location_id is not None and ap_location_id in ctx.missing_locations:
                if (currently_set and not owned) or (start_location_on and starter_chosen):
                    to_check.add(ap_location_id)

            desired_value = current_value | (1 << bit_index) if owned else current_value & ~(1 << bit_index)
            touched_bytes[byte_index] = desired_value

        if to_check:
            await ctx.check_locations(to_check)

        writes = [
            (self.flags_array_address + byte_index, bytes([new_value]), "ARM9 System Bus")
            for byte_index, new_value in touched_bytes.items()
            if new_value != original_bytes[byte_index]
        ]
        if not writes:
            return
        guards = [
            (self.flags_array_address + byte_index, bytes([original_bytes[byte_index]]), "ARM9 System Bus")
            for byte_index in touched_bytes
            if touched_bytes[byte_index] != original_bytes[byte_index]
        ]
        await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, guards)

