# species.py
#
# Randomization logic for HeartGold & SoulSilver (task C11, extended by
# task M4.5): starters, wild encounters (data/encounters.py), trainer
# parties (data/trainers.py), evolution targets, base stats
# (data/species.py) and move power/accuracy/PP (data/moves.py). This
# module only *transforms* the
# generated `data/` tables into new, equally-shaped ones -- it never mutates
# `data/*.py` itself (generated, gitignored, read-only from here) and it
# never builds any Archipelago `Region`/`Location`/`Item` object (see
# `regions.py`/`locations.py`/`items.py` for that): a later task wires these
# functions' output into the actual world (event items on encounter/trainer
# locations, etc.), same division of labour `rules.py`'s own docstring
# documents for itself.
#
# Determinism: every function that makes a random choice takes an explicit
# `rng: random.Random` parameter and only ever draws from it (`rng.choice`/
# `rng.sample`/`rng.shuffle`) -- never from the `random` module's own
# top-level functions. Once this project registers its `World` subclass (no
# `__init__.py` exists yet, see docs/architecture.md), the caller is expected
# to pass `world.random` (the `random.Random` instance Archipelago seeds
# per-multiworld from the player's seed) here. Two calls with two
# `random.Random` instances seeded identically, fed the same input data, are
# guaranteed to produce byte-for-byte identical output, because every
# randomized structure is walked in a fixed, deterministic order (plain
# dict/tuple iteration order, itself fixed by `data/*.py`'s own generation
# order -- see tests/test_randomization.py::test_wild_encounters_are_
# deterministic and friends).
#
# `options.py` (created in parallel by another agent, see task brief) now
# exists and defines `RandomizeWildPokemon`/`RandomizeTrainers`/
# `RandomizeEvolutions`/`RandomizeBaseStats`/`RandomizeMoves` (no
# `RandomizeStarters` -- starters is shelved, see `options.py`'s own
# docstring; `randomize_starters` below stays as tested, unconnected
# computation). This module deliberately does NOT import it: `options.py` itself imports `Options` from the local
# Archipelago clone (see its own docstring), and this module has no other
# reason to need that dependency (unlike `rules.py`, which genuinely needs
# `BaseClasses.Entrance`/`CollectionState` types) -- keeping it out lets
# tests/test_randomization.py exercise the actual, most important property
# here (determinism) without needing a local Archipelago checkout at all.
# Instead, the `mode`/`enabled` parameters below use plain ints/bools whose
# values are chosen to exactly match `options.py`'s own option values
# (`RandomizeWildPokemon.option_vanilla == WILD_VANILLA == 0`, etc., checked
# by tests/test_randomization.py::test_mode_constants_match_options_values
# whenever a local Archipelago checkout is available) -- a future `__init__.py`
# only needs to call e.g. `randomize_wild_encounters(world.random,
# world.options.randomize_wild_pokemon.value)` directly, no translation layer.

from __future__ import annotations

from random import Random

from data.encounters import ENCOUNTERS
from data.moves import MOVES
from data.species import SPECIES
from data.trainers import TRAINERS

# Mirrors options.RandomizeWildPokemon's option_vanilla/option_shuffle/
# option_full_random values (see this module's docstring for why they are
# duplicated here instead of imported).
WILD_VANILLA = 0
WILD_SHUFFLE = 1
WILD_FULL_RANDOM = 2

# Mirrors options.RandomizeEvolutions's option_off/option_keep_method/
# option_any_method values.
EVOLUTIONS_OFF = 0
EVOLUTIONS_KEEP_METHOD = 1
EVOLUTIONS_ANY_METHOD = 2

# Mirrors options.RandomizeBaseStats's option_off/option_shuffle/
# option_full_random values.
BASE_STATS_OFF = 0
BASE_STATS_SHUFFLE = 1
BASE_STATS_FULL_RANDOM = 2

# Mirrors options.RandomizeMoves's option_off/option_shuffle/
# option_full_random values.
MOVES_OFF = 0
MOVES_SHUFFLE = 1
MOVES_FULL_RANDOM = 2

