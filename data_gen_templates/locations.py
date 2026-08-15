# data_gen_templates/locations.py
#
# Turns `data_gen/locations.toml` into `data/locations.py` (task C4, Johto).
# Follows the same load_toml -> dict-literal-repr pattern as `generate_items`
# in `data_gen_templates/items.py`. See `data_gen/locations.toml`'s header
# for the source/extraction notes (ground_item/hidden_item/npc_gift/hm_tm/
# badge methodology, and the v1-scope exclusions).

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any

from . import GENERATED_FILE_HEADER, load_toml

_VALID_TYPES = {
    "ground_item",
    "hidden_item",
    "npc_gift",
    "hm_tm",
    "badge",
    "event",
    "trainer",
    "dexsanity",
    "static_pokemon",
}


def _build_location(entry: Mapping[str, Any]) -> dict[str, Any]:
    location: dict[str, Any] = {
        "region": entry["region"],
        "type": entry["type"],
        "id": entry["id"],
    }
    # original_item is absent for badge/event/trainer/dexsanity locations
    # (see data_gen/locations.toml header); x/z and label are only present
    # for a subset of location kinds; event is only present for type =
    # 'event'; trainer is only present for type = 'trainer'; species is only
    # present for type = 'dexsanity'.
    if "original_item" in entry:
        location["original_item"] = entry["original_item"]
    if "x" in entry:
        location["x"] = entry["x"]
    if "z" in entry:
        location["z"] = entry["z"]
    if "label" in entry:
        location["label"] = entry["label"]
    if "event" in entry:
        location["event"] = entry["event"]
    if "trainer" in entry:
        location["trainer"] = entry["trainer"]
    if "species" in entry:
        location["species"] = entry["species"]
    return location


def generate_locations() -> str:
    """Build the contents of `data/locations.py` from
    `data_gen/locations.toml`."""
    locations_toml = load_toml("locations")
    regions_toml = load_toml("regions")
    items_toml = load_toml("items")
    trainers_toml = load_toml("trainers")
    species_toml = load_toml("species")

    locations: dict[str, dict[str, Any]] = {}
    seen_ids: dict[tuple[str, int], str] = {}
    for key, entry in locations_toml.items():
        location = _build_location(entry)

        # Defensive: same spirit as data_gen_templates/items.py -- data_gen
        # sources are hand-editable even though this file was originally
        # machine-extracted from the decomp, so guard against a future edit
        # introducing an unknown type, a dangling region/item reference, or a
        # duplicate id within the same location type (ids are only meant to
        # be unique per-type here, e.g. a ground_item and a badge may
        # legitimately share a raw decomp id since they come from different
        # decomp id spaces -- see data_gen/locations.toml's header).
        if location["type"] not in _VALID_TYPES:
            print(
                f"warning: data_gen/locations.toml: {key}.type is "
                f"{location['type']!r}, expected one of {sorted(_VALID_TYPES)}; "
                "keeping as-is.",
                file=sys.stderr,
            )
        if location["region"] not in regions_toml:
            print(
                f"warning: data_gen/locations.toml: {key}.region references "
                f"unknown region {location['region']!r}; keeping as-is.",
                file=sys.stderr,
            )
        original_item = location.get("original_item")
        if original_item is not None and original_item not in items_toml:
            print(
                f"warning: data_gen/locations.toml: {key}.original_item "
                f"references unknown item {original_item!r}; keeping as-is.",
                file=sys.stderr,
            )
        trainer = location.get("trainer")
        if trainer is not None and trainer not in trainers_toml:
            print(
                f"warning: data_gen/locations.toml: {key}.trainer references "
                f"unknown trainer {trainer!r}; keeping as-is.",
                file=sys.stderr,
            )
        species = location.get("species")
        if species is not None and species not in species_toml:
            print(
                f"warning: data_gen/locations.toml: {key}.species references "
                f"unknown species {species!r}; keeping as-is.",
                file=sys.stderr,
            )
        id_key = (location["type"], location["id"])
        existing = seen_ids.get(id_key)
        if existing is not None:
            print(
                f"warning: data_gen/locations.toml: {key} has the same "
                f"(type, id) as {existing} ({id_key!r}); both will be kept "
                "in data/locations.py.",
                file=sys.stderr,
            )
        else:
            seen_ids[id_key] = key

        locations[key] = location

    lines = [GENERATED_FILE_HEADER, "\n", "LOCATIONS = {\n"]
    for key, location in locations.items():
        lines.append(f"    {key!r}: {location!r},\n")
    lines.append("}\n")
    return "".join(lines)
