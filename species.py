from __future__ import annotations

from collections.abc import Callable
from random import Random

from data.encounters import ENCOUNTERS
from data.moves import MOVES, TM_HM_MOVES
from data.species import SPECIES
from data.trainers import TRAINERS
from data.type_chart import TYPE_CHART

WILD_VANILLA = 0
WILD_SHUFFLE = 1
WILD_FULL_RANDOM = 2
WILD_ZONE_METHOD_MAPPING = 3

EVOLUTIONS_OFF = 0
EVOLUTIONS_KEEP_METHOD = 1
EVOLUTIONS_ANY_METHOD = 2

BASE_STATS_OFF = 0
BASE_STATS_SHUFFLE = 1
BASE_STATS_FULL_RANDOM = 2

MOVES_OFF = 0
MOVES_SHUFFLE = 1
MOVES_FULL_RANDOM = 2
MOVES_BALANCED = 3

_BASE_STAT_FIELDS = ("hp", "atk", "def", "spatk", "spdef", "speed")
_MOVE_COMBAT_FIELDS = ("power", "accuracy", "pp")

VANILLA_STARTERS = ("chikorita", "cyndaquil", "totodile")

_FISHING_RODS = ("old_rod", "good_rod", "super_rod")
_HEADBUTT_TIERS = ("common", "rare", "secret")

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
    pool = (key for key, data in species.items() if data["national_dex"] is not None)
    if exclude_legendaries:
        pool = (key for key in pool if key not in LEGENDARY_SPECIES)
    return tuple(sorted(pool))


def randomize_starters(
    rng: Random, enabled: bool, species: dict = SPECIES, *, exclude_legendaries: bool = False
) -> tuple[str, str, str]:
    if not enabled:
        return VANILLA_STARTERS
    pool = tuple(
        key for key in real_species_pool(species, exclude_legendaries=exclude_legendaries) if species[key]["evolutions"]
    )
    return tuple(rng.sample(pool, k=3))


def _zone_species_refs(zone: dict) -> tuple[dict, list[tuple[dict, str, str]]]:
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
        group_keys = sorted(groups)
        replacements = _fill_maximizing_distinctness(rng, pool, len(group_keys))
        for group_key, replacement in zip(group_keys, replacements):
            for container, ref_key in groups[group_key]:
                container[ref_key] = replacement
    else:
        raise ValueError(f"unknown wild-encounter randomization mode: {mode!r}")

    return {key: _finalize_zone(zone) for key, zone in new_zones.items()}


def species_encounter_sources(
    encounters: dict, *, source_filter: Callable[[str, str], bool] | None = None
) -> dict[str, frozenset[tuple[str, str]]]:
    result: dict[str, set[tuple[str, str]]] = {}

    def add(species: str, zone_key: str, method: str) -> None:
        if source_filter is not None and not source_filter(zone_key, method):
            return
        result.setdefault(species, set()).add((zone_key, method))

    for zone_key, zone in encounters.items():
        for slot in zone["land"]["slots"]:
            for time_of_day in ("morn", "day", "nite"):
                add(slot[time_of_day], zone_key, "land")
        for slot in zone["surf"]["slots"]:
            add(slot["species"], zone_key, "surf")
        for slot in zone["rock_smash"]["slots"]:
            add(slot["species"], zone_key, "rock_smash")
        for rod, table in zone["fishing"].items():
            for slot in table["slots"]:
                add(slot["species"], zone_key, rod)
        for tier, tier_slots in zone.get("headbutt", {}).items():
            method = "headbutt_secret" if tier == "secret" else "headbutt"
            for slot in tier_slots:
                add(slot["species"], zone_key, method)

    return {species: frozenset(sources) for species, sources in result.items()}


def species_encounter_methods(
    encounters: dict, *, source_filter: Callable[[str, str], bool] | None = None
) -> dict[str, frozenset[str]]:
    return {
        species: frozenset(
            "headbutt" if method == "headbutt_secret" else method for _zone_key, method in sources
        )
        for species, sources in species_encounter_sources(encounters, source_filter=source_filter).items()
    }


