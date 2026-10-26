from __future__ import annotations

from . import GENERATED_FILE_HEADER, load_toml


def generate_charmap() -> str:
    charmap_toml = load_toml("charmap")
    charmap: dict[str, int] = charmap_toml["charmap"]

    lines = [GENERATED_FILE_HEADER, "\n", "CHARMAP: dict[str, int] = {\n"]
    for char, code in charmap.items():
        lines.append(f"    {char!r}: {code!r},\n")
    lines.append("}\n")
    return "".join(lines)
