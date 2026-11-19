from __future__ import annotations

from dataclasses import dataclass

from Options import (
    Choice,
    DeathLink,
    DefaultOnToggle,
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

    Any mode other than vanilla also randomizes the species that only show
    up in special cases: swarms (land, surf and fishing), the night fishing
    species and the species heard through the radio sounds. Those are never
    expected by the logic. The AREA page of the Pokedex then shows where each
    species lives in this seed (swarms and radio species excluded).

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


class RandomizeTrades(Toggle):
    """Randomize the 9 in-game trades: each one offers a random Pokemon, named
    after its species, and asks for a random species that this seed places in
    the wild. Kirk's Shuckle, the Spearow carrying Kenya's mail and the other
    gifts or loans are not changed. Trades are never expected by the logic.
    Off by default."""

    display_name = "Randomize Trades"


class RandomizeStaticPokemon(Toggle):
    """Replace the Pokemon the game hands out or fixes in place with random
    species, one per spot and never the same species twice: the Kanto and
    Hoenn starters, the fossil revivals, Tyrogue, Dratini, Eevee, Tentacool,
    the legendary and static encounters (Mewtwo, the three birds, Suicune,
    Lugia, Rayquaza, Latios and Latias, Snorlax, Lapras, Sudowoodo, Red
    Gyarados, the Rocket Headquarters Electrodes). Levels stay the same.
    Ho-Oh, Kyogre, Groudon, the Togepi egg, the loaned Shuckle and Spearow and
    distribution gifts are never changed because the game checks for them,
    and Lugia stays as is when `legendarysanity` is on.
    `exclude_legendaries` removes legendaries from the draw. These Pokemon are
    never expected by the logic. Off by default."""

    display_name = "Randomize Static Pokémon"


class ExcludeLegendaries(Toggle):
    """Never place a legendary or mythical Pokémon (Articuno through
    Arceus) in the wild encounter pool when `randomize_wild_pokemon` is
    set to `full_random` or `zone_method_mapping`, as a starter when
    `randomize_starters` is on, or in a trainer's party when
    `randomize_trainers` is on. Has no effect on `vanilla`/`shuffle` --
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
    """Start your adventure in another Johto town.

    The whole opening plays out exactly like vanilla: you wake up at
    home, talk to Mom, walk out into New Bark Town, go to Elm's Lab and
    choose your starter the normal way. Only the lab's exit door changes:
    instead of putting you back in New Bark, it sends you to a Johto town
    of your choice (pick which one with `starting_town`).

    Off by default. The game logic fully accounts for your new starting
    town, this is not just cosmetic.

    The door only stays redirected until you have used it: once you are
    out in your new town, the client puts it back to normal, so later
    visits to the lab let you walk out into New Bark like in vanilla. That
    fix is re-applied automatically every time you relaunch BizHawk, so
    keep the client connected."""

    display_name = "Randomize Start Location"


class StartingTown(Choice):
    """Which Johto town you arrive in after choosing your starter.

    Only matters if `randomize_start_location` is on. Set to `random` in
    your YAML for a random town each seed."""

    display_name = "Starting Town"
    option_cherrygrove = 1
    option_violet = 2
    option_azalea = 3
    option_goldenrod = 5
    option_olivine = 6
    option_ecruteak = 7
    option_mahogany = 8
    option_blackthorn = 10
    default = 1


class RandomizeBicycle(Toggle):
    """Turn the Bicycle into a real item you must find, instead of
    getting it for free from the Goldenrod Bike Shop. Off by default."""

    display_name = "Randomize Bicycle"


class RandomizeTrainers(Toggle):
    """Randomize trainer Pokémon parties (Gym Leaders, Rivals, Elite Four, Red, and regular trainers)."""

    display_name = "Randomize Trainers"


class SimilarStrengthTrainers(Toggle):
    """With `randomize_trainers`, each trainer Pokémon is replaced by a
    species of similar strength: its base stat total stays within 15% of
    the original species' total (the window widens step by step only if no
    species fits). Also follows `exclude_legendaries`. No effect when
    `randomize_trainers` is off. Off by default."""

    display_name = "Similar Strength Trainers"


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
    - balanced: same idea, but Power and Accuracy are drawn *together*
      from weighted tiers instead of independently, so a big number never
      comes with a coin-flip accuracy: reliable 50% (55-95 power, 100
      accuracy), strong 25% (110-145, 95-100), heavy 20% (150-195, 85-95),
      devastating 5% (210-250, 75-85). Accuracy never goes below 75. The
      bands mirror real HGSS move data (60% of damaging moves are already
      100 accuracy, and vanilla never charges power in accuracy at the top:
      Explosion 250/100, Hyper Beam 150/90), and the weights put the median
      power around 75 versus vanilla's 70. PP is drawn exactly like
      full_random draws it -- deliberately, so all modes treat that column
      the same way. Status moves keep 0 power, one-hit-KO moves keep their
      vanilla 30 accuracy, and never-miss moves (Swift, Aerial Ace, Aura
      Sphere) stay never-miss.
    """

    display_name = "Randomize Moves"
    option_off = 0
    option_shuffle = 1
    option_full_random = 2
    option_balanced = 3
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
    range_end = 5000
    default = 3000


