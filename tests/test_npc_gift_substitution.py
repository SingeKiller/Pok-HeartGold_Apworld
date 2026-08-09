"""Tests for local item substitution (task C16): patching the `SetVar
VAR_SPECIAL_x8004, <item id>` operand a `npc_gift` (or NPC-delivered
`hm_tm`) location's own per-map script sets right before granting it, per
rom/npcgiftdata.py's own docstring (which documents the binary format
investigation and `TABLE` derivation this test file cross-checks).

Same two-layer structure as tests/test_local_item_substitution.py: a
synthetic-buffer layer that needs no real ROM, and a real-ROM cross-check
layer below "## Real ROM".
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
from rom import HeartGoldRom, eventscriptdata, npcgiftdata  # noqa: E402

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


def _npc_gift_shaped_keys(locations: dict) -> list[str]:
    """`npc_gift` locations plus the NPC-delivered half of `hm_tm` -- every
    key `npcgiftdata.TABLE` is expected to cover."""
    keys = []
    for key, loc in locations.items():
        if loc["type"] == "npc_gift":
            keys.append(key)
        elif loc["type"] == "hm_tm" and loc["id"] not in eventscriptdata.BLOCK_INDEX_BY_ITEMBALL_FLAG_ID:
            keys.append(key)
    return keys


# --- Binary format (no real ROM needed) --------------------------------------


def test_write_npc_gift_item_id_touches_only_the_target_site() -> None:
    """A synthetic 2-sub-file NARC standing in for scr_seq.narc (a plain
    duck-typed fake, since `write_npc_gift_item_id` only ever calls
    `rom.read_narc`/`rom.write_narc`): patching one `(narc_index, offset)`
    site must not perturb any other byte, in that sub-file or any other."""

    class FakeNarc:
        def __init__(self, files: dict[int, bytes]) -> None:
            self.files = files

    class FakeRom:
        def __init__(self, files: dict[int, bytes]) -> None:
            self._files = files
            self.written: FakeNarc | None = None

        def read_narc(self, path: str) -> FakeNarc:
            return FakeNarc(dict(self._files))

        def write_narc(self, path: str, narc: FakeNarc) -> None:
            self.written = narc

    original_files = {
        5: bytes(range(50, 70)),
        9: bytes(range(100, 140)),
    }
    fake_rom = FakeRom(original_files)

    npcgiftdata.write_npc_gift_item_id(fake_rom, 5, 10, 9999)

    patched = fake_rom.written.files
    assert patched[9] == original_files[9]
    assert struct.unpack_from("<H", patched[5], 10)[0] == 9999
    assert patched[5][:10] == original_files[5][:10]
    assert patched[5][12:] == original_files[5][12:]


def test_write_npc_gift_item_id_rejects_out_of_range_values() -> None:
    with pytest.raises(ValueError, match="0-65535"):
        npcgiftdata.write_npc_gift_item_id(object(), 0, 0, -1)
    with pytest.raises(ValueError, match="0-65535"):
        npcgiftdata.write_npc_gift_item_id(object(), 0, 0, 0x10000)


def test_table_has_no_duplicate_narc_offset_pairs() -> None:
    """Every `(narc_index, offset)` site should belong to exactly one
    location -- two locations claiming the same site would mean the
    derivation (see npcgiftdata.py's docstring) mixed something up."""
    seen: dict[tuple[int, int], str] = {}
    for location_key, sites in npcgiftdata.TABLE.items():
        for site in sites:
            assert site not in seen, (
                f"{site} claimed by both {seen.get(site)!r} and {location_key!r}"
            )
            seen[site] = location_key


# --- Real ROM cross-checks ----------------------------------------------------


def test_table_covers_every_npc_gift_shaped_location(rom: HeartGoldRom, generated_data: dict) -> None:
    locations = generated_data["LOCATIONS"]
    expected_keys = set(_npc_gift_shaped_keys(locations))
    assert expected_keys == set(npcgiftdata.TABLE.keys())


def test_real_rom_npc_gift_operands_match_vanilla_original_item(
    rom: HeartGoldRom, generated_data: dict
) -> None:
    """Cross-checks every `npc_gift`/NPC-delivered-`hm_tm` location's
    `TABLE` site(s) against the real ROM: each site's operand must equal
    `data/items.py[original_item]['id']` exactly."""
    locations = generated_data["LOCATIONS"]
    items = generated_data["ITEMS"]

    mismatches = []
    for location_key in _npc_gift_shaped_keys(locations):
        expected = items[locations[location_key]["original_item"]]["id"]
        for narc_index, offset in npcgiftdata.TABLE[location_key]:
            got = npcgiftdata.read_npc_gift_item_id(rom, narc_index, offset)
            if got != expected:
                mismatches.append((location_key, narc_index, offset, got, expected))
    assert mismatches == []


def test_write_npc_gift_substitution_leaves_other_locations_untouched(
    rom: HeartGoldRom, generated_data: dict
) -> None:
    locations = generated_data["LOCATIONS"]
    items = generated_data["ITEMS"]
    npc_keys = _npc_gift_shaped_keys(locations)

    before = {
        key: [npcgiftdata.read_npc_gift_item_id(rom, i, o) for i, o in npcgiftdata.TABLE[key]]
        for key in npc_keys
    }

    target_key = npc_keys[3]
    original_item_key = locations[target_key]["original_item"]
    new_item_key = "master_ball" if original_item_key != "master_ball" else "rare_candy"

    npcgiftdata.write_npc_gift_substitution(rom, target_key, new_item_key)

    for narc_index, offset in npcgiftdata.TABLE[target_key]:
        assert npcgiftdata.read_npc_gift_item_id(rom, narc_index, offset) == items[new_item_key]["id"]

    for key in npc_keys:
        if key == target_key:
            continue
        got = [npcgiftdata.read_npc_gift_item_id(rom, i, o) for i, o in npcgiftdata.TABLE[key]]
        assert got == before[key]


def test_write_npc_gift_substitution_rejects_non_npc_gift_location(rom: HeartGoldRom, generated_data: dict) -> None:
    locations = generated_data["LOCATIONS"]
    ground_key = next(key for key, loc in locations.items() if loc["type"] == "ground_item")
    with pytest.raises(npcgiftdata.NpcGiftDataError, match="npc_gift"):
        npcgiftdata.write_npc_gift_substitution(rom, ground_key, "master_ball")


def test_write_npc_gift_substitution_rejects_unknown_keys(rom: HeartGoldRom, generated_data: dict) -> None:
    locations = generated_data["LOCATIONS"]
    real_key = _npc_gift_shaped_keys(locations)[0]
    with pytest.raises(KeyError):
        npcgiftdata.write_npc_gift_substitution(rom, "not_a_real_location", "master_ball")
    with pytest.raises(KeyError):
        npcgiftdata.write_npc_gift_substitution(rom, real_key, "not_a_real_item")


def test_apply_local_item_substitutions_routes_npc_gift_and_hm_tm(
    rom: HeartGoldRom, generated_data: dict, tmp_path: Path
) -> None:
    """`patch_gen.apply_local_item_substitutions` routes each location to
    the right backend (ground_item/itemball-shaped hm_tm ->
    eventscriptdata, npc_gift/NPC-delivered hm_tm -> npcgiftdata) and
    round-trips through a saved+reloaded ROM."""
    locations = generated_data["LOCATIONS"]
    items = generated_data["ITEMS"]

    ground_key = next(key for key, loc in locations.items() if loc["type"] == "ground_item")
    npc_gift_key = next(key for key, loc in locations.items() if loc["type"] == "npc_gift")
    itemball_hm_tm_key = next(
        key
        for key, loc in locations.items()
        if loc["type"] == "hm_tm" and loc["id"] in eventscriptdata.BLOCK_INDEX_BY_ITEMBALL_FLAG_ID
    )
    npc_hm_tm_key = next(
        key
        for key, loc in locations.items()
        if loc["type"] == "hm_tm" and loc["id"] not in eventscriptdata.BLOCK_INDEX_BY_ITEMBALL_FLAG_ID
    )

    substitutions = {
        ground_key: "master_ball",
        npc_gift_key: "rare_candy",
        itemball_hm_tm_key: "full_restore",
        npc_hm_tm_key: "ultra_ball",
    }
    patch_gen.apply_local_item_substitutions(rom, substitutions)

    out_path = tmp_path / "heartgold_npc_gift_substitution_test.nds"
    rom.save(out_path)
    reloaded = HeartGoldRom.open(out_path, expect_vanilla=False)

    ground_block = eventscriptdata.BLOCK_INDEX_BY_ITEMBALL_FLAG_ID[locations[ground_key]["id"]]
    assert eventscriptdata.read_itemball_item_id(reloaded, ground_block) == items["master_ball"]["id"]

    for narc_index, offset in npcgiftdata.TABLE[npc_gift_key]:
        assert npcgiftdata.read_npc_gift_item_id(reloaded, narc_index, offset) == items["rare_candy"]["id"]

    hm_tm_block = eventscriptdata.BLOCK_INDEX_BY_ITEMBALL_FLAG_ID[locations[itemball_hm_tm_key]["id"]]
    assert eventscriptdata.read_itemball_item_id(reloaded, hm_tm_block) == items["full_restore"]["id"]

    for narc_index, offset in npcgiftdata.TABLE[npc_hm_tm_key]:
        assert npcgiftdata.read_npc_gift_item_id(reloaded, narc_index, offset) == items["ultra_ball"]["id"]


def test_all_npc_gift_shaped_locations_substitutable_without_crashing(
    rom: HeartGoldRom, generated_data: dict
) -> None:
    """Task's own requested format-limit check, mirrored from
    tests/test_local_item_substitution.py's ground_item equivalent."""
    locations = generated_data["LOCATIONS"]
    items = generated_data["ITEMS"]
    npc_keys = _npc_gift_shaped_keys(locations)
    dummy_item_key = "rare_candy"

    for key in npc_keys:
        npcgiftdata.write_npc_gift_substitution(rom, key, dummy_item_key)

    for key in npc_keys:
        for narc_index, offset in npcgiftdata.TABLE[key]:
            assert npcgiftdata.read_npc_gift_item_id(rom, narc_index, offset) == items[dummy_item_key]["id"]
