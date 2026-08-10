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
# exists and defines `RandomizeWildPokemon`/`RandomizeStarters`/
# `RandomizeTrainers`/`RandomizeEvolutions`/`RandomizeBaseStats`/
# `RandomizeMoves`. This module deliberately does NOT import it: `options.py` itself imports `Options` from the local
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


def randomize_base_stats(rng: Random, mode: int, species: dict = SPECIES) -> dict:
    """Randomize each species' `base_stats` dict (`hp`/`atk`/`def`/`spatk`/
    `spdef`/`speed`). Growth rate and every other species field are never
    touched by this function -- it only ever replaces `base_stats`.

    - `BASE_STATS_OFF`: returns `species` unchanged.
    - `BASE_STATS_SHUFFLE`: each stat column is shuffled independently
      across every species (`rng.shuffle`) -- the same multiset of values
      in that column still appears somewhere, just reassigned.
    - `BASE_STATS_FULL_RANDOM`: each stat is independently replaced by a
      fresh `rng.randint` draw within the real min-max range some vanilla
      species actually has for that same stat.

    Walks `species` in its own dict order and `_BASE_STAT_FIELDS` in its
    own fixed order, so the result is fully determined by `rng`'s seed."""
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
        for field in _BASE_STAT_FIELDS:
            values = [species[key]["base_stats"][field] for key in keys]
            low, high = min(values), max(values)
            for key in keys:
                new_stats[key][field] = rng.randint(low, high)
    else:
        raise ValueError(f"unknown base-stat randomization mode: {mode!r}")

    return {key: {**data, "base_stats": new_stats[key]} for key, data in species.items()}


# --- 6. Move stats -----------------------------------------------------------


def randomize_move_stats(rng: Random, mode: int, moves: dict = MOVES) -> dict:
    """Randomize each move's `power`/`accuracy`/`pp`. `type` (and every
    other move field: effect, category, ...) is never touched by this
    function -- "conservation du Type" is a hard invariant here, not just
    a default.

    - `MOVES_OFF`: returns `moves` unchanged.
    - `MOVES_SHUFFLE`: each of power/accuracy/pp is shuffled independently
      across every move (`rng.shuffle`).
    - `MOVES_FULL_RANDOM`: each of power/accuracy/pp is independently
      replaced by a fresh `rng.randint` draw within the real min-max range
      some vanilla move actually has for that same field.

    `accuracy == 0` is a sentinel, not a real percentage -- HGSS's own
    convention for "never misses" (Swift, Aerial Ace, ...; the OHKO moves
    Fissure/Horn Drill/Guillotine/Sheer Cold use a different, non-zero
    encoding for their level-based accuracy check and are unaffected by
    this). Moves with `accuracy == 0` keep it exactly as-is in every mode,
    and are excluded from the pool other moves' accuracy is drawn from --
    otherwise `shuffle`/`full_random` could hand `0` to an ordinary move
    (making it unmissable) or take it away from Swift/Aerial Ace (making
    them missable), neither a "randomize the percentage" outcome.

    Walks `moves` in its own dict order and `_MOVE_COMBAT_FIELDS` in its
    own fixed order, so the result is fully determined by `rng`'s seed."""
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
        for field in _MOVE_COMBAT_FIELDS:
            eligible_keys = tuple(key for key in keys if not (field == "accuracy" and moves[key][field] == 0))
            values = [moves[key][field] for key in eligible_keys]
            low, high = min(values), max(values)
            for key in eligible_keys:
                new_combat_stats[key][field] = rng.randint(low, high)
    else:
        raise ValueError(f"unknown move-stat randomization mode: {mode!r}")

    return {key: {**data, **new_combat_stats[key]} for key, data in moves.items()}
