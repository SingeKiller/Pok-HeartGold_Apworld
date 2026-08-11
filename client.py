# client.py
#
# BizHawk in-game connector for the HeartGold & SoulSilver Archipelago
# world. Two jobs:
#
#   - Check detection: read the vanilla savedata flag bits directly (see
#     location_flags.py) -- no ROM patch needed. Local items (this
#     player's own) are already substituted into the ROM itself
#     (patch_gen.apply_local_item_substitutions), so picking one up
#     already hands over the right item; this client's job there is just
#     noticing the flag and telling the server.
#   - Remote items (from another player's world): write them into the
#     running game's `Bag` savedata via RAM once `ctx.items_received`
#     reports them (no in-game "item received" animation).
#
# Uses Archipelago's own `worlds._bizhawk` connector (`BizHawkClient`/
# `AutoBizHawkClientRegister`, `worlds/_bizhawk/client.py`) and its generic
# `connector_bizhawk_generic.lua` BizHawk-side script -- same pattern
# `worlds/pokemon_emerald/client.py` and `ressources/platinum_archipelago/
# client.py` (read-only reference) both follow.
#
# Every read/write here is relative to the RAM address of the running
# game's `SaveData` struct (see save_layout.py). That address is **not**
# fixed -- HGSS double-buffers save data across two physical slots
# (`include/save.h`'s `SaveSlotSpec saveSlotSpecs[2]`), and either slot's
# in-RAM copy can be the active one depending on which was written last,
# so it moves across a save-file reload. This client relocates it fresh
# every session (and again whenever a reload is detected) by scanning for
# `SaveData.arrayHeaders[]`'s own signature -- see the "Dynamic SaveData
# location" section below for the mechanism, and docs/architecture.md's
# "## C16" section for the full investigation history (an earlier fixed-
# address approach caused a real save corruption before this was built).
#
# `HEARTGOLD_BAG_BASE_ADDRESS`/`HEARTGOLD_FLAGS_ARRAY_ADDRESS` env vars are
# a manual override (skips the scan, pins a fixed value) for
# troubleshooting -- unset by default.

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
# `SaveData` doesn't stay at a fixed RAM address across a save-file reload
# (HGSS double-buffers save data across two physical slots for write-
# safety, `include/save.h`'s `SaveSlotSpec saveSlotSpecs[2]` -- either
# slot's in-RAM copy can be the active one depending on which was written
# last). So: locate it fresh every session by scanning for `SaveData.
# arrayHeaders[]` (`include/save.h`) instead of trusting any fixed address.
# This table's *shape* is a compile-time constant independent of what the
# player actually owns: `arrayHeaders[0..4]` are five consecutive 16-byte
# `SaveArrayHeader{int id; u32 size; u32 offset; u16 crc; u16 slot;}`
# records whose `id` fields are exactly 0,1,2,3,4 in order (chunk ids
# `SAVE_SYSINFO`.."SAVE_FLAGS", `include/constants/save_arrays.h`). Once
# found, `arrayHeaders[SAVE_BAG].offset`/`arrayHeaders[SAVE_FLAGS].offset`
# give the *real*, ground-truth chunk offsets the game itself computed --
# no struct-size modeling, no pocket-capacity guessing.
#
# This signature is strong but not unique enough to trust blindly: real
# RAM has plenty of small integers, so a 64 KB scan can turn up more than
# one match. `_locate_save_addresses` checks every candidate's derived Bag
# address against real `ItemSlot` contents (`_bag_looks_plausible`) before
# accepting it, rather than trusting whichever candidate sorts first.

# `include/save.h`: `struct SaveArrayHeader { int id; u32 size; u32
# offset; u16 crc; u16 slot; }` -- 4+4+4+2+2 = 16 bytes, no padding
# ambiguity (every member is 4-byte-or-smaller, standard C ABI packs this
# tightly under both `save_layout.py` alignment cases).
_SAVE_ARRAY_HEADER_SIZE = 16
# Leading chunks (ids 0..4, SysInfo..SaveVarsFlags) to require an exact id
# match on before treating an offset as a scan candidate at all.
_SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT = 5
# `include/constants/save_arrays.h`: `SAVE_PAGE_MAX = 35`,
# `SAVE_SECTOR_SIZE = 0x1000` -- `SaveData.dynamic_region`'s fixed size
# (`include/save.h`), holding every numbered chunk (SysInfo..PCStorage).
_DYNAMIC_REGION_SIZE = 35 * 0x1000
# `SaveData` (`include/save.h`) field order: 4 leading `u32`s (16 bytes),
# then `dynamic_region[]`, then a `u32 saveCounter`, then `arrayHeaders[]`
# -- so `arrayHeaders`'s address is `dynamic_region_base +
# _DYNAMIC_REGION_SIZE + 4` (the `saveCounter` field). We only need the
# reverse of that arithmetic (given a found `arrayHeaders` address, get
# back `dynamic_region_base`).
_SAVE_COUNTER_SIZE = 4
_BAG_CHUNK_ID = 3  # SAVE_BAG, include/constants/save_arrays.h
_FLAGS_CHUNK_ID = 4  # SAVE_FLAGS, include/constants/save_arrays.h

