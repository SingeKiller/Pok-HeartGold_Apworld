# options.py
#
# Archipelago option definitions for the HeartGold & SoulSilver world.
# Every class docstring below is player-facing (shown in the generated
# YAML template and the WebHost options page) -- do not trim those.
#
# Imports only from Options, never worlds.*, to avoid triggering
# Archipelago's full world-plugin autoload before this project's own
# World class is registered.

from __future__ import annotations

from dataclasses import dataclass

from Options import Choice, DeathLink, OptionGroup, PerGameCommonOptions, Range, StartInventoryPool, Toggle


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
    - zone_method_mapping: every route's own encounter method (its grass
      table, its surf table, its Old Rod table, etc.) gets one replacement
      species, applied consistently to every slot in that table -- so
      every grass encounter on a given route is the same species, but that
      route's surf table can be a different one. Unlike full_random, this
      tries to use as many distinct species as possible across the whole
      game (no repeats until every eligible species has been used once).
    """

    display_name = "Randomize Wild Pokémon"
    option_vanilla = 0
    option_shuffle = 1
    option_full_random = 2
    option_zone_method_mapping = 3
    default = 0


class ExcludeLegendaries(Toggle):
    """Never place a legendary or mythical Pokémon (Articuno through
    Arceus) in the wild encounter pool when `randomize_wild_pokemon` is
    set to `full_random` or `zone_method_mapping`, or as a starter when
    `randomize_starters` is on. Has no effect on `vanilla`/`shuffle` --
    vanilla wild tables don't place legendaries in grass/surf/fishing/
    rock-smash slots to begin with, so there's nothing to exclude from a
    shuffle of the existing multiset.
    """

    display_name = "Exclude Legendaries"


class RandomizeStarters(Toggle):
    """Randomize the 3 starter Pokémon (Chikorita/Cyndaquil/Totodile) --
    also changes the rival's own starter, which is always your starter's
    type-advantaged counter, same as vanilla. Only species with at least
    one evolution are picked, matching vanilla (each starter has two).
    Live-verified: the Pokémon you actually receive is genuinely
    randomized, and the on-screen name shown during the selection scene
    matches it too."""

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
    """Add a check for catching each species for the first time.

    Seed-aware (task M3.4): only species that genuinely appear somewhere in
    this seed's own randomize_wild_pokemon tables get a check -- static/gift
    Pokemon (starters, legendaries, in-game gifts) stay vanilla/fixed and
    are never a Dexsanity check. Every Dexsanity check only ever holds a
    filler item, never a progression one: the access rule only requires
    owning the right catching tool (Surf, a fishing rod, Rock Smash) for
    some occurrence of that species, not the exact region it spawns in, so
    it is deliberately looser than the game's real logic and unsafe to gate
    anything mandatory behind.

    v1 stretch goal (see docs/scope.md) -- off by default, not required for
    a playable v1.
    """

    display_name = "Dexsanity"


class DisableOhkoMoves(Toggle):
    """Neutralize the four One-Hit KO moves (Guillotine, Horn Drill,
    Fissure, Sheer Cold): each becomes an ordinary 60 power / 100 accuracy
    move with no special effect, instead of an RNG-based instant KO.

    A Nuzlocke aid (see docs/scope.md's "Nuzlocke mode" section), not a
    randomizer -- this project does not enforce permadeath itself (that
    stays honor-system, tracked externally), but an instant, uncounterable
    KO is a bad interaction with a permadeath ruleset, so this option lets
    a player opt out of it entirely. Off by default (vanilla behavior
    unchanged)."""

    display_name = "Disable OHKO Moves"


class DisableTrappingAbilities(Toggle):
    """Remove every trapping ability (Arena Trap, Shadow Tag, Magnet Pull)
    from every Pokémon that has one: a species with a second, non-trapping
    ability gets that ability copied into both slots instead; a species
    whose *only* ability traps (e.g. Wobbuffet's Shadow Tag) gets Run Away
    instead.

    A Nuzlocke aid (see docs/scope.md's "Nuzlocke mode" section), not a
    randomizer -- an inescapable wild battle is a bad interaction with a
    permadeath ruleset. Off by default (vanilla behavior unchanged)."""

    display_name = "Disable Trapping Abilities"


class FastTextSpeed(Toggle):
    """Set Text Speed to Fast, the fastest tier the game itself defines,
    as soon as this client connects, instead of the vanilla default
    (Mid). Applied once per connection, directly to savedata -- can still
    be changed freely afterward from the in-game Options menu like any
    other setting. Off by default (vanilla behavior unchanged)."""

    display_name = "Fast Text Speed"


class SkipBattleAnimations(Toggle):
    """Set Battle Scene to Off as soon as this client connects, skipping
    move/entry animations in battle. Applied once per connection,
    directly to savedata -- can still be changed freely afterward from
    the in-game Options menu like any other setting. Off by default
    (vanilla behavior unchanged)."""

    display_name = "Skip Battle Animations"


class ReusableTms(Toggle):
    """Make TMs reusable: whenever a TM is consumed while teaching a
    move, this client puts it right back the next time it polls the Bag
    (HMs are already never consumed in vanilla). Off by default (vanilla
    behavior unchanged)."""

    display_name = "Reusable TMs"


class ConvertTradeEvolutions(Toggle):
    """Convert every trade and friendship evolution (Kadabra, Machoke,
    Graveler, Haunter, Onix/Steelix's trade-item variant, Eevee's
    friendship evolutions, Golbat, etc.) into a plain level-up evolution
    instead, at the level set by `trade_evolution_level` below --
    trading and grinding friendship are both genuine single-player
    accessibility problems. Applied after `randomize_evolutions`, so it
    fixes whichever method an edge actually ends up with, randomized or
    vanilla. Off by default (vanilla behavior unchanged)."""

    display_name = "Convert Trade/Friendship Evolutions"


class TradeEvolutionLevel(Range):
    """The level trade/friendship evolutions are converted to when
    `convert_trade_evolutions` is on. Ignored otherwise."""

    display_name = "Trade/Friendship Evolution Level"
    range_start = 1
    range_end = 100
    default = 30


class HeartGoldDeathLink(DeathLink):
    __doc__ = (
        DeathLink.__doc__
        + "\n\n    In Pokemon HeartGold/SoulSilver, having one of your own Pokemon "
        "faint sends a death, and receiving a death faints your entire "
        "party (zeroes each party Pokemon's current HP, same as a "
        "vanilla blackout).\n"
    )


@dataclass
class HeartGoldOptions(PerGameCommonOptions):
    game_version: GameVersion

    goal: Goal
    goal_badge_count: GoalBadgeCount

    randomize_wild_pokemon: RandomizeWildPokemon
    randomize_starters: RandomizeStarters
    randomize_trainers: RandomizeTrainers
    exclude_legendaries: ExcludeLegendaries
    randomize_evolutions: RandomizeEvolutions
    randomize_base_stats: RandomizeBaseStats
    randomize_moves: RandomizeMoves
    randomize_move_types: RandomizeMoveTypes
    randomize_species_types: RandomizeSpeciesTypes
    trainer_level_scaling: TrainerLevelScaling

    disable_ohko_moves: DisableOhkoMoves
    disable_trapping_abilities: DisableTrappingAbilities

    fast_text_speed: FastTextSpeed
    skip_battle_animations: SkipBattleAnimations
    reusable_tms: ReusableTms
    convert_trade_evolutions: ConvertTradeEvolutions
    trade_evolution_level: TradeEvolutionLevel

    death_link: HeartGoldDeathLink

    trainersanity: Trainersanity
    dexsanity: Dexsanity

    start_inventory_from_pool: StartInventoryPool


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
            RandomizeStarters,
            ExcludeLegendaries,
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
        "Nuzlocke Aids",
        [DisableOhkoMoves, DisableTrappingAbilities],
    ),
    OptionGroup(
        "Quality of Life",
        [FastTextSpeed, SkipBattleAnimations, ReusableTms, ConvertTradeEvolutions, TradeEvolutionLevel],
    ),
    OptionGroup(
        "DeathLink",
        [HeartGoldDeathLink],
    ),
    OptionGroup(
        "Stretch Goals",
        [Trainersanity, Dexsanity],
        start_collapsed=True,
    ),
]
