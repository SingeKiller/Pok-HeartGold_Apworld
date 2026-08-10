"""Tests for hidden-item local item substitution (task M4.5): patching
`sHiddenItemParam`'s `itemId` field, per rom/hiddenitemdata.py's own
docstring (which documents how this table's real RAM address was found --
a compiled ARM9 static table, unlike every other NARC-based table this
project patches, and compressed in the packed ROM on top of that).

Same real-ROM-fixture structure as tests/test_npc_gift_substitution.py.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import patch_gen  # noqa: E402
from rom import HeartGoldRom, hiddenitemdata  # noqa: E402

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


def _hidden_item_keys(locations: dict) -> list[str]:
    return [key for key, loc in locations.items() if loc["type"] == "hidden_item"]


# --- Real ROM cross-checks ----------------------------------------------------


def test_read_all_has_expected_shape_and_entry_zero(rom: HeartGoldRom) -> None:
    entries = hiddenitemdata.read_all(rom)
    assert len(entries) == hiddenitemdata.ENTRY_COUNT
    assert all(len(e) == hiddenitemdata.ENTRY_SIZE for e in entries)
    # entry 0: itemId=17 (Potion), quantity=1, unk3=0, unk4=0, index=0 --
    # the New Bark Town hidden item, live-verified byte-for-byte this task.
    assert entries[0] == bytes([0x11, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])


def test_every_hidden_item_location_resolves_and_matches_vanilla_item(
    rom: HeartGoldRom, generated_data: dict
) -> None:
    locations = generated_data["LOCATIONS"]
    items = generated_data["ITEMS"]

    mismatches = []
    for location_key in _hidden_item_keys(locations):
        location = locations[location_key]
        position = hiddenitemdata._find_position_by_index(rom, location["id"])
        entry = hiddenitemdata.read_entry(rom, position)
        got_item_id = int.from_bytes(entry[0:2], "little")
        expected_item_id = items[location["original_item"]]["id"]
        if got_item_id != expected_item_id:
            mismatches.append((location_key, got_item_id, expected_item_id))
    assert mismatches == []


def test_write_hidden_item_substitution_touches_only_target_entry(
    rom: HeartGoldRom, generated_data: dict
) -> None:
    locations = generated_data["LOCATIONS"]
    items = generated_data["ITEMS"]
    keys = _hidden_item_keys(locations)

    before = hiddenitemdata.read_all(rom)

    target_key = keys[5]
    original_item_key = locations[target_key]["original_item"]
    new_item_key = "master_ball" if original_item_key != "master_ball" else "rare_candy"
    hiddenitemdata.write_hidden_item_substitution(rom, target_key, new_item_key)

    after = hiddenitemdata.read_all(rom)
    target_position = hiddenitemdata._find_position_by_index(rom, locations[target_key]["id"])

    changed = [i for i in range(len(before)) if before[i] != after[i]]
    assert changed == [target_position]
    assert int.from_bytes(after[target_position][0:2], "little") == items[new_item_key]["id"]
    # quantity/unk3/unk4/index untouched
    assert after[target_position][2:] == before[target_position][2:]


def test_write_hidden_item_substitution_rejects_non_hidden_item_location(
    rom: HeartGoldRom, generated_data: dict
) -> None:
    locations = generated_data["LOCATIONS"]
    ground_key = next(key for key, loc in locations.items() if loc["type"] == "ground_item")
    with pytest.raises(hiddenitemdata.HiddenItemDataError, match="hidden_item"):
        hiddenitemdata.write_hidden_item_substitution(rom, ground_key, "master_ball")


def test_write_hidden_item_substitution_rejects_unknown_keys(rom: HeartGoldRom, generated_data: dict) -> None:
    locations = generated_data["LOCATIONS"]
    real_key = _hidden_item_keys(locations)[0]
    with pytest.raises(KeyError):
        hiddenitemdata.write_hidden_item_substitution(rom, "not_a_real_location", "master_ball")
    with pytest.raises(KeyError):
        hiddenitemdata.write_hidden_item_substitution(rom, real_key, "not_a_real_item")


def test_apply_local_item_substitutions_routes_hidden_item_and_round_trips(
    rom: HeartGoldRom, generated_data: dict, tmp_path: Path
) -> None:
    locations = generated_data["LOCATIONS"]
    items = generated_data["ITEMS"]
    hidden_key = _hidden_item_keys(locations)[2]

    patch_gen.apply_local_item_substitutions(rom, {hidden_key: "full_restore"})

    out_path = tmp_path / "heartgold_hidden_item_substitution_test.nds"
    rom.save(out_path)
    reloaded = HeartGoldRom.open(out_path, expect_vanilla=False)

    position = hiddenitemdata._find_position_by_index(reloaded, locations[hidden_key]["id"])
    entry = hiddenitemdata.read_entry(reloaded, position)
    assert int.from_bytes(entry[0:2], "little") == items["full_restore"]["id"]


def test_all_hidden_item_locations_substitutable_without_crashing(rom: HeartGoldRom, generated_data: dict) -> None:
    locations = generated_data["LOCATIONS"]
    items = generated_data["ITEMS"]
    keys = _hidden_item_keys(locations)
    dummy_item_key = "rare_candy"

    for key in keys:
        hiddenitemdata.write_hidden_item_substitution(rom, key, dummy_item_key)

    for key in keys:
        position = hiddenitemdata._find_position_by_index(rom, locations[key]["id"])
        entry = hiddenitemdata.read_entry(rom, position)
        assert int.from_bytes(entry[0:2], "little") == items[dummy_item_key]["id"]
