# data_gen_templates/species.py
#
# Turns `data_gen/species.toml` into `data/species.py` (task C2). Follows the
# same load_toml -> dict-literal-repr pattern as `generate_init` in
# `data_gen_templates/__init__.py`. TM/HM machine numbers recorded in
# `data_gen/species.toml` (`tms`/`hms`, matching the decomp's raw
# `personal.json` numbering) are resolved here to move keys via
# `data_gen/moves.toml`'s `[tm_hm]` table, so `data/species.py` is directly
# usable without needing to cross-reference `data/moves.py` at runtime.

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any

from . import GENERATED_FILE_HEADER, load_toml


def _resolve_tm_hm(
    species_key: str,
    kind: str,
    numbers: Any,
    tm_hm: Mapping[str, str],
    move_keys: set[str],
) -> tuple[str, ...]:
    resolved = []
    prefix = "tm" if kind == "tms" else "hm"
    for number in numbers:
        machine = f"{prefix}{number:02d}"
        move_key = tm_hm.get(machine)
        if move_key is None or move_key not in move_keys:
            print(
                f"warning: data_gen/species.toml: {species_key}.{kind} "
                f"references {machine!r}, which data_gen/moves.toml's "
                f"[tm_hm] table does not resolve to a known move; skipping.",
                file=sys.stderr,
            )
            continue
        resolved.append(move_key)
    return tuple(resolved)


def _build_species(
    key: str,
    entry: Mapping[str, Any],
    tm_hm: Mapping[str, str],
    move_keys: set[str],
    species_keys: set[str],
) -> dict[str, Any]:
    level_learnset = []
    for level, move_key in entry.get("level_learnset", []):
        if move_key not in move_keys:
            print(
                f"warning: data_gen/species.toml: {key}.level_learnset "
                f"references unknown move {move_key!r}; skipping entry.",
                file=sys.stderr,
            )
            continue
        level_learnset.append((level, move_key))

    evolutions = []
    for evo in entry.get("evolutions", []):
        target = evo["target"]
        if target not in species_keys:
            print(
                f"warning: data_gen/species.toml: {key}.evolutions "
                f"references unknown target species {target!r}; skipping.",
                file=sys.stderr,
            )
            continue
        evolutions.append(
            {"method": evo["method"], "target": target, "param": evo["param"]}
        )

    return {
        "id": entry["id"],
        "label": entry["label"],
        "national_dex": entry.get("national_dex"),
        "johto_dex": entry.get("johto_dex"),
        "types": tuple(entry["types"]),
        "base_stats": {
            "hp": entry["hp"],
            "atk": entry["atk"],
            "def": entry["def"],
            "spatk": entry["spatk"],
            "spdef": entry["spdef"],
            "speed": entry["speed"],
        },
        "catch_rate": entry["catch_rate"],
        "abilities": tuple(entry["abilities"]),
        "tm_moves": _resolve_tm_hm(key, "tms", entry["tms"], tm_hm, move_keys),
        "hm_moves": _resolve_tm_hm(key, "hms", entry["hms"], tm_hm, move_keys),
        "level_learnset": tuple(level_learnset),
        "evolutions": tuple(evolutions),
    }


def generate_species() -> str:
    """Build the contents of `data/species.py` from `data_gen/species.toml`."""
    species_toml = load_toml("species")
    moves_toml = load_toml("moves")
    tm_hm = moves_toml.get("tm_hm", {})
    move_keys = {k for k in moves_toml if k != "tm_hm"}
    species_keys = set(species_toml)

    species: dict[str, dict[str, Any]] = {}
    for key, entry in species_toml.items():
        species[key] = _build_species(key, entry, tm_hm, move_keys, species_keys)

    lines = [GENERATED_FILE_HEADER, "\n", "SPECIES = {\n"]
    for key, spec in species.items():
        lines.append(f"    {key!r}: {spec!r},\n")
    lines.append("}\n")
    return "".join(lines)
