"""Tests for the ROM access layer (task C13): rom/__init__.py's
`HeartGoldRom` (opening + validating a ROM, raw NitroFS read/write, save)
and the category submodules built on top of it (rom/itemdata.py,
rom/speciesdata.py, rom/trainerdata.py, rom/encounterdata.py,
rom/eventdata.py).

The ROM-opening validation tests (`test_open_rejects_*`) use small
synthetic byte strings and need no real ROM, so they always run. Every
other test needs the real HeartGold (US) ROM and follows the same
"skip cleanly if HEARTGOLD_ROM_PATH is unset/invalid" pattern as
tests/test_rom_roundtrip.py -- see that file's own docstring for why (the
ROM is a legally-dumped, user-supplied file never committed to this repo).

Tests that cross-check a ROM table's entry count against a `data/*.py`
table (task C13's own acceptance criterion: "le nombre d'items lu depuis
le ROM doit correspondre aux 513 de data/items.py") regenerate `data/` via
`python data_gen.py`, the same subprocess-based fixture pattern
tests/test_items.py/tests/test_data_gen.py already use.
"""

from __future__ import annotations

import hashlib
import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ndspy_narc = pytest.importorskip("ndspy.narc")

from rom import (  # noqa: E402
    HEARTGOLD_US_MD5,
    HeartGoldRom,
    InvalidRomError,
    NitroFsFileNotFoundError,
    encounterdata,
    eventdata,
    itemdata,
    speciesdata,
    trainerdata,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

ROM_PATH_ENV_VAR = "HEARTGOLD_ROM_PATH"

# Same arbitrary, well-known sample used by tests/test_rom_roundtrip.py.
SAMPLE_NITROFS_PATH = "pbr/item_data.narc"


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
    """Regenerate `data/` once for every test in this module that needs to
    cross-check a ROM table's entry count against it (see this file's own
    docstring)."""
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)

    importlib.invalidate_caches()
    items_mod = importlib.reload(importlib.import_module("data.items"))
    species_mod = importlib.reload(importlib.import_module("data.species"))
    trainers_mod = importlib.reload(importlib.import_module("data.trainers"))
    encounters_mod = importlib.reload(importlib.import_module("data.encounters"))
    yield {
        "ITEMS": items_mod.ITEMS,
        "SPECIES": species_mod.SPECIES,
        "TRAINERS": trainers_mod.TRAINERS,
        "ENCOUNTERS": encounters_mod.ENCOUNTERS,
    }
    shutil.rmtree(DATA_DIR, ignore_errors=True)


# --- Opening/validating a ROM (no real ROM file needed) ---------------------


def test_open_rejects_truncated_file() -> None:
    with pytest.raises(InvalidRomError, match="too small"):
        HeartGoldRom(b"\x00" * 16)


def test_open_rejects_wrong_hash() -> None:
    garbage = b"\x00" * 0x8000
    assert hashlib.md5(garbage).hexdigest() != HEARTGOLD_US_MD5
    with pytest.raises(InvalidRomError, match="MD5"):
        HeartGoldRom(garbage)


# --- Opening the real ROM ----------------------------------------------------


def test_open_real_rom(rom_bytes: bytes) -> None:
    assert hashlib.md5(rom_bytes).hexdigest() == HEARTGOLD_US_MD5
    heartgold_rom = HeartGoldRom(rom_bytes)
    assert bytes(heartgold_rom._rom.idCode) == b"IPKE"


def test_read_unknown_path_raises_clear_error(rom: HeartGoldRom) -> None:
    with pytest.raises(NitroFsFileNotFoundError, match="not/a/real/path"):
        rom.read_file("not/a/real/path")


# --- Raw NitroFS read/write/save round-trip ----------------------------------


def test_read_known_nitrofs_files(rom: HeartGoldRom) -> None:
    sample = rom.read_file(SAMPLE_NITROFS_PATH)
    assert len(sample) > 0

    item_table = rom.read_narc(itemdata.NITROFS_PATH)
    assert len(item_table.files) == itemdata.EXPECTED_ENTRY_COUNT

    species_table = rom.read_narc(speciesdata.NITROFS_PATH)
    assert len(species_table.files) == speciesdata.EXPECTED_ENTRY_COUNT

    trainer_stats_table = rom.read_narc(trainerdata.STATS_NITROFS_PATH)
    assert len(trainer_stats_table.files) == trainerdata.EXPECTED_ENTRY_COUNT


def test_write_file_then_reread_reflects_modification(rom: HeartGoldRom) -> None:
    original = rom.read_file(SAMPLE_NITROFS_PATH)
    modified = bytes([original[0] ^ 0xFF]) + original[1:]
    assert modified != original

    rom.write_file(SAMPLE_NITROFS_PATH, modified)
    assert rom.read_file(SAMPLE_NITROFS_PATH) == modified

    rebuilt = HeartGoldRom(rom.save_bytes(), expect_vanilla=False)
    assert rebuilt.read_file(SAMPLE_NITROFS_PATH) == modified
    assert rebuilt.read_file(SAMPLE_NITROFS_PATH) != original


