# data_gen_templates/encounter_zone_index.py
#
# Turns `data_gen/encounter_zone_index.toml` into
# `data/encounter_zone_index.py` (task M4.5): `data/encounters.py` zone key
# -> real raw NitroFS sub-file index in `g_enc_data.narc` (a/0/3/7). See
# `data_gen/encounter_zone_index.toml`'s own header for how this mapping
# was derived and verified.

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
