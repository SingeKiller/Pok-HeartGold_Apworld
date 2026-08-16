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

from Options import (
    Choice,
    DeathLink,
    OptionGroup,
    OptionSet,
    PerGameCommonOptions,
    Range,
    StartInventoryPool,
    Toggle,
)


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


class RandomizeStartLocation(Toggle):
    """Spawn straight in Elm's Lab instead of New Bark Town.

    You still choose your starter the normal way. Once chosen, the lab's
    exit door sends you to a random Johto town (pick which one with
    `starting_town`) instead of back outside in New Bark.

    Off by default. The game logic fully accounts for your new starting
    town, this is not just cosmetic."""

    display_name = "Randomize Start Location"


class StartingTown(Choice):
    """Which Johto town you arrive in after choosing your starter.

    Only matters if `randomize_start_location` is on. Set to `random` in
    your YAML for a random town each seed."""

    display_name = "Starting Town"
    option_cherrygrove = 1
    option_violet = 2
    option_azalea = 3
    option_cianwood = 4
    option_goldenrod = 5
    option_olivine = 6
    option_ecruteak = 7
    option_mahogany = 8
    option_lake_of_rage = 9
    option_blackthorn = 10
    default = 1


class RandomizeBag(Toggle):
    """Turn the Bag into a real item you must find, instead of getting it
    for free. Off by default."""

    display_name = "Randomize Bag"


class RandomizeTrainerCard(Toggle):
    """Turn the Trainer Card into a real item you must find, instead of
    getting it for free. Off by default."""

    display_name = "Randomize Trainer Card"


class RandomizePokedex(Toggle):
    """Turn the Pokedex into a real item you must find, instead of
    getting it for free. Off by default.

    Note: catching Pokemon still counts for Dexsanity right away even
    before you have this. Only the pause menu icon is locked."""

    display_name = "Randomize Pokedex"


class RandomizePokegear(Toggle):
    """Turn the Pokegear into a real item you must find, instead of
    getting it for free. Off by default."""

    display_name = "Randomize Pokegear"


class RandomizeSaveButton(Toggle):
    """Turn the Save menu button into a real item you must find, instead
    of getting it for free. Off by default."""

    display_name = "Randomize Save Button"


class RandomizeOptionsButton(Toggle):
    """Turn the Options menu button into a real item you must find,
    instead of getting it for free. Off by default."""

    display_name = "Randomize Options Button"


class RandomizeBicycle(Toggle):
    """Turn the Bicycle into a real item you must find, instead of
    getting it for free from the Goldenrod Bike Shop. Off by default."""

    display_name = "Randomize Bicycle"


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


class RandomizeMoveCategories(Toggle):
    """Randomly swap each damaging move between Physical and Special.
    Status moves are never changed."""

    display_name = "Randomize Move Categories"


class RandomizeTmMoves(Toggle):
    """Shuffle which move each TM teaches. HMs always keep their vanilla
    move, so field moves like Surf still work normally."""

    display_name = "Randomize TM Moves"


class RandomizeTypeChart(Toggle):
    """Shuffle type matchups (what is super effective, not very
    effective, or has no effect). The same number of each still exists,
    just moved to different type pairs."""

    display_name = "Randomize Type Chart"


class StartingMoney(Range):
    """How much money you start the game with. Vanilla is 3000. Set to
    `random` in your YAML for a random amount up to 5000."""

    display_name = "Starting Money"
    range_start = 0
    range_end = 5000  # capped well below MAX_MONEY (999999) to keep `random` sane
    default = 3000


class JohtoOnly(Toggle):
    """Remove all of Kanto from the game. No Kanto locations, no Kanto
    badges in the item pool.

    Johto's own Elite Four and the post game Red fight still work
    normally. If your goal is `n_badges` and you asked for more than 8,
    it gets capped to 8 automatically."""

    display_name = "Johto Only"


