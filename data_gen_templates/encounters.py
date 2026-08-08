# data_gen_templates/encounters.py
#
# Turns `data_gen/encounters.toml` into `data/encounters.py` (task C7a, wild
# encounters only -- trainer parties are a separate task, see
# data_gen/encounters.toml's header note). Follows the same
# load_toml -> dict-literal-repr pattern as `generate_regions` in
# `data_gen_templates/regions.py`. See `data_gen/encounters.toml`'s header
# for the source/extraction notes (map-code -> region resolution, the 9
# dropped zones, HEARTGOLD/SOULSILVER version resolution, table shapes).

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any

from . import GENERATED_FILE_HEADER, load_toml

_TIME_OF_DAY = ("morn", "day", "nite")
_ROD_KINDS = ("old_rod", "good_rod", "super_rod")


def _check_species(
    zone_key: str, table_path: str, species_key: str, species_keys: set[str]
) -> None:
    if species_key not in species_keys:
        print(
            f"warning: data_gen/encounters.toml: {zone_key}.{table_path} "
            f"references unknown species {species_key!r}; keeping as-is.",
            file=sys.stderr,
        )


def _build_land_slots(
    zone_key: str, slots: list[Mapping[str, Any]], species_keys: set[str]
) -> tuple[dict[str, Any], ...]:
    built = []
    for slot in slots:
        for tod in _TIME_OF_DAY:
            _check_species(zone_key, f"land.slots[].{tod}", slot[tod], species_keys)
        built.append(
            {
                "level": slot["level"],
                "morn": slot["morn"],
                "day": slot["day"],
                "nite": slot["nite"],
            }
        )
    return tuple(built)


def _build_flat_slots(
    zone_key: str, table_path: str, slots: list[Mapping[str, Any]], species_keys: set[str]
) -> tuple[dict[str, Any], ...]:
    built = []
    for slot in slots:
        _check_species(zone_key, f"{table_path}.slots[].species", slot["species"], species_keys)
        built.append(
            {
                "level_min": slot["level_min"],
                "level_max": slot["level_max"],
                "species": slot["species"],
            }
        )
    return tuple(built)


def _build_zone(
    key: str, entry: Mapping[str, Any], species_keys: set[str]
) -> dict[str, Any]:
    zone: dict[str, Any] = {
        "map_code": entry["map_code"],
        "land": {
            "rate": entry["land"]["rate"],
            "slots": _build_land_slots(key, entry["land"]["slots"], species_keys),
        },
        "surf": {
            "rate": entry["surf"]["rate"],
            "slots": _build_flat_slots(key, "surf", entry["surf"]["slots"], species_keys),
        },
        "rock_smash": {
            "rate": entry["rock_smash"]["rate"],
            "slots": _build_flat_slots(
                key, "rock_smash", entry["rock_smash"]["slots"], species_keys
            ),
        },
        "fishing": {
            rod: {
                "rate": entry["fishing"][rod]["rate"],
                "slots": _build_flat_slots(
                    key, f"fishing.{rod}", entry["fishing"][rod]["slots"], species_keys
                ),
            }
            for rod in _ROD_KINDS
        },
    }

    headbutt = entry.get("headbutt")
    if headbutt is not None:
        zone["headbutt"] = {
            slot_kind: _build_flat_slots(
                key, f"headbutt.{slot_kind}", headbutt[slot_kind], species_keys
            )
            for slot_kind in ("common", "rare", "secret")
        }

    return zone


def generate_encounters() -> str:
    """Build the contents of `data/encounters.py` from
    `data_gen/encounters.toml`."""
    encounters_toml = load_toml("encounters")
    regions_toml = load_toml("regions")
    species_toml = load_toml("species")
    species_keys = set(species_toml)

    encounters: dict[str, dict[str, Any]] = {}
    for key, entry in encounters_toml.items():
        # Defensive: same spirit as data_gen_templates/locations.py -- this
        # file was machine-extracted but is hand-editable, so guard against
        # a future edit introducing a dangling region reference (species
        # references are checked slot-by-slot in _build_zone/_check_species).
        if key not in regions_toml:
            print(
                f"warning: data_gen/encounters.toml: {key!r} does not match "
                "any region in data_gen/regions.toml; keeping as-is.",
                file=sys.stderr,
            )
        encounters[key] = _build_zone(key, entry, species_keys)

    lines = [GENERATED_FILE_HEADER, "\n", "ENCOUNTERS = {\n"]
    for key, zone in encounters.items():
        lines.append(f"    {key!r}: {zone!r},\n")
    lines.append("}\n")
    return "".join(lines)
