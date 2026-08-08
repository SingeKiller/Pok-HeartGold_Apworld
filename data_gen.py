#!/usr/bin/env python3
"""data_gen.py

Entry point: regenerates the `data/` package from `data_gen/` (source
config, toml/json) and `data_gen_templates/` (the Python that renders it
into `data/`). See docs/architecture.md, "## Layout".

`data/` is generated at dev time and is git-ignored; it must never be
committed. Running this script is idempotent: running it twice in a row
produces a byte-identical `data/` package both times.

Usage:
    python data_gen.py
"""

from __future__ import annotations

from pathlib import Path

from data_gen_templates import (
    generate_encounters,
    generate_init,
    generate_items,
    generate_locations,
    generate_moves,
    generate_regions,
    generate_rules,
    generate_species,
    generate_trainers,
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"


def _write(name: str, contents: str) -> None:
    (DATA_DIR / name).write_text(contents, encoding="utf-8", newline="\n")


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    _write("__init__.py", generate_init())
    _write("species.py", generate_species())
    _write("moves.py", generate_moves())
    _write("items.py", generate_items())
    _write("regions.py", generate_regions())
    _write("locations.py", generate_locations())
    _write("rules.py", generate_rules())
    _write("trainers.py", generate_trainers())
    _write("encounters.py", generate_encounters())


if __name__ == "__main__":
    main()
