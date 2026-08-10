"""Tests for the BizHawk client (task C16): `save_layout.py` (RAM struct
layout, pure), `location_flags.py` (check-detection flag mapping, needs
`data/` generated), and `client.py` (the actual `BizHawkClient`, needs the
local Archipelago checkout's `worlds._bizhawk` -- see conftest.py).

Nothing here talks to a real BizHawk/emulator process -- per this task's own
brief, that end-to-end piece is manual, out of reach for this agent (see
docs/architecture.md's "## C16" section and client.py's own module
docstring for exactly what remains unverified: the absolute RAM address of
the running game's `SaveData` struct, and which of the two
`save_layout.CANDIDATE_OFFSETS` cases the retail compiler actually used).
What *is* tested here, without any BizHawk connection:

  - `save_layout.py`'s struct-offset/chunk-framing arithmetic and the Bag
    pocket-write planner (pure functions, always run).
  - `location_flags.py`'s location -> vanilla-flag-id mapping (needs
    `data/`, regenerated via the same fixture pattern as
    tests/test_locations.py).
  - `client.py`'s pure helper functions (env var parsing, the AP item id ->
    Bag pocket map) and its async read/write orchestration methods
    (`_check_locations`/`_apply_next_received_item`/
    `_store_applied_item_count`) driven against a fake, in-memory `ctx` with
    `worlds._bizhawk.read`/`guarded_write` monkeypatched -- i.e. exactly the
    "mapping check -> location" / "mapping received item -> RAM write"
    logic the task brief asks for, exercised end-to-end in-process without
    an emulator.
"""

from __future__ import annotations

import asyncio
import importlib
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import save_layout

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


# === save_layout.py -- pure, no data/ needed ================================


def test_chunk_size_with_footer_rounds_up_to_4_then_adds_4():
    assert save_layout.chunk_size_with_footer(0) == 4
    assert save_layout.chunk_size_with_footer(1) == 8
    assert save_layout.chunk_size_with_footer(4) == 8
    assert save_layout.chunk_size_with_footer(5) == 12


def test_save_vars_flags_size_matches_decomp_constants():
    # struct SaveVarsFlags { u16 vars[NUM_VARS]; u8 flags[NUM_FLAGS/8]; }
    assert save_layout.NUM_VARS == 0x170
    assert save_layout.NUM_FLAGS == 2912
    assert save_layout.VARS_ARRAY_SIZE == 736
    assert save_layout.FLAGS_ARRAY_SIZE == 364
    assert save_layout.SAVE_VARS_FLAGS_SIZE == 1100


def test_flag_byte_and_bit_and_is_flag_set_round_trip():
    for flag_id in (0, 1, 7, 8, 1081, 2911):
        byte_index, bit_index = save_layout.flag_byte_and_bit(flag_id)
        flags = bytearray(save_layout.FLAGS_ARRAY_SIZE)
        flags[byte_index] |= 1 << bit_index
        assert save_layout.is_flag_set(bytes(flags), flag_id) is True
        # Every other bit in that same buffer must read as unset.
        flags[byte_index] = 0
        assert save_layout.is_flag_set(bytes(flags), flag_id) is False


def test_is_flag_set_out_of_range_is_false_not_a_crash():
    flags = bytes(save_layout.FLAGS_ARRAY_SIZE)
    assert save_layout.is_flag_set(flags, -1) is False
    assert save_layout.is_flag_set(flags, save_layout.NUM_FLAGS * 10) is False


def test_bag_pocket_offsets_are_contiguous_and_match_bag_size():
    expected_offset = 0
    for name, count in save_layout.BAG_POCKETS:
        offset, capacity = save_layout.BAG_POCKET_OFFSETS[name]
        assert offset == expected_offset
        assert capacity == count
        expected_offset += count * save_layout.ITEM_SLOT_SIZE
    # Trailing `u16 registeredItems[2]` after the last pocket.
    assert expected_offset + save_layout.REGISTERED_ITEMS_SIZE == save_layout.BAG_SIZE


