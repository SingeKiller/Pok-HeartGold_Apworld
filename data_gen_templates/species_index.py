# data_gen_templates/species_index.py
#
# Turns `data_gen/species_index.toml` into `data/species_index.py` (task
# M4.5): `data/species.py` key -> real raw NitroFS sub-file index shared by
# `personal.narc` (a/0/0/2) and `evo.narc` (a/0/3/4). See
# `data_gen/species_index.toml`'s own header for how this mapping was
# derived and verified.

from __future__ import annotations

from . import GENERATED_FILE_HEADER, load_toml


def generate_species_index() -> str:
    raw_index: dict = load_toml("species_index")["raw_index"]

    lines = [GENERATED_FILE_HEADER, ""]
    lines.append("SPECIES_KEY_TO_RAW_INDEX: dict[str, int] = {")
    for key in sorted(raw_index, key=lambda k: raw_index[k]):
        lines.append(f"    {key!r}: {raw_index[key]!r},")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)