# Scan window for `arrayHeaders` -- generous but bounded (EWRAM is only 4
# MiB total, 0x02000000-0x02400000, so an unbounded scan is not an option
# anyway). Centered on where `arrayHeaders` has actually been found to
# live across the handful of real sessions/reloads observed this project
# (`~0x0229F26C`-`~0x0229F280`, i.e. `dynamic_region_base` somewhere
# around `0x0227C200`-`0x0227C900`) -- widened well past the ~1.3 KB
# shift actually observed between the two physical save slots, since the
# true worst-case shift (a full flash sector, `SAVE_SECTOR_SIZE = 0x1000`)
# was not independently confirmed.
_ARRAY_HEADERS_SCAN_START = 0x02298000
_ARRAY_HEADERS_SCAN_LENGTH = 0x10000
# BizHawk connector reads much larger than this in one request have been
# observed to fail (`Separator is not found, and chunk exceed the limit`
# -- the connector's own response line gets too long) -- read the scan
# window in bounded chunks instead of one large request.
_ARRAY_HEADERS_SCAN_READ_CHUNK = 0x4000


async def _read_chunked(ctx: BizHawkClientContext, address: int, length: int, domain: str) -> bytes:
    """Read `length` bytes starting at `address`, transparently splitting
    into `_ARRAY_HEADERS_SCAN_READ_CHUNK`-sized requests (see that
    constant's own comment for why a single large read is not safe to
    issue directly)."""
    out = bytearray()
    offset = 0
    while offset < length:
        step = min(_ARRAY_HEADERS_SCAN_READ_CHUNK, length - offset)
        piece = (await bizhawk.read(ctx.bizhawk_ctx, [(address + offset, step, domain)]))[0]
        out.extend(piece)
        offset += step
    return bytes(out)


