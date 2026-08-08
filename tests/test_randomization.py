"""Tests for the randomization logic (task C11): `species.py` at the repo
root -- the randomizer, not `data/species.py` (the generated data it
randomizes; also loaded here, read-only, as its input).

The single most important property tested here (see this task's brief): two
runs seeded with the exact same `random.Random` seed must produce a
byte-for-byte (here: `==`) identical result -- Archipelago's own determinism
guarantee (same seed => same multiworld) depends on every world's
randomization logic upholding this. Also checks that randomizing actually
changes something versus the vanilla `data/*.py` tables (not an accidental
no-op), and that every randomized species/move reference still resolves in
`data/species.py`/`data/moves.py`.
"""

from __future__ import annotations

import collections
import importlib
import shutil
import subprocess
import sys
from pathlib import Path
from random import Random

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_MODULES = ("data.species", "data.moves", "data.trainers", "data.encounters", "species")


@pytest.fixture(scope="module")
def randomization_modules():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)

    importlib.invalidate_caches()
    modules = {}
    # Import order matters: `species` (root) imports `data.species`/
    # `data.trainers`/`data.encounters` -- reload those first so `species`
    # (root) doesn't end up bound to stale module objects.
    for name in _MODULES:
        if name in sys.modules:
            modules[name] = importlib.reload(sys.modules[name])
        else:
            modules[name] = importlib.import_module(name)
    yield modules
    shutil.rmtree(DATA_DIR, ignore_errors=True)


@pytest.fixture()
def species_logic(randomization_modules):
    return randomization_modules["species"]


@pytest.fixture()
def species_data(randomization_modules):
    return randomization_modules["data.species"].SPECIES


@pytest.fixture()
def moves_data(randomization_modules):
    return randomization_modules["data.moves"].MOVES


@pytest.fixture()
def trainers_data(randomization_modules):
    return randomization_modules["data.trainers"].TRAINERS


@pytest.fixture()
def encounters_data(randomization_modules):
    return randomization_modules["data.encounters"].ENCOUNTERS


# --- 1. Starters -------------------------------------------------------------


def test_starters_are_deterministic(species_logic, species_data) -> None:
    first = species_logic.randomize_starters(Random(12345), True, species_data)
    second = species_logic.randomize_starters(Random(12345), True, species_data)
    assert first == second


def test_starters_disabled_returns_vanilla(species_logic, species_data) -> None:
    result = species_logic.randomize_starters(Random(1), False, species_data)
    assert result == species_logic.VANILLA_STARTERS == ("chikorita", "cyndaquil", "totodile")


def test_starters_change_from_vanilla(species_logic, species_data) -> None:
    result = species_logic.randomize_starters(Random(999), True, species_data)
    assert result != species_logic.VANILLA_STARTERS


def test_starters_reference_real_distinct_species(species_logic, species_data) -> None:
    result = species_logic.randomize_starters(Random(42), True, species_data)
    assert len(result) == 3
    assert len(set(result)) == 3
    for key in result:
        assert key in species_data
        assert species_data[key]["national_dex"] is not None


# --- 2. Wild encounters --------------------------------------------------------


def _flatten_encounter_species(encounters: dict) -> list[str]:
    values: list[str] = []
    for zone in encounters.values():
        for slot in zone["land"]["slots"]:
            values.extend(slot[time_of_day] for time_of_day in ("morn", "day", "nite"))
        for table_name in ("surf", "rock_smash"):
            values.extend(slot["species"] for slot in zone[table_name]["slots"])
        for rod in ("old_rod", "good_rod", "super_rod"):
            values.extend(slot["species"] for slot in zone["fishing"][rod]["slots"])
        if "headbutt" in zone:
            for tier in ("common", "rare", "secret"):
                values.extend(slot["species"] for slot in zone["headbutt"][tier])
    return values


def test_wild_encounters_vanilla_is_noop(species_logic, encounters_data, species_data) -> None:
    result = species_logic.randomize_wild_encounters(
        Random(1), species_logic.WILD_VANILLA, encounters_data, species_data
    )
    assert result is encounters_data


