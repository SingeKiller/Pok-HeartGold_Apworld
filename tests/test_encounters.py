"""Tests for the wild-encounter data_gen pipeline (task C7a).

Regenerates `data/` (via `python data_gen.py`) and checks the actual zone
count observed from the decomp extraction (137 zones -- see
`data_gen/encounters.toml`'s header for the full methodology: 146 distinct
map codes across `gs_enc_data.json` (142 entries) + `headbutt.json` (4
headbutt-only maps), of which 9 do not resolve to a `data_gen/regions.toml`
region and are deliberately dropped: D47/D47R0102 (Safari Zone, out of v1
scope) and 7 genuinely-dead all-zero-rate placeholders (UNUSED_045/047/049/
050/064/138, and bare id "090")), plus a handful of witness zones read
directly out of the decomp.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


@pytest.fixture(scope="module")
def encounters():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)

    importlib.invalidate_caches()
    encounters_mod = importlib.import_module("data.encounters")
    importlib.reload(encounters_mod)
    yield encounters_mod.ENCOUNTERS
    shutil.rmtree(DATA_DIR, ignore_errors=True)


def test_zone_count_matches_extraction(encounters) -> None:
    """137 is the actual number of `data_gen/encounters.toml` zones that
    resolve to a `data_gen/regions.toml` region, not a guessed figure (see
    this module's docstring and data_gen/encounters.toml's header)."""
    assert len(encounters) == 137


def test_every_zone_has_all_tables(encounters) -> None:
    for key, zone in encounters.items():
        assert zone["map_code"], f"{key} is missing its map_code"
        assert "rate" in zone["land"] and "slots" in zone["land"]
        assert "rate" in zone["surf"] and "slots" in zone["surf"]
        assert "rate" in zone["rock_smash"] and "slots" in zone["rock_smash"]
        for rod in ("old_rod", "good_rod", "super_rod"):
            fishing = zone["fishing"][rod]
            assert "rate" in fishing and "slots" in fishing


def test_headbutt_present_for_59_zones(encounters) -> None:
    """59 (of 137) zones have a `headbutt` sub-table: 60 non-empty tables in
    headbutt.json minus D47 (Safari Zone, unresolved -- see
    data_gen/encounters.toml's header)."""
    zones_with_headbutt = [k for k, z in encounters.items() if "headbutt" in z]
    assert len(zones_with_headbutt) == 59
    for key in zones_with_headbutt:
        headbutt = encounters[key]["headbutt"]
        assert set(headbutt) == {"common", "rare", "secret"}


def test_route_29_land_witness(encounters) -> None:
    """Route 29 (map code R29) has a time-of-day-dependent land table:
    Pidgey/Sentret by day, swapped for Hoothoot at night on some slots --
    decomp-verified against gs_enc_data.json."""
    route_29 = encounters["route_29"]
    assert route_29["map_code"] == "R29"
    land = route_29["land"]
    assert land["rate"] == 25
    assert len(land["slots"]) == 12
    first = land["slots"][0]
    assert first == {"level": 2, "morn": "pidgey", "day": "pidgey", "nite": "hoothoot"}


def test_lake_of_rage_surf_witness(encounters) -> None:
    """Lake of Rage (map code T29) has a surf table with Magikarp and
    Gyarados -- decomp-verified against gs_enc_data.json."""
    lake_of_rage = encounters["lake_of_rage"]
    assert lake_of_rage["map_code"] == "T29"
    surf = lake_of_rage["surf"]
    assert surf["rate"] == 10
    species_seen = {slot["species"] for slot in surf["slots"]}
    assert species_seen == {"magikarp", "gyarados"}


def test_whirl_islands_surf_witness(encounters) -> None:
    """Whirl Islands 1F (map code D40R0101) has a surf table -- decomp-
    verified against gs_enc_data.json."""
    whirl_islands = encounters["whirl_islands_1f"]
    assert whirl_islands["map_code"] == "D40R0101"
    surf = whirl_islands["surf"]
    assert surf["rate"] == 10
    assert len(surf["slots"]) > 0
    for slot in surf["slots"]:
        assert slot["species"]


def test_new_bark_headbutt_witness(encounters) -> None:
    """New Bark Town (map code T20) has no gs_enc_data.json grass table
    (rate 0) but does have a headbutt tree table with Hoothoot/Pineco/
    Exeggcute (common) and rarer Spinarak alternates -- decomp-verified
    against headbutt.json."""
    new_bark = encounters["new_bark"]
    assert new_bark["map_code"] == "T20"
    assert new_bark["land"]["rate"] == 0
    headbutt = new_bark["headbutt"]
    common_species = {slot["species"] for slot in headbutt["common"]}
    assert "hoothoot" in common_species
    assert "pineco" in common_species


def test_all_species_are_known(encounters) -> None:
    """Every species key referenced anywhere in ENCOUNTERS must resolve in
    data/species.py -- data_gen_templates/encounters.py only warns (it does
    not drop or crash) on an unknown reference, so this test is the actual
    enforcement that the extraction/species-key mapping is correct."""
    from data.species import SPECIES

    species_keys = set(SPECIES)
    for key, zone in encounters.items():
        for slot in zone["land"]["slots"]:
            for tod in ("morn", "day", "nite"):
                assert slot[tod] in species_keys, f"{key}.land: unknown species {slot[tod]!r}"
        for table_name in ("surf", "rock_smash"):
            for slot in zone[table_name]["slots"]:
                assert slot["species"] in species_keys, (
                    f"{key}.{table_name}: unknown species {slot['species']!r}"
                )
        for rod in ("old_rod", "good_rod", "super_rod"):
            for slot in zone["fishing"][rod]["slots"]:
                assert slot["species"] in species_keys, (
                    f"{key}.fishing.{rod}: unknown species {slot['species']!r}"
                )
        headbutt = zone.get("headbutt")
        if headbutt is not None:
            for slot_kind in ("common", "rare", "secret"):
                for slot in headbutt[slot_kind]:
                    assert slot["species"] in species_keys, (
                        f"{key}.headbutt.{slot_kind}: unknown species {slot['species']!r}"
                    )


def test_every_zone_key_is_a_known_region(encounters) -> None:
    """Every ENCOUNTERS key must resolve in data/regions.py -- confirms the
    map-code -> region resolution documented in data_gen/encounters.toml's
    header actually landed cleanly for all 137 zones."""
    from data.regions import REGIONS

    region_keys = set(REGIONS)
    for key in encounters:
        assert key in region_keys, f"{key} is not a known region"


def test_encounters_are_idempotent() -> None:
    """Running data_gen.py twice must produce a byte-identical encounters
    module."""
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    try:
        subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)
        first = (DATA_DIR / "encounters.py").read_bytes()
        subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)
        second = (DATA_DIR / "encounters.py").read_bytes()
        assert first == second
    finally:
        shutil.rmtree(DATA_DIR, ignore_errors=True)
