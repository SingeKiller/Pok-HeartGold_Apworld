"""Tests for the species/moves data_gen pipeline (task C2).

Regenerates `data/` (via `python data_gen.py`) and checks a handful of
witness species against values read directly out of the decomp reference
(`ressources/Decomposition/pokeheartgold`, see the extraction notes at the
top of `data_gen/species.toml`), plus the actual total species/move counts
observed there -- not a memorized/assumed figure.
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
def species_and_moves():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)

    importlib.invalidate_caches()
    species_mod = importlib.import_module("data.species")
    moves_mod = importlib.import_module("data.moves")
    importlib.reload(species_mod)
    importlib.reload(moves_mod)
    yield species_mod.SPECIES, moves_mod.MOVES
    shutil.rmtree(DATA_DIR, ignore_errors=True)


def test_species_and_move_counts_match_decomp(species_and_moves) -> None:
    """The decomp (include/constants/species.h, personal.json) declares 493
    national-dex species (Bulbasaur..Arceus, national_dex 1-493) plus 12
    HGSS-relevant alternate forms with their own base-stats/learnset rows
    (Deoxys x3, Wormadam x2, Giratina Origin, Shaymin Sky, Rotom x5) -- 505
    species entries total. This is the actual figure found in the decomp,
    not the 493 the task brief floated as a starting assumption.

    include/constants/moves.h declares 467 moves (MOVE_POUND..MOVE_SHADOW_FORCE)
    with no gaps -- unlike the ITEM_EXPLORER_KIT gap found for items in Spike 3,
    every declared move constant has a matching files/poketool/waza/waza_tbl.narc
    stats row.
    """
    species, moves = species_and_moves
    assert len(species) == 505
    assert len(moves) == 467

    national_dex_species = [s for s in species.values() if s["national_dex"] is not None]
    assert len(national_dex_species) == 493

    alternate_forms = [
        "deoxys_atk", "deoxys_def", "deoxys_spd",
        "wormadam_sandy", "wormadam_trash",
        "giratina_origin", "shaymin_sky",
        "rotom_heat", "rotom_wash", "rotom_frost", "rotom_fan", "rotom_mow",
    ]
    for key in alternate_forms:
        assert key in species, f"missing expected alternate form {key!r}"
        assert species[key]["national_dex"] is None


def test_chikorita(species_and_moves) -> None:
    species, _moves = species_and_moves
    chikorita = species["chikorita"]
    assert chikorita["id"] == 152
    assert chikorita["national_dex"] == 152
    assert chikorita["types"] == ("grass",)
    assert chikorita["base_stats"] == {
        "hp": 45, "atk": 49, "def": 65, "spatk": 49, "spdef": 65, "speed": 45,
    }
    assert chikorita["catch_rate"] == 45
    assert chikorita["evolutions"] == (
        {"method": "level", "target": "bayleef", "param": 16},
    )


def test_eevee(species_and_moves) -> None:
    species, _moves = species_and_moves
    eevee = species["eevee"]
    assert eevee["id"] == 133
    assert eevee["national_dex"] == 133
    assert eevee["types"] == ("normal",)
    assert eevee["base_stats"] == {
        "hp": 55, "atk": 55, "def": 50, "spatk": 45, "spdef": 65, "speed": 55,
    }
    assert eevee["catch_rate"] == 45
    # Multi-branch evolution: Eevee has 7 possible evolutions in HGSS.
    targets = {evo["target"] for evo in eevee["evolutions"]}
    assert targets == {
        "vaporeon", "jolteon", "flareon", "espeon", "umbreon", "leafeon", "glaceon",
    }


def test_ho_oh(species_and_moves) -> None:
    species, _moves = species_and_moves
    ho_oh = species["ho_oh"]
    assert ho_oh["id"] == 250
    assert ho_oh["national_dex"] == 250
    assert ho_oh["types"] == ("fire", "flying")
    assert ho_oh["base_stats"] == {
        "hp": 106, "atk": 130, "def": 90, "spatk": 110, "spdef": 154, "speed": 90,
    }
    assert ho_oh["catch_rate"] == 3
    assert ho_oh["evolutions"] == ()


def test_magikarp(species_and_moves) -> None:
    species, _moves = species_and_moves
    magikarp = species["magikarp"]
    assert magikarp["id"] == 129
    assert magikarp["national_dex"] == 129
    assert magikarp["types"] == ("water",)
    assert magikarp["base_stats"] == {
        "hp": 20, "atk": 10, "def": 55, "spatk": 15, "spdef": 20, "speed": 80,
    }
    assert magikarp["catch_rate"] == 255
    assert magikarp["evolutions"] == (
        {"method": "level", "target": "gyarados", "param": 20},
    )


def test_absol(species_and_moves) -> None:
    """Ténéfix (FR) = Absol."""
    species, _moves = species_and_moves
    absol = species["absol"]
    assert absol["id"] == 359
    assert absol["national_dex"] == 359
    assert absol["types"] == ("dark",)
    assert absol["base_stats"] == {
        "hp": 65, "atk": 130, "def": 60, "spatk": 75, "spdef": 60, "speed": 75,
    }
    assert absol["catch_rate"] == 30
    assert absol["evolutions"] == ()


def test_move_pound(species_and_moves) -> None:
    _species, moves = species_and_moves
    pound = moves["pound"]
    assert pound == {
        "id": 1,
        "label": "POUND",
        "type": "normal",
        "category": "physical",
        "power": 40,
        "accuracy": 100,
        "pp": 35,
    }


def test_species_data_is_idempotent() -> None:
    """Running data_gen.py twice must produce byte-identical species/moves modules."""
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    try:
        subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)
        first = (DATA_DIR / "species.py").read_bytes(), (DATA_DIR / "moves.py").read_bytes()
        subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)
        second = (DATA_DIR / "species.py").read_bytes(), (DATA_DIR / "moves.py").read_bytes()
        assert first == second
    finally:
        shutil.rmtree(DATA_DIR, ignore_errors=True)