def test_bag_size_matches_hand_computed_value():
    # (165+50+101+12+40+64+24+30) * 4 + 4 == 1948 (0x79C)
    assert save_layout.BAG_SIZE == 1948


def test_stack_cap_for_pocket():
    assert save_layout.stack_cap_for_pocket("items") == save_layout.DEFAULT_STACK_CAP
    assert save_layout.stack_cap_for_pocket("keyItems") == save_layout.UNSTACKABLE_STACK_CAP
    assert save_layout.stack_cap_for_pocket("TMsHMs") == save_layout.UNSTACKABLE_STACK_CAP
    assert save_layout.stack_cap_for_pocket("mail") == save_layout.UNSTACKABLE_STACK_CAP


def test_compute_chunk_offsets_ordering_and_case_delta():
    apcs = save_layout.CANDIDATE_OFFSETS["apcs_4byte_longlong"]
    eabi = save_layout.CANDIDATE_OFFSETS["eabi_8byte_longlong"]

    for offsets in (apcs, eabi):
        assert offsets.sys_info_offset == 0
        assert 0 < offsets.player_data_offset < offsets.party_offset < offsets.bag_offset < offsets.vars_flags_offset
        assert offsets.bag_offset_in_savedata == save_layout.SAVEDATA_DYNAMIC_REGION_OFFSET + offsets.bag_offset
        assert (
            offsets.vars_flags_offset_in_savedata
            == save_layout.SAVEDATA_DYNAMIC_REGION_OFFSET + offsets.vars_flags_offset
        )

    # The only difference between the two cases is SysInfo's own chunk size
    # (the one struct in the chain with 8-byte members) -- see
    # save_layout.py's docstring. Both chunks start at offset 0 (id 0 is
    # always first), but that 8-byte size delta must propagate unchanged
    # through every later offset.
    assert eabi.case.sys_info_size - apcs.case.sys_info_size == 8
    delta = 8
    assert eabi.player_data_offset - apcs.player_data_offset == delta
    assert eabi.party_offset - apcs.party_offset == delta
    assert eabi.bag_offset - apcs.bag_offset == delta
    assert eabi.vars_flags_offset - apcs.vars_flags_offset == delta


def test_money_offset_in_savedata_is_well_defined():
    for offsets in save_layout.CANDIDATE_OFFSETS.values():
        assert offsets.money_offset_in_savedata == (
            save_layout.SAVEDATA_DYNAMIC_REGION_OFFSET
            + offsets.player_data_offset
            + save_layout.PLAYERDATA_MONEY_OFFSET
        )
        # Must land inside PLAYERDATA, not spill into the next chunk.
        assert offsets.player_data_offset + save_layout.PLAYERDATA_MONEY_OFFSET < offsets.party_offset


# --- plan_bag_item_write -----------------------------------------------------


def test_plan_bag_item_write_uses_first_free_slot_in_empty_pocket():
    pocket = bytes(4 * 5)  # 5 empty slots
    plan = save_layout.plan_bag_item_write(pocket, native_item_id=4, quantity=1, stack_cap=99)
    assert plan is not None
    offset, slot_bytes = plan
    assert offset == 0
    assert slot_bytes == (4).to_bytes(2, "little") + (1).to_bytes(2, "little")


def test_plan_bag_item_write_stacks_onto_existing_matching_slot():
    # slot 0: item 4 x 3, slot 1: empty.
    pocket = (4).to_bytes(2, "little") + (3).to_bytes(2, "little") + bytes(4)
    plan = save_layout.plan_bag_item_write(pocket, native_item_id=4, quantity=2, stack_cap=99)
    assert plan is not None
    offset, slot_bytes = plan
    assert offset == 0
    assert slot_bytes == (4).to_bytes(2, "little") + (5).to_bytes(2, "little")


