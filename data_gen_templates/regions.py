# data_gen_templates/regions.py
#
# Turns `data_gen/regions.toml` into `data/regions.py` (task C4, Johto).
# Follows the same load_toml -> dict-literal-repr pattern as `generate_items`
# in `data_gen_templates/items.py`. See `data_gen/regions.toml`'s header for
# the source/extraction notes (zone_event warps + map_matrix_0000_EVERYWHERE
# outdoor adjacency, and the hand-patched Ruins of Alph/magnet-train edges).

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any

from . import GENERATED_FILE_HEADER, load_toml

# Regions intentionally out of v1 scope (docs/scope.md) that some in-scope
# region's `exits` still points at (the vanilla map connects there, but the
# feature behind it -- Pokeathlon, Safari Zone, Battle Frontier, Union Room
# -- isn't modeled yet). Any *other* unresolved exit target is not expected
# and likely indicates a real gap in regions.toml (see R1 review, C4/C5).
EXPECTED_V2_DANGLING_EXITS = frozenset(
    {
        "pokeathlon_dome",
        "safari_zone_gate",
        "battle_frontier_frontier_access",
        "union",
    }
)


def _build_region(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "map_code": entry["map_code"],
        "exits": list(entry.get("exits", [])),
    }


def generate_regions() -> str:
    """Build the contents of `data/regions.py` from `data_gen/regions.toml`."""
    regions_toml = load_toml("regions")

    regions: dict[str, dict[str, Any]] = {
        key: _build_region(entry) for key, entry in regions_toml.items()
    }

    # Defensive: an `exits` target should normally resolve to another region
    # defined in this same file. `EXPECTED_V2_DANGLING_EXITS` are the only
    # known, intentional exceptions (out-of-v1-scope features, see
    # docs/scope.md); those get a quiet, distinct notice. Anything else is
    # unexpected and warned loudly, since it's most likely a real extraction
    # gap (e.g. the C4 `national_park_unused_gatehouse` miss caught in
    # review) rather than a documented scope boundary. Either way this only
    # warns, it never drops the exit or raises.
    for key, region in regions.items():
        for target in region["exits"]:
            if target in regions:
                continue
            if target in EXPECTED_V2_DANGLING_EXITS:
                print(
                    f"note: data_gen/regions.toml: {key}.exits references "
                    f"{target!r}, a documented v2/out-of-scope region "
                    "(docs/scope.md); keeping as-is.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"WARNING: data_gen/regions.toml: {key}.exits references "
                    f"unresolved region {target!r}, which is not in "
                    "EXPECTED_V2_DANGLING_EXITS -- this likely indicates a "
                    "missing region (a real extraction gap), not a known "
                    "scope boundary. Keeping as-is, but this should be "
                    "investigated.",
                    file=sys.stderr,
                )

    lines = [GENERATED_FILE_HEADER, "\n", "REGIONS = {\n"]
    for key, region in regions.items():
        lines.append(f"    {key!r}: {region!r},\n")
    lines.append("}\n")
    return "".join(lines)
