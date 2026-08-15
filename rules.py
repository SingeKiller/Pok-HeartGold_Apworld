# rules.py
#
# Applies data/rules.py's EXIT_RULES onto the Entrance objects built by
# regions.create_regions. set_rule is a local re-implementation of
# worlds.generic.Rules.set_rule to avoid importing the worlds package here.

from __future__ import annotations

from collections.abc import Callable

from BaseClasses import CollectionState, Entrance, MultiWorld, Region
from data.items import ITEMS
from data.rules import EXIT_RULES

from locations import badge_item_label, scenario_event_item_name


def set_rule(spot: Entrance, rule: Callable[[CollectionState], bool]) -> None:
    spot.access_rule = rule


def _make_access_rule(
    player: int,
    item_keys: tuple[str, ...],
    badge_names: tuple[str, ...],
    event_names: tuple[str, ...],
) -> Callable[[CollectionState], bool]:
    item_labels = tuple(ITEMS[key]["label"] for key in item_keys)
    # Badges are real, tradeable items as of task "Badges comme vrais items
    # AP" (2026-08-15) -- state.has checks the same badge_<name> item label
    # a player could receive from anywhere in the multiworld, not a locked
    # event tied to this player's own gym location.
    badge_labels = tuple(badge_item_label(name) for name in badge_names)
    scenario_events = tuple(scenario_event_item_name(name) for name in event_names)

    def rule(state: CollectionState) -> bool:
        return (
            all(state.has(label, player) for label in item_labels)
            and all(state.has(label, player) for label in badge_labels)
            and all(state.has(event, player) for event in scenario_events)
        )

    return rule


def set_rules(player: int, multiworld: MultiWorld, regions: dict[str, Region]) -> None:
    """Apply every EXIT_RULES entry to its matching Entrance."""
    for (src, dest), requirement in EXIT_RULES.items():
        if src not in regions or dest not in regions:
            continue
        entrance = multiworld.get_entrance(f"{src} -> {dest}", player)
        rule = _make_access_rule(
            player, tuple(requirement["items"]), tuple(requirement["badges"]), tuple(requirement.get("events", ()))
        )
        set_rule(entrance, rule)