def test_plan_bag_item_write_caps_stack_and_falls_back_to_free_slot_when_full():
    # slot 0: item 4 at the cap already, slot 1: free.
    pocket = (4).to_bytes(2, "little") + (99).to_bytes(2, "little") + bytes(4)
    plan = save_layout.plan_bag_item_write(pocket, native_item_id=4, quantity=1, stack_cap=99)
    assert plan is not None
    offset, slot_bytes = plan
    assert offset == 4  # the free slot, not the already-capped one
    assert slot_bytes == (4).to_bytes(2, "little") + (1).to_bytes(2, "little")


def test_plan_bag_item_write_returns_none_when_pocket_is_genuinely_full():
    # Two slots, both occupied by a different item, neither free nor
    # matching.
    pocket = (7).to_bytes(2, "little") + (99).to_bytes(2, "little") + (8).to_bytes(2, "little") + (
        99
    ).to_bytes(2, "little")
    assert save_layout.plan_bag_item_write(pocket, native_item_id=4, quantity=1, stack_cap=99) is None


def test_plan_bag_item_write_rejects_misaligned_buffer():
    with pytest.raises(ValueError):
        save_layout.plan_bag_item_write(bytes(3), native_item_id=4, quantity=1, stack_cap=99)


# === location_flags.py -- needs data/ ========================================


@pytest.fixture(scope="module")
def data_modules():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)

    importlib.invalidate_caches()
    modules = {}
    for name in ("data.items", "data.locations", "items", "locations", "location_flags"):
        if name in sys.modules:
            modules[name] = importlib.reload(sys.modules[name])
        else:
            modules[name] = importlib.import_module(name)
    yield modules
    shutil.rmtree(DATA_DIR, ignore_errors=True)


def test_ground_item_flag_id_is_the_raw_location_id(data_modules):
    location_flags = data_modules["location_flags"]
    LOCATIONS = data_modules["data.locations"].LOCATIONS

    ground_item_keys = [key for key, data in LOCATIONS.items() if data["type"] == "ground_item"]
    assert ground_item_keys
    for key in ground_item_keys:
        assert location_flags.flag_id_for_location(key) == LOCATIONS[key]["id"]


def test_hidden_item_flag_id_is_offset_by_hidden_items_flag_base(data_modules):
    location_flags = data_modules["location_flags"]
    LOCATIONS = data_modules["data.locations"].LOCATIONS

    hidden_item_keys = [key for key, data in LOCATIONS.items() if data["type"] == "hidden_item"]
    assert hidden_item_keys
    for key in hidden_item_keys:
        assert location_flags.flag_id_for_location(key) == save_layout.HIDDEN_ITEMS_FLAG_BASE + LOCATIONS[key]["id"]


def test_badge_locations_have_no_flag_id(data_modules):
    location_flags = data_modules["location_flags"]
    LOCATIONS = data_modules["data.locations"].LOCATIONS

    badge_keys = [key for key, data in LOCATIONS.items() if data["type"] == "badge"]
    assert badge_keys
    for key in badge_keys:
        assert location_flags.flag_id_for_location(key) is None


def test_flag_id_for_location_rejects_unknown_key(data_modules):
    location_flags = data_modules["location_flags"]
    with pytest.raises(KeyError):
        location_flags.flag_id_for_location("definitely_not_a_real_location")


def test_build_flag_id_to_ap_location_id_matches_location_id_map(data_modules):
    location_flags = data_modules["location_flags"]
    locations_mod = data_modules["locations"]
    LOCATIONS = data_modules["data.locations"].LOCATIONS

    ap_ids = locations_mod.create_location_label_to_code_map()
    mapping = location_flags.build_flag_id_to_ap_location_id()

    # Every entry must round-trip: flag id -> AP location id -> the same
    # location's own flag id.
    assert mapping
    for flag_id, ap_id in mapping.items():
        matching_keys = [
            key for key, data in LOCATIONS.items() if location_flags.flag_id_for_location(key) == flag_id
        ]
        assert any(ap_ids[key] == ap_id for key in matching_keys)

    # Every resolvable (non-badge, non-synthetic-band) location contributes
    # exactly one entry.
    resolvable = [key for key in LOCATIONS if location_flags.flag_id_for_location(key) is not None]
    assert len(mapping) == len(resolvable)


