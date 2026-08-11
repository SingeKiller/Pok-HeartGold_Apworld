# data_gen_templates/encounters.py
#
# Turns `data_gen/encounters.toml` into `data/encounters.py` (task C7a, wild
# encounters only -- trainer parties are a separate task, see
# data_gen/encounters.toml's header note). Follows the same
# load_toml -> dict-literal-repr pattern as `generate_regions` in
# `data_gen_templates/regions.py`. See `data_gen/encounters.toml`'s header
# for the source/extraction notes (map-code -> region resolution, the 9
# dropped zones, HEARTGOLD/SOULSILVER version resolution, table shapes).
#
# Version resolution (2026-08-11 fix): 699 fields (across the 137 included
# zones) carry a `{heartgold = ..., soulsilver = ...}` dual-value sub-table
# in the toml instead of a plain scalar, wherever the decomp source actually
# diverges between versions (see data_gen/encounters.toml's header). `_resolve`
# picks the requested version's branch for such fields; plain scalars are
# used as-is for both versions. `generate_encounters` builds two fully
# resolved dicts, `ENCOUNTERS_HEARTGOLD` and `ENCOUNTERS_SOULSILVER`, with no
# trace of the dual-value schema left in either -- callers never need to
# know the toml has version-conditional data.

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any, Literal

from . import GENERATED_FILE_HEADER, load_toml

_TIME_OF_DAY = ("morn", "day", "nite")
_ROD_KINDS = ("old_rod", "good_rod", "super_rod")
_VERSIONS: tuple[Literal["heartgold"], Literal["soulsilver"]] = ("heartgold", "soulsilver")

Version = Literal["heartgold", "soulsilver"]


def _resolve(value: Any, version: Version) -> Any:
    """Resolve a possibly dual-valued toml field for `version`. Dual fields
    are `{heartgold = ..., soulsilver = ...}` inline sub-tables (see
    data_gen/encounters.toml's header); anything else is a plain scalar and
    is returned unchanged for both versions."""
    if isinstance(value, Mapping) and set(value.keys()) == {"heartgold", "soulsilver"}:
        return value[version]
    return value


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
    zone_key: str, slots: list[Mapping[str, Any]], species_keys: set[str], version: Version
) -> tuple[dict[str, Any], ...]:
    built = []
    for slot in slots:
        resolved = {tod: _resolve(slot[tod], version) for tod in _TIME_OF_DAY}
        for tod in _TIME_OF_DAY:
            _check_species(zone_key, f"land.slots[].{tod}", resolved[tod], species_keys)
        built.append(
            {
                "level": _resolve(slot["level"], version),
                "morn": resolved["morn"],
                "day": resolved["day"],
                "nite": resolved["nite"],
            }
        )
    return tuple(built)


def _build_flat_slots(
    zone_key: str,
    table_path: str,
    slots: list[Mapping[str, Any]],
    species_keys: set[str],
    version: Version,
) -> tuple[dict[str, Any], ...]:
    built = []
    for slot in slots:
        species = _resolve(slot["species"], version)
        _check_species(zone_key, f"{table_path}.slots[].species", species, species_keys)
        built.append(
            {
                "level_min": _resolve(slot["level_min"], version),
                "level_max": _resolve(slot["level_max"], version),
                "species": species,
            }
        )
    return tuple(built)


def _build_zone(
    key: str, entry: Mapping[str, Any], species_keys: set[str], version: Version
) -> dict[str, Any]:
    zone: dict[str, Any] = {
        "map_code": entry["map_code"],
        "land": {
            "rate": entry["land"]["rate"],
            "slots": _build_land_slots(key, entry["land"]["slots"], species_keys, version),
        },
        "surf": {
            "rate": entry["surf"]["rate"],
            "slots": _build_flat_slots(
                key, "surf", entry["surf"]["slots"], species_keys, version
            ),
        },
        "rock_smash": {
            "rate": entry["rock_smash"]["rate"],
            "slots": _build_flat_slots(
                key, "rock_smash", entry["rock_smash"]["slots"], species_keys, version
            ),
        },
        "fishing": {
            rod: {
                "rate": entry["fishing"][rod]["rate"],
                "slots": _build_flat_slots(
                    key, f"fishing.{rod}", entry["fishing"][rod]["slots"], species_keys, version
                ),
            }
            for rod in _ROD_KINDS
        },
    }

    headbutt = entry.get("headbutt")
    if headbutt is not None:
        zone["headbutt"] = {
            slot_kind: _build_flat_slots(
                key, f"headbutt.{slot_kind}", headbutt[slot_kind], species_keys, version
            )
            for slot_kind in ("common", "rare", "secret")
        }

    return zone


def _build_encounters(
    encounters_toml: Mapping[str, Any],
    regions_toml: Mapping[str, Any],
    species_keys: set[str],
    version: Version,
) -> dict[str, dict[str, Any]]:
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
        encounters[key] = _build_zone(key, entry, species_keys, version)
    return encounters


def generate_encounters() -> str:
    """Build the contents of `data/encounters.py` from
    `data_gen/encounters.toml`: `ENCOUNTERS_HEARTGOLD` and
    `ENCOUNTERS_SOULSILVER`, each fully resolved for their version, plus
    `ENCOUNTERS` as a HeartGold-compatible alias (see module header)."""
    encounters_toml = load_toml("encounters")
    regions_toml = load_toml("regions")
    species_toml = load_toml("species")
    species_keys = set(species_toml)

    by_version = {
        version: _build_encounters(encounters_toml, regions_toml, species_keys, version)
        for version in _VERSIONS
    }

    lines = [GENERATED_FILE_HEADER, "\n"]
    for version in _VERSIONS:
        var_name = f"ENCOUNTERS_{version.upper()}"
        lines.append(f"{var_name} = {{\n")
        for key, zone in by_version[version].items():
            lines.append(f"    {key!r}: {zone!r},\n")
        lines.append("}\n\n")
    lines.append("# Compatibility alias: everything that predates SoulSilver support\n")
    lines.append("# (notably species.py's randomize_wild_encounters default) imports\n")
    lines.append("# ENCOUNTERS and expects the HeartGold table.\n")
    lines.append("ENCOUNTERS = ENCOUNTERS_HEARTGOLD\n")
    return "".join(lines)
