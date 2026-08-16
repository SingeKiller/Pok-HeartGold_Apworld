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
    """Spawn already inside Prof. Elm's Lab instead of New Bark's player
    house -- the walk through New Bark, Mom, and the outdoor overworld
    are skipped, but the starter-choice scene itself is NOT: you still
    pick your own starter from a real 3-way in-game choice (its species
    pool is controlled by `randomize_starters`, same as vanilla start).
    The moment you pick one, your Bag/Trainer Card/Save button/Options
    button/Pokédex/Pokégear are unlocked (vanilla would normally unlock
    these via New Bark content this option skips) -- except for whichever
    of those `randomize_menu_unlocks` turns into a real item instead, which
    wait for that item like normal -- and leaving the lab's only door
    warps you to a random Johto town (see `starting_town` to choose which
    one) instead of back outside in New Bark.

    Off by default (vanilla intro, unchanged). Live-verified end to end
    (2026-08-17): spawn point, unmodified starter-choice scene, exit-door
    redirect (tested against 3 different destination towns), and the
    menu-unlock flags all confirmed working together on the real US
    HeartGold ROM.

    Logic-integrated, not just cosmetic: this project's own region graph
    treats the chosen `starting_town` as the actual free/reachable origin
    (not New Bark) -- Archipelago's own fill algorithm genuinely accounts
    for where the player starts. All 10 candidate towns verified
    completable via real generation + fill (`tests/test_world_init.py`)."""

    display_name = "Randomize Start Location"


class StartingTown(Choice):
    """Only used when `randomize_start_location` is on: which Johto town
    Elm's Lab's exit door sends you to. Set this to `random` in your
    YAML for Archipelago's own generator-side randomization (no separate
    on/off toggle needed) -- the plain default below is just a concrete
    fallback value, not this option's actual intended behavior. Mount
    Silver/Indigo Plateau and every Kanto town are deliberately not
    offered -- see `randomize_start_location`'s own docstring for why."""

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


class RandomizeMenuUnlocks(OptionSet):
    """Turn any of these 6 pause-menu icons into a real, shufflable AP
    item instead of always being unlocked for free: `bag`, `trainer_card`,
    `pokedex`, `pokegear`, `save_button`, `options_button`. Each one you
    pick here becomes a real Location (where its flag is set in vanilla --
    New Bark's Mom scene for all but `pokedex`, Route 30's Mr. Pokémon for
    `pokedex`) holding a real, tradeable item -- pick this one up as
    someone else's check, or find it anywhere else in the multiworld,
    before that icon appears in your own pause menu.

    None selected by default (matches vanilla: every icon unlocks the
    normal way, no effect on generation).

    None of these gate reachability anywhere in this project's own rules
    -- they're all `useful`, not `progression` -- so combine freely with
    `randomize_start_location` (which otherwise unlocks the same icons for
    free once you pick a starter; whichever ones you list here are excluded
    from that automatic grant and wait for the real item instead).

    Real, decomp-confirmed gap, not fixed by this option: the flag this
    project can read/write only gates the pause-menu icon itself (src/
    sys_flags.c's CheckGotMenuIconI) -- it doesn't touch whatever else the
    vanilla scene also does alongside it. In particular, catching a
    Pokémon still populates Dexsanity/the real Pokédex data immediately
    regardless of whether you've received `menu_unlock_pokedex` yet -- only
    the icon (and therefore being able to open the Pokédex screen from the
    pause menu) is what's actually gated."""

    display_name = "Randomize Menu Unlocks"
    valid_keys = {"bag", "trainer_card", "pokedex", "pokegear", "save_button", "options_button"}
    default = frozenset()


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
    """Randomize each damaging move's Category (Physical/Special) --
    Generation IV determines damage stat (Attack/Sp. Attack) and defense
    stat (Defense/Sp. Defense) per move, not per type, so this is a real,
    engine-honored split (unlike Gen 1-3/5's type-based category). Status
    moves (Category = Status) are never touched either direction -- a
    damaging move never becomes Status and a Status move never becomes
    damaging, since that would leave a 0-power "damaging" move or a
    Status move that deals damage with no stat behind it. Independent of
    `randomize_move_types`/`randomize_moves`."""

    display_name = "Randomize Move Categories"