def test_unsupported_location_keys_all_lack_a_flag_id(data_modules):
    location_flags = data_modules["location_flags"]
    for key in location_flags.unsupported_location_keys():
        assert location_flags.flag_id_for_location(key) is None


# === client.py -- needs the local Archipelago checkout's worlds._bizhawk ====

bizhawk = pytest.importorskip("worlds._bizhawk")
pytest.importorskip("worlds._bizhawk.client")


@pytest.fixture(scope="module")
def client_module(data_modules):
    """Import client.py *after* data/ exists (it transitively imports
    data.items via items.py) -- same ordering constraint
    tests/test_world_init.py's own fixture documents."""
    if "client" in sys.modules:
        return importlib.reload(sys.modules["client"])
    return importlib.import_module("client")


def test_client_registers_with_bizhawk_framework(client_module):
    from worlds._bizhawk.client import AutoBizHawkClientRegister

    assert client_module.HeartGoldClient.game == "Pokemon HeartGold"
    assert client_module.HeartGoldClient.system == "NDS"
    handlers = AutoBizHawkClientRegister.game_handlers[("NDS",)]
    assert isinstance(handlers["Pokemon HeartGold"], client_module.HeartGoldClient)


def test_resolve_save_data_address_parses_hex_and_decimal(client_module, monkeypatch):
    monkeypatch.setenv(client_module.HEARTGOLD_SAVE_DATA_ADDRESS_ENV, "0x02100000")
    assert client_module._resolve_save_data_address() == 0x02100000

    monkeypatch.setenv(client_module.HEARTGOLD_SAVE_DATA_ADDRESS_ENV, "34603008")
    assert client_module._resolve_save_data_address() == 34603008

    monkeypatch.delenv(client_module.HEARTGOLD_SAVE_DATA_ADDRESS_ENV, raising=False)
    assert client_module._resolve_save_data_address() is None

    monkeypatch.setenv(client_module.HEARTGOLD_SAVE_DATA_ADDRESS_ENV, "not-a-number")
    assert client_module._resolve_save_data_address() is None


def test_address_overrides_default_to_none(client_module, monkeypatch):
    # No env var set at all -- both the instance attributes (set in
    # `__init__`/`validate_rom`) and the override-resolver functions
    # themselves must be `None`, i.e. "not manually overridden, use the
    # dynamic `arrayHeaders` scan" (see client.py's own module docstring,
    # "Dynamic SaveData location").
    monkeypatch.delenv(client_module.HEARTGOLD_BAG_BASE_ADDRESS_ENV, raising=False)
    monkeypatch.delenv(client_module.HEARTGOLD_FLAGS_ARRAY_ADDRESS_ENV, raising=False)

    handler = client_module.HeartGoldClient()
    assert handler.bag_base_address is None
    assert handler.flags_array_address is None

    assert client_module._resolve_bag_base_address_override() is None
    assert client_module._resolve_flags_array_address_override() is None

    # An invalid env var must not produce a bogus address -- `None`, same
    # as the absent case above (caller falls back to the dynamic scan).
    monkeypatch.setenv(client_module.HEARTGOLD_BAG_BASE_ADDRESS_ENV, "not-a-number")
    assert client_module._resolve_bag_base_address_override() is None

    monkeypatch.setenv(client_module.HEARTGOLD_FLAGS_ARRAY_ADDRESS_ENV, "not-a-number")
    assert client_module._resolve_flags_array_address_override() is None

    # A valid override is still honored (the fallback above is only for the
    # absent/invalid cases, not a blanket ignore of the env var).
    monkeypatch.setenv(client_module.HEARTGOLD_BAG_BASE_ADDRESS_ENV, "0x02100000")
    assert client_module._resolve_bag_base_address_override() == 0x02100000

    monkeypatch.setenv(client_module.HEARTGOLD_FLAGS_ARRAY_ADDRESS_ENV, "34603008")
    assert client_module._resolve_flags_array_address_override() == 34603008


