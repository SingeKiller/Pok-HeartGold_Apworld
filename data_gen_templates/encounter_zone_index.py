from __future__ import annotations

from . import GENERATED_FILE_HEADER, load_toml


def generate_encounter_zone_index() -> str:
    raw_index: dict = load_toml("encounter_zone_index")["raw_index"]

    lines = [GENERATED_FILE_HEADER, ""]
    lines.append("ENCOUNTER_ZONE_KEY_TO_RAW_INDEX: dict[str, int] = {")
    for key in sorted(raw_index, key=lambda k: raw_index[k]):
        lines.append(f"    {key!r}: {raw_index[key]!r},")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)
