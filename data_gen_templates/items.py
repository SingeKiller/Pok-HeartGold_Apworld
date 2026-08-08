# data_gen_templates/items.py
#
# Turns `data_gen/items.toml` into `data/items.py` (task C3). Follows the
# same load_toml -> dict-literal-repr pattern as `generate_init` in
# `data_gen_templates/__init__.py`. See `data_gen/items.toml`'s header for
# the source/extraction notes (decomp files used, the ITEM_EXPLORER_KIT
# gap, why badges have no entries here, and the progression/useful/filler
# classification methodology).

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any

from . import GENERATED_FILE_HEADER, load_toml

_VALID_CLASSIFICATIONS = {"progression", "useful", "filler"}


def _build_item(key: str, entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": entry["id"],
        "label": entry["label"],
        "price": entry["price"],
        "pocket": entry["pocket"],
        "classification": entry["classification"],
    }


def generate_items() -> str:
    """Build the contents of `data/items.py` from `data_gen/items.toml`."""
    items_toml = load_toml("items")

    items: dict[str, dict[str, Any]] = {}
    seen_ids: dict[int, str] = {}
    for key, entry in items_toml.items():
        item = _build_item(key, entry)

        # Defensive: `data_gen/items.toml` is hand-editable (even though it
        # was originally machine-extracted from the decomp, see its header
        # comment), so guard against a future edit introducing an invalid
        # classification or a duplicate numeric id -- same defensive spirit
        # as data_gen/moves.toml's tm_hm cross-references (see
        # docs/architecture.md Spike 3, the ITEM_EXPLORER_KIT gap).
        if item["classification"] not in _VALID_CLASSIFICATIONS:
            print(
                f"warning: data_gen/items.toml: {key}.classification is "
                f"{item['classification']!r}, expected one of "
                f"{sorted(_VALID_CLASSIFICATIONS)}; keeping as-is.",
                file=sys.stderr,
            )
        existing = seen_ids.get(item["id"])
        if existing is not None:
            print(
                f"warning: data_gen/items.toml: {key}.id={item['id']!r} "
                f"duplicates {existing}.id; both will be kept in data/items.py.",
                file=sys.stderr,
            )
        else:
            seen_ids[item["id"]] = key

        items[key] = item

    lines = [GENERATED_FILE_HEADER, "\n", "ITEMS = {\n"]
    for key, item in items.items():
        lines.append(f"    {key!r}: {item!r},\n")
    lines.append("}\n")
    return "".join(lines)