# This order is only the sequence `randomize_base_stats` below consumes
# `rng` in (part of this module's own determinism contract) -- it is
# deliberately independent of `rom/speciesdata.py`'s
# `_BASE_STAT_FIELD_OFFSETS`, whose order is dictated by the real ROM
# struct layout instead. Both are correct for their own purpose; do not
# "align" one to the other, that would just perturb existing seeds' RNG
# draw order for no behavior change.
_BASE_STAT_FIELDS = ("hp", "atk", "def", "spatk", "spdef", "speed")
_MOVE_COMBAT_FIELDS = ("power", "accuracy", "pp")

# HGSS's vanilla starter trio (Prof. Elm's lab / rival_silver_2/rival_silver_3
# in data/trainers.py), used when starter randomization is disabled.
VANILLA_STARTERS = ("chikorita", "cyndaquil", "totodile")

_FISHING_RODS = ("old_rod", "good_rod", "super_rod")
_HEADBUTT_TIERS = ("common", "rare", "secret")


def real_species_pool(species: dict = SPECIES) -> tuple[str, ...]:
    """The 493 `data/species.py` entries with a real national Pokedex number
    -- excludes the 12 HGSS alternate forms (Deoxys x3, Wormadam x2, Giratina
    Origin, Shaymin Sky, Rotom x5, see tests/test_species.py), which are not
    sensible standalone starters/wild-encounter/trainer-party/evolution-
    target picks on their own. Sorted for a deterministic, RNG-independent
    base ordering (`rng.sample`/`rng.shuffle` below only ever consume this
    fixed sequence)."""
    return tuple(sorted(key for key, data in species.items() if data["national_dex"] is not None))


# --- 1. Starters -----------------------------------------------------------


def randomize_starters(rng: Random, enabled: bool, species: dict = SPECIES) -> tuple[str, str, str]:
    """Pick the 3 starter species (also used for the rival's own starter,
    see data/trainers.py's `rival_silver_2`/`rival_silver_3`). `enabled=False`
    returns `VANILLA_STARTERS` unchanged; otherwise 3 distinct species are
    drawn from `real_species_pool(species)` via `rng.sample` (deterministic
    given `rng`'s seed, see this module's docstring)."""
    if not enabled:
        return VANILLA_STARTERS
    pool = real_species_pool(species)
    return tuple(rng.sample(pool, k=3))  # type: ignore[return-value]


# --- 2. Wild encounters ------------------------------------------------------


def _zone_species_refs(zone: dict) -> tuple[dict, list[tuple[dict, str]]]:
    """Deep-copy one `data/encounters.py` `ENCOUNTERS[...]` zone into plain
    mutable dicts/lists, and return it together with a flat list of
    `(container, key)` pairs -- one per species leaf -- in a fixed traversal
    order: `land`'s time-of-day slots (morn/day/nite each counted
    separately, since each is independently visible), then `surf`, then
    `rock_smash`, then each `fishing` rod, then `headbutt`'s tiers if
    present. `container[key]` still holds the *original* species at this
    point; callers overwrite it in place, in this same order, then convert
    the returned zone's inner lists back to tuples (`_finalize_zone`) to
    match `data/encounters.py`'s own shape."""
    new_zone: dict = {"map_code": zone["map_code"]}
    refs: list[tuple[dict, str]] = []

    land = zone["land"]
    new_land_slots = [dict(slot) for slot in land["slots"]]
    for slot in new_land_slots:
        for time_of_day in ("morn", "day", "nite"):
            refs.append((slot, time_of_day))
    new_zone["land"] = {"rate": land["rate"], "slots": new_land_slots}

    for table_name in ("surf", "rock_smash"):
        table = zone[table_name]
        new_slots = [dict(slot) for slot in table["slots"]]
        for slot in new_slots:
            refs.append((slot, "species"))
        new_zone[table_name] = {"rate": table["rate"], "slots": new_slots}

    fishing = zone["fishing"]
    new_fishing: dict = {}
    for rod in _FISHING_RODS:
        rod_table = fishing[rod]
        new_slots = [dict(slot) for slot in rod_table["slots"]]
        for slot in new_slots:
            refs.append((slot, "species"))
        new_fishing[rod] = {"rate": rod_table["rate"], "slots": new_slots}
    new_zone["fishing"] = new_fishing

    if "headbutt" in zone:
        headbutt = zone["headbutt"]
        new_headbutt: dict = {}
        for tier in _HEADBUTT_TIERS:
            new_slots = [dict(slot) for slot in headbutt[tier]]
            for slot in new_slots:
                refs.append((slot, "species"))
            new_headbutt[tier] = new_slots
        new_zone["headbutt"] = new_headbutt

    return new_zone, refs


