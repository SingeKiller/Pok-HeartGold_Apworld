# options.py
#
# Archipelago option definitions for the HeartGold & SoulSilver world (v1
# scope, see docs/scope.md): wild-encounter/starter/trainer/evolution
# randomization toggles, a configurable victory condition, and the two v1
# stretch goals (Trainersanity, Dexsanity), off by default. Follows the
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


class RandomizeStarters(Toggle):
    """Randomize the three starter Pokémon (and the rival's) given by Prof. Elm."""

    display_name = "Randomize Starters"


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
    up) and every other species field (types, abilities, catch rate,
    TM/HM compatibility, learnset, ...) are never touched -- this option
    is unrelated to level scaling (docs/scope.md's v2 list).

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
    """Randomize each move's Power/PP/Accuracy. A move's Type is never
    changed (so TM/HM compatibility and STAB stay meaningful), and
    nothing else about it (effect, category, priority, ...) is touched.

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
    goal: Goal
    goal_badge_count: GoalBadgeCount

    randomize_wild_pokemon: RandomizeWildPokemon
    randomize_starters: RandomizeStarters
    randomize_trainers: RandomizeTrainers
    randomize_evolutions: RandomizeEvolutions
    randomize_base_stats: RandomizeBaseStats
    randomize_moves: RandomizeMoves

    trainersanity: Trainersanity
    dexsanity: Dexsanity


OPTION_GROUPS = [
    OptionGroup(
        "Goal",
        [Goal, GoalBadgeCount],
    ),
    OptionGroup(
        "Randomizers",
        [
            RandomizeWildPokemon,
            RandomizeStarters,
            RandomizeTrainers,
            RandomizeEvolutions,
            RandomizeBaseStats,
            RandomizeMoves,
        ],
    ),
    OptionGroup(
        "Stretch Goals",
        [Trainersanity, Dexsanity],
        start_collapsed=True,
    ),
]