class JohtoOnly(Toggle):
    """Remove all of Kanto from the game. No Kanto locations, no Kanto
    badges in the item pool.

    Johto's own Elite Four still works normally. Red cannot be reached
    (Mt. Silver opens from Kanto), so the `champion_red` goal is refused.
    If your goal is `n_badges` and you asked for more than 8, it gets
    capped to 8 automatically."""

    display_name = "Johto Only"


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


class RandomizeAbilities(Toggle):
    """Give every Pokémon species random abilities. A species with one
    ability still has one, a species with two different ones gets two
    different ones.
    Wonder Guard, Forecast and Multitype are never given. Applied before
    `disable_trapping_abilities`, so that option still removes any
    trapping ability drawn here. Off by default."""

    display_name = "Randomize Abilities"


class RandomizeTmCompatibility(Choice):
    """Randomize which Pokémon species can learn which TMs.
    Vanilla: nothing changes. Half: every species can learn each of the 92
    TMs with a one in two chance. Full: every species can learn every TM.
    In both randomized modes every species can learn all 8 HMs and the Flash
    TM, so the logic that assumes you can use your HMs never breaks. Off by
    default."""

    display_name = "Randomize TM Compatibility"
    option_vanilla = 0
    option_half = 1
    option_full = 2
    default = 0


