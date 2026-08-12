# species.py
#
# Randomization logic: starters, wild encounters, trainer parties,
# evolution targets, base stats, and move power/accuracy/PP/type. Pure
# transforms of the generated data/*.py tables into new, equally-shaped
# ones -- never mutates data/*.py itself, never builds any Archipelago
# Region/Location/Item object (see regions.py/locations.py/items.py).
#
# Determinism: every function that makes a random choice takes an explicit
# rng: random.Random parameter, never draws from the `random` module's own
# top-level functions -- the caller passes world.random. mode/enabled
# parameters use plain ints/bools matching options.py's own option values
# (checked by tests/test_randomization.py::
# test_mode_constants_match_options_values) rather than importing options.py
# directly, so this module stays testable without a local Archipelago
# checkout.
#
# Nuzlocke aids (disable_ohko_moves/neutralize_trapping_abilities) are
# deterministic toggles, not randomizers -- neither takes an rng parameter.

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

_BASE_STAT_FIELDS = ("hp", "atk", "def", "spatk", "spdef", "speed")
_MOVE_COMBAT_FIELDS = ("power", "accuracy", "pp")

# HGSS's vanilla starter trio (Prof. Elm's lab / rival_silver_2/rival_silver_3
# in data/trainers.py), used when starter randomization is disabled.
VANILLA_STARTERS = ("chikorita", "cyndaquil", "totodile")

_FISHING_RODS = ("old_rod", "good_rod", "super_rod")
_HEADBUTT_TIERS = ("common", "rare", "secret")


def real_species_pool(species: dict = SPECIES) -> tuple[str, ...]:
    """The species with a real national Pokedex number -- excludes HGSS
    alternate forms (Deoxys/Wormadam/Giratina Origin/Shaymin Sky/Rotom).
    Sorted for a deterministic base ordering."""
    return tuple(sorted(key for key, data in species.items() if data["national_dex"] is not None))


# --- 1. Starters -----------------------------------------------------------


def randomize_starters(rng: Random, enabled: bool, species: dict = SPECIES) -> tuple[str, str, str]:
    """Pick the 3 starter species (also used for the rival's own starter).
    `enabled=False` returns `VANILLA_STARTERS` unchanged."""
    if not enabled:
        return VANILLA_STARTERS
    pool = real_species_pool(species)
    return tuple(rng.sample(pool, k=3))  # type: ignore[return-value]


# --- 2. Wild encounters ------------------------------------------------------


def _zone_species_refs(zone: dict) -> tuple[dict, list[tuple[dict, str]]]:
    """Deep-copy one ENCOUNTERS zone into plain mutable dicts/lists, and
    return it together with a flat list of (container, key) pairs -- one
    per species leaf -- in a fixed traversal order. Callers overwrite in
    place, then `_finalize_zone` converts back to tuples."""
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
    """Convert a _zone_species_refs-built zone's inner lists back into
    tuples."""
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
    """Randomize every trainer party's species. Levels, movesets, held
    items, and abilities are left vanilla for v1 -- only `species` is
    replaced. `enabled=False` returns `trainers` unchanged."""
    if not enabled:
        return trainers

    pool = real_species_pool(species)
    new_trainers: dict[str, dict] = {}
    for key, trainer in trainers.items():
        new_party = tuple({**mon, "species": rng.choice(pool)} for mon in trainer["party"])
        new_trainers[key] = {**trainer, "party": new_party}
    return new_trainers


_MIN_LEVEL = 1
_MAX_LEVEL = 100  # HGSS's own level cap


def scale_trainer_levels(scale_percent: int, trainers: dict = TRAINERS) -> dict:
    """Scale every trainer party mon's level by scale_percent (100 =
    vanilla). Clamped to HGSS's 1-100 range. `scale_percent=100` returns
    `trainers` unchanged."""
    if scale_percent == 100:
        return trainers

    new_trainers: dict[str, dict] = {}
    for key, trainer in trainers.items():
        new_party = tuple(
            {**mon, "level": max(_MIN_LEVEL, min(_MAX_LEVEL, round(mon["level"] * scale_percent / 100)))}
            for mon in trainer["party"]
        )
        new_trainers[key] = {**trainer, "party": new_party}
    return new_trainers


# --- 4. Evolutions -----------------------------------------------------------