def _looks_like_array_headers(data: bytes, offset: int) -> bool:
    """True if `data[offset:]` starts with `_SAVE_ARRAY_HEADER_SIGNATURE_
    CHUNK_COUNT` consecutive `SaveArrayHeader` records whose `id` fields
    are exactly 0, 1, 2, ... in order -- see this section's own docstring
    for why this is a reliable, content-independent signature."""
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
    The 5-consecutive-sequential-int signature is strong but not
    cryptographic -- real RAM is full of small integers, so a scan across
    a 64 KB window can plausibly turn up more than one match. Returning
    every candidate (instead of just the first) is what lets
    `_locate_save_addresses` verify each one against real Bag contents
    rather than trusting whichever happens to sort first."""
    needed = _SAVE_ARRAY_HEADER_SIZE * _SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT
    return [offset for offset in range(0, len(data) - needed, 4) if _looks_like_array_headers(data, offset)]


async def _find_array_headers_address(ctx: BizHawkClientContext) -> int | None:
    """First plausible `SaveData.arrayHeaders[]` candidate address in
    `_ARRAY_HEADERS_SCAN_START`..`+_ARRAY_HEADERS_SCAN_LENGTH` (ARM9 System
    Bus), unverified against real Bag contents -- only used by
    `_array_headers_still_valid`'s signature re-check. `_locate_save_
    addresses` (the actual session-start/reload path) uses `_find_array_
    headers_candidates` plus a plausibility check instead; see that
    function's own docstring for why."""
    data = await _read_chunked(ctx, _ARRAY_HEADERS_SCAN_START, _ARRAY_HEADERS_SCAN_LENGTH, "ARM9 System Bus")
    candidates = _find_array_headers_candidates(data)
    return _ARRAY_HEADERS_SCAN_START + candidates[0] if candidates else None


async def _chunk_offset(ctx: BizHawkClientContext, array_headers_address: int, chunk_id: int) -> int:
    """Read `arrayHeaders[chunk_id].offset` directly (ground truth,
    exactly what the game itself uses internally -- no struct-size model,
    no capacity assumptions)."""
    record_address = array_headers_address + chunk_id * _SAVE_ARRAY_HEADER_SIZE
    record_bytes = (
        await bizhawk.read(ctx.bizhawk_ctx, [(record_address, _SAVE_ARRAY_HEADER_SIZE, "ARM9 System Bus")])
    )[0]
    _record_id, _size, offset, _crc, _slot = struct.unpack("<iIIHH", bytes(record_bytes))
    return offset


# A real Bag "items" pocket slot (u16 id, u16 quantity) is either empty
# (id 0) or a real item (id 1..MAX_PLAUSIBLE_ITEM_ID, data/items.py's own
# highest id) in a small stack. Checked against the first few slots before
# trusting a scan candidate -- see `_bag_looks_plausible`'s own docstring.
_MAX_PLAUSIBLE_ITEM_ID = 536
_MAX_PLAUSIBLE_ITEM_QUANTITY = 999
_PLAUSIBILITY_CHECK_SLOT_COUNT = 8


async def _bag_looks_plausible(ctx: BizHawkClientContext, bag_address: int) -> bool:
    """Read the first `_PLAUSIBILITY_CHECK_SLOT_COUNT` "items"-pocket slots
    at a candidate `bag_address` and check every one looks like a real
    `ItemSlot` (empty, or a real item id at a small quantity) -- the
    verification step the `arrayHeaders` scan signature alone doesn't
    provide (real RAM has enough small integers that a false-positive
    signature match across a 64 KB window is plausible; this catches it
    before any read/write trusts the wrong address)."""
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
    """Locate this session's real `Bag`/`SaveVarsFlags.flags[]` addresses
    fresh, via `SaveData.arrayHeaders[]` (see this section's own
    docstring). Tries every scan candidate in order, accepting the first
    one whose derived Bag address passes `_bag_looks_plausible` -- not just
    the first signature match, since that signature alone isn't reliable
    enough on its own (see `_find_array_headers_candidates`'s docstring).
    Returns `(bag_address, flags_array_address, array_headers_address)`,
    or `None` if nothing plausible was found this attempt (e.g.
    mid-transition; caller should just retry next tick, per
    `HeartGoldClient.game_watcher`)."""
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
    """Cheap per-tick check: re-read just the signature bytes at a
    previously-found `arrayHeaders` address and confirm they still match.
    If this ever fails mid-session (e.g. the player reloaded a save,
    which is exactly the scenario that motivated this whole module -- see
    this section's docstring), the caller re-runs the full scan rather
    than keep reading/writing at a now-wrong address."""
    signature_size = _SAVE_ARRAY_HEADER_SIZE * _SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT
    try:
        data = (
            await bizhawk.read(ctx.bizhawk_ctx, [(array_headers_address, signature_size, "ARM9 System Bus")])
        )[0]
    except bizhawk.RequestFailedError:
        return False
    return _looks_like_array_headers(bytes(data), 0)

# Server data-storage key this client uses to remember, across client
# restarts, how many of `ctx.items_received` have already been written into
# the bag (there is no in-ROM/in-save counter this client controls -- see
# this module's own docstring -- so this is the best available substitute).
# Scoped per team+slot, same convention as
# `ressources/platinum_archipelago/client.py`'s own `pokemon_platinum_*_
# {ctx.team}_{ctx.slot}` keys and `worlds/pokemon_emerald/client.py`'s
# `pokemon_wonder_trades_{ctx.team}`.
#
# Known, documented limitation (inherent to not having ROM/save-side
# cooperation at all, not specific to this key): if the player reloads an
# in-game save state/file from *before* some already-applied remote items
# were written, this counter does not roll back with it -- those items will
# not be re-granted. Fixing this for real needs the ROM/ARM-hook side of the
# ground-item protocol design (docs/architecture.md's "## C14" section,
# "Chosen protocol (design)"), out of scope for this client-only v1.
_APPLIED_ITEM_COUNT_KEY_TEMPLATE = "pokemon_heartgold_applied_item_count_{team}_{slot}"


# -- Item id <-> Bag pocket mapping ------------------------------------------


def _build_ap_item_id_to_bag_write_info() -> dict[int, tuple[int, str]]:
    """AP item id -> (native HG/SS item id, Bag field name to write it
    into). Built once at import time from the generated `data/items.py`
    package (same source `items.py`'s own id map uses)."""
    result: dict[int, tuple[int, str]] = {}
    for data in ITEMS.values():
        bag_field = POCKET_KEY_TO_BAG_FIELD.get(data["pocket"])
        if bag_field is None:
            continue
        result[HEARTGOLD_ITEM_ID_BASE + data["id"]] = (data["id"], bag_field)
    return result