def _build_fake_array_headers_blob(bag_offset: int, flags_offset: int) -> bytes:
    """A synthetic `SaveData.arrayHeaders[]` blob: 5 sequential
    `SaveArrayHeader{int id; u32 size; u32 offset; u16 crc; u16 slot;}`
    records (ids 0-4), with `_BAG_CHUNK_ID`/`_FLAGS_CHUNK_ID`'s `offset`
    fields set to the given values -- everything else is arbitrary but
    valid-shaped."""
    import struct

    out = bytearray()
    for chunk_id in range(5):
        offset = bag_offset if chunk_id == 3 else flags_offset if chunk_id == 4 else 0
        out += struct.pack("<iIIHH", chunk_id, 100, offset, 0, 0)
    return bytes(out)


def test_looks_like_array_headers_matches_real_signature_and_rejects_near_misses(client_module):
    blob = _build_fake_array_headers_blob(bag_offset=1604, flags_offset=3556)
    assert client_module._looks_like_array_headers(blob, 0) is True

    # Same shape but ids off by one (0,1,2,3,5 instead of 0,1,2,3,4) --
    # must not match, this is exactly the kind of near-miss the scan needs
    # to reject to stay reliable.
    import struct

    broken = bytearray(blob)
    struct.pack_into("<i", broken, 4 * 16, 5)
    assert client_module._looks_like_array_headers(bytes(broken), 0) is False

    # Too short to even contain the signature.
    assert client_module._looks_like_array_headers(blob[:10], 0) is False


def test_locate_save_addresses_derives_bag_and_flags_from_array_headers(client_module, monkeypatch):
    array_headers_address = 0x0229F26C
    bag_chunk_offset = 1604
    flags_chunk_offset = 3556
    blob = _build_fake_array_headers_blob(bag_offset=bag_chunk_offset, flags_offset=flags_chunk_offset)

    scan_start = client_module._ARRAY_HEADERS_SCAN_START
    signature_position_in_scan = array_headers_address - scan_start

    async def fake_read(bizhawk_ctx, read_list):
        (address, size, domain) = read_list[0]
        assert domain == "ARM9 System Bus"
        # The scan reads the whole window in chunks; only the chunk(s)
        # overlapping our planted signature need real bytes, the rest can
        # be zero (no other 0,1,2,3,4 sequence will appear by chance).
        result = bytearray(size)
        blob_start_in_this_chunk = signature_position_in_scan - address + scan_start
        for i, byte in enumerate(blob):
            pos = blob_start_in_this_chunk + i
            if 0 <= pos < size:
                result[pos] = byte
        return [bytes(result)]

    monkeypatch.setattr(client_module.bizhawk, "read", fake_read)

    ctx = _make_fake_ctx(missing_locations=set(), items_received=[])
    located = asyncio.run(client_module._locate_save_addresses(ctx))
    assert located is not None
    bag_address, flags_array_address, found_array_headers_address = located

    assert found_array_headers_address == array_headers_address
    dynamic_region_base = array_headers_address - client_module._SAVE_COUNTER_SIZE - client_module._DYNAMIC_REGION_SIZE
    assert bag_address == dynamic_region_base + bag_chunk_offset
    assert flags_array_address == dynamic_region_base + flags_chunk_offset + client_module.FLAGS_ARRAY_OFFSET


def test_locate_save_addresses_returns_none_when_signature_not_found(client_module, monkeypatch):
    async def fake_read(bizhawk_ctx, read_list):
        (address, size, domain) = read_list[0]
        return [bytes(size)]  # all zero, no signature anywhere

    monkeypatch.setattr(client_module.bizhawk, "read", fake_read)

    ctx = _make_fake_ctx(missing_locations=set(), items_received=[])
    located = asyncio.run(client_module._locate_save_addresses(ctx))
    assert located is None


def test_ensure_addresses_located_prefers_manual_overrides_without_scanning(client_module, monkeypatch):
    async def fail_read(*_args, **_kwargs):
        raise AssertionError("must not scan RAM when both addresses are manually overridden")

    monkeypatch.setattr(client_module.bizhawk, "read", fail_read)

    handler = client_module.HeartGoldClient()
    handler._manual_bag_base_override = 0x0227C8AC
    handler._manual_flags_array_override = 0x0227D32C

    ctx = _make_fake_ctx(missing_locations=set(), items_received=[])
    assert asyncio.run(handler._ensure_addresses_located(ctx)) is True


