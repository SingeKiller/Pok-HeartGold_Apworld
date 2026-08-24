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

# The two ends of the Magnet Train ride, as an unordered pair: data/rules.py
# carries the edge in both directions (the Pass is a permanent key item and
# both station attendants run the same `HasItem ITEM_PASS` check, see
# data_gen/rules.toml), and the `magnet_train` option has to reach both.
MAGNET_TRAIN_REGIONS = frozenset(
    {"goldenrod_magnet_train_station_2f", "saffron_magnet_train_station_2f"}
)
MAGNET_TRAIN_PASS_ITEM_LABEL = ITEMS["pass"]["label"]

# The scenario event the `magnet_train` option adds on top of the ride when
# the player asks for Kanto to stay late-game. Same event the S.S. Aqua
# ferry already requires, which is the whole point: with both crossings
# behind it, nothing in Kanto can be expected of the player before the
# League.
_ELITE_FOUR_EVENT = "elite_four_defeated"


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


def set_rules(
    player: int,
    multiworld: MultiWorld,
    regions: dict[str, Region],
    magnet_train: bool = True,
) -> None:
    """Apply every EXIT_RULES entry to its matching Entrance. Both
    endpoint regions existing doesn't guarantee the Entrance between them
    does: `create_regions` (regions.py) only connects the exits
    data/regions.py actually lists, so an EXIT_RULES pair naming an edge
    that data no longer carries (a one-way edge corrected to point the
    other way, for instance) would leave both regions in place with no
    Entrance between them. Hence the Entrance-existence check before
    calling `multiworld.get_entrance`, which raises if it doesn't exist
    (latent bug found by code review, 2026-08-17; not currently triggered,
    every EXIT_RULES pair matches a real exit today).

    `magnet_train` is the player's own option (default on). Off, the ride
    keeps its Pass requirement and gains `elite_four_defeated` on top: the
    edge is deliberately *not* removed, so the graph stays exactly the one
    every other test measures and only the requirement hardens. That is
    also the safe direction -- logic stricter than the game can never make
    a seed unbeatable, and the player is still free to take the train as
    soon as they hold the Pass."""
    for (src, dest), requirement in EXIT_RULES.items():
        if src not in regions or dest not in regions:
            continue
        entrance_name = f"{src} -> {dest}"
        if entrance_name not in {exit_.name for exit_ in regions[src].exits}:
            continue
        entrance = multiworld.get_entrance(entrance_name, player)
        events = tuple(requirement.get("events", ()))
        if not magnet_train and {src, dest} == MAGNET_TRAIN_REGIONS:
            events += (_ELITE_FOUR_EVENT,)
        rule = _make_access_rule(
            player, tuple(requirement["items"]), tuple(requirement["badges"]), events
        )
        set_rule(entrance, rule)