class ExtraRouteBlockers(Toggle):
    """Close a real shortcut on Route 46 that lets you skip most of the
    game with almost no items.

    Off by default, keeps the shortcut. On, forces the normal route
    through Mahogany instead. Safe with any other option, nothing
    becomes unreachable."""

    display_name = "Extra Route Blockers"


class RandomizeSpeciesTypes(Toggle):
    """Randomize each Pokémon species' Type(s). A species keeps its
    original single-type/dual-type status -- only *which* type(s) is
    randomized. Never assigns the "???" (Mystery) type, same reasoning as
    `randomize_move_types`. Unrelated to `randomize_base_stats` (stats)
    and TM/HM compatibility/learnsets (unaffected by this option)."""

    display_name = "Randomize Species Types"


class RandomizeLearnsets(Toggle):
    """Randomize which move each Pokemon learns at each level. The
    levels themselves stay the same, only the moves change."""

    display_name = "Randomize Learnsets"


class TrainerLevelScaling(Range):
    """Scale every trainer Pokémon's level by this percentage (100 = vanilla
    levels, unchanged). A difficulty knob, not a randomizer -- the same
    percentage applies uniformly to every trainer, every generation. Levels
    are clamped to HGSS's own 1-100 range after scaling.

    Ignored when `sphere_based_trainer_leveling` is on.
    """

    display_name = "Trainer Level Scaling"
    range_start = 50
    range_end = 200
    default = 100


class SphereBasedTrainerLeveling(Toggle):
    """Rescale every trainer's levels to match how deep into *this seed's
    own randomized region graph* they actually sit, instead of vanilla's
    fixed story order -- a trainer near the start of your reachable area
    gets an easy level, one behind a lot of required items gets a hard
    one, regardless of where they'd be in a vanilla playthrough.

    Computed after the world is filled, from the real order items become
    available in this seed -- not a live in-game read, and not related to
    your own party's actual levels. Each trainer's party keeps its own
    internal level spread, just re-centered on a level appropriate for
    when you can reach them. Overrides `trainer_level_scaling` when on.

    Covers every regular trainer battle and every Gym Leader (scaled
    against their own separate curve, so a Leader stays boss-tier
    relative to the other Leaders instead of being pulled toward this
    seed's single weakest regular trainer). Elite Four members and
    rivals are left at their vanilla level -- neither has a reliably
    known region in this world's own data.
    """

    display_name = "Sphere-Based Trainer Leveling"


class SphereBasedTrainerLevelingBonus(Range):
    """Shift every level computed by `sphere_based_trainer_leveling` by
    this many levels before clamping to HGSS's 1-100 range -- negative
    makes every trainer easier, positive makes every trainer harder.
    Ignored when `sphere_based_trainer_leveling` is off.
    """

    display_name = "Sphere-Based Trainer Leveling Bonus"
    range_start = -20
    range_end = 20
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


class HiddenItemsRequireDowsingMachine(Toggle):
    """Require owning the Dowsing Machine in logic before any hidden item
    location is considered reachable.

    Off by default: vanilla never actually requires it to pick up an
    already-known hidden item (it's purely a detection aid, not a real
    gate), matching this world's own accessibility assumptions everywhere
    else.
    """

    display_name = "Hidden Items Require Dowsing Machine"


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


class DexsanityTrigger(Choice):
    """What counts as "getting" a species for `dexsanity` purposes.

    - catch: the check fires when you actually catch that species for
      the first time (Pokédex.caughtSpecies) -- the original behavior.
    - encounter: the check fires the moment you merely see that species
      in a wild encounter (Pokédex.seenSpecies), no catch required --
      much faster to complete, since a single battle (or even just
      running from one) is enough.

    Ignored when `dexsanity` is off.
    """

    display_name = "Dexsanity Trigger"
    option_catch = 0
    option_encounter = 1
    default = 0


