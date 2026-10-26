from __future__ import annotations

from . import GENERATED_FILE_HEADER, load_toml


def generate_type_chart() -> str:
    type_chart_toml = load_toml("type_chart")
    entries = type_chart_toml["entry"]

    lines = [GENERATED_FILE_HEADER, "\n", "TYPE_CHART = [\n"]
    for entry in entries:
        lines.append(f"    {dict(entry)!r},\n")
    lines.append("]\n")
    return "".join(lines)
