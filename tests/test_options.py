"""Tests for the Archipelago option definitions (task C10).

Needs the local Archipelago clone's `Options.py` on `sys.path` (added by
`tests/conftest.py` from `ARCHIPELAGO_PATH`) -- skips cleanly via
`pytest.importorskip` if it isn't available, the same convention used by
the rest of this suite for Archipelago-framework-dependent tests (see
`tests/conftest.py`).
"""

from __future__ import annotations

import pytest

pytest.importorskip("Options")

from dataclasses import fields

from options import (
    OPTION_GROUPS,
    Dexsanity,
    Goal,
    GoalBadgeCount,
    HeartGoldOptions,
    RandomizeEvolutions,
    RandomizeWildPokemon,
    Trainersanity,
)


def _default_instance() -> HeartGoldOptions:
    return HeartGoldOptions(
        **{name: option.from_any(option.default) for name, option in HeartGoldOptions.type_hints.items()}
    )


def test_instantiates_with_defaults() -> None:
    options = _default_instance()
    assert options.goal.value == Goal.option_elite_four
    assert options.goal_badge_count.value == 16
    assert options.randomize_wild_pokemon.value == RandomizeWildPokemon.option_vanilla
    assert options.randomize_trainers.value == 0
    assert options.randomize_evolutions.value == RandomizeEvolutions.option_off
    assert options.trainersanity.value == 0
    assert options.dexsanity.value == 0


def test_trainersanity_and_dexsanity_default_off() -> None:
    """Both v1 stretch goals (see docs/scope.md) must default to off."""
    assert Trainersanity.default == 0
    assert Dexsanity.default == 0


def test_every_heartgold_option_has_a_docstring() -> None:
    """Each field's Option class's docstring is what the AP Launcher/WebHost
    displays to the player -- none of this project's own option classes may
    ship without one."""
    for f in fields(HeartGoldOptions):
        option_cls = HeartGoldOptions.type_hints[f.name]
        # Only check this project's own option classes (module "options"),
        # not the inherited PerGameCommonOptions fields (LocalItems, etc.,
        # defined in the Archipelago framework itself, out of this task's
        # scope).
        if option_cls.__module__ != "options":
            continue
        assert option_cls.__doc__ is not None, f"{option_cls.__name__} has no docstring"
        assert option_cls.__doc__.strip(), f"{option_cls.__name__} has an empty docstring"


def test_goal_badge_count_range() -> None:
    assert GoalBadgeCount.range_start == 1
    assert GoalBadgeCount.range_end == 16


def test_option_groups_only_reference_declared_options() -> None:
    declared = set(HeartGoldOptions.type_hints.values())
    for group in OPTION_GROUPS:
        for option_cls in group.options:
            assert option_cls in declared, f"{option_cls.__name__} is in an OptionGroup but not on HeartGoldOptions"
