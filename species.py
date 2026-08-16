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
from data.moves import MOVES, TM_HM_MOVES
from data.species import SPECIES
from data.trainers import TRAINERS
from data.type_chart import TYPE_CHART

# Mirrors options.RandomizeWildPokemon's option_vanilla/option_shuffle/
# option_full_random/option_zone_method_mapping values (see this module's
# docstring for why they are duplicated here instead of imported).
WILD_VANILLA = 0
WILD_SHUFFLE = 1
WILD_FULL_RANDOM = 2
WILD_ZONE_METHOD_MAPPING = 3

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

# Gen 1-4 legendaries and mythicals present in HGSS's National Dex (up to
# Arceus, #493) -- not derived from a decomp data source (this project's
# species data has no "legendary" flag of its own), a hardcoded list per
# the well-established convention. Sub-legendaries (Regi trio, lake trio,
# Latias/Latios) and mythicals (Mew, Celebi, Jirachi, Deoxys, Phione,
# Manaphy, Darkrai, Shaymin, Arceus) are included alongside the "box art"
# legendaries -- excluded together by exclude_legendaries, no finer split.
LEGENDARY_SPECIES = frozenset(
    {
        "articuno",
        "zapdos",
        "moltres",
        "mewtwo",
        "mew",
        "raikou",
        "entei",
        "suicune",
        "lugia",
        "ho_oh",
        "celebi",
        "regirock",
        "regice",
        "registeel",
        "latias",
        "latios",
        "kyogre",
        "groudon",
        "rayquaza",
        "jirachi",
        "deoxys",
        "uxie",
        "mesprit",
        "azelf",
        "dialga",
        "palkia",
        "heatran",
        "regigigas",
        "giratina",
        "cresselia",
        "phione",
        "manaphy",
        "darkrai",
        "shaymin",
        "arceus",
    }
)


def real_species_pool(species: dict = SPECIES, *, exclude_legendaries: bool = False) -> tuple[str, ...]:
    """The species with a real national Pokedex number -- excludes HGSS
    alternate forms (Deoxys/Wormadam/Giratina Origin/Shaymin Sky/Rotom).
    `exclude_legendaries=True` also drops LEGENDARY_SPECIES. Sorted for a
    deterministic base ordering."""
    pool = (key for key, data in species.items() if data["national_dex"] is not None)
    if exclude_legendaries:
        pool = (key for key in pool if key not in LEGENDARY_SPECIES)
    return tuple(sorted(pool))


# --- 1. Starters -----------------------------------------------------------


def randomize_starters(
    rng: Random, enabled: bool, species: dict = SPECIES, *, exclude_legendaries: bool = False
) -> tuple[str, str, str]:
    """Pick the 3 starter species (also used for the rival's own starter),
    restricted to species with at least one evolution -- matching vanilla,
    where each starter has two. `enabled=False` returns `VANILLA_STARTERS`
    unchanged."""
    if not enabled:
        return VANILLA_STARTERS
    pool = tuple(
        key for key in real_species_pool(species, exclude_legendaries=exclude_legendaries) if species[key]["evolutions"]
    )
    return tuple(rng.sample(pool, k=3))  # type: ignore[return-value]


# --- 2. Wild encounters ------------------------------------------------------


def _zone_species_refs(zone: dict) -> tuple[dict, list[tuple[dict, str, str]]]:
    """Deep-copy one ENCOUNTERS zone into plain mutable dicts/lists, and
    return it together with a flat list of (container, key, method) triples
    -- one per species leaf -- in a fixed traversal order. `method` is one
    of 'land'/'surf'/'rock_smash'/'old_rod'/'good_rod'/'super_rod'/
    'headbutt' (task M3.4's species_encounter_methods uses the same set) --
    used by WILD_ZONE_METHOD_MAPPING below to group refs; the two older
    modes just ignore it. Callers overwrite container[key] in place, then
    `_finalize_zone` converts back to tuples."""
    new_zone: dict = {"map_code": zone["map_code"]}
    refs: list[tuple[dict, str, str]] = []

    land = zone["land"]
    new_land_slots = [dict(slot) for slot in land["slots"]]
    for slot in new_land_slots:
        for time_of_day in ("morn", "day", "nite"):
            refs.append((slot, time_of_day, "land"))
    new_zone["land"] = {"rate": land["rate"], "slots": new_land_slots}

    for table_name in ("surf", "rock_smash"):
        table = zone[table_name]
        new_slots = [dict(slot) for slot in table["slots"]]
        for slot in new_slots:
            refs.append((slot, "species", table_name))
        new_zone[table_name] = {"rate": table["rate"], "slots": new_slots}

    fishing = zone["fishing"]
    new_fishing: dict = {}
    for rod in _FISHING_RODS:
        rod_table = fishing[rod]
        new_slots = [dict(slot) for slot in rod_table["slots"]]
        for slot in new_slots:
            refs.append((slot, "species", rod))
        new_fishing[rod] = {"rate": rod_table["rate"], "slots": new_slots}
    new_zone["fishing"] = new_fishing

    if "headbutt" in zone:
        headbutt = zone["headbutt"]
        new_headbutt: dict = {}
        for tier in _HEADBUTT_TIERS:
            new_slots = [dict(slot) for slot in headbutt[tier]]
            for slot in new_slots:
                refs.append((slot, "species", "headbutt"))
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