class RandomizeWildHeldItems(Toggle):
    """Give every Pokémon species a random common and a random rare held item
    for wild Pokémon, drawn from ordinary items only (medicine, balls,
    berries, battle items and regular held items). About half of the species
    keep no common item and about three in four keep no rare item, so wild
    Pokémon do not flood you with items. Key items, TMs, HMs and mail are
    never given, and these items are never part of the logic. Off by
    default."""

    display_name = "Randomize Wild Held Items"


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
    - pokedex: catch a configurable number of species (see the
      `goal_pokedex_count` option). Only species that can be caught in the
      wild in your seed count.
    - legendary_hunt: catch a configurable number of the fixed legendary
      Pokemon (see the `goal_legendary_count` option). Works with or without
      `legendarysanity`.
    """

    display_name = "Goal"
    option_elite_four = 0
    option_champion_red = 1
    option_n_badges = 2
    option_pokedex = 4
    option_legendary_hunt = 5
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


class GoalPokedexCount(Range):
    """Number of species you must have caught in your Pokedex to win when the
    `goal` option is set to `pokedex`. Ignored for any other `goal` value.

    Only species that can be caught in the wild in your seed count, so the value
    is lowered to that number if it is higher (for example with `johto_only`).
    """

    display_name = "Goal Pokedex Count"
    range_start = 1
    range_end = 493
    default = 150


class GoalLegendaryCount(Range):
    """Number of fixed legendary Pokemon you must catch to win when the `goal`
    option is set to `legendary_hunt`. Ignored for any other `goal` value.

    Your world holds 6 of them (Ho-Oh, Lugia, Zapdos, Mewtwo, Articuno,
    Moltres). A higher value than your world holds is lowered to what it holds
    (for example with `johto_only`). Only a catch counts, defeating the
    legendary does not. The count follows the legendary encounter itself, so it
    still works when `randomize_static_pokemon` replaces the Pokemon found
    there. Roaming legendaries, Suicune, and the Hoenn legendaries do not
    count.
    """

    display_name = "Goal Legendary Count"
    range_start = 1
    range_end = 6
    default = 3


class EliteFourBadges(Range):
    """How many badges, from Johto or Kanto, the logic expects you to own before
    it sends you into the Pokemon League. As in the original game, the League door
    itself checks nothing, so you may go earlier at your own risk. With
    `johto_only` on, values above 8 count as 8. Default 8."""

    display_name = "Elite Four Badges"
    range_start = 0
    range_end = 16
    default = 8


class BlueKantoLeaders(Range):
    """How many of the 7 other Kanto Gym Leaders you must beat before Blue, on
    Cinnabar Island, agrees to wait for you in the Viridian Gym. Badges received
    from other players do not count, only Leaders beaten. Default 7, as in the
    original game."""

    display_name = "Kanto Leaders for Blue"
    range_start = 0
    range_end = 7
    default = 7


class RedBadges(Range):
    """How many of the 16 badges you must own before Prof. Oak, in Pallet Town,
    gives you Rock Climb and opens the way to Route 28 and Mt. Silver. Badges
    received from other players count. Below 16, beating Blue is no longer
    required for this. Default 16, as in the original game, where Blue is the
    last gym."""

    display_name = "Badges for Red"
    range_start = 0
    range_end = 16
    default = 16


class RequireFlash(Toggle):
    """Require Flash (TM70) in logic before entering a dark cave: Rock
    Tunnel, Dark Cave, the first two floors of the Whirl Islands and Cerulean
    Cave (the maps the game itself darkens until Flash is used).

    Off by default: the caves can be crossed in the dark, it is only harder
    to see where you are going.
    """

    display_name = "Require Flash"


class HiddenItemsRequireDowsingMachine(Toggle):
    """Require owning the Dowsing Machine in logic before any hidden item
    location is considered reachable.

    Hidden items are always part of the pool; this option does not remove
    them. Off by default: in game you can pick up a hidden item by pressing
    A on its tile without the Dowsing Machine, so the logic does not wait
    for it.
    """

    display_name = "Hidden Items Require Dowsing Machine"


class MagnetTrain(DefaultOnToggle):
    """Open the Goldenrod <-> Saffron Magnet Train as an early way into Kanto.

    In the game the train needs two things: the Magnet Train Pass, and the
    Kanto Power Plant repaired (a policeman blocks both stations until
    then). The Power Plant is in Kanto, so without help the train can never
    be the way in, and the S.S. Aqua only sails once the Elite Four and the
    Champion are beaten.

    On by default: the Kanto Power Plant is considered repaired from the
    very start of your game. The Magnet Train can therefore be used as soon
    as you have the Pass, and Kanto can be visited long before the Pokemon
    League. The Machine Part quest is skipped: you never have to bring the
    part back to the Power Plant (Misty and the Cerulean Gym Rocket still
    play out as usual). The Power Plant manager's TM57, only handed over
    at the end of that quest, is removed from the locations.

    Turn it off to keep Kanto as late-game content: the train then counts
    only once the Power Plant has really been repaired, which needs you to
    be in Kanto already, so nothing you need can be hidden over there
    before the League. The Pass no longer opens anything a seed needs, so
    it is placed as a merely useful item instead of a progression one.
    """

    display_name = "Magnet Train"


class RemoteItems(Toggle):
    """Never write your own items directly into the game -- always
    receive them from the server instead, the same way you already
    receive items from other players.

    Off by default. Turn this on if you want to share your save file
    between multiple people, or if you want to restart a corrupted save
    without losing progress: the server just resends everything you
    already found."""

    display_name = "Remote Items"


class Trainersanity(Toggle):
    """Add a check for every trainer battle won.

    Off by default.
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

    The two 1% grass slots and the 1% Surf slot are ignored: a species
    only found there gets no check.

    Off by default.
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

    "headbutt" covers the Pokemon found by using Headbutt on trees. The
    logic expects you to have reached the Headbutt tutor in Ilex Forest
    first, since the move has no TM in this game.

    Ignored when `dexsanity` is off.
    """

    display_name = "Dexsanity Encounter Types"
    valid_keys = {"land", "surf", "rock_smash", "old_rod", "good_rod", "super_rod", "headbutt"}
    default = frozenset(valid_keys)


class TrainersanityCount(Range):
    """With `trainersanity` on, how many trainer battles are checks, picked
    at random among every trainer this seed has (all of them by default).
    Ignored when `trainersanity` is off."""

    display_name = "Trainersanity Count"
    range_start = 1
    range_end = 390
    default = 390


class DexsanityCount(Range):
    """With `dexsanity` on, how many species are checks at most, picked at
    random among the species this seed's wild tables really hold (all of
    them by default). Ignored when `dexsanity` is off."""

    display_name = "Dexsanity Count"
    range_start = 1
    range_end = 493
    default = 493


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


class RandomizeShopItems(Toggle):
    """Changes what the specialty counter of the 13 town Poke Marts sells: any
    item can appear, HMs and TMs included. HMs and TMs are sold one at a time and
    leave the list once you own them; each counter also keeps a consumable (ball,
    medicine or battle item). The other shops and the regular counter do not
    change, so Poke Balls and Potions can always be bought. Key items stay out of
    these lists unless Shop Key Items is on. While this is on, each wild Pokemon
    you defeat also gives 20 money. Off by default."""

    display_name = "Randomize Shop Items"


class ShopKeyItems(Toggle):
    """Lets Randomize Shop Items also sell key items, such as the Bicycle or the
    S.S. Ticket, one at a time for 500 or 1000. WARNING: buying a story item can
    reach places early and may disturb that story's scripts. The logic does not
    count on these purchases. Does nothing without Randomize Shop Items. Off by
    default."""

    display_name = "Shop Key Items"


class Shopsanity(Toggle):
    """The specialty counter of every town Poke Mart (13 in Johto and Kanto)
    also sells two items from the multiworld, 26 checks in all. Each one can
    be bought once; the shop shows its name, and the price depends on how
    useful the item is. While this is on, each wild Pokemon you defeat also gives
    20 money, so you can always earn enough to buy them. Off by default."""

    display_name = "Shopsanity"


class GameCornerPrizes(Toggle):
    """The ten item prizes of the Goldenrod Game Corner and the ten of the Celadon
    Game Corner prize counter become checks, 20 in all. Each one can be taken once
    and costs only 50 Coins (win them at Voltorb Flip) instead of 1000 to 15000.
    The counter menu shows the item you will get and who it is for. The Pokemon
    prizes do not change. The logic needs the Coin Case. Celadon is left out with
    Johto Only. Off by default."""

    display_name = "Game Corner Prizes"


class ApricornTrees(Toggle):
    """The first time you pick the Apricorn from each of the 31 Apricorn trees of
    Johto and Kanto is a check. The trees still give their Apricorn every day as
    usual. The logic needs the Apricorn Box, and some trees also need Cut or Surf
    (with their badges). Kanto is left out with Johto Only. Off by default."""

    display_name = "Apricorn Trees"


class BugContest(Toggle):
    """Taking part in the Bug-Catching Contest of the National Park becomes a
    check. It is sent when the contest ends and is judged, whatever your rank and
    even if you caught nothing, so you can enter and finish at once. The check is
    given once. The contest also takes place every day instead of only on
    Tuesday, Thursday and Saturday, still once per day, and the usual contest
    prize is still given. Off by default."""

    display_name = "Bug-Catching Contest"


class DisableOhkoMoves(Toggle):
    """Neutralize the four One-Hit KO moves (Guillotine, Horn Drill,
    Fissure, Sheer Cold): each becomes an ordinary 60 power / 100 accuracy
    move with no special effect, instead of an RNG-based instant KO.

    A Nuzlocke aid, not a
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

    A Nuzlocke aid, not a
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