def test_ensure_addresses_located_scans_once_then_caches(client_module, monkeypatch):
    array_headers_address = 0x0229F26C
    blob = _build_fake_array_headers_blob(bag_offset=1604, flags_offset=3556)
    scan_start = client_module._ARRAY_HEADERS_SCAN_START
    signature_position_in_scan = array_headers_address - scan_start

    read_calls: list[int] = []

    async def fake_read(bizhawk_ctx, read_list):
        (address, size, domain) = read_list[0]
        read_calls.append(address)
        result = bytearray(size)
        blob_start_in_this_chunk = signature_position_in_scan - address + scan_start
        for i, byte in enumerate(blob):
            pos = blob_start_in_this_chunk + i
            if 0 <= pos < size:
                result[pos] = byte
        return [bytes(result)]

    monkeypatch.setattr(client_module.bizhawk, "read", fake_read)

    handler = client_module.HeartGoldClient()
    ctx = _make_fake_ctx(missing_locations=set(), items_received=[])

    assert asyncio.run(handler._ensure_addresses_located(ctx)) is True
    assert handler.bag_base_address is not None
    assert handler.flags_array_address is not None
    calls_after_first_locate = len(read_calls)

    # Second call: the cached `arrayHeaders` address is still valid (same
    # fake_read still serves the signature there), so this must be a
    # single cheap validation read, not a full re-scan of the window.
    assert asyncio.run(handler._ensure_addresses_located(ctx)) is True
    assert len(read_calls) == calls_after_first_locate + 1


def test_ensure_addresses_located_rescans_when_cache_goes_stale(client_module, monkeypatch):
    # Simulates exactly the scenario that motivated this module: the save
    # was reloaded and `SaveData` (and therefore `arrayHeaders`) moved to
    # a different address -- the previously-cached address no longer
    # contains the signature, so a fresh scan must find the new one.
    old_array_headers_address = 0x0229F26C
    new_array_headers_address = 0x0229EA00
    old_blob = _build_fake_array_headers_blob(bag_offset=1604, flags_offset=3556)
    new_blob = _build_fake_array_headers_blob(bag_offset=2000, flags_offset=4000)
    scan_start = client_module._ARRAY_HEADERS_SCAN_START

    active_address = {"value": old_array_headers_address}
    active_blob = {"value": old_blob}

    async def fake_read(bizhawk_ctx, read_list):
        (address, size, domain) = read_list[0]
        signature_position_in_scan = active_address["value"] - scan_start
        result = bytearray(size)
        blob_start_in_this_chunk = signature_position_in_scan - address + scan_start
        for i, byte in enumerate(active_blob["value"]):
            pos = blob_start_in_this_chunk + i
            if 0 <= pos < size:
                result[pos] = byte
        return [bytes(result)]

    monkeypatch.setattr(client_module.bizhawk, "read", fake_read)

    handler = client_module.HeartGoldClient()
    ctx = _make_fake_ctx(missing_locations=set(), items_received=[])

    assert asyncio.run(handler._ensure_addresses_located(ctx)) is True
    first_bag_address = handler.bag_base_address

    # "Reload the save": the old location no longer has the signature,
    # the new one does.
    active_address["value"] = new_array_headers_address
    active_blob["value"] = new_blob

    assert asyncio.run(handler._ensure_addresses_located(ctx)) is True
    assert handler.bag_base_address != first_bag_address


def test_resolve_save_layout_case_name_only_accepts_known_cases(client_module, monkeypatch):
    monkeypatch.setenv(client_module.HEARTGOLD_SAVE_LAYOUT_CASE_ENV, "apcs_4byte_longlong")
    assert client_module._resolve_save_layout_case_name() == "apcs_4byte_longlong"

    monkeypatch.setenv(client_module.HEARTGOLD_SAVE_LAYOUT_CASE_ENV, "made_up_case")
    assert client_module._resolve_save_layout_case_name() is None

    monkeypatch.delenv(client_module.HEARTGOLD_SAVE_LAYOUT_CASE_ENV, raising=False)
    assert client_module._resolve_save_layout_case_name() is None