def _finalize_zone(zone: dict) -> dict:
    """Convert a `_zone_species_refs`-built zone's inner lists back into
    tuples, matching `data/encounters.py`'s own shape."""
    finalized: dict = {
        "map_code": zone["map_code"],
        "land": {"rate": zone["land"]["rate"], "slots": tuple(zone["land"]["slots"])},
    }
    for table_name in ("surf", "rock_smash"):
        finalized[table_name] = {"rate": zone[table_name]["rate"], "slots": tuple(zone[table_name]["slots"])}
    finalized["fishing"] = {
        rod: {"rate": zone["fishing"][rod]["rate"], "slots": tuple(zone["fishing"][rod]["slots"])}
        for rod in _FISHING_RODS
    }
    if "headbutt" in zone:
        finalized["headbutt"] = {tier: tuple(zone["headbutt"][tier]) for tier in _HEADBUTT_TIERS}
    return finalized


def randomize_wild_encounters(
    rng: Random, mode: int, encounters: dict = ENCOUNTERS, species: dict = SPECIES
) -> dict:
    """Randomize every wild-encounter species reference in `encounters`
    (grass/surf/fishing/rock-smash/headbutt, see data/encounters.py).

    - `WILD_VANILLA`: returns `encounters` unchanged.
    - `WILD_SHUFFLE`: a single global permutation of the actual multiset of
      species appearing across every slot in the game -- the same set of
      species (with the same multiplicity) still appears somewhere, just
      moved to different slots.
    - `WILD_FULL_RANDOM`: every slot independently gets a fresh
      `rng.choice` from `real_species_pool(species)`.

    Both randomized modes walk every zone (in `encounters`' own dict order)
    and every slot within a zone (in `_zone_species_refs`'s fixed order),
    so the sequence of `rng` draws -- and therefore the result -- is fully
    determined by `rng`'s seed."""
    if mode == WILD_VANILLA:
        return encounters

    pool = real_species_pool(species)
    new_zones: dict[str, dict] = {}
    all_refs: list[tuple[dict, str]] = []
    for key, zone in encounters.items():
        new_zone, refs = _zone_species_refs(zone)
        new_zones[key] = new_zone
        all_refs.extend(refs)

    if mode == WILD_SHUFFLE:
        shuffled_values = [container[ref_key] for container, ref_key in all_refs]
        rng.shuffle(shuffled_values)
        for (container, ref_key), value in zip(all_refs, shuffled_values):
            container[ref_key] = value
    elif mode == WILD_FULL_RANDOM:
        for container, ref_key in all_refs:
            container[ref_key] = rng.choice(pool)
    else:
        raise ValueError(f"unknown wild-encounter randomization mode: {mode!r}")

    return {key: _finalize_zone(zone) for key, zone in new_zones.items()}


# --- 3. Trainer parties ------------------------------------------------------


def randomize_trainer_parties(rng: Random, enabled: bool, trainers: dict = TRAINERS, species: dict = SPECIES) -> dict:
    """Randomize every trainer party's species (data/trainers.py). Levels,
    movesets, held items, ability overrides and everything else about each
    party slot are left exactly as-is for v1 -- only `species` is replaced
    (see the task brief: "niveaux/movesets peuvent rester vanilla pour v1
    si le temps manque"; kept vanilla here as a deliberate, documented v1
    choice, not a time-shortage accident). `enabled=False` returns
    `trainers` unchanged.

    Each party slot independently gets a fresh `rng.choice` from
    `real_species_pool(species)`, walking `trainers` in its own dict order
    and each party in its own tuple order, so the result is fully determined
    by `rng`'s seed."""
    if not enabled:
        return trainers

    pool = real_species_pool(species)
    new_trainers: dict[str, dict] = {}
    for key, trainer in trainers.items():
        new_party = tuple({**mon, "species": rng.choice(pool)} for mon in trainer["party"])
        new_trainers[key] = {**trainer, "party": new_party}
    return new_trainers


# --- 4. Evolutions -----------------------------------------------------------