def test_wild_encounters_shuffle_is_deterministic(species_logic, encounters_data, species_data) -> None:
    first = species_logic.randomize_wild_encounters(
        Random(7), species_logic.WILD_SHUFFLE, encounters_data, species_data
    )
    second = species_logic.randomize_wild_encounters(
        Random(7), species_logic.WILD_SHUFFLE, encounters_data, species_data
    )
    assert first == second


def test_wild_encounters_full_random_is_deterministic(species_logic, encounters_data, species_data) -> None:
    first = species_logic.randomize_wild_encounters(
        Random(31), species_logic.WILD_FULL_RANDOM, encounters_data, species_data
    )
    second = species_logic.randomize_wild_encounters(
        Random(31), species_logic.WILD_FULL_RANDOM, encounters_data, species_data
    )
    assert first == second


def test_wild_encounters_shuffle_changes_something(species_logic, encounters_data, species_data) -> None:
    result = species_logic.randomize_wild_encounters(
        Random(123), species_logic.WILD_SHUFFLE, encounters_data, species_data
    )
    assert result != encounters_data


def test_wild_encounters_full_random_changes_something(species_logic, encounters_data, species_data) -> None:
    result = species_logic.randomize_wild_encounters(
        Random(123), species_logic.WILD_FULL_RANDOM, encounters_data, species_data
    )
    assert result != encounters_data


def test_wild_encounters_shuffle_preserves_species_multiset(species_logic, encounters_data, species_data) -> None:
    """Shuffle mode is a true permutation: the exact same species appear
    the exact same number of times overall, just moved to different slots."""
    result = species_logic.randomize_wild_encounters(
        Random(55), species_logic.WILD_SHUFFLE, encounters_data, species_data
    )
    assert collections.Counter(_flatten_encounter_species(result)) == collections.Counter(
        _flatten_encounter_species(encounters_data)
    )


def test_wild_encounters_shapes_are_preserved(species_logic, encounters_data, species_data) -> None:
    result = species_logic.randomize_wild_encounters(
        Random(3), species_logic.WILD_FULL_RANDOM, encounters_data, species_data
    )
    assert set(result) == set(encounters_data)
    for key, zone in encounters_data.items():
        randomized_zone = result[key]
        assert randomized_zone["map_code"] == zone["map_code"]
        assert randomized_zone["land"]["rate"] == zone["land"]["rate"]
        assert len(randomized_zone["land"]["slots"]) == len(zone["land"]["slots"])
        for table_name in ("surf", "rock_smash"):
            assert randomized_zone[table_name]["rate"] == zone[table_name]["rate"]
            assert len(randomized_zone[table_name]["slots"]) == len(zone[table_name]["slots"])
        for rod in ("old_rod", "good_rod", "super_rod"):
            assert randomized_zone["fishing"][rod]["rate"] == zone["fishing"][rod]["rate"]
            assert len(randomized_zone["fishing"][rod]["slots"]) == len(zone["fishing"][rod]["slots"])
        assert ("headbutt" in randomized_zone) == ("headbutt" in zone)
        if "headbutt" in zone:
            for tier in ("common", "rare", "secret"):
                assert len(randomized_zone["headbutt"][tier]) == len(zone["headbutt"][tier])


def test_wild_encounters_reference_real_species(species_logic, encounters_data, species_data) -> None:
    result = species_logic.randomize_wild_encounters(
        Random(11), species_logic.WILD_FULL_RANDOM, encounters_data, species_data
    )
    pool = set(species_logic.real_species_pool(species_data))
    for key in _flatten_encounter_species(result):
        assert key in pool
        assert key in species_data


# --- 3. Trainer parties --------------------------------------------------------


def test_trainer_parties_disabled_is_noop(species_logic, trainers_data, species_data) -> None:
    result = species_logic.randomize_trainer_parties(Random(1), False, trainers_data, species_data)
    assert result is trainers_data


def test_trainer_parties_are_deterministic(species_logic, trainers_data, species_data) -> None:
    first = species_logic.randomize_trainer_parties(Random(2024), True, trainers_data, species_data)
    second = species_logic.randomize_trainer_parties(Random(2024), True, trainers_data, species_data)
    assert first == second


def test_trainer_parties_change_from_vanilla(species_logic, trainers_data, species_data) -> None:
    result = species_logic.randomize_trainer_parties(Random(8), True, trainers_data, species_data)
    assert result != trainers_data


