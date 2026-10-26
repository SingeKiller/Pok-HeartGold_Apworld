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
    if "soulsilver_region" in entry:
        location["soulsilver_region"] = entry["soulsilver_region"]
    return location


def generate_locations() -> str:
    locations_toml = load_toml("locations")
    regions_toml = load_toml("regions")
    items_toml = load_toml("items")
    trainers_toml = load_toml("trainers")
    species_toml = load_toml("species")

    locations: dict[str, dict[str, Any]] = {}
    seen_ids: dict[tuple[str, int], str] = {}
    for key, entry in locations_toml.items():
        location = _build_location(entry)

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
        soulsilver_region = location.get("soulsilver_region")
        if soulsilver_region is not None and soulsilver_region not in regions_toml:
            print(
                f"warning: data_gen/locations.toml: {key}.soulsilver_region "
                f"references unknown region {soulsilver_region!r}; keeping as-is.",
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
