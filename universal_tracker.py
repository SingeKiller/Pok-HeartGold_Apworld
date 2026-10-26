from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from __init__ import HeartGoldWorld

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
    "trainersanity_count",
    "dexsanity",
    "dexsanity_count",
    "dexsanity_encounter_types",
    "randomize_start_location",
    "starting_town",
    "randomize_bicycle",
    "legendarysanity",
    "magnet_train",
    "require_flash",
    "hidden_items_require_dowsing_machine",
)

SLOT_DATA_OPTIONS_KEY = "options"


def build_ut_slot_data(world: "HeartGoldWorld") -> dict[str, Any]:
    return {name: getattr(world.options, name).value for name in TRACKED_OPTION_NAMES}


def load_ut_slot_data(world: "HeartGoldWorld") -> None:
    if not world.is_universal_tracker:
        return

    slot_data = world.ut_slot_data
    options = slot_data.get(SLOT_DATA_OPTIONS_KEY)
    if options is None:
        options = {name: slot_data[name] for name in ("goal", "goal_badge_count") if name in slot_data}

    for name, value in options.items():
        option = getattr(world.options, name, None)
        if option is not None:
            option.value = value
