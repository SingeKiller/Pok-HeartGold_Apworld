# data_gen_templates/rules.py
#
# Turns `data_gen/rules.toml` into `data/rules.py` (task C6). Follows the
# same load_toml -> dict-literal-repr pattern as `generate_regions` in
# `data_gen_templates/regions.py`. Unlike the other `data_gen_templates/*.py`
# modules, the actual rule-composition logic (expanding `[[exit_rule]]`
# entries into directed region-pair Requirements) lives in the root-level
# `data_gen_rules.py`, not here -- see that module's docstring for why.
# See `data_gen/rules.toml`'s header for the source/extraction methodology
# (decomp field_move.c badge table, zone_event object-sprite obstacle
# evidence, and the documented, not-hidden limitations).

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any

from data_gen_rules import Requirement, build_exit_rules, validate_requirement

from . import GENERATED_FILE_HEADER, load_toml


def _requirement_to_dict(requirement: Requirement) -> dict[str, Any]:
    return {
        "items": list(requirement.items),
        "badges": list(requirement.badges),
        "events": list(requirement.events),
    }


def generate_rules() -> str:
    """Build the contents of `data/rules.py` from `data_gen/rules.toml`."""
    rules_toml = load_toml("rules")
    regions_toml = load_toml("regions")
    items_toml = load_toml("items")
    locations_toml = load_toml("locations")

    hm_badges: Mapping[str, str] = rules_toml.get("hm_badges", {})
    hm_items: Mapping[str, str] = rules_toml.get("hm_items", {})
    badges: Mapping[str, int] = rules_toml.get("badges", {})
    exit_rule_entries = rules_toml.get("exit_rule", [])

    exit_rules = build_exit_rules(exit_rule_entries, hm_badges, hm_items)

    # `events` are granted by `type = "event"` data_gen/locations.toml
    # locations (their own `event` field names the flag), not by a fixed
    # table in this file the way badges are -- see this file's own header
    # and locations.py's event_item_name.
    known_events = {
        entry["event"] for entry in locations_toml.values() if entry.get("type") == "event" and "event" in entry
    }

    # Defensive: `data_gen/rules.toml` is hand-authored (not machine-extracted
    # like most other data_gen/ sources -- see its header), so guard against
    # a typo introducing a dangling region/item/badge/event reference. Same
    # defensive spirit as data_gen_templates/regions.py and
    # data_gen_templates/locations.py: warn, never crash or silently drop.
    known_items = set(items_toml)
    known_badges = set(badges)
    for (src, dst), requirement in exit_rules.items():
        for region_key in (src, dst):
            if region_key not in regions_toml:
                print(
                    f"warning: data_gen/rules.toml: exit_rule {src!r} -> {dst!r} "
                    f"references unknown region {region_key!r}; keeping as-is.",
                    file=sys.stderr,
                )
        for message in validate_requirement(requirement, known_items, known_badges, known_events):
            print(
                f"warning: data_gen/rules.toml: exit_rule {src!r} -> {dst!r}: {message}; "
                "keeping as-is.",
                file=sys.stderr,
            )

    lines = [GENERATED_FILE_HEADER, "\n", "EXIT_RULES = {\n"]
    for (src, dst), requirement in exit_rules.items():
        lines.append(f"    ({src!r}, {dst!r}): {_requirement_to_dict(requirement)!r},\n")
    lines.append("}\n")
    lines.append("\n")
    lines.append(f"HM_BADGES = {dict(hm_badges)!r}\n")
    lines.append(f"HM_ITEMS = {dict(hm_items)!r}\n")
    lines.append(f"BADGES = {dict(badges)!r}\n")
    return "".join(lines)
