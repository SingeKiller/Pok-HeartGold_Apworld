"""Tests for the Archipelago World registration (task C12): `__init__.py`'s
`HeartGoldWorld`, which wires together everything already built by
items.py/locations.py/regions.py/rules.py/options.py/species.py into the
`World` subclass Archipelago's `worlds.AutoWorld` plugin loader actually
instantiates.

Needs a local Archipelago checkout importable as `BaseClasses`/`worlds`
(see tests/conftest.py) -- skips cleanly if unavailable, same convention as
tests/test_world_structure.py and tests/test_options.py.

`worlds.AutoWorld` autoloads *every* world plugin found in the local
Archipelago checkout's `worlds/` folder the moment it is imported (see
items.py's/locations.py's/regions.py's/rules.py's/options.py's own
docstrings for why every other root module of this project avoids that
import) -- unavoidable here, since this project's `__init__.py` *is* the
thing registering "Pokemon HeartGold" with that very autoloader; this is
also exactly what happens the moment a real Archipelago install loads this
project as a world. A handful of *other*, unrelated world plugins in the
local checkout are expected to fail to load in this dev environment
(missing optional third-party deps like `requests`/`zilliandomizer`, not
this project's own dependencies) -- `worlds/__init__.py` itself tolerates
that per-plugin and only logs a warning, so it does not affect these tests.

Most importantly (this task's own "T1"): `test_real_generation_multiple_
seeds_and_option_combinations` below runs this project's `HeartGoldWorld`
through Archipelago's own, real, unmodified `create_regions`/`create_items`/
`set_rules`/`connect_entrances`/`generate_basic`/`pre_fill` stages (via the
local Archipelago checkout's own `test.general.setup_multiworld` test
helper -- the same helper Archipelago's own world test suites use) followed
by Archipelago's own real `Fill.distribute_items_restrictive` fill
algorithm and `MultiWorld.can_beat_game()` accessibility sweep, for 5
different seeds across varied option combinations (every `goal` value,
every `randomize_wild_pokemon` mode, starters/trainers/evolutions on and
off, Trainersanity/Dexsanity on and off) -- checking no exception (in
particular no `Fill.FillError`) is raised and the resulting seed is
actually completable.

This exercises the exact same World-facing logic a real `Generate.py` CLI
run does (regions/items/rules/fill/accessibility) without the surrounding
argparse/YAML-rolling/output-writing layer, which adds no further coverage
of this project's own code. A full `Generate.py` CLI run (building
`pokemon_heartgold.apworld` via `build.py`, dropping it into the local
Archipelago checkout's auto-created `custom_worlds/` folder -- never into
its own read-only `worlds/` folder -- and running `Generate.py
--player_files_path ...`) was additionally exercised by hand for this task
across the same 5 seed/option combinations below (see this task's own
RESULT notes) and also succeeded end-to-end (real multidata output archive
produced each time); it is not wired into this automated suite because it
needs a spawned subprocess, a temporary player-files directory and a
temporary Archipelago `custom_worlds/` drop-in, none of which are needed to
exercise this project's own code any further than the in-process
`Fill.distribute_items_restrictive` + `can_beat_game()` check already does.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

bc = pytest.importorskip("BaseClasses")
pytest.importorskip("worlds.AutoWorld")
pytest.importorskip("test.general")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

_MODULES = (
    "data.items",
    "data.locations",
    "data.regions",
    "data.rules",
    "items",
    "locations",
    "regions",
    "rules",
    "options",
    "species",
)

# The project's own Archipelago World registration lives in `__init__.py` at
# the repository root (an Archipelago packaging constraint, see CLAUDE.md's
# Repository Structure note and this project's own __init__.py docstring)
# -- a filename Python's import machinery does not treat as an ordinary flat
# top-level module name the way it treats `items.py`/`locations.py`/etc.
# (bare `importlib.import_module("__init__")` is ambiguous and, empirically,
# resolves inconsistently once pytest's own import machinery is active,
# occasionally re-executing the module under a second identity and tripping
# `worlds.AutoWorld`'s "game already registered" guard -- *not* a bug in
# `__init__.py` itself: a real Archipelago load always imports it under an
# unambiguous dotted name instead (`worlds.pokemon_heartgold`, see this
# task's own RESULT notes for a real `worlds.AutoWorld` autoload and a real
# `Generate.py` run, both single-registration). Loading it here via
# `importlib.util.spec_from_file_location` with an explicit, unambiguous
# module name sidesteps that bare-name ambiguity entirely.
_HEARTGOLD_WORLD_MODULE_NAME = "heartgold_world_under_test"
_HEARTGOLD_INIT_PATH = ROOT / "__init__.py"


def _import_heartgold_world_module():
    import importlib.util

    sys.modules.pop(_HEARTGOLD_WORLD_MODULE_NAME, None)
    spec = importlib.util.spec_from_file_location(_HEARTGOLD_WORLD_MODULE_NAME, _HEARTGOLD_INIT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_HEARTGOLD_WORLD_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module

# The 5 seed/option combinations this task's brief asks for -- one per
# `goal` value at least once, every `randomize_wild_pokemon` mode at least
# once, starters/trainers/evolutions both on and off, Trainersanity/
# Dexsanity both on and off. Mirrors the 5 player YAMLs hand-run against a
# real `Generate.py` for this task (see this module's own docstring).
_SEED_OPTION_COMBINATIONS: tuple[tuple[int, dict[str, Any]], ...] = (
    (
        12345,
        {
            "goal": "elite_four",
            "goal_badge_count": 16,
            "randomize_wild_pokemon": "vanilla",
            "randomize_starters": False,
            "randomize_trainers": False,
            "randomize_evolutions": "off",
            "trainersanity": False,
            "dexsanity": False,
        },
    ),
    (
        42222,
        {
            "goal": "n_badges",
            "goal_badge_count": 8,
            "randomize_wild_pokemon": "full_random",
            "randomize_starters": True,
            "randomize_trainers": True,
            "randomize_evolutions": "any_method",
            "trainersanity": True,
            "dexsanity": True,
        },
    ),
    (
        52222,
        {
            "goal": "champion_red",
            "goal_badge_count": 16,
            "randomize_wild_pokemon": "shuffle",
            "randomize_starters": True,
            "randomize_trainers": False,
            "randomize_evolutions": "keep_method",
            "trainersanity": False,
            "dexsanity": False,
        },
    ),
    (
        62222,
        {
            "goal": "elite_four",
            "goal_badge_count": 16,
            "randomize_wild_pokemon": "vanilla",
            "randomize_starters": False,
            "randomize_trainers": True,
            "randomize_evolutions": "off",
            "trainersanity": True,
            "dexsanity": False,
        },
    ),
    (
        72222,
        {
            "goal": "n_badges",
            "goal_badge_count": 1,
            "randomize_wild_pokemon": "full_random",
            "randomize_starters": True,
            "randomize_trainers": True,
            "randomize_evolutions": "any_method",
            "trainersanity": False,
            "dexsanity": False,
        },
    ),
)


@pytest.fixture(scope="module")
def world_modules():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)

    importlib.invalidate_caches()
    modules = {}
    # Import order matters: locations.py imports items.py, rules.py imports
    # locations.py (same convention as tests/test_world_structure.py's own
    # world_modules fixture).
    for name in _MODULES:
        if name in sys.modules:
            modules[name] = importlib.reload(sys.modules[name])
        else:
            modules[name] = importlib.import_module(name)
    # __init__.py itself is loaded last, once (module-scoped fixture, so
    # this whole block runs exactly once per test module) -- see
    # _import_heartgold_world_module's own docstring above for why it is
    # not just `importlib.import_module("__init__")`.
    modules["__init__"] = _import_heartgold_world_module()
    yield modules
    shutil.rmtree(DATA_DIR, ignore_errors=True)


@pytest.fixture()
def heartgold_world_type(world_modules):
    return world_modules["__init__"].HeartGoldWorld


# --- registration -----------------------------------------------------------


def test_world_registers_with_archipelago(heartgold_world_type):
    from worlds.AutoWorld import AutoWorldRegister

    assert heartgold_world_type.game == "Pokemon HeartGold"
    assert AutoWorldRegister.world_types["Pokemon HeartGold"] is heartgold_world_type


def test_item_and_location_id_maps_are_populated(heartgold_world_type, world_modules):
    items_data = world_modules["data.items"].ITEMS
    locations_data = world_modules["data.locations"].LOCATIONS
    non_badge_count = sum(1 for data in locations_data.values() if data["type"] != "badge")

    assert len(heartgold_world_type.item_name_to_id) == len(items_data)
    assert len(heartgold_world_type.location_name_to_id) == non_badge_count


def test_origin_region_is_a_real_region(heartgold_world_type, world_modules):
    assert heartgold_world_type.origin_region_name in world_modules["data.regions"].REGIONS


# --- basic generation steps run without exception ---------------------------


def _setup(heartgold_world_type, options: dict[str, Any] | None = None, seed: int | None = None, steps=None):
    from test.general import gen_steps, setup_multiworld

    return setup_multiworld(heartgold_world_type, steps if steps is not None else gen_steps, seed, options)


def test_generation_steps_run_without_exception(heartgold_world_type):
    multiworld = _setup(heartgold_world_type, seed=1)
    world = multiworld.worlds[1]

    assert len(multiworld.get_locations(1)) == len(heartgold_world_type.location_name_to_id) + 16  # + 16 badges
    assert len(multiworld.itempool) == len(heartgold_world_type.location_name_to_id)
    assert hasattr(world, "generated_starters")
    assert hasattr(world, "generated_encounters")
    assert hasattr(world, "generated_trainer_parties")
    assert hasattr(world, "generated_species")


def test_completion_condition_reachable_with_full_inventory(heartgold_world_type):
    multiworld = _setup(heartgold_world_type, seed=2)
    state = multiworld.get_all_state(False)
    assert multiworld.completion_condition[1](state) is True


@pytest.mark.parametrize(
    "goal,goal_badge_count",
    [("elite_four", 16), ("champion_red", 16), ("n_badges", 4)],
)
def test_completion_condition_per_goal_reachable_with_full_inventory(heartgold_world_type, goal, goal_badge_count):
    multiworld = _setup(
        heartgold_world_type, options={"goal": goal, "goal_badge_count": goal_badge_count}, seed=3
    )
    state = multiworld.get_all_state(False)
    assert multiworld.completion_condition[1](state) is True


def test_completion_condition_n_badges_not_met_with_empty_inventory(heartgold_world_type):
    multiworld = _setup(heartgold_world_type, options={"goal": "n_badges", "goal_badge_count": 1}, seed=4)
    empty_state = bc.CollectionState(multiworld)
    assert multiworld.completion_condition[1](empty_state) is False


# --- determinism -------------------------------------------------------------


def test_species_randomization_is_deterministic_given_the_same_seed(heartgold_world_type):
    options = {
        "randomize_wild_pokemon": "full_random",
        "randomize_starters": True,
        "randomize_trainers": True,
        "randomize_evolutions": "any_method",
    }
    first = _setup(heartgold_world_type, options=options, seed=99).worlds[1]
    second = _setup(heartgold_world_type, options=options, seed=99).worlds[1]

    assert first.generated_starters == second.generated_starters
    assert first.generated_encounters == second.generated_encounters
    assert first.generated_trainer_parties == second.generated_trainer_parties
    assert first.generated_species == second.generated_species


# --- T1: real generation, several seeds and option combinations -------------


@pytest.mark.parametrize("seed,options", _SEED_OPTION_COMBINATIONS)
def test_real_generation_multiple_seeds_and_option_combinations(heartgold_world_type, seed, options):
    """The most important test of this task (see this module's own
    docstring): real `create_regions`/`create_items`/`set_rules`/
    `connect_entrances`/`generate_basic`/`pre_fill` (Archipelago's own,
    unmodified `test.general.setup_multiworld`) followed by Archipelago's
    own real `Fill.distribute_items_restrictive` -- must place every item
    without raising (in particular no `Fill.FillError`), and the resulting
    seed must actually be completable."""
    from Fill import distribute_items_restrictive

    multiworld = _setup(heartgold_world_type, options=options, seed=seed)

    distribute_items_restrictive(multiworld)

    assert not multiworld.get_unfilled_locations()
    assert multiworld.can_beat_game()
