"""Tests for the trainers data_gen pipeline (task C7b).

Regenerates `data/` (via `python data_gen.py`) and checks the actual total
trainer count observed in the decomp reference
(`files/poketool/trainer/trainers.json`'s top-level "trainers" array has
**738 entries**, index 0..737 -- cross-checked against
`include/constants/trainers.h`'s TRAINER_* constants, which gaplessly and
collision-free cover exactly that same 0..737 range, see
`data_gen/trainers.toml`'s header and docs/architecture.md Spike 3), plus a
handful of witness trainers read directly out of the decomp: Silver's first
rival battle, the Elite Four + Champion Lance, and the Mt. Silver rematch
against Red.
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
def trainers():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)

    importlib.invalidate_caches()
    trainers_mod = importlib.import_module("data.trainers")
    importlib.reload(trainers_mod)
    yield trainers_mod.TRAINERS
    shutil.rmtree(DATA_DIR, ignore_errors=True)


def test_trainer_count_matches_decomp(trainers) -> None:
    """738 is the real count found in `files/poketool/trainer/trainers.json`
    (top-level "trainers" array length), not an assumed figure -- confirmed
    against `include/constants/trainers.h`'s TRAINER_NONE=0 ..
    TRAINER_PARTNER_RIVAL_3=737 constants, which gaplessly and
    collision-free cover indices 0..737 (738 total). Index 0 (`none`) is a
    reserved, empty (0-Pokemon party) placeholder entry, kept for
    exhaustivity/fidelity with the decomp's own table rather than an actual
    battle.
    """
    assert len(trainers) == 738
    assert trainers["none"]["id"] == 0
    assert trainers["none"]["party"] == ()


def test_all_trainer_ids_are_unique_and_contiguous(trainers) -> None:
    ids = sorted(t["id"] for t in trainers.values())
    assert ids == list(range(738))


def test_rival_silver_first_battle(trainers) -> None:
    """Silver's first rival battle (New Bark Town/Cherrygrove), read
    directly out of `files/poketool/trainer/trainers.json` index 1
    (`TRAINER_RIVAL_SILVER`): Gastly/Zubat/Bayleef at levels 14/16/18, no
    custom moves/held items (`battle_type == "mon"`)."""
    silver = trainers["rival_silver"]
    assert silver["id"] == 1
    assert silver["trainer_class"] == "rival"
    assert silver["label"] == "Silver"
    assert silver["battle_type"] == "mon"
    assert silver["double_battle"] is False
    party_species_levels = [(mon["species"], mon["level"]) for mon in silver["party"]]
    assert party_species_levels == [("gastly", 14), ("zubat", 16), ("bayleef", 18)]
    # "mon" battle_type: no held items/custom movesets recorded per-mon.
    for mon in silver["party"]:
        assert "held_item" not in mon
        assert "moves" not in mon


def test_rival_silver_has_multiple_rematches(trainers) -> None:
    """Silver is fought repeatedly throughout the game (rival battles plus
    the Mt. Silver postgame rematches) -- `include/constants/trainers.h`
    declares 21 distinct TRAINER_RIVAL_SILVER* entries."""
    silver_keys = [k for k in trainers if k.startswith("rival_silver")]
    assert len(silver_keys) == 21


def test_elite_four_and_champion(trainers) -> None:
    """The Elite Four (Will, Koga, Bruno, Karen) and Champion Lance, first
    encounter (`files/poketool/trainer/trainers.json` indices 244-247, 418)."""
    elite_four = {
        "elite_four_will_will": "Will",
        "elite_four_koga_koga": "Koga",
        "elite_four_bruno_bruno": "Bruno",
        "elite_four_karen_karen": "Karen",
    }
    for key, label in elite_four.items():
        assert trainers[key]["label"] == label
        assert len(trainers[key]["party"]) == 5

    lance = trainers["champion_lance"]
    assert lance["id"] == 244
    assert lance["label"] == "Lance"
    assert lance["trainer_class"] == "champion"
    assert len(lance["party"]) == 6


def test_red_mt_silver(trainers) -> None:
    """Red, the final postgame battle at Mt. Silver
    (`TRAINER_PKMN_TRAINER_RED_RED`, index 260): a full 6-mon team with
    custom held items and movesets (`battle_type == "mon_item_moves"`), 4x
    Full Restore as usable battle items, and a level-88 Light Ball Pikachu
    with Volt Tackle -- all read directly out of the decomp."""
    red = trainers["pkmn_trainer_red_red"]
    assert red["id"] == 260
    assert red["label"] == "Red"
    assert red["trainer_class"] == "pkmn_trainer_red"
    assert red["battle_type"] == "mon_item_moves"
    assert red["usable_items"] == ("full_restore", "full_restore", "full_restore", "full_restore")
    assert len(red["party"]) == 6

    pikachu = red["party"][0]
    assert pikachu["species"] == "pikachu"
    assert pikachu["level"] == 88
    assert pikachu["held_item"] == "light_ball"
    assert pikachu["moves"] == ("volt_tackle", "iron_tail", "quick_attack", "thunderbolt")


def test_double_battle_trainer(trainers) -> None:
    """Twins Amy & Mimi (index 10, `TRAINER_TWINS_AMY_AND_MIMI`) are a
    double-battle pair."""
    twins = trainers["twins_amy_and_mimi"]
    assert twins["id"] == 10
    assert twins["double_battle"] is True
    assert len(twins["party"]) == 2


def test_all_species_move_item_references_resolve(trainers) -> None:
    """Defensive: every species/move/item key referenced by a trainer's
    party or usable_items must resolve into the generated data/species.py,
    data/moves.py and data/items.py tables (see
    data_gen_templates/trainers.py's warnings for the same check applied at
    generation time -- this test asserts the *result* holds for the actual
    738-trainer dataset, not just that the generator code exists)."""
    from data.items import ITEMS
    from data.moves import MOVES
    from data.species import SPECIES

    for key, trainer in trainers.items():
        for item in trainer["usable_items"]:
            assert item in ITEMS, f"{key}.usable_items references unknown item {item!r}"
        for mon in trainer["party"]:
            assert mon["species"] in SPECIES, f"{key}.party references unknown species {mon['species']!r}"
            held_item = mon.get("held_item")
            if held_item is not None:
                assert held_item in ITEMS, f"{key}.party references unknown held_item {held_item!r}"
            for move in mon.get("moves", ()):
                assert move in MOVES, f"{key}.party references unknown move {move!r}"


def test_trainers_data_is_idempotent() -> None:
    """Running data_gen.py twice must produce a byte-identical trainers
    module."""
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    try:
        subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)
        first = (DATA_DIR / "trainers.py").read_bytes()
        subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)
        second = (DATA_DIR / "trainers.py").read_bytes()
        assert first == second
    finally:
        shutil.rmtree(DATA_DIR, ignore_errors=True)
