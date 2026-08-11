# options.py
#
# Archipelago option definitions for the HeartGold & SoulSilver world (v1
# scope, see docs/scope.md): wild-encounter/trainer/evolution
# randomization toggles, a configurable victory condition, and the two v1
# stretch goals (Trainersanity, Dexsanity), off by default. Starters is
# shelved for a later resume (task M4.5 -- see docs/architecture.md's "M4.5
# continued" sections: the vanilla species assignment couldn't be located
# in the ROM after extensive live/static investigation), so no
# `RandomizeStarters` option is exposed here; `species.py`'s own
# `randomize_starters` computation stays in place, tested, ready to be
# reconnected once/if a patch target is found. Follows the
# `Options.py` API of the local Archipelago clone (`Toggle`/`Choice`/
# `Range`/`PerGameCommonOptions`/`OptionGroup`) the same way
# `ressources/platinum_archipelago/options.py` does (read-only reference,
# not copied) -- simplified to only the options this project's v1 scope
# actually needs; richer per-category whitelist/blacklist/logic-method
# options (as in the reference) are left for later tasks once the
# corresponding randomization logic itself is implemented (out of this
# task's scope, see task brief).
#
# Deliberately imports only from `Options` (the local Archipelago clone's
# option framework module), never from `worlds.*`: importing the `worlds`
# package triggers Archipelago's full world-plugin autoloading (see
# `worlds/__init__.py` in the local Archipelago clone), which is far too
# heavy a dependency to pull in before this project has its own registered
# `__init__.py`/World class -- the same reasoning `rules.py` documents for
# avoiding `worlds.generic.Rules`. `Options.py` itself only imports
# `Utils`/`schema`/`typing_extensions` at module scope (its `worlds.AutoWorld`
# import is `TYPE_CHECKING`-only), so importing it does not trigger the
# world-plugin autoload either.
#
# No randomization logic lives here -- just the option definitions
# themselves; which randomizer/`data_gen` code actually reads them is a
# separate, later concern.

from __future__ import annotations

from dataclasses import dataclass

from Options import Choice, OptionGroup, PerGameCommonOptions, Range, Toggle


class GameVersion(Choice):
    """Which physical ROM this patch is meant for: HeartGold or SoulSilver.

    This matters because wild encounters -- and potentially other data --
    genuinely differ between the two versions (e.g. Route 29's morning
    Sentret/Rattata swap). This choice must match the ROM you actually plan
    to patch: generating with the wrong value produces a patch that writes
    the other version's data into your ROM (see `output_patch.py`'s
    version-mismatch check, which refuses to apply a mismatched patch at
    patch time rather than silently miswriting the ROM).
    """

    display_name = "Game Version"
    option_heartgold = 0
    option_soulsilver = 1
    default = 0


class RandomizeWildPokemon(Choice):
    """Randomize wild Pokémon encounters (grass / surf / fishing / rock
    smash / headbutt, across HGSS's morning/day/night tables).

    - vanilla: no randomization, wild encounters stay as in the base game.
    - shuffle: shuffles which species appear across every wild encounter
      slot in the game (a permutation -- the same set of species still
      appears somewhere, just moved around).
    - full_random: every wild encounter slot is replaced by an
      independently-chosen random species.
    """

    display_name = "Randomize Wild Pokémon"
    option_vanilla = 0
    option_shuffle = 1
    option_full_random = 2
    default = 0


class RandomizeTrainers(Toggle):
    """Randomize trainer Pokémon parties (Gym Leaders, Rivals, Elite Four, Red, and regular trainers)."""

    display_name = "Randomize Trainers"


class RandomizeEvolutions(Choice):
    """Randomize what each Pokémon evolves into.

    - off: evolutions stay vanilla.
    - keep_method: evolution targets are randomized, but each species keeps
      its original evolution method (e.g. a level-up evolution stays a
      level-up evolution, just into a different species) -- logic can keep
      assuming the vanilla method is reachable.
    - any_method: evolution targets and methods are both randomized freely;
      logic no longer assumes any particular evolution method for a given
      species.
    """

    display_name = "Randomize Evolutions"
    option_off = 0
    option_keep_method = 1
    option_any_method = 2
    default = 0


class RandomizeBaseStats(Choice):
    """Randomize each Pokémon species' base stats (HP/Attack/Defense/Sp.
    Attack/Sp. Defense/Speed). Growth rate (the EXP curve used to level
    up) and every other species field (types -- see `randomize_species_
    types` -- abilities, catch rate, TM/HM compatibility, learnset, ...)
    are never touched by this option -- also unrelated to trainer level
    scaling (`trainer_level_scaling`).

    - off: base stats stay vanilla.
    - shuffle: shuffles each stat column independently across every
      species (a permutation -- the same multiset of, say, HP values
      still appears somewhere, just reassigned to different species).
    - full_random: each of the six stats is independently replaced by a
      fresh random value, drawn from the range actually used by some real
      species' stat in that same column (e.g. HP is randomized within the
      real min-max HP range across all species) -- avoids literal
      1/255 extremes that no vanilla species ever has.
    """

    display_name = "Randomize Base Stats"
    option_off = 0
    option_shuffle = 1
    option_full_random = 2
    default = 0


