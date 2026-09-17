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

MAGNET_TRAIN_PASS_ITEM_LABEL = ITEMS["pass"]["label"]

# The scenario event the `magnet_train` option is really about (dead seed
# fix, 0.9.1). The ride's own vanilla gate is the Pass AND this event: the
# station policeman only steps aside once FLAG_RESTORED_POWER is set (see
# data_gen/rules.toml's Magnet Train entry), and the Power Plant sits in
# Kanto, so off, the train can never be the way in. On, the client sets that
# flag itself as soon as a game exists (client.py's
# _apply_power_plant_prerestored), so the event is true from the start and
# is dropped from every edge that names it: the ride itself, the Route 5/6
# Underground Path gates and the Lavender radio station.
POWER_PLANT_EVENT = "power_plant_restored"


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

    `magnet_train` is the player's own option (default on). Off, every
    edge keeps its data requirement as is, the ride included: the Pass plus
    `power_plant_restored`, which is exactly the game's own condition and
    keeps the train out of logic until Kanto has been reached another way.
    On, `power_plant_restored` is removed from every edge, because the
    client pre-sets FLAG_RESTORED_POWER (see POWER_PLANT_EVENT): the ride
    then needs the Pass alone. The graph itself never changes, only the
    requirements do."""
    for (src, dest), requirement in EXIT_RULES.items():
        if src not in regions or dest not in regions:
            continue
        entrance_name = f"{src} -> {dest}"
        if entrance_name not in {exit_.name for exit_ in regions[src].exits}:
            continue
        entrance = multiworld.get_entrance(entrance_name, player)
        events = tuple(requirement.get("events", ()))
        if magnet_train:
            events = tuple(event for event in events if event != POWER_PLANT_EVENT)
        rule = _make_access_rule(
            player, tuple(requirement["items"]), tuple(requirement["badges"]), events
        )
        set_rule(entrance, rule)
