from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any

from . import GENERATED_FILE_HEADER, load_toml

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
    regions_toml = load_toml("regions")

    regions: dict[str, dict[str, Any]] = {
        key: _build_region(entry) for key, entry in regions_toml.items()
    }

    for key, region in regions.items():
        for target in region["exits"]:
            if target in regions:
                continue
            if target in EXPECTED_V2_DANGLING_EXITS:
                print(
                    f"note: data_gen/regions.toml: {key}.exits references "
                    f"{target!r}, an out-of-scope region; keeping as-is.",
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
