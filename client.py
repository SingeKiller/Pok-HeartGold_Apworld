# client.py
#
# Task C16 -- BizHawk in-game connector for the HeartGold & SoulSilver
# Archipelago world (docs/architecture.md's "## ROM code injection strategy
# (revised after C14)", option 3, "Client-only (RAM-only)", chosen for v1):
#
#   - Check detection: read the existing `FLAG_HIDE_ITEMBALL_*`/
#     `FLAG_GOT_*_FROM_*`/`FLAG_HIDDENITEM_*` savedata bits directly (see
#     `location_flags.py` and docs/architecture.md's "## C14" section) --
#     genuinely vanilla behavior, no ROM patch needed. "Local" items
#     (destined for this same player) are already substituted directly into
#     the ROM's own data (`rom/eventscriptdata.py`/`rom/npcgiftdata.py`, via
#     `patch_gen.py`'s `apply_local_item_substitutions`), so the player
#     already receives the right item just by picking it up in-game; this
#     client's own job is purely to notice the flag and tell the server.
#   - Remote items (destined for another player's world): once this
#     client's own bookkeeping (see `_APPLIED_ITEM_COUNT_KEY_TEMPLATE` below)
#     says an item from `ctx.items_received` hasn't been granted yet, write it
#     directly into the running game's `Bag` savedata via RAM (no in-game
#     "item received" animation for v1 -- the acknowledged, documented cost
#     of the client-only strategy, see docs/architecture.md).
#
# Uses the local Archipelago checkout's own `worlds._bizhawk` connector
# module (the generic `bizhawk-apiclient`/`connector_bizhawk_generic.lua`
# BizHawk-side script is provided by Archipelago itself, not reimplemented
# here) and its `BizHawkClient`/`AutoBizHawkClientRegister` framework
# (`worlds/_bizhawk/client.py`), the same pattern
# `worlds/pokemon_emerald/client.py` and
# `ressources/platinum_archipelago/client.py` (read-only reference, not
# copied) both follow.
#
# *** THE ONE OPEN BLOCKER THIS TASK COULD NOT RESOLVE (read before use) ***
#
# Every read/write this client performs is relative to the RAM address of
# the running game's `SaveData` struct (see `save_layout.py`). That address
# is a `static` C global (`sSaveDataPtr`, Decomposition src/save.c) with no
# fixed, documented value -- unlike e.g. `pokemon_emerald`'s
# `gSaveBlock1Ptr`, whose real address the emerald decomp's own linked
# build assigns and that project's `data.py` bakes in, this project has no
# real linked build to read such an address from (proprietary MWCC
# 2.0/sp2p2 + Nitro SDK 4.2, unavailable in this dev environment -- the same
# constraint already recorded in docs/architecture.md's "## ROM code
# injection strategy" and "## C14" -> "Blocker 1"). Nor does this project's
# "client-only, no ROM code" v1 strategy give itself a self-locating magic
# marker in RAM the way `ressources/platinum_archipelago`'s own client can
# (that reference client's `AP_STRUCT_PTR_ADDRESS` trick only works because
# their build burns a real, linked `ap.bin`/protocol struct into the ROM --
# a capability this project deliberately set aside, see
# docs/architecture.md).
#
# *** RESOLVED 2026-08-10 *** -- `save_layout.py`'s `CANDIDATE_OFFSETS`
# model (theoretical, derived from decomp struct sizes) turned out to
# disagree with the real, live RAM layout by an amount that was never fully
# root-caused (see docs/architecture.md's "## C16" addenda) -- so rather
# than route through that unreliable base+offset arithmetic, the two
# addresses this client actually needs were found directly, empirically, in
# a live BizHawk session (Lua memory dump, diffed byte-for-byte before/after
# a real, known in-game pickup -- see docs/architecture.md's "Manual
# discovery session results", 2026-08-10 entry): `CONFIRMED_BAG_BASE_ADDRESS`
# (verified by direct content match: a real Potion x7 ItemSlot, and by a
# Bag quantity byte incrementing 7->8 exactly on a further pickup) and
# `CONFIRMED_FLAGS_ARRAY_ADDRESS` (verified by a single, clean bit
# 0->1 flip exactly matching a picked-up ground item's flag id, with no
# other explanation fitting as well). Both are ARM9 System Bus addresses,
# specific to this save's actual RAM layout on this BizHawk/core
# configuration -- override via `HEARTGOLD_BAG_BASE_ADDRESS`/
# `HEARTGOLD_FLAGS_ARRAY_ADDRESS` env vars if a different setup needs
# different values; the hardcoded defaults are what was actually confirmed
# working, not a guess.
#
# `HEARTGOLD_SAVE_DATA_ADDRESS_ENV`/`HEARTGOLD_SAVE_LAYOUT_CASE_ENV` below
# are now UNUSED (kept only so `_missing_configuration_message` still
# documents how the underlying `SaveChunkOffsets` model works, for anyone
# extending this client to a field the confirmed addresses don't cover) --
# this client no longer refuses to run by default, since the two addresses
# it actually needs now have confirmed, safe values baked in.

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import worlds._bizhawk as bizhawk
from data.items import ITEMS
from worlds._bizhawk.client import BizHawkClient