def randomize_trainer_parties(rng: Random, enabled: bool, trainers: dict = TRAINERS, species: dict = SPECIES) -> dict:
    if not enabled:
        return trainers

    pool = real_species_pool(species)
    new_trainers: dict[str, dict] = {}
    for key, trainer in trainers.items():
        new_party = tuple({**mon, "species": rng.choice(pool)} for mon in trainer["party"])
        new_trainers[key] = {**trainer, "party": new_party}
    return new_trainers


_MIN_LEVEL = 1
_MAX_LEVEL = 100


def scale_trainer_levels(scale_percent: int, trainers: dict = TRAINERS) -> dict:
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
    if not trainer_sphere:
        return trainers

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
        old_base_level = max(mon["level"] for mon in trainer["party"])
        new_party = tuple(
            {**mon, "level": max(_MIN_LEVEL, min(_MAX_LEVEL, round(mon["level"] * base_target / old_base_level) + bonus))}
            for mon in trainer["party"]
        )
        new_trainers[key] = {**trainer, "party": new_party}
    return new_trainers


_UNASSIGNABLE_EVOLUTION_METHODS = frozenset(
    {"coronet", "eterna", "route217", "level_ninjask", "level_shedinja", "trade", "trade_item"}
)
_UNASSIGNABLE_EVOLUTION_PAIRS = frozenset({("item_night", "razor_claw"), ("item_night", "razor_fang")})


def _all_method_param_pairs(species: dict) -> tuple[tuple[str, object], ...]:
    pairs = {
        (evo["method"], evo["param"])
        for data in species.values()
        for evo in data["evolutions"]
        if evo["method"] not in _UNASSIGNABLE_EVOLUTION_METHODS
        and (evo["method"], evo["param"]) not in _UNASSIGNABLE_EVOLUTION_PAIRS
    }
    return tuple(sorted(pairs, key=lambda pair: (pair[0], str(pair[1]))))


def randomize_evolutions(rng: Random, mode: int, species: dict = SPECIES) -> dict:
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


_TRADE_AND_FRIENDSHIP_EVOLUTION_METHODS = frozenset(
    {"trade", "trade_item", "friendship", "friendship_day", "friendship_night"}
)
_LOCATION_EVOLUTION_STONES = {"eterna": "leaf_stone", "route217": "dawn_stone"}


def convert_trade_and_friendship_evolutions(species: dict, enabled: bool, level: int) -> dict:
    if not enabled:
        return species

    new_species: dict[str, dict] = {}
    for key, data in species.items():
        new_evolutions = []
        for evo in data["evolutions"]:
            if evo["method"] in _TRADE_AND_FRIENDSHIP_EVOLUTION_METHODS or evo["method"] == "coronet":
                new_evolutions.append({"method": "level", "target": evo["target"], "param": level})
            elif evo["method"] in _LOCATION_EVOLUTION_STONES:
                stone = _LOCATION_EVOLUTION_STONES[evo["method"]]
                new_evolutions.append({"method": "stone", "target": evo["target"], "param": stone})
            else:
                new_evolutions.append(evo)
        new_species[key] = {**data, "evolutions": tuple(new_evolutions)}
    return restore_shadowed_time_evolutions(new_species)


def restore_shadowed_time_evolutions(species: dict, vanilla: dict = SPECIES) -> dict:
    time_methods = {"friendship_day", "friendship_night"}
    fixed: dict[str, dict] = {}
    for key, data in species.items():
        levels = [evo["param"] for evo in data["evolutions"] if evo["method"] == "level"]
        vanilla_evolutions = vanilla.get(key, {}).get("evolutions", ())
        evolutions = []
        for index, evo in enumerate(data["evolutions"]):
            original = vanilla_evolutions[index] if index < len(vanilla_evolutions) else None
            if (
                evo["method"] == "level"
                and levels.count(evo["param"]) > 1
                and original is not None
                and original["method"] in time_methods
            ):
                evo = {**original, "target": evo["target"]}
            evolutions.append(evo)
        fixed[key] = {**data, "evolutions": _split_same_level_pair(tuple(evolutions))}
    return fixed