class RunningShoesAtStart(Toggle):
    """Start with the Running Shoes instead of waiting for the Cherrygrove
    Guide Gent's tour, which a random start can skip. Given by this
    client as soon as the save exists. Off by default (vanilla behavior
    unchanged)."""

    display_name = "Running Shoes at Start"


class MapCardAtStart(Toggle):
    """Start with the Pokegear's Map Card instead of waiting for the
    Cherrygrove Guide Gent's tour, which a random start can skip. Given by
    this client as soon as the save exists. Off by default (vanilla
    behavior unchanged)."""

    display_name = "Map Card at Start"


class FlyPointsAtStart(Toggle):
    """Every Johto town is a Fly destination from the start, instead of
    only the towns already visited (Mt. Silver and Kanto stay as vanilla).
    Fly itself still needs HM02 and the Storm Badge. The logic does not
    count on it: flying to a town never visited can reach checks earlier
    than the logic expects. Off by default (vanilla behavior unchanged)."""

    display_name = "Fly Points at Start"


class UnlockButton(DefaultOnToggle):
    """A way out if you ever get stuck, in the in-game Options screen. WARNING:
    this removes the SOUND setting, the UNLOCK row takes its place, so Stereo
    and Mono can no longer be changed and the game stays in Stereo. Set UNLOCK
    to ON and choose CONFIRM: on your next step you return to the last Pokemon
    Center you visited, with your party healed. No DeathLink is sent. The
    client must be connected, and it does not work in the Safari Zone. On by
    default; turn it off to keep the SOUND setting."""

    display_name = "Unlock Button"