def _fill_maximizing_distinctness(rng: Random, pool: tuple[str, ...], count: int) -> list[str]:
    """`count` values drawn from `pool`, using every pool member at most
    once before any repeat -- i.e. `rng.sample` when `count <= len(pool)`,
    otherwise every pool member once (in random order) followed by
    `rng.choices` (with replacement) for the remainder. Used by
    WILD_ZONE_METHOD_MAPPING, whose group count (species.py's own
    zone+method groups) can exceed a legendaries-excluded pool -- 458 real
    species without legendaries vs. up to ~460 HeartGold groups, see this
    task's own scoping notes -- so a plain `rng.sample` would raise."""
    if count <= len(pool):
        return rng.sample(pool, k=count)
    result = list(pool)
    rng.shuffle(result)
    result.extend(rng.choices(pool, k=count - len(pool)))
    return result


def randomize_wild_encounters(
    rng: Random,
    mode: int,
    encounters: dict = ENCOUNTERS,
    species: dict = SPECIES,
    *,
    exclude_legendaries: bool = False,
) -> dict:
    """Randomize every wild-encounter species reference in `encounters`
    (grass/surf/fishing/rock-smash/headbutt, see data/encounters.py).

    - `WILD_VANILLA`: returns `encounters` unchanged.
    - `WILD_SHUFFLE`: a single global permutation of the actual multiset of
      species appearing across every slot in the game -- the same set of
      species (with the same multiplicity) still appears somewhere, just
      moved to different slots. `exclude_legendaries` has no effect here:
      vanilla wild tables don't place legendaries in grass/surf/fishing/
      rock-smash slots to begin with, so there is nothing to exclude from
      a permutation of the existing multiset.
    - `WILD_FULL_RANDOM`: every slot independently gets a fresh
      `rng.choice` from `real_species_pool(species, exclude_legendaries=
      exclude_legendaries)`.
    - `WILD_ZONE_METHOD_MAPPING` (task M3.4 follow-up): every (zone, method)
      group -- e.g. "route_29's land table", "route_29's surf table" are two
      separate groups -- gets one replacement species, applied to every slot
      in that group (so every land encounter on a given route is the same
      species, but that route's surf table can be a different species).
      Drawn via `_fill_maximizing_distinctness` so as many distinct species
      as possible appear across the whole game (unlike WILD_FULL_RANDOM,
      which does not try to avoid repeats at all).

    Every randomized mode walks every zone (in `encounters`' own dict
    order) and every slot within a zone (in `_zone_species_refs`'s fixed
    order), so the sequence of `rng` draws -- and therefore the result --
    is fully determined by `rng`'s seed."""
    if mode == WILD_VANILLA:
        return encounters

    pool = real_species_pool(species, exclude_legendaries=exclude_legendaries)
    new_zones: dict[str, dict] = {}
    all_refs: list[tuple[str, dict, str, str]] = []
    for key, zone in encounters.items():
        new_zone, refs = _zone_species_refs(zone)
        new_zones[key] = new_zone
        all_refs.extend((key, container, ref_key, method) for container, ref_key, method in refs)

    if mode == WILD_SHUFFLE:
        shuffled_values = [container[ref_key] for _zone_key, container, ref_key, _method in all_refs]
        rng.shuffle(shuffled_values)
        for (_zone_key, container, ref_key, _method), value in zip(all_refs, shuffled_values):
            container[ref_key] = value
    elif mode == WILD_FULL_RANDOM:
        for _zone_key, container, ref_key, _method in all_refs:
            container[ref_key] = rng.choice(pool)
    elif mode == WILD_ZONE_METHOD_MAPPING:
        groups: dict[tuple[str, str], list[tuple[dict, str]]] = {}
        for zone_key, container, ref_key, method in all_refs:
            groups.setdefault((zone_key, method), []).append((container, ref_key))
        group_keys = sorted(groups)  # deterministic order for the rng draw
        replacements = _fill_maximizing_distinctness(rng, pool, len(group_keys))
        for group_key, replacement in zip(group_keys, replacements):
            for container, ref_key in groups[group_key]:
                container[ref_key] = replacement
    else:
        raise ValueError(f"unknown wild-encounter randomization mode: {mode!r}")

    return {key: _finalize_zone(zone) for key, zone in new_zones.items()}