from items import HEARTGOLD_ITEM_ID_BASE
from location_flags import build_flag_id_to_ap_location_id
from rom import HEARTGOLD_US_ID_CODE
from save_layout import (
    BAG_POCKET_OFFSETS,
    CANDIDATE_OFFSETS,
    FLAGS_ARRAY_SIZE,
    POCKET_KEY_TO_BAG_FIELD,
    is_flag_set,
    plan_bag_item_write,
    stack_cap_for_pocket,
)

if TYPE_CHECKING:
    from worlds._bizhawk.context import BizHawkClientContext

# -- Required manual configuration (see this module's docstring) ------------

HEARTGOLD_SAVE_DATA_ADDRESS_ENV = "HEARTGOLD_SAVE_DATA_ADDRESS"
HEARTGOLD_SAVE_LAYOUT_CASE_ENV = "HEARTGOLD_SAVE_LAYOUT_CASE"

# Confirmed 2026-08-10 (see this module's docstring above). ARM9 System Bus
# addresses (Main RAM domain + 0x02000000).
HEARTGOLD_BAG_BASE_ADDRESS_ENV = "HEARTGOLD_BAG_BASE_ADDRESS"
HEARTGOLD_FLAGS_ARRAY_ADDRESS_ENV = "HEARTGOLD_FLAGS_ARRAY_ADDRESS"
CONFIRMED_BAG_BASE_ADDRESS = 0x0227CDA0
CONFIRMED_FLAGS_ARRAY_ADDRESS = 0x0227D39C


def _resolve_bag_base_address() -> int:
    raw = os.environ.get(HEARTGOLD_BAG_BASE_ADDRESS_ENV)
    if not raw:
        return CONFIRMED_BAG_BASE_ADDRESS
    try:
        return int(raw, 0)
    except ValueError:
        return CONFIRMED_BAG_BASE_ADDRESS


def _resolve_flags_array_address() -> int:
    raw = os.environ.get(HEARTGOLD_FLAGS_ARRAY_ADDRESS_ENV)
    if not raw:
        return CONFIRMED_FLAGS_ARRAY_ADDRESS
    try:
        return int(raw, 0)
    except ValueError:
        return CONFIRMED_FLAGS_ARRAY_ADDRESS

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


def _resolve_save_data_address() -> int | None:
    raw = os.environ.get(HEARTGOLD_SAVE_DATA_ADDRESS_ENV)
    if not raw:
        return None
    try:
        return int(raw, 0)
    except ValueError:
        return None


