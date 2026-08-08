#!/usr/bin/env python3
"""data_gen_rules.py

Root-level (not `data_gen_templates/`) helpers for composing/validating HGSS
region-exit access rules (task C6, see `data_gen/rules.toml`). Kept
separate from `data_gen_templates/rules.py` for the same reason
`ressources/platinum_archipelago` keeps its own `data_gen_rules.py` at the
package root (read-only reference, not copied): rule-composition/validation
logic is reusable beyond the one-shot `data_gen.py` -> `data/` generation
pass -- `tests/test_rules.py` needs the exact same normalization/validation
to check the generated graph without reimplementing it, and a future
`rules.py` (world logic, once this project reaches that stage) will need
the same `Requirement` shape again. `data_gen_templates/*.py` modules, by
contrast, are purely "toml -> data/*.py string" renderers with no reuse
value outside `data_gen.py` itself, so they stay separate from this file.

This module is deliberately generic: it takes `hm_badges`/`hm_items` as
plain dict arguments rather than hardcoding HGSS-specific move/badge names,
so all the actual game data stays in `data_gen/rules.toml` (this project's
convention throughout `data_gen/` -- see e.g. `data_gen/moves.toml`'s
`[tm_hm]` table), not duplicated into Python.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Requirement:
    """A single (AND-combined) access requirement: own every item in
    `items` (a `data_gen/items.toml` key each) and hold every badge in
    `badges` (a `data_gen/rules.toml` `[badges]` key each)."""

    items: tuple[str, ...] = ()
    badges: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not self.items and not self.badges


def hm_requirement(hm: str, hm_badges: Mapping[str, str], hm_items: Mapping[str, str]) -> Requirement:
    """Build the Requirement for field-using a given HM: the HM's own bag
    item (`hm_items`, to know/teach the move at all) plus the badge vanilla
    requires to use it in the field (`hm_badges`, if any -- absent for e.g.
    Flash, which has no badge requirement, see `data_gen/rules.toml`'s
    header). Raises KeyError for an `hm` missing from `hm_items` (a rules
    author typo -- caught eagerly here rather than silently producing an
    incomplete rule; `data_gen_templates/rules.py` is the defensive,
    warn-not-crash layer for *data* problems, this is a programmer-error
    guard for the composition helpers themselves).
    """
    items = (hm_items[hm],)
    badge = hm_badges.get(hm)
    badges = (badge,) if badge is not None else ()
    return Requirement(items=items, badges=badges)


def combine(*requirements: Requirement) -> Requirement:
    """AND-combine several Requirements into one (deduplicated,
    order-preserving)."""
    items: list[str] = []
    badges: list[str] = []
    for requirement in requirements:
        for item in requirement.items:
            if item not in items:
                items.append(item)
        for badge in requirement.badges:
            if badge not in badges:
                badges.append(badge)
    return Requirement(items=tuple(items), badges=tuple(badges))


def build_exit_rule_requirement(
    entry: Mapping[str, object],
    hm_badges: Mapping[str, str],
    hm_items: Mapping[str, str],
) -> Requirement:
    """Build the combined (AND) Requirement for one `data_gen/rules.toml`
    `[[exit_rule]]` entry: each of its `hms` field-moves (see
    `hm_requirement`) AND its own bare `items`/`badges` lists."""
    parts = [hm_requirement(hm, hm_badges, hm_items) for hm in entry.get("hms", [])]
    extra_items = tuple(entry.get("items", []))
    extra_badges = tuple(entry.get("badges", []))
    if extra_items or extra_badges:
        parts.append(Requirement(items=extra_items, badges=extra_badges))
    return combine(*parts)


def expand_directed_pairs(entry: Mapping[str, object]) -> list[tuple[str, str]]:
    """Expand one `[[exit_rule]]` entry's `from`/`to`/`bidirectional` into
    the directed (from, to) region-key pair(s) it applies to. `bidirectional`
    defaults to True (matches `data_gen/rules.toml`'s documented default)."""
    src = entry["from"]
    dst = entry["to"]
    if entry.get("bidirectional", True):
        return [(src, dst), (dst, src)]
    return [(src, dst)]


def build_exit_rules(
    exit_rules_toml: Sequence[Mapping[str, object]],
    hm_badges: Mapping[str, str],
    hm_items: Mapping[str, str],
) -> dict[tuple[str, str], Requirement]:
    """Build the full `{(from, to): Requirement}` mapping for every
    `[[exit_rule]]` entry in `data_gen/rules.toml`. Later entries for the
    same directed pair overwrite earlier ones (no duplicate directed pairs
    are expected in `data_gen/rules.toml`; `data_gen_templates/rules.py` is
    responsible for warning if that ever happens)."""
    rules: dict[tuple[str, str], Requirement] = {}
    for entry in exit_rules_toml:
        requirement = build_exit_rule_requirement(entry, hm_badges, hm_items)
        for pair in expand_directed_pairs(entry):
            rules[pair] = requirement
    return rules


def is_satisfied(
    requirement: Requirement,
    owned_items: Sequence[str] | set[str],
    owned_badges: Sequence[str] | set[str],
) -> bool:
    """True if `owned_items`/`owned_badges` together satisfy every item and
    badge `requirement` demands (AND semantics). Used both by
    `tests/test_rules.py` (graph connectivity with a full inventory) and
    intended for reuse by a future world-logic `rules.py` traversal check."""
    owned_items_set = owned_items if isinstance(owned_items, set) else set(owned_items)
    owned_badges_set = owned_badges if isinstance(owned_badges, set) else set(owned_badges)
    return all(item in owned_items_set for item in requirement.items) and all(
        badge in owned_badges_set for badge in requirement.badges
    )


def validate_requirement(
    requirement: Requirement,
    known_items: Sequence[str] | None = None,
    known_badges: Sequence[str] | None = None,
) -> list[str]:
    """Return human-readable warning strings for any item/badge referenced
    by `requirement` that isn't in `known_items`/`known_badges`. Never
    raises -- defensive, same spirit as this repo's other
    `data_gen_templates/*.py` dangling-reference warnings (see e.g.
    `data_gen_templates/regions.py`)."""
    warnings: list[str] = []
    if known_items is not None:
        known_items_set = set(known_items)
        for item in requirement.items:
            if item not in known_items_set:
                warnings.append(f"unknown item {item!r}")
    if known_badges is not None:
        known_badges_set = set(known_badges)
        for badge in requirement.badges:
            if badge not in known_badges_set:
                warnings.append(f"unknown badge {badge!r}")
    return warnings
