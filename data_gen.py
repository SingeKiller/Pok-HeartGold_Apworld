#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path

from data_gen_templates import (
    generate_charmap,
    generate_encounter_zone_index,
    generate_encounters,
    generate_init,
    generate_items,
    generate_locations,
    generate_moves,
    generate_regions,
    generate_rules,
    generate_species,
    generate_species_index,
    generate_trainers,
    generate_type_chart,
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"


def _write(name: str, contents: str) -> None:
    (DATA_DIR / name).write_text(contents, encoding="utf-8", newline="\n")


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    _write("__init__.py", generate_init())
    _write("species.py", generate_species())
    _write("species_index.py", generate_species_index())
    _write("moves.py", generate_moves())
    _write("items.py", generate_items())
    _write("regions.py", generate_regions())
    _write("locations.py", generate_locations())
    _write("rules.py", generate_rules())
    _write("trainers.py", generate_trainers())
    _write("encounters.py", generate_encounters())
    _write("encounter_zone_index.py", generate_encounter_zone_index())
    _write("charmap.py", generate_charmap())
    _write("type_chart.py", generate_type_chart())


if __name__ == "__main__":
    main()