def test_missing_configuration_message_names_both_env_vars(client_module):
    message = client_module._missing_configuration_message()
    assert client_module.HEARTGOLD_SAVE_DATA_ADDRESS_ENV in message
    assert client_module.HEARTGOLD_SAVE_LAYOUT_CASE_ENV in message
    for name in save_layout.CANDIDATE_OFFSETS:
        assert name in message


def test_ap_item_id_to_bag_write_info_covers_known_items(client_module, data_modules):
    from items import HEARTGOLD_ITEM_ID_BASE

    ITEMS = data_modules["data.items"].ITEMS

    poke_ball_ap_id = HEARTGOLD_ITEM_ID_BASE + ITEMS["poke_ball"]["id"]
    assert client_module._AP_ITEM_ID_TO_BAG_WRITE_INFO[poke_ball_ap_id] == (ITEMS["poke_ball"]["id"], "balls")

    bicycle_ap_id = HEARTGOLD_ITEM_ID_BASE + ITEMS["bicycle"]["id"]
    assert client_module._AP_ITEM_ID_TO_BAG_WRITE_INFO[bicycle_ap_id] == (ITEMS["bicycle"]["id"], "keyItems")

    # Every real item (all 8 pockets are covered by POCKET_KEY_TO_BAG_FIELD)
    # must resolve to a write target -- none should be silently dropped.
    assert len(client_module._AP_ITEM_ID_TO_BAG_WRITE_INFO) == len(ITEMS)


# -- async orchestration, driven against a fake ctx + monkeypatched bizhawk.* -


class _FakeBizHawkRequestFailedError(Exception):
    pass


def _make_fake_ctx(*, missing_locations, items_received, team=0, slot=1):
    checked: list[set[int]] = []

    async def check_locations(locations):
        checked.append(set(locations))
        return set(locations)

    sent_msgs: list[list[dict]] = []

    async def send_msgs(msgs):
        sent_msgs.append(msgs)

    ctx = SimpleNamespace(
        server=SimpleNamespace(socket=SimpleNamespace(closed=False)),
        slot_data={},
        missing_locations=set(missing_locations),
        items_received=list(items_received),
        team=team,
        slot=slot,
        bizhawk_ctx=None,
        stored_data={},
        check_locations=check_locations,
        send_msgs=send_msgs,
    )
    ctx._checked_calls = checked
    ctx._sent_msgs = sent_msgs
    return ctx


def test_check_locations_reads_flags_and_reports_newly_set_ones(client_module, data_modules, monkeypatch):
    location_flags = data_modules["location_flags"]
    flag_map = location_flags.build_flag_id_to_ap_location_id()
    flag_id, ap_location_id = next(iter(flag_map.items()))

    flags_bytes = bytearray(save_layout.FLAGS_ARRAY_SIZE)
    byte_index, bit_index = save_layout.flag_byte_and_bit(flag_id)
    flags_bytes[byte_index] |= 1 << bit_index

    async def fake_read(bizhawk_ctx, read_list):
        (address, size, domain) = read_list[0]
        assert domain == "ARM9 System Bus"
        assert size == save_layout.FLAGS_ARRAY_SIZE
        return [bytes(flags_bytes)]

    monkeypatch.setattr(client_module.bizhawk, "read", fake_read)

    handler = client_module.HeartGoldClient()

    ctx = _make_fake_ctx(missing_locations={ap_location_id}, items_received=[])

    asyncio.run(handler._check_locations(ctx))

    assert ctx._checked_calls == [{ap_location_id}]
    assert handler.local_checked_locations == {ap_location_id}