def _all_method_param_pairs(species: dict) -> tuple[tuple[str, object], ...]:
    """Every distinct `(method, param)` pair actually used by some vanilla
    evolution in `species` (e.g. `("level", 16)`, `("stone", "fire_stone")`,
    `("trade_item", "kings_rock")`, `("friendship_day", 0)`...). Used by
    `randomize_evolutions`'s `EVOLUTIONS_ANY_METHOD` mode to pick a
    method+param combination that is always structurally valid (a real
    param for that method), rather than inventing an untested pairing."""
    pairs = {(evo["method"], evo["param"]) for data in species.values() for evo in data["evolutions"]}
    return tuple(sorted(pairs, key=lambda pair: (pair[0], str(pair[1]))))


def randomize_evolutions(rng: Random, mode: int, species: dict = SPECIES) -> dict:
    """Randomize evolution targets (data/species.py `evolutions`).

    - `EVOLUTIONS_OFF`: returns `species` unchanged.
    - `EVOLUTIONS_KEEP_METHOD`: each evolution edge keeps its original
      `method`/`param` (a level-up evolution stays a level-up evolution at
      the same level, a stone evolution still needs the same stone, ...) but
      gets a freshly-chosen `target`.
    - `EVOLUTIONS_ANY_METHOD`: both `target` and `method`/`param` are
      randomized -- the `(method, param)` pair is drawn from
      `_all_method_param_pairs(species)` so it is always a real, structurally
      valid combination (see that helper's docstring), just reassigned to a
      different evolution edge.

    A species never evolves into itself, and (best-effort, not guaranteed
    globally -- see module docstring) a species' own sibling evolution
    branches (e.g. Eevee's 7) don't get duplicated into the same target
    twice. Walks `species` in its own dict order and each species'
    `evolutions` tuple in its own order, so the result is fully determined
    by `rng`'s seed."""
    if mode == EVOLUTIONS_OFF:
        return species

    pool = real_species_pool(species)
    method_param_pairs = _all_method_param_pairs(species) if mode == EVOLUTIONS_ANY_METHOD else ()

    new_species: dict[str, dict] = {}
    for key, data in species.items():
        used_targets: set[str] = set()
        new_evolutions = []
        for evo in data["evolutions"]:
            choices = [candidate for candidate in pool if candidate != key and candidate not in used_targets]
            if not choices:
                choices = [candidate for candidate in pool if candidate != key]
            target = rng.choice(choices)
            used_targets.add(target)

            if mode == EVOLUTIONS_KEEP_METHOD:
                new_evolutions.append({**evo, "target": target})
            elif mode == EVOLUTIONS_ANY_METHOD:
                method, param = rng.choice(method_param_pairs)
                new_evolutions.append({"method": method, "target": target, "param": param})
            else:
                raise ValueError(f"unknown evolution randomization mode: {mode!r}")
        new_species[key] = {**data, "evolutions": tuple(new_evolutions)}
    return new_species


# --- 5. Base stats -----------------------------------------------------------


# `BASE_STATS_FULL_RANDOM`'s redistribution (added after live playtest
# feedback, see this function's own docstring): each stat must land in a
# real, ROM-representable range. `rom/speciesdata.py`'s `_BASE_STAT_FIELD_
# OFFSETS` writes each stat as a single unsigned byte (0-255) -- 255 is
# therefore the hard ceiling here regardless of how high a species' own
# BST happens to be (Arceus's 720 spread evenly would only need ~120 per
# stat, so this only ever binds for a deliberately lopsided draw). 1 is the
# floor: a real 0 in any stat (especially HP) is degenerate/unplayable,
# not just "low".
_BASE_STAT_MIN = 1
_BASE_STAT_MAX = 255


def _redistribute_preserving_total(rng: Random, total: int, count: int) -> list[int]:
    """`count` positive integers, each in `[_BASE_STAT_MIN, _BASE_STAT_MAX]`,
    summing to exactly `total` -- a uniformly random composition (the
    "stars and bars" construction: reserve the minimum for every part
    up front, then cut the remaining budget at `count - 1` random points).
    Order is not meaningful (caller shuffles); retries (rejection
    sampling) if an unlucky cut pushes any single part over the max --
    astronomically rare for real base-stat totals (even a legendary's
    ~680-720 BST across 6 stats averages ~120), but not impossible, so
    this is a real loop, not a formality."""
    reserve = _BASE_STAT_MIN * count
    remainder = total - reserve
    if remainder < 0:
        raise ValueError(f"total {total} is too small to give {count} stats at least {_BASE_STAT_MIN} each")

    for _ in range(500):
        cuts = sorted(rng.randint(0, remainder) for _ in range(count - 1))
        parts = []
        previous = 0
        for cut in cuts:
            parts.append(cut - previous)
            previous = cut
        parts.append(remainder - previous)
        parts = [p + _BASE_STAT_MIN for p in parts]
        if all(p <= _BASE_STAT_MAX for p in parts):
            return parts

    # Reachable only for a pathologically lopsided total across very few
    # stats (not the case for this project's 6-stat calls) -- clamp and
    # accept a slightly-off total rather than loop forever.
    return [min(p, _BASE_STAT_MAX) for p in parts]