def _split_same_level_pair(evolutions: tuple[dict, ...]) -> tuple[dict, ...]:
    level_edges = [index for index, evo in enumerate(evolutions) if evo["method"] == "level"]
    by_level: dict[object, list[int]] = {}
    for index in level_edges:
        by_level.setdefault(evolutions[index]["param"], []).append(index)
    result = list(evolutions)
    for indexes in by_level.values():
        if len(indexes) == 2:
            first, second = indexes
            result[first] = {**result[first], "method": "level_pid_lo"}
            result[second] = {**result[second], "method": "level_pid_hi"}
    return tuple(result)


def ensure_evolution_moves_learnable(species: dict) -> dict:
    fixed: dict[str, dict] = {}
    for key, data in species.items():
        needed = [evo["param"] for evo in data["evolutions"] if evo["method"] == "has_move"]
        learnset = list(data["level_learnset"])
        for move in needed:
            if learnset and all(move_key != move for _level, move_key in learnset):
                learnset[-1] = (learnset[-1][0], move)
        fixed[key] = {**data, "level_learnset": tuple(learnset)} if needed else data
    return fixed


_BASE_STAT_MIN = 1
_BASE_STAT_MAX = 255


def _redistribute_preserving_total(rng: Random, total: int, count: int) -> list[int]:
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

_MOVE_POWER_SENTINEL = 1

_SINGLE_HIT_POWER_RANGE = (40, 250)
_MULTI_HIT_MIN_PER_HIT_POWER = 10
_MOVE_ACCURACY_RANGE = (40, 100)
_MOVE_ACCURACY_JITTER = 10
_MOVE_ACCURACY_STEP = 5
_PP_CHOICES = (5, 10, 15, 20, 25, 30, 35, 40)


def _round_to_multiple(value: float, multiple: int, low: int, high: int) -> int:
    rounded = round(value / multiple) * multiple
    return max(low, min(high, rounded))


_BALANCED_ACCURACY_FLOOR = 75

_BALANCED_STAT_STEP = 5

_BALANCED_TIERS = (
    (50, (55, 95), (100, 100)),
    (25, (110, 145), (95, 100)),
    (20, (150, 195), (85, 95)),
    (5, (210, 250), (75, 85)),
)
_BALANCED_TIER_WEIGHTS = tuple(tier[0] for tier in _BALANCED_TIERS)

_BALANCED_MULTI_HIT_EFFECT_HITS: dict[str, float] = {
    "multi_hit": 3.0,
    "hit_twice": 2.0,
    "hit_three_times": 3.0,
    "poison_multi_hit": 2.0,
}

_BALANCED_EXCLUDED_EFFECTS = frozenset(
    {
        "one_hit_ko",
        "double_power_each_turn",
        "double_power_each_turn_lock_into",
        "beat_up",
        "struggle",
    }
)


def _balanced_power_and_accuracy(rng: Random, effect: str) -> tuple[int, int]:
    _, (power_low, power_high), (accuracy_low, accuracy_high) = rng.choices(
        _BALANCED_TIERS, weights=_BALANCED_TIER_WEIGHTS
    )[0]

    rolled_power = rng.randrange(power_low, power_high + 1, _BALANCED_STAT_STEP)
    hits = _BALANCED_MULTI_HIT_EFFECT_HITS.get(effect)
    power = rolled_power if hits is None else max(_MULTI_HIT_MIN_PER_HIT_POWER, round(rolled_power / hits))

    accuracy = rng.randrange(accuracy_low, accuracy_high + 1, _BALANCED_STAT_STEP)
    return power, accuracy


