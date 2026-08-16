# data_gen_templates/type_chart.py
#
# Turns `data_gen/type_chart.toml` into `data/type_chart.py`. Follows the
# same load_toml -> list-of-dict-literal-repr pattern as this package's
# other generate_* functions, except the source is a TOML array-of-tables
# ([[entry]]) instead of a top-level table, since row ORDER must survive
# unchanged into `data/type_chart.py` (see data_gen/type_chart.toml's own
# header for why).

from __future__ import annotations

from . import GENERATED_FILE_HEADER, load_toml


def generate_type_chart() -> str:
    """Build the contents of `data/type_chart.py` from
    `data_gen/type_chart.toml`."""
    type_chart_toml = load_toml("type_chart")
    entries = type_chart_toml["entry"]

    lines = [GENERATED_FILE_HEADER, "\n", "TYPE_CHART = [\n"]
    for entry in entries:
        lines.append(f"    {dict(entry)!r},\n")
    lines.append("]\n")
    return "".join(lines)