class RandomizeTmMoves(Toggle):
    """Shuffle which move each TM (TM01-TM92) teaches -- a permutation, so
    the same 92 moves stay available, just reassigned across machine
    numbers. HM01-HM08 always keep their vanilla move (Cut/Fly/Surf/
    Strength/Whirlpool/Rock Smash/Waterfall/Rock Climb) -- this project's
    region-access rules key off owning the HM item, not whatever move it
    currently teaches, so randomizing HM-taught moves would risk a player
    logically having "Surf" (per AP rules) but being unable to actually
    Surf in the field."""

    display_name = "Randomize TM Moves"


class RandomizeTypeChart(Toggle):
    """Shuffle the type-effectiveness chart's resistances/weaknesses/
    immunities -- a permutation, so the same overall mix (how many
    super-effective/not-very-effective/no-effect matchups exist) still
    exists, just redistributed onto different attacker/defender type
    pairs. Any (attacker, defender) pair not already an exception in the
    vanilla chart stays a normal (1x) matchup either way -- this option
    never creates a brand new exception, only reassigns which pairs the
    existing exceptions apply to. Independent of `randomize_move_types`/
    `randomize_species_types` (those change which type a move/species
    *is*; this changes what the types themselves *do* to each other)."""

    display_name = "Randomize Type Chart"


class StartingMoney(Range):
    """How much money the player starts the game with (vanilla is 3000).
    A plain fixed value by default -- set this to `random` in your YAML
    for Archipelago's own generator-side randomization (no separate
    on/off toggle needed). Applied once, client-side, on first connection
    to this slot -- guarded by a flag this world stores server-side (not
    a "money still looks vanilla" heuristic, which could misfire if the
    player's money later happens to pass back through the same value),
    so a later reconnect never re-applies it and wipes out money the
    player has since earned or spent."""

    display_name = "Starting Money"
    range_start = 0
    range_end = 5000  # capped well below MAX_MONEY (999999) to keep `random` sane
    default = 3000


class JohtoOnly(Toggle):
    """Exclude all of Kanto (180 regions -- every Kanto town/route/cave/
    building, the S.S. Aqua ferry, and the Kanto side of the Goldenrod<->
    Saffron Magnet Train) from the region graph entirely: no location is
    created there, and Kanto's 8 badges are never added to the item pool.
    Johto's own Elite Four/Champion Lance and the post-game Red fight on
    Mount Silver are unaffected -- both sit on the Johto side of the
    graph and need no Kanto badge to reach in this project's own rules.
    If `goal` is `n_badges` and `goal_badge_count` is above 8, it's
    silently capped to 8 when this is on (only Johto's badges exist)."""

    display_name = "Johto Only"


class ExtraRouteBlockers(Toggle):
    """Close a real, documented vanilla shortcut for extra difficulty:
    Route 46's one-way ledge down into Route 45 (public route-guide
    knowledge -- no known vanilla mechanism ever reverses a ledge drop).

    Off by default, this shortcut is left exactly as vanilla and lets a
    player reach 7 of Johto's 16 badges (Violet, Azalea, Goldenrod,
    Ecruteak, Cianwood, Olivine, Blackthorn) with effectively zero items
    -- found via real tester spoiler-log feedback (2026-08-15/16, see
    docs/scope.md's "Region graph logic fixes" entry), and deliberately
    kept rather than treated as a bug to patch. Turning this on removes
    that single edge from the region graph entirely, forcing the normal
    Mahogany/Ice Path route into that side of the map instead -- purely a
    difficulty toggle, not a bugfix, since the shortcut is genuine vanilla
    behavior. Safe to combine with anything else: that side of the map is
    also reachable the normal way regardless of any other option, so this
    never disconnects anything, only closes one detour."""

    display_name = "Extra Route Blockers"


class RandomizeSpeciesTypes(Toggle):
    """Randomize each Pokémon species' Type(s). A species keeps its
    original single-type/dual-type status -- only *which* type(s) is
    randomized. Never assigns the "???" (Mystery) type, same reasoning as
    `randomize_move_types`. Unrelated to `randomize_base_stats` (stats)
    and TM/HM compatibility/learnsets (unaffected by this option)."""

    display_name = "Randomize Species Types"


class RandomizeLearnsets(Toggle):
    """Randomize which move each species learns at each level-up slot.
    The level itself is untouched -- only which move lands there. Purely
    cosmetic to this project's own logic: unlike `randomize_tm_moves`, no
    region-access rule anywhere depends on which move a species learns by
    leveling up (only on owning the HM item), so there is no HM-safety
    concern to work around here."""

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
    randomize_menu_unlocks: RandomizeMenuUnlocks
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
            RandomizeMenuUnlocks,
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