def _all_method_param_pairs(species: dict) -> tuple[tuple[str, object], ...]:
    """Every distinct (method, param) pair actually used by some vanilla
    evolution -- used by EVOLUTIONS_ANY_METHOD to pick a combination that's
    always structurally valid."""
    pairs = {(evo["method"], evo["param"]) for data in species.values() for evo in data["evolutions"]}
    return tuple(sorted(pairs, key=lambda pair: (pair[0], str(pair[1]))))


def randomize_evolutions(rng: Random, mode: int, species: dict = SPECIES) -> dict:
    """Randomize evolution targets (data/species.py `evolutions`).

    - `EVOLUTIONS_OFF`: returns `species` unchanged.
    - `EVOLUTIONS_KEEP_METHOD`: each edge keeps its original method/param,
      gets a freshly-chosen target.
    - `EVOLUTIONS_ANY_METHOD`: both target and method/param are randomized,
      drawn from `_all_method_param_pairs`.

    A species never evolves into itself; best-effort (not globally
    guaranteed) avoidance of duplicate targets within one species' own
    evolution branches."""
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


# 255 is the ROM's hard ceiling (each stat is a single unsigned byte,
# rom/speciesdata.py); 1 is the floor (a real 0 in any stat is degenerate).
_BASE_STAT_MIN = 1
_BASE_STAT_MAX = 255


