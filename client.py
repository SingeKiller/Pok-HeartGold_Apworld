# client.py
#
# BizHawk in-game connector. Two jobs:
#   - Check detection: read the vanilla savedata flag bits directly (see
#     location_flags.py) -- no ROM patch needed.
#   - Remote items: write them into the running game's Bag savedata via
#     RAM once ctx.items_received reports them.
#
# Every read/write here is relative to the RAM address of the running
# game's SaveData struct. That address is NOT fixed -- HGSS double-
# buffers save data across two physical slots, so it moves across a
# save-file reload. This client relocates it fresh every session (and
# whenever a reload is detected) by scanning for SaveData.arrayHeaders[]'s
# own signature -- see the "Dynamic SaveData location" section below. An
# earlier fixed-address approach caused a real save corruption before
# this was built -- see NOTES.md.
#
# HEARTGOLD_BAG_BASE_ADDRESS/HEARTGOLD_FLAGS_ARRAY_ADDRESS env vars are a
# manual override (skips the scan) for troubleshooting -- unset by
# default.
#
# A QoL pair (fast_text_speed/skip_battle_animations) was tried and
# pulled 2026-08-11 -- see NOTES.md.

from __future__ import annotations

import os
import struct
from typing import TYPE_CHECKING

import worlds._bizhawk as bizhawk
from worlds._bizhawk.client import BizHawkClient

