# regions.py
#
# Builds the Archipelago region graph (`Region` + `Entrance`) for HeartGold &
# SoulSilver from the generated `data/regions.py` (450 regions, each with a
# list of `exits`). Follows the same overall shape as
# `ressources/platinum_archipelago/regions.py` (read-only reference, not
# copied), simplified: this project's `data/regions.py` has no per-region
# "group"/wild-encounter/trainer subgraph yet (out of this task's scope --
# see the task brief), so this module only needs to build the plain
# region/exit graph.
#
# No `Location` objects are created here -- see `locations.create_locations`,
# which attaches `HeartGoldLocation` objects to the `Region` objects this
# module returns. No access-rule/logic application either -- see `rules.py`.
# No randomization logic lives here either (see task brief).

from __future__ import annotations

from BaseClasses import MultiWorld, Region
from data.regions import REGIONS


def create_regions(player: int, multiworld: MultiWorld) -> dict[str, Region]:
    """Create one `Region` per `data/regions.py` entry and connect them
    according to each entry's `exits`, registering every region on
    `multiworld` (needed for `multiworld.get_region`/`get_entrance` lookups,
    e.g. by `rules.set_rules`). Returns the `{region_key: Region}` map for
    `locations.create_locations` to attach locations to.

    An `exits` entry that points at a region key not present in
    `data/regions.py` at all is a documented, intentional dangling
    reference to a region outside this project's v1 scope (the Pokeathlon
    Dome, the Safari Zone gate, the Battle Frontier, the online Union Room
    -- see docs/scope.md and `data_gen/regions.toml`'s header notes); no
    `Entrance` is created for it, exactly as a real player would find a dead
    end there.
    """
    regions: dict[str, Region] = {name: Region(name, player, multiworld) for name in REGIONS}
    multiworld.regions.extend(regions.values())

    for name, data in REGIONS.items():
        source = regions[name]
        for exit_name in data["exits"]:
            if exit_name not in regions:
                continue
            source.connect(regions[exit_name], f"{name} -> {exit_name}")

    return regions
