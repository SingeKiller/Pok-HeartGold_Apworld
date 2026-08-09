"""Tests for local item substitution (task C15): patching a `ground_item`
itemball's script bytecode operand in `scr_seq_0141.bin` so it grants a
different item, per docs/architecture.md's "## ROM code injection strategy
(revised after C14)" -> "Local items" bullet and rom/eventscriptdata.py's
own docstring (which documents the binary format investigation this test
file cross-checks).

Two independent layers are covered:

- **Binary format, no real ROM needed** (`test_write_itemball_item_id_*`,
  `test_block_offset_*`): a small synthetic `scr_seq_0141.bin`-shaped buffer
  built from this module's own documented constants, so these always run
  (including in CI, which has no ROM -- same "skip cleanly if
  HEARTGOLD_ROM_PATH is unset/invalid" convention as
  tests/test_rom_roundtrip.py/tests/test_rom_access.py/tests/test_patch_gen.py
  for everything else).
- **Real ROM cross-checks** (everything below the "Real ROM" section
  header): applies substitutions to a copy of the real HeartGold (US) ROM,
  verifies untouched `ground_item` locations keep their vanilla
  `original_item`, and includes the task's own requested "substitute every
  ground_item location with a dummy item, make sure none of the 217 writes
  raises" format-limit check.
"""

from __future__ import annotations

import importlib
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ndspy_narc = pytest.importorskip("ndspy.narc")

import patch_gen  # noqa: E402
from rom import HeartGoldRom, eventscriptdata  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

ROM_PATH_ENV_VAR = "HEARTGOLD_ROM_PATH"


def _rom_path() -> Path | None:
    raw_path = os.environ.get(ROM_PATH_ENV_VAR)
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_file():
        return None
    return path


@pytest.fixture()
def rom_bytes() -> bytes:
    path = _rom_path()
    if path is None:
        pytest.skip(
            f"HeartGold ROM not available locally: set {ROM_PATH_ENV_VAR} to "
            "a valid ROM path to run this test."
        )
    return path.read_bytes()


@pytest.fixture()
def rom(rom_bytes: bytes) -> HeartGoldRom:
    return HeartGoldRom(rom_bytes)


@pytest.fixture(scope="module")
def generated_data():
    """Regenerate `data/` once for every test in this module that needs
    `data/locations.py`/`data/items.py` -- same subprocess-based fixture
    pattern tests/test_rom_access.py already uses."""
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)

    importlib.invalidate_caches()
    locations_mod = importlib.reload(importlib.import_module("data.locations"))
    items_mod = importlib.reload(importlib.import_module("data.items"))
    yield {
        "LOCATIONS": locations_mod.LOCATIONS,
        "ITEMS": items_mod.ITEMS,
    }
    shutil.rmtree(DATA_DIR, ignore_errors=True)


def _ground_item_keys(locations: dict) -> list[str]:
    return [key for key, loc in locations.items() if loc["type"] == "ground_item"]


def _block_index_for(locations: dict, location_key: str) -> int:
    return eventscriptdata.BLOCK_INDEX_BY_ITEMBALL_FLAG_ID[locations[location_key]["id"]]


# --- Binary format (synthetic buffer, no real ROM needed) --------------------


def test_module_constants_match_documented_layout() -> None:
    """See rom/eventscriptdata.py's own docstring for how each of these was
    derived from the decomp and cross-checked against the real ROM."""
    assert eventscriptdata.HEADER_ENTRY_COUNT == 256
    assert eventscriptdata.HEADER_SIZE == 256 * 4 + 2 == 1026
    assert eventscriptdata.SCRDEF_END_MARKER == 0xFD13
    assert eventscriptdata.BLOCK_COUNT == 255
    assert eventscriptdata.BLOCK_SIZE == 20
    assert eventscriptdata.ITEM_ID_OPERAND_OFFSET == 4
    assert eventscriptdata.QUANTITY_OPERAND_OFFSET == 10


def test_block_index_table_covers_254_of_255_blocks() -> None:
    """One block (58, the Celadon Coin Case -- see this module's docstring)
    has no matching ground_item location, so the table has 254 entries, not
    255."""
    assert len(eventscriptdata.BLOCK_INDEX_BY_ITEMBALL_FLAG_ID) == 254
    assert set(eventscriptdata.BLOCK_INDEX_BY_ITEMBALL_FLAG_ID.values()) == set(range(255)) - {58}