_AP_ITEM_ID_TO_BAG_WRITE_INFO = _build_ap_item_id_to_bag_write_info()

# flag id -> AP location id, computed once at import time (see
# location_flags.py). `HeartGoldClient.__init__` builds the reverse
# (location id lookups aren't needed on the hot path -- only "is this flag
# newly set" is).
_FLAG_ID_TO_AP_LOCATION_ID = build_flag_id_to_ap_location_id()

# AP location ids already covered by ROM substitution (see
# location_flags.build_locally_substituted_ap_location_ids's own
# docstring for the double-delivery bug this prevents) -- computed once at
# import time, same convention as _FLAG_ID_TO_AP_LOCATION_ID above.
_LOCALLY_SUBSTITUTED_AP_LOCATION_IDS = build_locally_substituted_ap_location_ids()


class HeartGoldClient(BizHawkClient):
    game = "Pokemon HeartGold"
    system = "NDS"
    # Matches output_patch.HeartGoldProcedurePatch.patch_file_ending.
    # AutoBizHawkClientRegister reads this class attribute at class-
    # definition time (see worlds/_bizhawk/client.py) to register
    # ".apheartgold" on the generic "BizHawk Client" launcher component's
    # SuffixIdentifier -- this is what makes the Launcher's "Open Patch"
    # file dialog recognize/accept a real .apheartgold file at all. Left
    # as None for a while during early development, before output_patch.py
    # existed (see git history) -- must stay in sync with
    # HeartGoldProcedurePatch.patch_file_ending now that it does.
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
        ctx.items_handling = 0b011  # locations + remote items
        ctx.want_slot_data = True
        ctx.watcher_timeout = 1.0

        self.local_checked_locations = set()
        # Manual env var overrides, if set, take priority over the scan
        # every tick (see game_watcher below).
        self._manual_bag_base_override = _resolve_address_override(HEARTGOLD_BAG_BASE_ADDRESS_ENV)
        self._manual_flags_array_override = _resolve_address_override(HEARTGOLD_FLAGS_ARRAY_ADDRESS_ENV)
        self.bag_base_address = self._manual_bag_base_override
        self.flags_array_address = self._manual_flags_array_override
        self._array_headers_address = None
        self._applied_item_count = 0

        return True

    async def _ensure_addresses_located(self, ctx: BizHawkClientContext) -> bool:
        """Make sure `self.bag_base_address`/`self.flags_array_address` are
        current for *this* moment, relocating via `SaveData.arrayHeaders[]`
        if needed (first tick, or the save was reloaded since the last
        successful location -- see the "Dynamic SaveData location" section
        above). Returns whether both addresses are currently usable."""
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
            # Not located yet (e.g. mid save-reload transition) -- skip
            # this tick entirely rather than read/write at a stale or
            # missing address. Retried automatically next tick.
            return

        applied_key = _APPLIED_ITEM_COUNT_KEY_TEMPLATE.format(team=ctx.team, slot=ctx.slot)
        ctx.set_notify(applied_key)
        self._applied_item_count = max(self._applied_item_count, int(ctx.stored_data.get(applied_key, 0) or 0))

        try:
            await self._check_locations(ctx)
            await self._apply_next_received_item(ctx, applied_key)
        except bizhawk.RequestFailedError:
            # Exit handler and return to main loop to reconnect, same
            # convention as worlds/pokemon_emerald/client.py's own
            # game_watcher.
            pass

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
        # this player's OWN locations, which this client already delivered
        # for real via ROM substitution (see output_patch.
        # build_item_substitutions) the moment the player picked it up
        # in-game. Writing it into the Bag again here would double it (a
        # real bug found via live multiplayer testing, 2026-08-11 -- see
        # location_flags.build_locally_substituted_ap_location_ids's own
        # docstring). `next_item.player` is the location's owning player
        # (the "sending" player, per NetUtils.NetworkItem), so this only
        # ever skips this player's own already-substituted locations, never
        # a real remote item received from someone else's world.
        already_delivered_locally = (
            next_item.player == ctx.slot and next_item.location in _LOCALLY_SUBSTITUTED_AP_LOCATION_IDS
        )
        write_info = None if already_delivered_locally else _AP_ITEM_ID_TO_BAG_WRITE_INFO.get(next_item.item)
        if write_info is None:
            # Not one of this world's own bag items (e.g. a badge/event
            # item, which never reaches a client -- see locations.py's own
            # module docstring -- or, in a future item-link/trap scenario,
            # an item this pocket map doesn't know about), or already
            # delivered locally (see above). Count it as "applied" so the
            # queue does not stall on it forever.
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