def randomize_base_stats(rng: Random, mode: int, species: dict = SPECIES) -> dict:
    """Randomize each species' `base_stats` dict (`hp`/`atk`/`def`/`spatk`/
    `spdef`/`speed`). Growth rate and every other species field are never
    touched by this function -- it only ever replaces `base_stats`.

    - `BASE_STATS_OFF`: returns `species` unchanged.
    - `BASE_STATS_SHUFFLE`: each stat column is shuffled independently
      across every species (`rng.shuffle`) -- the same multiset of values
      in that column still appears somewhere, just reassigned.
    - `BASE_STATS_FULL_RANDOM`: each species' own base stat *total* (the
      sum of all 6 stats, i.e. its BST) is preserved exactly -- only how
      that total is split across the 6 stats is randomized (`rng`-driven
      composition, see `_redistribute_preserving_total`). Chosen after
      live playtest feedback: independently randint-ing each stat (the
      original behavior) could and did produce results disconnected from
      a species' own power level (e.g. a lopsidedly weak or absurdly
      strong-for-its-BST result) -- redistributing a real, preserved
      total keeps every species roughly as strong overall as it started,
      while still fully scrambling *which* stat that strength shows up
      in.

    Walks `species` in its own dict order, so the result is fully
    determined by `rng`'s seed."""
    if mode == BASE_STATS_OFF:
        return species

    keys = tuple(species.keys())
    new_stats: dict[str, dict[str, int]] = {key: dict(species[key]["base_stats"]) for key in keys}

    if mode == BASE_STATS_SHUFFLE:
        for field in _BASE_STAT_FIELDS:
            values = [species[key]["base_stats"][field] for key in keys]
            rng.shuffle(values)
            for key, value in zip(keys, values):
                new_stats[key][field] = value
    elif mode == BASE_STATS_FULL_RANDOM:
        for key in keys:
            total = sum(species[key]["base_stats"][field] for field in _BASE_STAT_FIELDS)
            parts = _redistribute_preserving_total(rng, total, len(_BASE_STAT_FIELDS))
            rng.shuffle(parts)
            for field, value in zip(_BASE_STAT_FIELDS, parts):
                new_stats[key][field] = value
    else:
        raise ValueError(f"unknown base-stat randomization mode: {mode!r}")

    return {key: {**data, "base_stats": new_stats[key]} for key, data in species.items()}


# --- 6. Move stats -----------------------------------------------------------
#
# `MOVES_FULL_RANDOM`'s power/accuracy/PP ranges below (added after live
# playtest feedback -- the original independent-randint-per-field design
# produced disconnected, un-fun results: e.g. a live-tested seed's Tackle
# landing on power=9/accuracy=89/PP=1) are a deliberate design, not a
# derived-from-the-ROM constant like this module's other tables:
#
# - PP: a multiple of 5 in [5, 40] -- every *vanilla* PP value already is
#   a multiple of 5 (HGSS's own convention bar Struggle, which this
#   randomizer never touches at all, see data/moves.py), so this keeps
#   randomized PP looking like a real value a player would recognize.
# - Power (physical/special moves only -- status moves keep their
#   vanilla power, almost always 0, untouched: power is meaningless for
#   a move that deals no direct damage): [40, 250] for an ordinary
#   single-hit move. Multi-hit moves (`_MULTI_HIT_MOVES` below) get their
#   power divided down by their average hit count instead of the raw
#   [40, 250] roll, so a move that hits 2-5 times doesn't also hit
#   2-5x as hard per hit as a single-hit move -- both land on
#   comparable *total expected damage*.
# - Accuracy (physical/special moves with a real, non-zero vanilla
#   accuracy -- see the `accuracy == 0` sentinel note below): linear in
#   the move's own (pre-multi-hit-division) power, from 100% at the
#   lowest possible power (40) down to 40% at the highest (250), plus a
#   little random jitter, then rounded to the nearest multiple of 5 (still
#   clamped to [40, 100]) -- every *vanilla* HGSS accuracy value is
#   already a multiple of 5, same reasoning as PP above. Status moves'
#   own accuracy (when not the `0` sentinel) keeps the *previous* simple
#   independent-randint-within-vanilla-range behavior (also rounded to a
#   multiple of 5), since status moves have no power to derive it from.