class RandomizeMoves(Choice):
    """Randomize each move's Power/PP/Accuracy. A move's Type is a
    separate option (`randomize_move_types`) -- unaffected by this one --
    and nothing else about a move (effect, category, priority, ...) is
    touched by either.

    - off: move stats stay vanilla.
    - shuffle: shuffles each of Power/PP/Accuracy independently across
      every move (a permutation).
    - full_random: each of Power/PP/Accuracy is independently replaced by
      a fresh random value, drawn from the range actually used by some
      real move in that same column.
    """

    display_name = "Randomize Moves"
    option_off = 0
    option_shuffle = 1
    option_full_random = 2
    default = 0


class RandomizeMoveTypes(Toggle):
    """Randomize each move's Type. TM/HM compatibility and each species'
    own learnset are unaffected by this (they're keyed by move identity,
    not type) -- only which type a move deals damage/gets same-type-attack-
    bonus as changes. Never assigns the "???" (Mystery) type to any move,
    including one whose vanilla type already is "???" (Curse) -- it's
    engine-special-cased, not a genuine 18th type to draw from."""

    display_name = "Randomize Move Types"


class RandomizeSpeciesTypes(Toggle):
    """Randomize each Pokémon species' Type(s). A species keeps its
    original single-type/dual-type status -- only *which* type(s) is
    randomized. Never assigns the "???" (Mystery) type, same reasoning as
    `randomize_move_types`. Unrelated to `randomize_base_stats` (stats)
    and TM/HM compatibility/learnsets (unaffected by this option)."""

    display_name = "Randomize Species Types"


class TrainerLevelScaling(Range):
    """Scale every trainer Pokémon's level by this percentage (100 = vanilla
    levels, unchanged). A difficulty knob, not a randomizer -- the same
    percentage applies uniformly to every trainer, every generation. Levels
    are clamped to HGSS's own 1-100 range after scaling."""

    display_name = "Trainer Level Scaling"
    range_start = 50
    range_end = 200
    default = 100


class Goal(Choice):
    """The victory condition for this world.

    - elite_four: defeat the Elite Four and Champion, entering the Hall of Fame.
    - champion_red: also defeat Red at the top of Mt. Silver.
    - n_badges: obtain a configurable number of badges (see the
      `goal_badge_count` option) -- no specific boss fight is required.
    """

    display_name = "Goal"
    option_elite_four = 0
    option_champion_red = 1
    option_n_badges = 2
    default = 0


class GoalBadgeCount(Range):
    """Number of badges required to win when the `goal` option is set to
    `n_badges`. Ignored for any other `goal` value.

    HeartGold & SoulSilver have 16 badges in total (8 Johto, 8 Kanto).
    """

    display_name = "Goal Badge Count"
    range_start = 1
    range_end = 16
    default = 16


class Trainersanity(Toggle):
    """Add a check for every trainer battle won.

    v1 stretch goal (see docs/scope.md) -- off by default, not required for
    a playable v1.
    """

    display_name = "Trainersanity"


class Dexsanity(Toggle):
    """Add a check for registering each Pokémon species as seen/caught in the Pokédex.

    v1 stretch goal (see docs/scope.md) -- off by default, not required for
    a playable v1.
    """

    display_name = "Dexsanity"


@dataclass
class HeartGoldOptions(PerGameCommonOptions):
    game_version: GameVersion

    goal: Goal
    goal_badge_count: GoalBadgeCount

    randomize_wild_pokemon: RandomizeWildPokemon
    randomize_trainers: RandomizeTrainers
    randomize_evolutions: RandomizeEvolutions
    randomize_base_stats: RandomizeBaseStats
    randomize_moves: RandomizeMoves
    randomize_move_types: RandomizeMoveTypes
    randomize_species_types: RandomizeSpeciesTypes
    trainer_level_scaling: TrainerLevelScaling

    trainersanity: Trainersanity
    dexsanity: Dexsanity


OPTION_GROUPS = [
    OptionGroup(
        "Game Version",
        [GameVersion],
    ),
    OptionGroup(
        "Goal",
        [Goal, GoalBadgeCount],
    ),
    OptionGroup(
        "Randomizers",
        [
            RandomizeWildPokemon,
            RandomizeTrainers,
            RandomizeEvolutions,
            RandomizeBaseStats,
            RandomizeMoves,
            RandomizeMoveTypes,
            RandomizeSpeciesTypes,
            TrainerLevelScaling,
        ],
    ),
    OptionGroup(
        "Stretch Goals",
        [Trainersanity, Dexsanity],
        start_collapsed=True,
    ),
]