class DexsanityEncounterTypes(OptionSet):
    """Which wild-encounter methods count toward `dexsanity` in the
    first place -- a species only obtainable through a method you
    deselect here gets no Dexsanity check at all this seed (same as a
    species this seed's own wild tables never place anywhere).

    All methods are on by default (matches the original, unrestricted
    behavior). Turn a method off if you don't want, say, fishing to be
    required to finish the Pokédex.

    Ignored when `dexsanity` is off.
    """

    display_name = "Dexsanity Encounter Types"
    valid_keys = {"land", "surf", "rock_smash", "old_rod", "good_rod", "super_rod", "headbutt"}
    default = frozenset(valid_keys)


class Legendarysanity(Toggle):
    """Add a check for catching Ho-Oh (Bell Tower) and Lugia (Whirl
    Islands), both only reachable after defeating the Elite Four/Champion,
    matching vanilla.

    Off by default: with this off, both stay exactly as in vanilla (same
    place, same post-Elite Four requirement) -- they're just not tracked
    as an Archipelago check, matching how other Pokemon Archipelago worlds
    treat static legendary encounters.
    """

    display_name = "Legendarysanity"


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
    johto_only: JohtoOnly
    extra_route_blockers: ExtraRouteBlockers

    randomize_wild_pokemon: RandomizeWildPokemon
    randomize_starters: RandomizeStarters
    randomize_start_location: RandomizeStartLocation
    starting_town: StartingTown
    randomize_bag: RandomizeBag
    randomize_trainer_card: RandomizeTrainerCard
    randomize_pokedex: RandomizePokedex
    randomize_pokegear: RandomizePokegear
    randomize_save_button: RandomizeSaveButton
    randomize_options_button: RandomizeOptionsButton
    randomize_bicycle: RandomizeBicycle
    randomize_trainers: RandomizeTrainers
    exclude_legendaries: ExcludeLegendaries
    randomize_evolutions: RandomizeEvolutions
    randomize_base_stats: RandomizeBaseStats
    randomize_moves: RandomizeMoves
    randomize_move_types: RandomizeMoveTypes
    randomize_move_categories: RandomizeMoveCategories
    randomize_tm_moves: RandomizeTmMoves
    randomize_type_chart: RandomizeTypeChart
    starting_money: StartingMoney
    randomize_species_types: RandomizeSpeciesTypes
    randomize_learnsets: RandomizeLearnsets
    trainer_level_scaling: TrainerLevelScaling
    sphere_based_trainer_leveling: SphereBasedTrainerLeveling
    sphere_based_trainer_leveling_bonus: SphereBasedTrainerLevelingBonus

    hidden_items_require_dowsing_machine: HiddenItemsRequireDowsingMachine

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
    dexsanity_trigger: DexsanityTrigger
    dexsanity_encounter_types: DexsanityEncounterTypes
    legendarysanity: Legendarysanity

    start_inventory_from_pool: StartInventoryPool


OPTION_GROUPS = [
    OptionGroup(
        "Game Version",
        [GameVersion],
    ),
    OptionGroup(
        "Goal",
        [Goal, GoalBadgeCount, JohtoOnly, ExtraRouteBlockers],
    ),
    OptionGroup(
        "Randomizers",
        [
            RandomizeWildPokemon,
            RandomizeStarters,
            RandomizeStartLocation,
            StartingTown,
            RandomizeBag,
            RandomizeTrainerCard,
            RandomizePokedex,
            RandomizePokegear,
            RandomizeSaveButton,
            RandomizeOptionsButton,
            RandomizeBicycle,
            ExcludeLegendaries,
            RandomizeTrainers,
            RandomizeEvolutions,
            RandomizeBaseStats,
            RandomizeMoves,
            RandomizeMoveTypes,
            RandomizeMoveCategories,
            RandomizeTmMoves,
            RandomizeTypeChart,
            StartingMoney,
            RandomizeSpeciesTypes,
            RandomizeLearnsets,
            TrainerLevelScaling,
            SphereBasedTrainerLeveling,
            SphereBasedTrainerLevelingBonus,
            HiddenItemsRequireDowsingMachine,
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
        [Trainersanity, Dexsanity, DexsanityTrigger, DexsanityEncounterTypes, Legendarysanity],
        start_collapsed=True,
    ),
]