def _resolve_save_layout_case_name() -> str | None:
    raw = os.environ.get(HEARTGOLD_SAVE_LAYOUT_CASE_ENV)
    if raw and raw in CANDIDATE_OFFSETS:
        return raw
    return None


def _missing_configuration_message() -> str:
    case_names = ", ".join(sorted(CANDIDATE_OFFSETS))
    return (
        "Pokemon HeartGold client: SaveData RAM address not configured -- "
        "checks/item-receiving are paused (nothing will be read or written "
        "until this is set; see docs/architecture.md's '## C16' section for "
        "the full procedure). Summary: in BizHawk's RAM Search (domain "
        "'ARM9 System Bus'), search for your character's current in-game "
        "money as a 4-byte value, narrow it down by spending/earning coins "
        "and re-searching 'changed value', then set the "
        f"{HEARTGOLD_SAVE_DATA_ADDRESS_ENV} environment variable to "
        "(that address - one of the two candidate money offsets below), and "
        f"{HEARTGOLD_SAVE_LAYOUT_CASE_ENV} to whichever of [{case_names}] "
        "matches -- pick whichever produces a plausible-looking Bag (item "
        "ids under ~537) when read at the computed offset. Candidate money "
        "offsets from SaveData's own base: "
        + ", ".join(
            f"{name}={offsets.money_offset_in_savedata:#x}" for name, offsets in sorted(CANDIDATE_OFFSETS.items())
        )
    )


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


class HeartGoldClient(BizHawkClient):
    game = "Pokemon HeartGold"
    system = "NDS"
    # No distinct patched-ROM file suffix yet -- this project's own patch
    # pipeline (patch_gen.py) does not yet produce a single distributable
    # per-seed patch file the way e.g. pokemon_emerald's `.apemerald` does
    # (see docs/architecture.md and __init__.py's own docstring: local-item
    # substitution and the ARM-hook scaffolding are separate, not-yet-wired
    # pieces). Players point BizHawk at their own already-patched ROM copy
    # directly; nothing to register a launcher file-suffix for yet.
    patch_suffix = None

    local_checked_locations: set[int]
    bag_base_address: int
    flags_array_address: int
    _applied_item_count: int

    def __init__(self) -> None:
        super().__init__()
        self.local_checked_locations = set()
        self.bag_base_address = CONFIRMED_BAG_BASE_ADDRESS
        self.flags_array_address = CONFIRMED_FLAGS_ARRAY_ADDRESS
        self._applied_item_count = 0

    async def validate_rom(self, ctx: BizHawkClientContext) -> bool:
        try:
            id_code = (await bizhawk.read(ctx.bizhawk_ctx, [(0x0C, 4, "ROM")]))[0]
        except bizhawk.RequestFailedError:
            return False

        if bytes(id_code) != HEARTGOLD_US_ID_CODE:
            return False

        ctx.game = self.game
        # Ask for remote items too (0b001 locations-only | 0b010
        # remote-items -- see CommonClient's own `items_handling` bit
        # convention).
        ctx.items_handling = 0b011
        ctx.want_slot_data = True
        ctx.watcher_timeout = 1.0

        self.local_checked_locations = set()
        self.bag_base_address = _resolve_bag_base_address()
        self.flags_array_address = _resolve_flags_array_address()
        self._applied_item_count = 0

        return True

    async def game_watcher(self, ctx: BizHawkClientContext) -> None:
        if ctx.server is None or ctx.server.socket.closed or ctx.slot_data is None:
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
        write_info = _AP_ITEM_ID_TO_BAG_WRITE_INFO.get(next_item.item)
        if write_info is None:
            # Not one of this world's own bag items (e.g. a badge/event
            # item, which never reaches a client -- see locations.py's own
            # module docstring -- or, in a future item-link/trap scenario,
            # an item this pocket map doesn't know about). Count it as
            # "applied" so the queue does not stall on it forever.
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