# Average hit count for each of HGSS's known multi-hit moves (used only to
# scale `MOVES_FULL_RANDOM`'s power draw down, see this section's own
# docstring) -- fixed-count moves (Double Kick, Twineedle) use their exact
# count; the rest use HGSS's own classic 2/3/4/5-hit probability weights
# (37.5%/37.5%/12.5%/12.5%), whose expected value is exactly 3. Not derived
# from a decomp data source (`data/moves.py` itself has no hit-count field,
# see this section's own docstring) -- a hardcoded list of Gen IV's own
# well-known multi-hit moves.
_MULTI_HIT_MOVES: dict[str, float] = {
    "double_kick": 2.0,
    "twineedle": 2.0,
    "triple_kick": 3.0,
    "double_slap": 3.0,
    "comet_punch": 3.0,
    "fury_attack": 3.0,
    "pin_missile": 3.0,
    "spike_cannon": 3.0,
    "barrage": 3.0,
    "fury_swipes": 3.0,
    "bone_rush": 3.0,
    "bullet_seed": 3.0,
    "icicle_spear": 3.0,
    "rock_blast": 3.0,
    "arm_thrust": 3.0,
}

# A second sentinel, discovered while writing this section's own tests:
# `power == 1` marks a move whose real damage is computed by special-case
# battle-engine code, not a literal base-power multiplication (every OHKO
# move; weight/HP/happiness/item-dependent moves like Low Kick/Flail/
# Return/Fling; fixed/variable-formula moves like Seismic Toss/Counter/
# Hidden Power/Psywave; ...). Exactly analogous to the `accuracy == 0`
# "never misses" sentinel already documented above -- neither field is a
# real value to randomize for these moves, so both are left exactly as
# vanilla.
_MOVE_POWER_SENTINEL = 1

_SINGLE_HIT_POWER_RANGE = (40, 250)
_MULTI_HIT_MIN_PER_HIT_POWER = 10
_MOVE_ACCURACY_RANGE = (40, 100)
_MOVE_ACCURACY_JITTER = 10
_MOVE_ACCURACY_STEP = 5
_PP_CHOICES = (5, 10, 15, 20, 25, 30, 35, 40)


def _round_to_multiple(value: float, multiple: int, low: int, high: int) -> int:
    """`value` rounded to the nearest multiple of `multiple`, then clamped
    to `[low, high]` (both already exact multiples for every caller here,
    so the clamp never itself breaks the multiple-of invariant)."""
    rounded = round(value / multiple) * multiple
    return max(low, min(high, rounded))


def _random_power_and_accuracy(rng: Random, move_key: str, category: str, vanilla_power: int) -> tuple[int, int]:
    """One `(power, accuracy)` draw for `MOVES_FULL_RANDOM`, per this
    section's own docstring. `accuracy` here is the damaging-move formula
    only -- callers handle the `accuracy == 0` sentinel and status moves'
    own fallback separately, this function is never called for either."""
    low, high = _SINGLE_HIT_POWER_RANGE
    rolled_power = rng.randint(low, high)

    hits = _MULTI_HIT_MOVES.get(move_key)
    power = rolled_power if hits is None else max(_MULTI_HIT_MIN_PER_HIT_POWER, round(rolled_power / hits))

    acc_low, acc_high = _MOVE_ACCURACY_RANGE
    fraction = (rolled_power - low) / (high - low)
    target_accuracy = acc_high - fraction * (acc_high - acc_low)
    jitter = rng.randint(-_MOVE_ACCURACY_JITTER, _MOVE_ACCURACY_JITTER)
    accuracy = _round_to_multiple(target_accuracy + jitter, _MOVE_ACCURACY_STEP, acc_low, acc_high)

    return power, accuracy