class ForgetHmMoves(DefaultOnToggle):
    """HM moves can be replaced like any other move: when a Pokemon learns a
    new move, by level up or with a TM or HM, you may choose to forget Surf,
    Cut or any other HM move. HMs are never used up, so you can teach them
    again at any time. On by default; turn it off for the vanilla rule (HM
    moves can only be removed by the Move Deleter)."""

    display_name = "Forget HM Moves"


class HmsWithoutTeaching(Toggle):
    """Cut, Rock Smash, Strength, Rock Climb, Surf, Waterfall and Whirlpool can be
    used on their obstacle as soon as the matching HM is in your Bag (with the
    usual badge), even if no Pokemon of your team knows the move. If a Pokemon
    knows the move it is used as usual; otherwise the first healthy Pokemon of
    your team does it. Going down a waterfall while surfing is always allowed so
    that you can never be stuck at the top of one. Fly and Flash are not covered:
    they still need a Pokemon that knows the move. Off by default."""

    display_name = "HMs Without Teaching"


class HiddenItemMarkers(Toggle):
    """Shows a gold Poke Ball on every hidden item you have not taken yet, at its
    exact place. On a rock, a tree or a wall it floats above with an arrow pointing
    down at the spot. Face it and press A to take the item; the marker then
    disappears. A marker blocks its tile until then. The logic does not change. Off
    by default."""

    display_name = "Hidden Item Markers"


class ForeignItemNames(Toggle):
    """EXPERIMENTAL. When you pick up an item that belongs to another player (or one
    of your own badges placed at an item location), the game shows its real name and
    its owner instead of the generic "Item sent to another player!" text. This
    rewrites the item scripts and adds text to the game, and it has not been fully
    tested in game. Leave it off unless you want to try it. The logic does not
    change. Off by default."""

    display_name = "Foreign Item Names"


class ItemReceivedMessages(Toggle):
    """Show a message on the BizHawk screen for each item received, with
    the name of the player who found it, and for each item you send to
    another player, with the name of that player. A batch of many items at
    once (after a reload or on a new save) shows a single count instead. Off
    by default."""

    display_name = "Item Received Messages"


class GlobalExpShare(Toggle):
    """Every Pokemon in your party gains Exp. after a battle, as in the
    modern games: the Pokemon that took part split the full amount as
    usual, and every other party member gets half of it. Fainted Pokemon
    and Eggs get nothing. A held Exp. Share no longer changes anything.
    Off by default (vanilla behavior: only an Exp. Share holder shares)."""

    display_name = "Global Exp. Share"


class ExpMultiplier(Range):
    """Multiplies all Exp. gained in battle, in percent. 100 is vanilla,
    200 doubles it, 50 halves it. Applied before the Lucky Egg, trainer
    battle and traded Pokemon bonuses."""

    display_name = "Exp. Multiplier"
    range_start = 10
    range_end = 1000
    default = 100


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
        + "\n\n    In Pokemon HeartGold/SoulSilver, a death is a whiteout: "
        "whiting out sends one, and receiving one whites you out on your "
        "next step, back to the last Pokemon Center as the game itself "
        "does. Needs a ROM patched by this APWorld version or later.\n"
    )


