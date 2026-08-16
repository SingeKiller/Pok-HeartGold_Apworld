# universal_tracker.py
#
# Universal Tracker (`tracker.apworld`) support. UT re-runs this world's own
# generation locally against a connected slot, so it needs the slot's real
# options back: `fill_slot_data` writes them, `load_ut_slot_data` applies
# them (see `interpret_slot_data`/`ut_can_gen_without_yaml` in __init__.py).
#
# Only `goal`/`goal_badge_count` actually change this world's logic -- the
# region graph, locations and HM/badge rules are all static. The rest is
# round-tripped anyway so a re-run's options match the real slot, and so UT
# keeps working if a randomizer option ever starts gating a Location.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from __init__ import HeartGoldWorld

# Every `HeartGoldOptions` field except AP-common ones (e.g.
# `start_inventory_from_pool`), which UT takes from the multidata itself.
#
# exclude_legendaries and dexsanity (task M3.4) are both load-bearing here,
# not just round-tripped for completeness: Dexsanity's location set is
# computed from species.species_encounter_methods(world.generated_
# encounters), which a UT re-run recomputes locally by re-seeding
# randomize_wild_encounters -- if either option's value silently diverged
# from the real generation, the re-run would produce a different encounter
# table (exclude_legendaries) or a different location set (dexsanity) than
# the actual seed, desyncing the tracker.
TRACKED_OPTION_NAMES = (
    "goal",
    "goal_badge_count",
    "johto_only",
    "game_version",
    "randomize_wild_pokemon",
    "randomize_starters",
    "exclude_legendaries",
    "randomize_trainers",
    "randomize_evolutions",
    "randomize_base_stats",
    "randomize_moves",
    "randomize_move_types",
    "randomize_species_types",
    "trainer_level_scaling",
    "trainersanity",
    "dexsanity",
    "dexsanity_encounter_types",
    "randomize_start_location",
    "starting_town",
    "randomize_bag",
    "randomize_trainer_card",
    "randomize_pokedex",
    "randomize_pokegear",
    "randomize_save_button",
    "randomize_options_button",
    "randomize_bicycle",
    "legendarysanity",
    "extra_route_blockers",
)

# Nested rather than written flat: slot data's top-level "game_version" is
# data/'s own GAME_VERSION constant (always "HeartGold"), which would
# collide with the per-player option of the same name (an int: HG/SS).
SLOT_DATA_OPTIONS_KEY = "options"


def build_ut_slot_data(world: "HeartGoldWorld") -> dict[str, Any]:
    """This player's value for every `TRACKED_OPTION_NAMES` option."""
    return {name: getattr(world.options, name).value for name in TRACKED_OPTION_NAMES}


def load_ut_slot_data(world: "HeartGoldWorld") -> None:
    """Apply a UT re-generation's slot data back onto `world.options`.
    No-op during a real generation."""
    if not world.is_universal_tracker:
        return

    slot_data = world.ut_slot_data
    options = slot_data.get(SLOT_DATA_OPTIONS_KEY)
    if options is None:
        # Seeds from apworld <= 0.1.4 predate the nested key but already
        # published these two flat -- exactly the logic-relevant subset.
        options = {name: slot_data[name] for name in ("goal", "goal_badge_count") if name in slot_data}

    # Unknown names are skipped: slot data was written by whatever version
    # generated the seed, which may name options this one doesn't have.
    for name, value in options.items():
        option = getattr(world.options, name, None)
        if option is not None:
            option.value = value
