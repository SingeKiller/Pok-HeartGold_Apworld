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

from locations import badge_event_item_name


def set_rule(spot: Entrance, rule: Callable[[CollectionState], bool]) -> None:
    spot.access_rule = rule


def _make_access_rule(
    player: int, item_keys: tuple[str, ...], badge_names: tuple[str, ...]
) -> Callable[[CollectionState], bool]:
    item_labels = tuple(ITEMS[key]["label"] for key in item_keys)
    badge_events = tuple(badge_event_item_name(name) for name in badge_names)

    def rule(state: CollectionState) -> bool:
        return all(state.has(label, player) for label in item_labels) and all(
            state.has(event, player) for event in badge_events
        )

    return rule


def set_rules(player: int, multiworld: MultiWorld, regions: dict[str, Region]) -> None:
    """Apply every EXIT_RULES entry to its matching Entrance."""
    for (src, dest), requirement in EXIT_RULES.items():
        if src not in regions or dest not in regions:
            continue
        entrance = multiworld.get_entrance(f"{src} -> {dest}", player)
        rule = _make_access_rule(player, tuple(requirement["items"]), tuple(requirement["badges"]))
        set_rule(entrance, rule)