def _random_power_and_accuracy(rng: Random, move_key: str, category: str, vanilla_power: int) -> tuple[int, int]:
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
    elif mode == MOVES_BALANCED:
        for key in keys:
            new_combat_stats[key]["pp"] = rng.choice(_PP_CHOICES)

        for key in keys:
            data = moves[key]
            new_combat_stats[key]["power"] = data["power"]
            new_combat_stats[key]["accuracy"] = data["accuracy"]
            if (
                data["category"] == "status"
                or data["power"] == _MOVE_POWER_SENTINEL
                or data["effect"] in _BALANCED_EXCLUDED_EFFECTS
            ):
                continue
            power, accuracy = _balanced_power_and_accuracy(rng, data["effect"])
            new_combat_stats[key]["power"] = power
            if data["accuracy"] != 0:
                new_combat_stats[key]["accuracy"] = accuracy
    else:
        raise ValueError(f"unknown move-stat randomization mode: {mode!r}")

    return {key: {**data, **new_combat_stats[key]} for key, data in moves.items()}


def randomize_move_types(rng: Random, enabled: bool, moves: dict = MOVES) -> dict:
    if not enabled:
        return moves

    real_types = tuple(sorted({data["type"] for data in moves.values()} - {"mystery"}))
    return {key: {**data, "type": rng.choice(real_types)} for key, data in moves.items()}


def randomize_move_categories(rng: Random, enabled: bool, moves: dict = MOVES) -> dict:
    if not enabled:
        return moves

    return {
        key: (
            {**data, "category": rng.choice(("physical", "special"))} if data["category"] != "status" else data
        )
        for key, data in moves.items()
    }


def randomize_tm_hm_moves(rng: Random, enabled: bool, tm_hm_moves: dict = TM_HM_MOVES) -> dict:
    if not enabled:
        return tm_hm_moves

    tm_keys = tuple(k for k in tm_hm_moves if k.startswith("tm") and k != "tm70")
    shuffled_moves = [tm_hm_moves[k] for k in tm_keys]
    rng.shuffle(shuffled_moves)
    new_tm_moves = dict(zip(tm_keys, shuffled_moves))

    return {key: new_tm_moves.get(key, value) for key, value in tm_hm_moves.items()}


def randomize_type_chart(rng: Random, enabled: bool, type_chart: list = TYPE_CHART) -> list:
    if not enabled:
        return type_chart

    randomizable_indices = [i for i, row in enumerate(type_chart) if row["randomizable"]]
    shuffled_multipliers = [type_chart[i]["multiplier"] for i in randomizable_indices]
    rng.shuffle(shuffled_multipliers)

    new_chart = list(type_chart)
    for i, multiplier in zip(randomizable_indices, shuffled_multipliers):
        new_chart[i] = {**new_chart[i], "multiplier": multiplier}
    return new_chart


_OHKO_NEUTRALIZED_EFFECT = "hit"
_OHKO_NEUTRALIZED_POWER = 60
_OHKO_NEUTRALIZED_ACCURACY = 100


def disable_ohko_moves(enabled: bool, moves: dict = MOVES) -> dict:
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


TRAPPING_ABILITIES = frozenset({23, 42, 71})
_RUN_AWAY_ABILITY = 50


def neutralize_trapping_abilities(enabled: bool, species: dict = SPECIES) -> dict:
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
            new_abilities = (_RUN_AWAY_ABILITY, 0)
        elif trap1:
            new_abilities = (ability2, ability2)
        else:
            new_abilities = (ability1, ability1)

        new_species[key] = {**data, "abilities": new_abilities}
    return new_species


def randomize_learnsets(rng: Random, enabled: bool, species: dict = SPECIES) -> dict:
    if not enabled:
        return species

    move_keys = tuple(MOVES.keys())
    new_species: dict[str, dict] = {}
    for key, data in species.items():
        new_learnset = tuple((level, rng.choice(move_keys)) for level, _move_key in data["level_learnset"])
        new_species[key] = {**data, "level_learnset": new_learnset}
    return new_species