def test_block_offset_is_header_size_plus_index_times_block_size() -> None:
    assert eventscriptdata._block_offset(0) == eventscriptdata.HEADER_SIZE
    assert eventscriptdata._block_offset(1) == eventscriptdata.HEADER_SIZE + eventscriptdata.BLOCK_SIZE
    assert eventscriptdata._block_offset(254) == eventscriptdata.HEADER_SIZE + 254 * eventscriptdata.BLOCK_SIZE


def test_block_offset_rejects_out_of_range_index() -> None:
    with pytest.raises(ValueError, match="out of range"):
        eventscriptdata._block_offset(-1)
    with pytest.raises(ValueError, match="out of range"):
        eventscriptdata._block_offset(255)


def _synthetic_itemball_blob() -> bytearray:
    """Build a minimal but structurally faithful `scr_seq_0141.bin`-shaped
    buffer: the real header shape (ScrDef words + ScrDefEnd marker) followed
    by 255 blocks, each holding a distinct, easily-recognizable item id
    (`1000 + block_index`) at the documented `SetVar`/`GoTo`/`End` shape --
    so a test can assert that patching one block never perturbs any other
    block's bytes."""
    total_size = eventscriptdata.HEADER_SIZE + eventscriptdata.BLOCK_COUNT * eventscriptdata.BLOCK_SIZE
    blob = bytearray(total_size)
    struct.pack_into("<H", blob, eventscriptdata.SCRDEF_END_OFFSET, eventscriptdata.SCRDEF_END_MARKER)
    for index in range(eventscriptdata.BLOCK_COUNT):
        offset = eventscriptdata._block_offset(index)
        struct.pack_into("<H", blob, offset + 0, 41)  # SetVar opcode
        struct.pack_into("<H", blob, offset + 2, 0x8008)  # VAR_SPECIAL_x8008
        struct.pack_into("<H", blob, offset + 4, 1000 + index)  # item id (unique per block)
        struct.pack_into("<H", blob, offset + 6, 41)  # SetVar opcode
        struct.pack_into("<H", blob, offset + 8, 0x8009)  # VAR_SPECIAL_x8009
        struct.pack_into("<H", blob, offset + 10, 1)  # quantity
        struct.pack_into("<H", blob, offset + 12, 22)  # GoTo opcode
        struct.pack_into("<i", blob, offset + 14, 0)  # GoTo relative offset (arbitrary here)
        struct.pack_into("<H", blob, offset + 18, 2)  # End opcode
    return blob


def test_read_itemball_item_id_reads_documented_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    blob = _synthetic_itemball_blob()
    monkeypatch.setattr(eventscriptdata, "read_itemball_script_blob", lambda rom: bytes(blob))

    for index in (0, 1, 254):
        assert eventscriptdata.read_itemball_item_id(object(), index) == 1000 + index


def test_write_itemball_item_id_touches_only_the_target_block(monkeypatch: pytest.MonkeyPatch) -> None:
    original = _synthetic_itemball_blob()
    written: dict[str, bytes] = {}
    monkeypatch.setattr(eventscriptdata, "read_itemball_script_blob", lambda rom: bytes(original))
    monkeypatch.setattr(
        eventscriptdata, "write_itemball_script_blob", lambda rom, data: written.__setitem__("blob", data)
    )

    eventscriptdata.write_itemball_item_id(object(), 5, 9999)

    patched = written["blob"]
    assert len(patched) == len(original)

    target_offset = eventscriptdata._block_offset(5) + eventscriptdata.ITEM_ID_OPERAND_OFFSET
    assert struct.unpack_from("<H", patched, target_offset)[0] == 9999

    # Everything outside that single 2-byte operand -- including block 5's
    # own quantity/GoTo/End, every other block, and the header -- is
    # byte-identical to the original.
    assert patched[:target_offset] == bytes(original[:target_offset])
    assert patched[target_offset + 2 :] == bytes(original[target_offset + 2 :])