# --- Category submodules: read/write/save round-trip -------------------------


def test_itemdata_write_entry_roundtrips(rom: HeartGoldRom) -> None:
    entries = itemdata.read_all(rom)
    original_entry = entries[1]
    modified_entry = bytes([original_entry[0] ^ 0xFF]) + original_entry[1:]

    itemdata.write_entry(rom, 1, modified_entry)
    assert itemdata.read_entry(rom, 1) == modified_entry

    rebuilt = HeartGoldRom(rom.save_bytes(), expect_vanilla=False)
    assert itemdata.read_entry(rebuilt, 1) == modified_entry
    assert itemdata.read_entry(rebuilt, 0) == entries[0]


def test_speciesdata_write_entry_roundtrips(rom: HeartGoldRom) -> None:
    entries = speciesdata.read_all(rom)
    original_entry = entries[1]
    modified_entry = bytes([original_entry[0] ^ 0xFF]) + original_entry[1:]

    speciesdata.write_entry(rom, 1, modified_entry)
    assert speciesdata.read_entry(rom, 1) == modified_entry

    rebuilt = HeartGoldRom(rom.save_bytes(), expect_vanilla=False)
    assert speciesdata.read_entry(rebuilt, 1) == modified_entry


def test_trainerdata_write_entry_roundtrips(rom: HeartGoldRom) -> None:
    original_stats = trainerdata.read_stats_entry(rom, 5)
    modified_stats = bytes([original_stats[0] ^ 0xFF]) + original_stats[1:]
    trainerdata.write_stats_entry(rom, 5, modified_stats)
    assert trainerdata.read_stats_entry(rom, 5) == modified_stats

    original_party = trainerdata.read_party_entry(rom, 5)
    modified_party = bytes([original_party[0] ^ 0xFF]) + original_party[1:]
    trainerdata.write_party_entry(rom, 5, modified_party)
    assert trainerdata.read_party_entry(rom, 5) == modified_party

    rebuilt = HeartGoldRom(rom.save_bytes(), expect_vanilla=False)
    assert trainerdata.read_stats_entry(rebuilt, 5) == modified_stats
    assert trainerdata.read_party_entry(rebuilt, 5) == modified_party


def test_encounterdata_write_entry_roundtrips(rom: HeartGoldRom) -> None:
    original_entry = encounterdata.read_entry(rom, 0)
    modified_entry = bytes([original_entry[0] ^ 0xFF]) + original_entry[1:]
    encounterdata.write_entry(rom, 0, modified_entry)
    assert encounterdata.read_entry(rom, 0) == modified_entry

    rebuilt = HeartGoldRom(rom.save_bytes(), expect_vanilla=False)
    assert encounterdata.read_entry(rebuilt, 0) == modified_entry


def test_eventdata_is_readable(rom: HeartGoldRom) -> None:
    entries = eventdata.read_all(rom)
    assert len(entries) == eventdata.EXPECTED_ENTRY_COUNT
    assert all(isinstance(entry, bytes) for entry in entries)


def test_write_all_rejects_wrong_entry_count(rom: HeartGoldRom) -> None:
    entries = itemdata.read_all(rom)
    with pytest.raises(ValueError, match="entry count must match"):
        itemdata.write_all(rom, entries[:-1])


# --- Cross-checks against data/*.py (regenerated via data_gen.py) -----------


def test_item_table_count_matches_data_items(rom: HeartGoldRom, generated_data) -> None:
    """Task C13's own acceptance criterion: the item table read from the
    ROM must correspond to the 513 real items in data/items.py (the 514th
    NARC sub-file is the ITEM_NONE placeholder, index 0 -- excluded from
    data/items.py, see data_gen/items.toml's header)."""
    entries = itemdata.read_all(rom)
    assert len(entries) - 1 == len(generated_data["ITEMS"]) == 513


def test_species_table_covers_data_species(rom: HeartGoldRom, generated_data) -> None:
    """See rom/speciesdata.py's own docstring for why this is a >=, not an
    exact match: the real NARC has a few extra engine-reserved slots not
    modeled in data/species.py."""
    entries = speciesdata.read_all(rom)
    assert len(entries) >= len(generated_data["SPECIES"]) == 505


def test_trainer_tables_match_data_trainers(rom: HeartGoldRom, generated_data) -> None:
    assert len(trainerdata.read_all_stats(rom)) == len(generated_data["TRAINERS"]) == 738
    assert len(trainerdata.read_all_parties(rom)) == len(generated_data["TRAINERS"]) == 738


def test_encounter_table_covers_data_encounters(rom: HeartGoldRom, generated_data) -> None:
    """See rom/encounterdata.py's own docstring for why this is a >=, not
    an exact match: some maps were filtered out of data/encounters.py
    during data_gen extraction."""
    entries = encounterdata.read_all(rom)
    assert len(entries) >= len(generated_data["ENCOUNTERS"]) == 137
