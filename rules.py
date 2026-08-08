# rules.py
#
# Applies the 67 directed HM/badge/item gating rules from the generated
# `data/rules.py` (`EXIT_RULES`) onto the `Entrance` objects built by
# `regions.create_regions`, using the badge event items placed by
# `locations.create_locations`. Follows the same overall shape as
# `ressources/platinum_archipelago/rules.py` (read-only reference, not
# copied), simplified: this project has no HM-compatibility/species logic
# yet (out of this task's scope).
#
# `set_rule` below is a deliberately local, one-line re-implementation of
# `worlds.generic.Rules.set_rule` (`spot.access_rule = rule`), not an import
# of it: importing the `worlds` package triggers Archipelago's full
# world-plugin autoloading (see `worlds/__init__.py` in the local
# Archipelago clone), which is far too heavy a dependency for this
# standalone module to pull in before this project has its own registered
# `__init__.py`/World class.
#
# No randomization logic lives here (see task brief) -- just wiring the
# already-generated rules onto the already-built graph.

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
    """Apply every `data/rules.py` `EXIT_RULES` entry to its matching
    `Entrance` (named `f"{src} -> {dest}"` by `regions.create_regions`).
    Both `src` and `dest` are guaranteed to exist in `regions` for every
    `EXIT_RULES` entry (see `tests/test_rules.py::
    test_exit_rule_regions_are_real_exits` at the `data/` generation layer)
    -- `regions` is still checked defensively here so a future, smaller
    region subset (e.g. an options-gated variant) degrades gracefully
    instead of raising.
    """
    for (src, dest), requirement in EXIT_RULES.items():
        if src not in regions or dest not in regions:
            continue
        entrance = multiworld.get_entrance(f"{src} -> {dest}", player)
        rule = _make_access_rule(player, tuple(requirement["items"]), tuple(requirement["badges"]))
        set_rule(entrance, rule)