@dataclass
class HeartGoldOptions(PerGameCommonOptions):
    game_version: GameVersion

    goal: Goal
    goal_badge_count: GoalBadgeCount
    goal_pokedex_count: GoalPokedexCount
    goal_legendary_count: GoalLegendaryCount
    johto_only: JohtoOnly

    randomize_wild_pokemon: RandomizeWildPokemon
    randomize_starters: RandomizeStarters
    randomize_start_location: RandomizeStartLocation
    starting_town: StartingTown
    randomize_bicycle: RandomizeBicycle
    randomize_trainers: RandomizeTrainers
    similar_strength_trainers: SimilarStrengthTrainers
    exclude_legendaries: ExcludeLegendaries
    randomize_trades: RandomizeTrades
    randomize_static_pokemon: RandomizeStaticPokemon
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
    randomize_abilities: RandomizeAbilities
    randomize_tm_compatibility: RandomizeTmCompatibility
    randomize_wild_held_items: RandomizeWildHeldItems
    trainer_level_scaling: TrainerLevelScaling
    sphere_based_trainer_leveling: SphereBasedTrainerLeveling
    sphere_based_trainer_leveling_bonus: SphereBasedTrainerLevelingBonus

    hidden_items_require_dowsing_machine: HiddenItemsRequireDowsingMachine
    require_flash: RequireFlash
    elite_four_badges: EliteFourBadges
    blue_kanto_leaders: BlueKantoLeaders
    red_badges: RedBadges
    magnet_train: MagnetTrain
    remote_items: RemoteItems

    disable_ohko_moves: DisableOhkoMoves
    disable_trapping_abilities: DisableTrappingAbilities

    fast_text_speed: FastTextSpeed
    running_shoes_at_start: RunningShoesAtStart
    map_card_at_start: MapCardAtStart
    fly_points_at_start: FlyPointsAtStart
    item_received_messages: ItemReceivedMessages
    unlock_button: UnlockButton
    forget_hm_moves: ForgetHmMoves
    hms_without_teaching: HmsWithoutTeaching
    hidden_item_markers: HiddenItemMarkers
    foreign_item_names: ForeignItemNames
    global_exp_share: GlobalExpShare
    exp_multiplier: ExpMultiplier
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
    shopsanity: Shopsanity
    game_corner_prizes: GameCornerPrizes
    apricorn_trees: ApricornTrees
    bug_contest: BugContest
    randomize_shop_items: RandomizeShopItems
    shop_key_items: ShopKeyItems
    trainersanity_count: TrainersanityCount
    dexsanity_count: DexsanityCount

    start_inventory_from_pool: StartInventoryPool


OPTION_GROUPS = [
    OptionGroup(
        "Game Version",
        [GameVersion],
    ),
    OptionGroup(
        "Goal",
        [Goal, GoalBadgeCount, GoalPokedexCount, GoalLegendaryCount, JohtoOnly],
    ),
    OptionGroup(
        "Randomizers",
        [
            RandomizeWildPokemon,
            RandomizeStarters,
            RandomizeStaticPokemon,
            RandomizeStartLocation,
            StartingTown,
            RandomizeBicycle,
            ExcludeLegendaries,
            RandomizeTrainers,
            SimilarStrengthTrainers,
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
            RandomizeAbilities,
            RandomizeTmCompatibility,
            RandomizeWildHeldItems,
            TrainerLevelScaling,
            SphereBasedTrainerLeveling,
            SphereBasedTrainerLevelingBonus,
            HiddenItemsRequireDowsingMachine,
            RequireFlash,
            MagnetTrain,
            RemoteItems,
        ],
    ),
    OptionGroup(
        "Nuzlocke Aids",
        [DisableOhkoMoves, DisableTrappingAbilities],
    ),
    OptionGroup(
        "Quality of Life",
        [
            FastTextSpeed,
            RunningShoesAtStart,
            MapCardAtStart,
            FlyPointsAtStart,
            ItemReceivedMessages, UnlockButton, HmsWithoutTeaching, HiddenItemMarkers, ForeignItemNames,
            GlobalExpShare,
            ExpMultiplier,
            SkipBattleAnimations,
            ReusableTms,
            ConvertTradeEvolutions,
            TradeEvolutionLevel,
        ],
    ),
    OptionGroup(
        "DeathLink",
        [HeartGoldDeathLink],
    ),
    OptionGroup(
        "Stretch Goals",
        [Trainersanity, TrainersanityCount, Dexsanity, DexsanityCount, DexsanityTrigger, DexsanityEncounterTypes,
         Legendarysanity, Shopsanity, GameCornerPrizes, ApricornTrees, BugContest, RandomizeShopItems, ShopKeyItems],
        start_collapsed=True,
    ),
]