# Encounter method names as used by species_encounter_methods below. "land"
# and "headbutt" carry no vanilla HM/badge gate (see data_gen/rules.toml's
# header -- headbutt is a Gen4 tutor move, not an HM); the other five each
# need a specific item (an HM+badge pair for surf/rock_smash, a bag key item
# for the three fishing rods) before the player can actually trigger that
# encounter table.
_UNGATED_ENCOUNTER_METHODS = frozenset({"land", "headbutt"})


def species_encounter_methods(encounters: dict) -> dict[str, frozenset[str]]:
    """Map every species appearing anywhere in `encounters` (normally
    world.generated_encounters, i.e. already through
    randomize_wild_encounters for this seed) to the set of encounter
    methods it's obtainable through -- 'land', 'surf', 'rock_smash',
    'old_rod', 'good_rod', 'super_rod', 'headbutt'. Used by Dexsanity
    (task M3.4) to scope its locations to species genuinely catchable in
    this seed, and to size each one's access rule to the cheapest method
    that actually works."""
    result: dict[str, set[str]] = {}

    def add(species: str, method: str) -> None:
        result.setdefault(species, set()).add(method)

    for zone in encounters.values():
        for slot in zone["land"]["slots"]:
            for time_of_day in ("morn", "day", "nite"):
                add(slot[time_of_day], "land")
        for slot in zone["surf"]["slots"]:
            add(slot["species"], "surf")
        for slot in zone["rock_smash"]["slots"]:
            add(slot["species"], "rock_smash")
        for rod, table in zone["fishing"].items():
            for slot in table["slots"]:
                add(slot["species"], rod)
        for tier_slots in zone.get("headbutt", {}).values():
            for slot in tier_slots:
                add(slot["species"], "headbutt")

    return {species: frozenset(methods) for species, methods in result.items()}


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