def test_check_locations_ignores_flags_for_locations_not_missing(client_module, data_modules, monkeypatch):
    location_flags = data_modules["location_flags"]
    flag_map = location_flags.build_flag_id_to_ap_location_id()
    flag_id, ap_location_id = next(iter(flag_map.items()))

    flags_bytes = bytearray(save_layout.FLAGS_ARRAY_SIZE)
    byte_index, bit_index = save_layout.flag_byte_and_bit(flag_id)
    flags_bytes[byte_index] |= 1 << bit_index

    async def fake_read(bizhawk_ctx, read_list):
        return [bytes(flags_bytes)]

    monkeypatch.setattr(client_module.bizhawk, "read", fake_read)

    handler = client_module.HeartGoldClient()

    # ap_location_id already checked server-side -> not in missing_locations.
    ctx = _make_fake_ctx(missing_locations=set(), items_received=[])

    asyncio.run(handler._check_locations(ctx))

    assert ctx._checked_calls == []


def test_apply_next_received_item_writes_into_free_bag_slot(client_module, data_modules, monkeypatch):
    from NetUtils import NetworkItem

    from items import HEARTGOLD_ITEM_ID_BASE

    ITEMS = data_modules["data.items"].ITEMS
    poke_ball = ITEMS["poke_ball"]
    poke_ball_ap_id = HEARTGOLD_ITEM_ID_BASE + poke_ball["id"]

    written: list[tuple[int, bytes, str]] = []

    async def fake_read(bizhawk_ctx, read_list):
        (address, size, domain) = read_list[0]
        assert domain == "ARM9 System Bus"
        return [bytes(size)]  # empty pocket

    async def fake_guarded_write(bizhawk_ctx, write_list, guard_list):
        written.extend(write_list)
        return True

    monkeypatch.setattr(client_module.bizhawk, "read", fake_read)
    monkeypatch.setattr(client_module.bizhawk, "guarded_write", fake_guarded_write)

    handler = client_module.HeartGoldClient()
    # The address itself is arbitrary here -- see the "Dynamic SaveData
    # location" tests above for how it's actually derived in practice.
    handler.bag_base_address = 0x0227C8AC

    ctx = _make_fake_ctx(
        missing_locations=set(),
        items_received=[NetworkItem(item=poke_ball_ap_id, location=0, player=1, flags=0)],
    )

    asyncio.run(handler._apply_next_received_item(ctx, "some_key"))

    assert handler._applied_item_count == 1
    assert len(written) == 1
    address, value, domain = written[0]
    assert domain == "ARM9 System Bus"
    assert bytes(value) == poke_ball["id"].to_bytes(2, "little") + (1).to_bytes(2, "little")

    pocket_offset, _capacity = save_layout.BAG_POCKET_OFFSETS["balls"]
    expected_address = handler.bag_base_address + pocket_offset
    assert address == expected_address

    # Bookkeeping was persisted to data storage too.
    assert ctx.stored_data["some_key"] == 1
    assert ctx._sent_msgs and ctx._sent_msgs[0][0]["cmd"] == "Set"


def test_apply_next_received_item_skips_items_it_does_not_own(client_module, monkeypatch):
    from NetUtils import NetworkItem

    async def fail_read(*_args, **_kwargs):
        raise AssertionError("should not read RAM for an item this client cannot place")

    monkeypatch.setattr(client_module.bizhawk, "read", fail_read)

    handler = client_module.HeartGoldClient()

    # An id that is not any real HeartGold item's AP id.
    ctx = _make_fake_ctx(missing_locations=set(), items_received=[NetworkItem(item=-1, location=0, player=1, flags=0)])

    asyncio.run(handler._apply_next_received_item(ctx, "some_key"))

    assert handler._applied_item_count == 1
    assert ctx.stored_data["some_key"] == 1


def test_apply_next_received_item_does_nothing_when_already_caught_up(client_module):
    handler = client_module.HeartGoldClient()
    handler._applied_item_count = 0

    ctx = _make_fake_ctx(missing_locations=set(), items_received=[])

    asyncio.run(handler._apply_next_received_item(ctx, "some_key"))

    assert handler._applied_item_count == 0
    assert ctx._sent_msgs == []
