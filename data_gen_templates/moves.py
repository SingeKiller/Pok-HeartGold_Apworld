# data_gen_templates/moves.py
#
# Turns `data_gen/moves.toml` into `data/moves.py` (task C2). Follows the
# same load_toml -> dict-literal-repr pattern as `generate_init` in
# `data_gen_templates/__init__.py`.

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any

from . import GENERATED_FILE_HEADER, load_toml


def _build_move(key: str, entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": entry["id"],
        "label": entry["label"],
        "type": entry["type"],
        "category": entry["category"],
        "effect": entry["effect"],
        "power": entry["power"],
        "accuracy": entry["accuracy"],
        "pp": entry["pp"],
    }


def generate_moves() -> str:
    """Build the contents of `data/moves.py` from `data_gen/moves.toml`."""
    moves_toml = load_toml("moves")
    tm_hm = moves_toml.get("tm_hm", {})

    moves: dict[str, dict[str, Any]] = {}
    for key, entry in moves_toml.items():
        if key == "tm_hm":
            continue
        moves[key] = _build_move(key, entry)

    # Defensive: `[tm_hm]` machine-number -> move-key entries should always
    # resolve to a move that's actually present above. This should never
    # trigger given `data_gen/moves.toml` is machine-extracted from the same
    # decomp source, but data_gen sources are hand-editable, so guard against
    # a future edit introducing a dangling reference (see docs/architecture.md
    # Spike 3, the ITEM_EXPLORER_KIT gap, for why this project treats decomp-
    # derived data as reliable but not 100% trustworthy).
    for machine, move_key in tm_hm.items():
        if move_key not in moves:
            print(
                f"warning: data_gen/moves.toml: [tm_hm].{machine} references "
                f"unknown move {move_key!r}; skipping.",
                file=sys.stderr,
            )

    tm_hm_clean = {k: v for k, v in tm_hm.items() if v in moves}

    lines = [GENERATED_FILE_HEADER, "\n", "MOVES = {\n"]
    for key, move in moves.items():
        lines.append(f"    {key!r}: {move!r},\n")
    lines.append("}\n")
    lines.append("\n")
    lines.append("# TM/HM machine number (e.g. 'tm06', 'hm03') -> move key.\n")
    lines.append("TM_HM_MOVES = {\n")
    for machine, move_key in tm_hm_clean.items():
        lines.append(f"    {machine!r}: {move_key!r},\n")
    lines.append("}\n")
    return "".join(lines)