def test_trainer_parties_preserve_non_species_fields(species_logic, trainers_data, species_data) -> None:
    result = species_logic.randomize_trainer_parties(Random(4), True, trainers_data, species_data)

    silver = result["rival_silver"]
    vanilla_silver = trainers_data["rival_silver"]
    assert len(silver["party"]) == len(vanilla_silver["party"])
    assert [mon["level"] for mon in silver["party"]] == [mon["level"] for mon in vanilla_silver["party"]]

    red = result["pkmn_trainer_red_red"]
    vanilla_red = trainers_data["pkmn_trainer_red_red"]
    assert [mon.get("moves") for mon in red["party"]] == [mon.get("moves") for mon in vanilla_red["party"]]
    assert [mon.get("held_item") for mon in red["party"]] == [mon.get("held_item") for mon in vanilla_red["party"]]
    assert red["usable_items"] == vanilla_red["usable_items"]

    assert result["none"]["party"] == () == trainers_data["none"]["party"]


def test_trainer_parties_reference_real_species(species_logic, trainers_data, species_data) -> None:
    result = species_logic.randomize_trainer_parties(Random(6), True, trainers_data, species_data)
    pool = set(species_logic.real_species_pool(species_data))
    for trainer in result.values():
        for mon in trainer["party"]:
            assert mon["species"] in pool
            assert mon["species"] in species_data


# --- 4. Evolutions --------------------------------------------------------------


def test_evolutions_off_is_noop(species_logic, species_data) -> None:
    result = species_logic.randomize_evolutions(Random(1), species_logic.EVOLUTIONS_OFF, species_data)
    assert result is species_data


def test_evolutions_keep_method_is_deterministic(species_logic, species_data) -> None:
    first = species_logic.randomize_evolutions(Random(321), species_logic.EVOLUTIONS_KEEP_METHOD, species_data)
    second = species_logic.randomize_evolutions(Random(321), species_logic.EVOLUTIONS_KEEP_METHOD, species_data)
    assert first == second


def test_evolutions_any_method_is_deterministic(species_logic, species_data) -> None:
    first = species_logic.randomize_evolutions(Random(654), species_logic.EVOLUTIONS_ANY_METHOD, species_data)
    second = species_logic.randomize_evolutions(Random(654), species_logic.EVOLUTIONS_ANY_METHOD, species_data)
    assert first == second


def test_evolutions_keep_method_changes_targets_but_not_method_or_param(species_logic, species_data) -> None:
    result = species_logic.randomize_evolutions(Random(99), species_logic.EVOLUTIONS_KEEP_METHOD, species_data)
    assert result != species_data
    for key, data in species_data.items():
        for vanilla_evo, new_evo in zip(data["evolutions"], result[key]["evolutions"], strict=True):
            assert new_evo["method"] == vanilla_evo["method"]
            assert new_evo["param"] == vanilla_evo["param"]


def test_evolutions_any_method_changes_something(species_logic, species_data) -> None:
    result = species_logic.randomize_evolutions(Random(555), species_logic.EVOLUTIONS_ANY_METHOD, species_data)
    assert result != species_data


def test_evolutions_never_target_themselves(species_logic, species_data) -> None:
    for mode in (species_logic.EVOLUTIONS_KEEP_METHOD, species_logic.EVOLUTIONS_ANY_METHOD):
        result = species_logic.randomize_evolutions(Random(17), mode, species_data)
        for key, data in result.items():
            for evo in data["evolutions"]:
                assert evo["target"] != key


def test_evolutions_reference_real_species_and_known_methods(species_logic, species_data) -> None:
    valid_methods = {method for method, _param in species_logic._all_method_param_pairs(species_data)}
    for mode in (species_logic.EVOLUTIONS_KEEP_METHOD, species_logic.EVOLUTIONS_ANY_METHOD):
        result = species_logic.randomize_evolutions(Random(29), mode, species_data)
        for data in result.values():
            for evo in data["evolutions"]:
                assert evo["target"] in species_data
                assert species_data[evo["target"]]["national_dex"] is not None
                assert evo["method"] in valid_methods


