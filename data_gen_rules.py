#!/usr/bin/env python3

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Requirement:
    items: tuple[str, ...] = ()
    badges: tuple[str, ...] = ()
    events: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not self.items and not self.badges and not self.events


def hm_requirement(hm: str, hm_badges: Mapping[str, str], hm_items: Mapping[str, str]) -> Requirement:
    items = (hm_items[hm],)
    badge = hm_badges.get(hm)
    badges = (badge,) if badge is not None else ()
    return Requirement(items=items, badges=badges)


def combine(*requirements: Requirement) -> Requirement:
    items: list[str] = []
    badges: list[str] = []
    events: list[str] = []
    for requirement in requirements:
        for item in requirement.items:
            if item not in items:
                items.append(item)
        for badge in requirement.badges:
            if badge not in badges:
                badges.append(badge)
        for event in requirement.events:
            if event not in events:
                events.append(event)
    return Requirement(items=tuple(items), badges=tuple(badges), events=tuple(events))


def build_exit_rule_requirement(
    entry: Mapping[str, object],
    hm_badges: Mapping[str, str],
    hm_items: Mapping[str, str],
) -> Requirement:
    parts = [hm_requirement(hm, hm_badges, hm_items) for hm in entry.get("hms", [])]
    extra_items = tuple(entry.get("items", []))
    extra_badges = tuple(entry.get("badges", []))
    extra_events = tuple(entry.get("events", []))
    if extra_items or extra_badges or extra_events:
        parts.append(Requirement(items=extra_items, badges=extra_badges, events=extra_events))
    return combine(*parts)


def expand_directed_pairs(entry: Mapping[str, object]) -> list[tuple[str, str]]:
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
    owned_events: Sequence[str] | set[str] = (),
) -> bool:
    owned_items_set = owned_items if isinstance(owned_items, set) else set(owned_items)
    owned_badges_set = owned_badges if isinstance(owned_badges, set) else set(owned_badges)
    owned_events_set = owned_events if isinstance(owned_events, set) else set(owned_events)
    return (
        all(item in owned_items_set for item in requirement.items)
        and all(badge in owned_badges_set for badge in requirement.badges)
        and all(event in owned_events_set for event in requirement.events)
    )


def validate_requirement(
    requirement: Requirement,
    known_items: Sequence[str] | None = None,
    known_badges: Sequence[str] | None = None,
    known_events: Sequence[str] | None = None,
) -> list[str]:
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
    if known_events is not None:
        known_events_set = set(known_events)
        for event in requirement.events:
            if event not in known_events_set:
                warnings.append(f"unknown event {event!r}")
    return warnings
