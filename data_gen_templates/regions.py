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
    # defined in this same file. It's expected *not* to for the Johto/Kanto
    # boundary regions (Mount Silver, Victory Road, Tohjo Falls, the
    # Goldenrod<->Saffron magnet train) -- see data_gen/regions.toml's
    # header -- since Kanto regions don't exist yet (a future C5 task), so
    # this only warns, it never drops the exit or raises: the dangling
    # reference is exactly what lets C5 complete the graph later without
    # editing this file. Same defensive spirit as data_gen_templates/items.py.
    for key, region in regions.items():
        for target in region["exits"]:
            if target not in regions:
                print(
                    f"warning: data_gen/regions.toml: {key}.exits references "
                    f"unknown region {target!r} (expected for Johto<->Kanto "
                    "boundary regions until a future Kanto task adds it); "
                    "keeping as-is.",
                    file=sys.stderr,
                )

    lines = [GENERATED_FILE_HEADER, "\n", "REGIONS = {\n"]
    for key, region in regions.items():
        lines.append(f"    {key!r}: {region!r},\n")
    lines.append("}\n")
    return "".join(lines)