def test_evolutions_edge_count_is_preserved(species_logic, species_data) -> None:
    """Randomizing targets/methods must not add or remove evolution edges."""
    for mode in (species_logic.EVOLUTIONS_KEEP_METHOD, species_logic.EVOLUTIONS_ANY_METHOD):
        result = species_logic.randomize_evolutions(Random(2), mode, species_data)
        for key, data in species_data.items():
            assert len(result[key]["evolutions"]) == len(data["evolutions"])


# --- Full pipeline: the most important property ---------------------------------


def _run_pipeline(species_logic, seed, species_data, trainers_data, encounters_data):
    rng = Random(seed)
    starters = species_logic.randomize_starters(rng, True, species_data)
    encounters = species_logic.randomize_wild_encounters(
        rng, species_logic.WILD_SHUFFLE, encounters_data, species_data
    )
    trainers = species_logic.randomize_trainer_parties(rng, True, trainers_data, species_data)
    evolutions = species_logic.randomize_evolutions(rng, species_logic.EVOLUTIONS_KEEP_METHOD, species_data)
    return starters, encounters, trainers, evolutions


def test_full_pipeline_is_deterministic_given_the_same_seed(
    species_logic, species_data, trainers_data, encounters_data
) -> None:
    first = _run_pipeline(species_logic, 20260808, species_data, trainers_data, encounters_data)
    second = _run_pipeline(species_logic, 20260808, species_data, trainers_data, encounters_data)
    assert first == second


def test_full_pipeline_differs_across_seeds(species_logic, species_data, trainers_data, encounters_data) -> None:
    first = _run_pipeline(species_logic, 1, species_data, trainers_data, encounters_data)
    second = _run_pipeline(species_logic, 2, species_data, trainers_data, encounters_data)
    assert first != second


def test_full_pipeline_differs_from_vanilla(species_logic, species_data, trainers_data, encounters_data) -> None:
    starters, encounters, trainers, evolutions = _run_pipeline(
        species_logic, 1, species_data, trainers_data, encounters_data
    )
    assert starters != species_logic.VANILLA_STARTERS
    assert encounters != encounters_data
    assert trainers != trainers_data
    assert evolutions != species_data


def test_full_pipeline_references_resolve(
    species_logic, species_data, moves_data, trainers_data, encounters_data
) -> None:
    """Every species referenced anywhere in the randomized pipeline's output
    must resolve in data/species.py, and every move referenced (movesets are
    left vanilla by randomize_trainer_parties, see its docstring) must still
    resolve in data/moves.py."""
    starters, encounters, trainers, evolutions = _run_pipeline(
        species_logic, 3, species_data, trainers_data, encounters_data
    )
    for key in starters:
        assert key in species_data
    for key in _flatten_encounter_species(encounters):
        assert key in species_data
    for trainer in trainers.values():
        for mon in trainer["party"]:
            assert mon["species"] in species_data
            for move in mon.get("moves", ()):
                assert move in moves_data
    for data in evolutions.values():
        for evo in data["evolutions"]:
            assert evo["target"] in species_data


# --- mode constants stay numerically compatible with options.py -----------------


def test_mode_constants_match_options_values(species_logic) -> None:
    """`species.py` deliberately does not import `options.py` (see its own
    module docstring), but its `WILD_*`/`EVOLUTIONS_*` mode constants must
    still match `options.RandomizeWildPokemon`/`RandomizeEvolutions`'s own
    option values exactly, so a future `__init__.py` can pass
    `world.options.randomize_wild_pokemon.value` straight through with no
    translation layer. Skips cleanly if the local Archipelago checkout
    `options.py` itself depends on isn't available (see tests/conftest.py)."""
    options = pytest.importorskip("options")
    assert species_logic.WILD_VANILLA == options.RandomizeWildPokemon.option_vanilla
    assert species_logic.WILD_SHUFFLE == options.RandomizeWildPokemon.option_shuffle
    assert species_logic.WILD_FULL_RANDOM == options.RandomizeWildPokemon.option_full_random
    assert species_logic.EVOLUTIONS_OFF == options.RandomizeEvolutions.option_off
    assert species_logic.EVOLUTIONS_KEEP_METHOD == options.RandomizeEvolutions.option_keep_method
    assert species_logic.EVOLUTIONS_ANY_METHOD == options.RandomizeEvolutions.option_any_method