def randomize_move_stats(rng: Random, mode: int, moves: dict = MOVES) -> dict:
    """Randomize each move's `power`/`accuracy`/`pp`. `type` (and every
    other move field: effect, category, ...) is never touched by this
    function -- "conservation du Type" is a hard invariant here, not just
    a default.

    - `MOVES_OFF`: returns `moves` unchanged.
    - `MOVES_SHUFFLE`: each of power/accuracy/pp is shuffled independently
      across every move (`rng.shuffle`) -- the same multiset of real
      vanilla values still appears somewhere, just reassigned, so this
      mode is unaffected by the `MOVES_FULL_RANDOM`-only balance rules
      this section's own docstring describes.
    - `MOVES_FULL_RANDOM`: PP is an independent multiple-of-5 draw; power
      and accuracy are drawn jointly per move (accuracy derived from that
      same move's own power) for physical/special moves, or independently
      within the vanilla range for status moves' accuracy (power stays
      untouched) -- see this section's own docstring for the full design
      and why.

    `accuracy == 0` is a sentinel, not a real percentage -- HGSS's own
    convention for "never misses" (Swift, Aerial Ace, ...; the OHKO moves
    Fissure/Horn Drill/Guillotine/Sheer Cold use a different, non-zero
    encoding for their level-based accuracy check and are unaffected by
    this). Moves with `accuracy == 0` keep it exactly as-is in every mode.

    Walks `moves` in its own dict order, so the result is fully determined
    by `rng`'s seed."""
    if mode == MOVES_OFF:
        return moves

    keys = tuple(moves.keys())
    new_combat_stats: dict[str, dict[str, int]] = {key: {} for key in keys}

    if mode == MOVES_SHUFFLE:
        for field in _MOVE_COMBAT_FIELDS:
            eligible_keys = tuple(key for key in keys if not (field == "accuracy" and moves[key][field] == 0))
            values = [moves[key][field] for key in eligible_keys]
            rng.shuffle(values)
            for key, value in zip(eligible_keys, values):
                new_combat_stats[key][field] = value
    elif mode == MOVES_FULL_RANDOM:
        for key in keys:
            new_combat_stats[key]["pp"] = rng.choice(_PP_CHOICES)

        eligible_accuracy_keys = tuple(key for key in keys if moves[key]["accuracy"] != 0)
        fallback_accuracy_values = [moves[key]["accuracy"] for key in eligible_accuracy_keys]
        acc_low, acc_high = _MOVE_ACCURACY_RANGE
        # Clamped into the same [40, 100] floor/ceiling the power-derived
        # formula uses below -- the raw vanilla pool includes OHKO moves'
        # real 30% (a power-sentinel, excluded from *this* draw entirely,
        # see the loop below), which would otherwise let a status move's
        # fallback accuracy land under the intended floor too.
        fallback_low = max(acc_low, min(fallback_accuracy_values))
        fallback_high = min(acc_high, max(fallback_accuracy_values))

        for key in keys:
            data = moves[key]
            if data["accuracy"] == 0 or data["power"] == _MOVE_POWER_SENTINEL:
                # `accuracy == 0` ("never misses") and `power == 1`
                # ("variable/special-mechanic power, computed elsewhere at
                # battle time" -- OHKO moves, Low Kick, Seismic Toss,
                # Counter, Flail, Hidden Power, ... see this section's own
                # docstring) are both sentinels, not real values to
                # randomize -- a move with either keeps *both* fields
                # exactly as vanilla (deriving a fake accuracy from a fake
                # power would be meaningless for these).
                new_combat_stats[key]["accuracy"] = data["accuracy"]
                new_combat_stats[key]["power"] = data["power"]
                continue
            if data["category"] == "status":
                new_combat_stats[key]["power"] = data["power"]
                rolled = rng.randint(fallback_low, fallback_high)
                new_combat_stats[key]["accuracy"] = _round_to_multiple(
                    rolled, _MOVE_ACCURACY_STEP, fallback_low, fallback_high
                )
                continue
            power, accuracy = _random_power_and_accuracy(rng, key, data["category"], data["power"])
            new_combat_stats[key]["power"] = power
            new_combat_stats[key]["accuracy"] = accuracy
    else:
        raise ValueError(f"unknown move-stat randomization mode: {mode!r}")

    return {key: {**data, **new_combat_stats[key]} for key, data in moves.items()}