def test_write_itemball_item_id_rejects_out_of_range_values() -> None:
    """The operand is a plain unsigned 16-bit field (see rom/eventscriptdata.py's
    docstring); the range check runs before any ROM access is attempted, so
    this needs no real ROM."""
    with pytest.raises(ValueError, match="0-65535"):
        eventscriptdata.write_itemball_item_id(object(), 0, -1)
    with pytest.raises(ValueError, match="0-65535"):
        eventscriptdata.write_itemball_item_id(object(), 0, 0x10000)


# --- Real ROM cross-checks ----------------------------------------------------


def test_real_rom_scr_seq_0141_header_shape(rom: HeartGoldRom) -> None:
    blob = eventscriptdata.read_itemball_script_blob(rom)
    marker = struct.unpack_from("<H", blob, eventscriptdata.SCRDEF_END_OFFSET)[0]
    assert marker == eventscriptdata.SCRDEF_END_MARKER
    assert len(blob) > eventscriptdata.HEADER_SIZE + eventscriptdata.BLOCK_COUNT * eventscriptdata.BLOCK_SIZE


def test_real_rom_ground_item_operands_match_vanilla_original_item(
    rom: HeartGoldRom, generated_data: dict
) -> None:
    """Cross-checks every one of the 217 `ground_item` locations in
    `data_gen/locations.toml` against the real ROM: the item-id operand at
    that location's mapped block must equal `data/items.py[original_item]['id']`
    exactly -- i.e. `BLOCK_INDEX_BY_ITEMBALL_FLAG_ID` is correct."""
    locations = generated_data["LOCATIONS"]
    items = generated_data["ITEMS"]
    ground_keys = _ground_item_keys(locations)
    assert len(ground_keys) == 217

    mismatches = []
    for key in ground_keys:
        block_index = _block_index_for(locations, key)
        got = eventscriptdata.read_itemball_item_id(rom, block_index)
        expected = items[locations[key]["original_item"]]["id"]
        if got != expected:
            mismatches.append((key, got, expected))
    assert mismatches == []


def test_write_ground_item_substitution_leaves_other_locations_untouched(
    rom: HeartGoldRom, generated_data: dict
) -> None:
    locations = generated_data["LOCATIONS"]
    items = generated_data["ITEMS"]
    ground_keys = _ground_item_keys(locations)

    before = {key: eventscriptdata.read_itemball_item_id(rom, _block_index_for(locations, key)) for key in ground_keys}

    target_key = ground_keys[3]
    original_item_key = locations[target_key]["original_item"]
    new_item_key = "master_ball" if original_item_key != "master_ball" else "rare_candy"

    eventscriptdata.write_ground_item_substitution(rom, target_key, new_item_key)

    target_block_index = _block_index_for(locations, target_key)
    assert eventscriptdata.read_itemball_item_id(rom, target_block_index) == items[new_item_key]["id"]

    for key in ground_keys:
        if key == target_key:
            continue
        assert eventscriptdata.read_itemball_item_id(rom, _block_index_for(locations, key)) == before[key]


def test_write_ground_item_substitution_rejects_non_ground_item_location(
    rom: HeartGoldRom, generated_data: dict
) -> None:
    """`hm_tm` is accepted too (task C16, for its itemball-shaped half --
    see tests/test_npc_gift_substitution.py), so this picks a type that is
    never accepted (`npc_gift`)."""
    locations = generated_data["LOCATIONS"]
    non_ground_key = next(key for key, loc in locations.items() if loc["type"] == "npc_gift")
    with pytest.raises(eventscriptdata.ScriptDataError, match="ground_item"):
        eventscriptdata.write_ground_item_substitution(rom, non_ground_key, "master_ball")


def test_write_ground_item_substitution_accepts_itemball_shaped_hm_tm(
    rom: HeartGoldRom, generated_data: dict
) -> None:
    """Task C16: `hm_tm` locations whose flag id is a real
    `scr_seq_0141.bin` block (i.e. the vanilla delivery mechanism actually
    is a plain item ball) are patched the exact same way as `ground_item`
    -- see this function's own docstring."""
    locations = generated_data["LOCATIONS"]
    items = generated_data["ITEMS"]
    itemball_hm_tm_key = next(
        key
        for key, loc in locations.items()
        if loc["type"] == "hm_tm" and loc["id"] in eventscriptdata.BLOCK_INDEX_BY_ITEMBALL_FLAG_ID
    )
    block_index = eventscriptdata.BLOCK_INDEX_BY_ITEMBALL_FLAG_ID[locations[itemball_hm_tm_key]["id"]]

    eventscriptdata.write_ground_item_substitution(rom, itemball_hm_tm_key, "master_ball")

    assert eventscriptdata.read_itemball_item_id(rom, block_index) == items["master_ball"]["id"]


