# data_gen_templates/charmap.py
#
# Turns `data_gen/charmap.toml` into `data/charmap.py` (task "Replace the
# ??? placeholder", 2026-08-15). Follows the same load_toml -> dict-literal
# pattern as every other data_gen_templates module. See
# `data_gen/charmap.toml`'s header for the source/extraction notes.

from __future__ import annotations

from . import GENERATED_FILE_HEADER, load_toml


def generate_charmap() -> str:
    """Build the contents of `data/charmap.py` from `data_gen/charmap.toml`."""
    charmap_toml = load_toml("charmap")
    charmap: dict[str, int] = charmap_toml["charmap"]

    lines = [GENERATED_FILE_HEADER, "\n", "CHARMAP: dict[str, int] = {\n"]
    for char, code in charmap.items():
        lines.append(f"    {char!r}: {code!r},\n")
    lines.append("}\n")
    return "".join(lines)
