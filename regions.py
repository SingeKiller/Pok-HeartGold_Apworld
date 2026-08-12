# regions.py
#
# Builds the Archipelago region graph (Region + Entrance) from the generated
# data/regions.py. Locations are attached separately by
# locations.create_locations; access rules by rules.py.

from __future__ import annotations

from BaseClasses import MultiWorld, Region
from data.regions import REGIONS


def create_regions(player: int, multiworld: MultiWorld) -> dict[str, Region]:
    """Create one Region per data/regions.py entry and connect them per
    each entry's exits. An exits entry pointing at a region key outside
    v1 scope (Pokeathlon Dome, Safari Zone gate, Battle Frontier, Union
    Room -- see docs/scope.md) is skipped: no Entrance is created, exactly
    as a real player would find a dead end there."""
    regions: dict[str, Region] = {name: Region(name, player, multiworld) for name in REGIONS}
    multiworld.regions.extend(regions.values())

    for name, data in REGIONS.items():
        source = regions[name]
        for exit_name in data["exits"]:
            if exit_name not in regions:
                continue
            source.connect(regions[exit_name], f"{name} -> {exit_name}")

    return regions