from data.items import ITEMS
from items import HEARTGOLD_ITEM_ID_BASE
from location_flags import build_flag_id_to_ap_location_id, build_locally_substituted_ap_location_ids
from rom import HEARTGOLD_US_ID_CODE, SOULSILVER_US_ID_CODE
from save_layout import (
    BAG_POCKET_OFFSETS,
    FLAGS_ARRAY_OFFSET,
    FLAGS_ARRAY_SIZE,
    POCKET_KEY_TO_BAG_FIELD,
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
# arrayHeaders[] instead of trusting any fixed address. arrayHeaders[0..4]
# are five consecutive 16-byte SaveArrayHeader records whose id fields are
# exactly 0,1,2,3,4 in order -- a compile-time-constant shape independent
# of what the player owns. Once found, arrayHeaders[SAVE_BAG].offset/
# arrayHeaders[SAVE_FLAGS].offset give the real, ground-truth chunk
# offsets the game itself computed. The signature is strong but not
# unique enough to trust blindly (real RAM has plenty of small integers),
# so `_locate_save_addresses` also checks each candidate's derived Bag
# address against real ItemSlot contents before accepting it.

_SAVE_ARRAY_HEADER_SIZE = 16  # include/save.h: SaveArrayHeader, 4+4+4+2+2
_SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT = 5  # SysInfo..SaveVarsFlags
_DYNAMIC_REGION_SIZE = 35 * 0x1000  # SAVE_PAGE_MAX * SAVE_SECTOR_SIZE
_SAVE_COUNTER_SIZE = 4
_BAG_CHUNK_ID = 3  # SAVE_BAG
_FLAGS_CHUNK_ID = 4  # SAVE_FLAGS

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


async def _locate_save_addresses(ctx: BizHawkClientContext) -> tuple[int, int, int] | None:
    """Locate this session's real Bag/SaveVarsFlags.flags[] addresses
    fresh. Tries every scan candidate, accepting the first whose derived
    Bag address passes `_bag_looks_plausible`. Returns None if nothing
    plausible was found (caller retries next tick)."""
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
        return bag_address, flags_array_address, array_headers_address

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

_FLAG_ID_TO_AP_LOCATION_ID = build_flag_id_to_ap_location_id()

# AP location ids already covered by ROM substitution -- see NOTES.md for
# the double-delivery bug this prevents.
_LOCALLY_SUBSTITUTED_AP_LOCATION_IDS = build_locally_substituted_ap_location_ids()


class HeartGoldClient(BizHawkClient):
    game = "Pokemon HeartGold"
    system = "NDS"
    # Must match output_patch.HeartGoldProcedurePatch.patch_file_ending --
    # this is what makes the Launcher's "Open Patch" dialog recognize a
    # real .apheartgold file.
    patch_suffix = ".apheartgold"

    local_checked_locations: set[int]
    bag_base_address: int | None
    flags_array_address: int | None
    _array_headers_address: int | None
    _manual_bag_base_override: int | None
    _manual_flags_array_override: int | None
    _applied_item_count: int

    def __init__(self) -> None:
        super().__init__()
        self.local_checked_locations = set()
        self.bag_base_address = None
        self.flags_array_address = None
        self._array_headers_address = None
        self._manual_bag_base_override = None
        self._manual_flags_array_override = None
        self._applied_item_count = 0

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
        self._array_headers_address = None
        self._applied_item_count = 0

        return True

    async def _ensure_addresses_located(self, ctx: BizHawkClientContext) -> bool:
        """Make sure bag_base_address/flags_array_address are current,
        relocating via SaveData.arrayHeaders[] if needed. Returns whether
        both addresses are currently usable."""
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
            self._array_headers_address = None
            return False

        bag_address, flags_array_address, array_headers_address = located
        self.bag_base_address = (
            bag_address if self._manual_bag_base_override is None else self._manual_bag_base_override
        )
        self.flags_array_address = (
            flags_array_address if self._manual_flags_array_override is None else self._manual_flags_array_override
        )
        self._array_headers_address = array_headers_address
        return True

    async def game_watcher(self, ctx: BizHawkClientContext) -> None:
        if ctx.server is None or ctx.server.socket.closed or ctx.slot_data is None:
            return

        if not await self._ensure_addresses_located(ctx):
            return  # retried automatically next tick

        applied_key = _APPLIED_ITEM_COUNT_KEY_TEMPLATE.format(team=ctx.team, slot=ctx.slot)
        ctx.set_notify(applied_key)
        self._applied_item_count = max(self._applied_item_count, int(ctx.stored_data.get(applied_key, 0) or 0))

        try:
            await self._check_locations(ctx)
            await self._apply_next_received_item(ctx, applied_key)
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

        if newly_checked and newly_checked != self.local_checked_locations:
            self.local_checked_locations = newly_checked
            await ctx.check_locations(newly_checked)

    async def _apply_next_received_item(self, ctx: BizHawkClientContext, applied_key: str) -> None:
        if self._applied_item_count >= len(ctx.items_received):
            return

        next_item = ctx.items_received[self._applied_item_count]

        # Archipelago's server sends every item belonging to this player
        # through items_received once its location is checked -- including
        # this player's own locations, which this client already
        # delivered via ROM substitution. Writing it into the Bag again
        # would double it -- see NOTES.md.
        already_delivered_locally = (
            next_item.player == ctx.slot and next_item.location in _LOCALLY_SUBSTITUTED_AP_LOCATION_IDS
        )
        write_info = None if already_delivered_locally else _AP_ITEM_ID_TO_BAG_WRITE_INFO.get(next_item.item)
        if write_info is None:
            # Not one of this world's own bag items, or already delivered
            # locally -- count it as "applied" so the queue doesn't stall.
            self._applied_item_count += 1
            await self._store_applied_item_count(ctx, applied_key)
            return

        native_item_id, bag_field = write_info
        pocket_offset, pocket_capacity = BAG_POCKET_OFFSETS[bag_field]
        pocket_address = self.bag_base_address + pocket_offset
        pocket_size = pocket_capacity * 4

        pocket_bytes = (await bizhawk.read(ctx.bizhawk_ctx, [(pocket_address, pocket_size, "ARM9 System Bus")]))[0]

        plan = plan_bag_item_write(bytes(pocket_bytes), native_item_id, 1, stack_cap_for_pocket(bag_field))
        if plan is None:
            # Pocket genuinely full -- try again next tick (e.g. once the
            # player has made room); do not advance the counter.
            return

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
            return

        self._applied_item_count += 1
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