def scale_trainer_levels_by_sphere(trainers: dict, trainer_sphere: dict[str, int], bonus: int = 0) -> dict:
    """Rescale every trainer's party around a target level derived from
    how deep into the *actual randomized region graph* that trainer sits
    (`trainer_sphere`: trainer key -> 0-indexed sphere, from the real
    fill's own item-collection order -- not vanilla story position), an
    alternative to the flat-percentage `scale_trainer_levels` above.
    Target level curve is linear between the weakest and strongest
    vanilla trainer level found anywhere in `trainers` (sphere 0 -> that
    minimum, the deepest sphere present in `trainer_sphere` -> that
    maximum), then shifted by `bonus` levels (negative = easier, positive
    = harder) before clamping. Each trainer's party is scaled
    proportionally around its own strongest mon (preserving relative
    levels within the party, the same "reshape around a base level" idea
    `scale_trainer_levels` uses for a flat percentage). A trainer absent
    from `trainer_sphere` (its region was never reached in this seed's
    own fill) is left unchanged. Empty `trainer_sphere` returns
    `trainers` unchanged."""
    if not trainer_sphere:
        return trainers

    # Scoped to just the trainers this call is actually scaling (e.g. Gym
    # Leaders only, or regular trainers only, depending on the caller) --
    # not the whole `trainers` dict, which would pull the target curve
    # toward this seed's single weakest/strongest trainer of ANY kind.
    all_levels = [mon["level"] for key in trainer_sphere for mon in trainers[key]["party"]]
    min_level, max_level = min(all_levels), max(all_levels)
    max_sphere = max(trainer_sphere.values())

    new_trainers: dict[str, dict] = {}
    for key, trainer in trainers.items():
        sphere = trainer_sphere.get(key)
        if sphere is None:
            new_trainers[key] = trainer
            continue
        base_target = min_level if max_sphere == 0 else min_level + (max_level - min_level) * sphere / max_sphere
        target_level = max(_MIN_LEVEL, min(_MAX_LEVEL, round(base_target + bonus)))
        old_base_level = max(mon["level"] for mon in trainer["party"])
        new_party = tuple(
            {**mon, "level": max(_MIN_LEVEL, min(_MAX_LEVEL, round(mon["level"] * target_level / old_base_level)))}
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


# Trade ("trade", "trade_item") and friendship ("friendship",
# "friendship_day", "friendship_night") evolution methods all genuinely
# require a second player/console to trigger in vanilla -- a real
# single-player accessibility problem, independent of whether
# randomize_evolutions above is on (a randomized evolution can just as
# easily land on one of these methods as a vanilla one already had).
_TRADE_AND_FRIENDSHIP_EVOLUTION_METHODS = frozenset(
    {"trade", "trade_item", "friendship", "friendship_day", "friendship_night"}
)


def convert_trade_and_friendship_evolutions(species: dict, enabled: bool, level: int) -> dict:
    """Rewrite every evolution edge whose *current* method (vanilla, or
    already-randomized by `randomize_evolutions` above) is trade- or
    friendship-based into a plain `level` evolution at `level` instead --
    a QoL/accessibility option, not a randomizer. Runs after
    `randomize_evolutions` so it always sees (and fixes) whichever method
    a given edge actually ended up with. `enabled=False` returns `species`
    unchanged."""
    if not enabled:
        return species

    new_species: dict[str, dict] = {}
    for key, data in species.items():
        new_evolutions = []
        for evo in data["evolutions"]:
            if evo["method"] in _TRADE_AND_FRIENDSHIP_EVOLUTION_METHODS:
                new_evolutions.append({"method": "level", "target": evo["target"], "param": level})
            else:
                new_evolutions.append(evo)
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


def randomize_move_categories(rng: Random, enabled: bool, moves: dict = MOVES) -> dict:
    """Randomize each damaging move's Category between "physical" and
    "special" (a coin flip per move). "status" moves are never touched
    either direction -- a damaging move never becomes "status" and vice
    versa, since Generation IV's category determines which stat pair
    (Attack/Defense vs Sp. Attack/Sp. Defense) the move actually uses.
    `enabled=False` returns `moves` unchanged."""
    if not enabled:
        return moves

    return {
        key: (
            {**data, "category": rng.choice(("physical", "special"))} if data["category"] != "status" else data
        )
        for key, data in moves.items()
    }


def randomize_tm_hm_moves(rng: Random, enabled: bool, tm_hm_moves: dict = TM_HM_MOVES) -> dict:
    """Shuffle which move each TM (TM01-TM92) teaches -- a permutation, so
    the same 92 moves stay available, just reassigned across machine
    numbers. HM01-HM08 are never touched: this project's region-access
    rules key off owning the HM item, not off whatever move it currently
    teaches, so an HM must always teach its vanilla field move or a
    player with the AP-logic "Surf" item could be left unable to actually
    Surf. `enabled=False` returns `tm_hm_moves` unchanged."""
    if not enabled:
        return tm_hm_moves

    tm_keys = tuple(k for k in tm_hm_moves if k.startswith("tm"))
    shuffled_moves = [tm_hm_moves[k] for k in tm_keys]
    rng.shuffle(shuffled_moves)
    new_tm_moves = dict(zip(tm_keys, shuffled_moves))

    return {key: new_tm_moves.get(key, value) for key, value in tm_hm_moves.items()}


def randomize_type_chart(rng: Random, enabled: bool, type_chart: list = TYPE_CHART) -> list:
    """Shuffle the `multiplier` (not_effective/no_effect/super_effective)
    column across every `randomizable: True` row -- a permutation, so the
    same overall mix of immunities/resistances/weaknesses still exists,
    just redistributed onto different attacker/defender pairs. Each row's
    own `attacker`/`defender`/`special` fields and the list's own order
    are never touched (row order encodes a real engine dependency -- see
    data_gen/type_chart.toml's header comment -- reordering would be
    unsafe even though this function never does it). The two
    `randomizable: False` marker rows (foresight_marker, end_table) are
    never touched either direction. `enabled=False` returns `type_chart`
    unchanged."""
    if not enabled:
        return type_chart

    randomizable_indices = [i for i, row in enumerate(type_chart) if row["randomizable"]]
    shuffled_multipliers = [type_chart[i]["multiplier"] for i in randomizable_indices]
    rng.shuffle(shuffled_multipliers)

    new_chart = list(type_chart)
    for i, multiplier in zip(randomizable_indices, shuffled_multipliers):
        new_chart[i] = {**new_chart[i], "multiplier": multiplier}
    return new_chart


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


def randomize_learnsets(rng: Random, enabled: bool, species: dict = SPECIES) -> dict:
    """Randomize each species' level-up learnset (`level_learnset`, a
    tuple of `(level, move_key)` pairs) -- each entry's move is replaced
    with an independently-drawn real move, the level it's learned at is
    left untouched (matches vanilla level-up pacing, only which move
    lands there changes). Purely cosmetic to this project's own logic:
    unlike `randomize_tm_moves`, no region-access rule anywhere depends
    on which move a species learns by leveling up (only on owning the HM
    *item*, see randomize_tm_hm_moves's own docstring), so there is no
    HM-exclusion concern here the way there was there. `enabled=False`
    returns `species` unchanged."""
    if not enabled:
        return species

    move_keys = tuple(MOVES.keys())
    new_species: dict[str, dict] = {}
    for key, data in species.items():
        new_learnset = tuple((level, rng.choice(move_keys)) for level, _move_key in data["level_learnset"])
        new_species[key] = {**data, "level_learnset": new_learnset}
    return new_species