def _redistribute_preserving_total(rng: Random, total: int, count: int) -> list[int]:
    """`count` positive integers in [_BASE_STAT_MIN, _BASE_STAT_MAX] summing
    to exactly `total` -- a uniformly random composition ("stars and bars").
    Order is not meaningful (caller shuffles); retries (rejection sampling)
    if an unlucky cut pushes any part over the max -- astronomically rare
    for real base-stat totals (even a legendary's
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

    return [min(p, _BASE_STAT_MAX) for p in parts]


def randomize_base_stats(rng: Random, mode: int, species: dict = SPECIES) -> dict:
    """Randomize each species' base_stats dict. Growth rate and every
    other species field are untouched.

    - `BASE_STATS_OFF`: returns `species` unchanged.
    - `BASE_STATS_SHUFFLE`: each stat column shuffled independently.
    - `BASE_STATS_FULL_RANDOM`: each species' own BST (stat total) is
      preserved, only its split across the 6 stats is randomized (see
      NOTES.md for why)."""
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


def randomize_species_types(rng: Random, enabled: bool, species: dict = SPECIES) -> dict:
    """Randomize each species' `types` tuple, preserving typing complexity
    (single-type stays single, dual-type stays dual with 2 distinct
    types). Never draws "mystery" (engine-special-cased, not a real 18th
    type). `enabled=False` returns `species` unchanged."""
    if not enabled:
        return species

    real_types = tuple(sorted({t for data in species.values() for t in data["types"]} - {"mystery"}))
    new_species: dict[str, dict] = {}
    for key, data in species.items():
        if len(data["types"]) == 1:
            new_types = (rng.choice(real_types),)
        else:
            new_types = tuple(rng.sample(real_types, 2))
        new_species[key] = {**data, "types": new_types}
    return new_species


# --- 6. Move stats -----------------------------------------------------------
#
# MOVES_FULL_RANDOM's power/accuracy/PP ranges are a deliberate balance
# design, not derived from the ROM -- see NOTES.md for the full rationale.

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

# `power == 1` marks a move whose real damage is special-cased by the
# battle engine (OHKO moves, Low Kick/Flail/Return/Fling, Seismic
# Toss/Counter/Hidden Power/Psywave, ...) -- see NOTES.md.
_MOVE_POWER_SENTINEL = 1

_SINGLE_HIT_POWER_RANGE = (40, 250)
_MULTI_HIT_MIN_PER_HIT_POWER = 10
_MOVE_ACCURACY_RANGE = (40, 100)
_MOVE_ACCURACY_JITTER = 10
_MOVE_ACCURACY_STEP = 5
_PP_CHOICES = (5, 10, 15, 20, 25, 30, 35, 40)


def _round_to_multiple(value: float, multiple: int, low: int, high: int) -> int:
    """`value` rounded to the nearest multiple of `multiple`, clamped to
    [low, high]."""
    rounded = round(value / multiple) * multiple
    return max(low, min(high, rounded))


def _random_power_and_accuracy(rng: Random, move_key: str, category: str, vanilla_power: int) -> tuple[int, int]:
    """One (power, accuracy) draw for MOVES_FULL_RANDOM -- damaging moves
    only, callers handle the accuracy==0 sentinel and status moves
    separately."""
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
    """Randomize each move's power/accuracy/pp. `type` and every other
    field are never touched.

    - `MOVES_OFF`: returns `moves` unchanged.
    - `MOVES_SHUFFLE`: power/accuracy/pp each shuffled independently.
    - `MOVES_FULL_RANDOM`: see this file's module comment / NOTES.md for
      the balance design.

    `accuracy == 0` is HGSS's own "never misses" sentinel (Swift, Aerial
    Ace, ...) and is kept exactly as-is in every mode."""
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
        fallback_low = max(acc_low, min(fallback_accuracy_values))
        fallback_high = min(acc_high, max(fallback_accuracy_values))

        for key in keys:
            data = moves[key]
            if data["accuracy"] == 0 or data["power"] == _MOVE_POWER_SENTINEL:
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


def randomize_move_types(rng: Random, enabled: bool, moves: dict = MOVES) -> dict:
    """Randomize each move's `type`. Never draws "mystery" (HGSS's real
    vanilla type for Curse, engine-special-cased, not a real 18th type) --
    a move whose vanilla type already is "mystery" can still be reassigned
    away from it. `enabled=False` returns `moves` unchanged."""
    if not enabled:
        return moves

    real_types = tuple(sorted({data["type"] for data in moves.values()} - {"mystery"}))
    return {key: {**data, "type": rng.choice(real_types)} for key, data in moves.items()}


# --- 7. Nuzlocke aids ---------------------------------------------------------
# Deterministic toggles, not randomizers -- see docs/scope.md's
# "Nuzlocke mode" section.

# Must stay byte-for-byte consistent with rom/movedata.py's
# write_ohko_neutralization.
_OHKO_NEUTRALIZED_EFFECT = "hit"
_OHKO_NEUTRALIZED_POWER = 60
_OHKO_NEUTRALIZED_ACCURACY = 100


def disable_ohko_moves(enabled: bool, moves: dict = MOVES) -> dict:
    """Neutralize every move whose vanilla effect is "one_hit_ko"
    (Guillotine/Horn Drill/Fissure/Sheer Cold) into an ordinary 60
    power/100 accuracy move. `enabled=False` returns `moves` unchanged."""
    if not enabled:
        return moves

    return {
        key: (
            {
                **data,
                "effect": _OHKO_NEUTRALIZED_EFFECT,
                "power": _OHKO_NEUTRALIZED_POWER,
                "accuracy": _OHKO_NEUTRALIZED_ACCURACY,
            }
            if data["effect"] == "one_hit_ko"
            else data
        )
        for key, data in moves.items()
    }


TRAPPING_ABILITIES = frozenset({23, 42, 71})  # SHADOW_TAG, MAGNET_PULL, ARENA_TRAP
_RUN_AWAY_ABILITY = 50  # ABILITY_RUN_AWAY -- fallback for mono-ability trappers, see NOTES.md


def neutralize_trapping_abilities(enabled: bool, species: dict = SPECIES) -> dict:
    """Remove every trapping ability (TRAPPING_ABILITIES) from `species`.
    A species with a real second ability gets that ability copied into
    both slots; a mono-ability trapper (e.g. Wobbuffet's Shadow Tag) gets
    Run Away instead. `enabled=False` returns `species` unchanged."""
    if not enabled:
        return species

    new_species: dict[str, dict] = {}
    for key, data in species.items():
        ability1, ability2 = data["abilities"]
        trap1 = ability1 in TRAPPING_ABILITIES
        trap2 = ability2 in TRAPPING_ABILITIES

        if not trap1 and not trap2:
            new_species[key] = data
            continue

        if trap1 and trap2:
            new_abilities = (_RUN_AWAY_ABILITY, _RUN_AWAY_ABILITY)
        elif ability2 == 0:
            # Mono-ability species whose only (trapping) ability is ability1.
            new_abilities = (_RUN_AWAY_ABILITY, 0)
        elif trap1:
            # ability2 is a real, non-trapping ability -- copy it into slot 1.
            new_abilities = (ability2, ability2)
        else:
            # trap2: ability1 is a real, non-trapping ability -- copy it into slot 2.
            new_abilities = (ability1, ability1)

        new_species[key] = {**data, "abilities": new_abilities}
    return new_species