def test_write_ground_item_substitution_rejects_npc_delivered_hm_tm(
    rom: HeartGoldRom, generated_data: dict
) -> None:
    """The other half of `hm_tm` (NPC-delivered, no itemball block) is
    explicitly rejected here -- it belongs to
    rom/npcgiftdata.py's write_npc_gift_substitution instead."""
    locations = generated_data["LOCATIONS"]
    npc_hm_tm_key = next(
        key
        for key, loc in locations.items()
        if loc["type"] == "hm_tm" and loc["id"] not in eventscriptdata.BLOCK_INDEX_BY_ITEMBALL_FLAG_ID
    )
    with pytest.raises(eventscriptdata.ScriptDataError, match="npcgiftdata"):
        eventscriptdata.write_ground_item_substitution(rom, npc_hm_tm_key, "master_ball")


def test_write_ground_item_substitution_rejects_unknown_keys(rom: HeartGoldRom, generated_data: dict) -> None:
    locations = generated_data["LOCATIONS"]
    real_ground_key = _ground_item_keys(locations)[0]
    with pytest.raises(KeyError):
        eventscriptdata.write_ground_item_substitution(rom, "not_a_real_location", "master_ball")
    with pytest.raises(KeyError):
        eventscriptdata.write_ground_item_substitution(rom, real_ground_key, "not_a_real_item")


def test_apply_local_item_substitutions_applies_mapping_and_roundtrips_saved_rom(
    rom: HeartGoldRom, generated_data: dict, tmp_path: Path
) -> None:
    """Task's own validation ask: apply a mapping of a few reassigned
    locations to a ROM copy, save it, reread the NARC from the saved
    ROM, and confirm both the touched locations *and* the untouched ones
    are correct (no bleed into neighboring script blocks caused by the
    ndspy repack itself)."""
    locations = generated_data["LOCATIONS"]
    items = generated_data["ITEMS"]
    ground_keys = _ground_item_keys(locations)

    before = {key: eventscriptdata.read_itemball_item_id(rom, _block_index_for(locations, key)) for key in ground_keys}

    substitutions = {
        ground_keys[0]: "master_ball",
        ground_keys[1]: "rare_candy",
        ground_keys[50]: "full_restore",
    }
    patch_gen.apply_local_item_substitutions(rom, substitutions)

    out_path = tmp_path / "heartgold_local_item_substitution_test.nds"
    rom.save(out_path)
    reloaded = HeartGoldRom.open(out_path, expect_vanilla=False)

    for key, item_key in substitutions.items():
        block_index = _block_index_for(locations, key)
        assert eventscriptdata.read_itemball_item_id(reloaded, block_index) == items[item_key]["id"]

    for key in ground_keys:
        if key in substitutions:
            continue
        block_index = _block_index_for(locations, key)
        assert eventscriptdata.read_itemball_item_id(reloaded, block_index) == before[key]


def test_all_ground_item_locations_substitutable_without_crashing(
    rom: HeartGoldRom, generated_data: dict
) -> None:
    """Task's own requested format-limit check: substitute *every*
    `ground_item` location with a single dummy item and make sure none of
    the 217 writes raises (the operand is an unsigned 16-bit field and
    every native item id in data/items.py tops out at 536, so this is
    expected to always succeed -- this test is what actually proves that,
    rather than assuming it)."""
    locations = generated_data["LOCATIONS"]
    items = generated_data["ITEMS"]
    ground_keys = _ground_item_keys(locations)
    dummy_item_key = "rare_candy"

    substitutions = {key: dummy_item_key for key in ground_keys}
    patch_gen.apply_local_item_substitutions(rom, substitutions)

    for key in ground_keys:
        block_index = _block_index_for(locations, key)
        assert eventscriptdata.read_itemball_item_id(rom, block_index) == items[dummy_item_key]["id"]
