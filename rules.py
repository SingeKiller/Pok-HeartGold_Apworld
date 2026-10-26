from __future__ import annotations

from collections.abc import Callable

from BaseClasses import CollectionState, Entrance, MultiWorld, Region
from data.items import ITEMS
from data.regions import REGIONS
from data.rules import EXIT_RULES

from locations import badge_item_label, scenario_event_item_name

MAGNET_TRAIN_PASS_ITEM_LABEL = ITEMS["pass"]["label"]

POWER_PLANT_EVENT = "power_plant_restored"

DARK_MAP_CODES = frozenset({
    "D05R0101", "D05R0102",
    "D42R0101", "D42R0102",
    "D40R0101", "D40R0102",
    "D03R0101", "D03R0102", "D03R0103",
})
FLASH_ITEM = "tm70"


def is_dark_entry(src: str, dest: str) -> bool:
    return REGIONS[dest]["map_code"] in DARK_MAP_CODES and REGIONS[src]["map_code"] not in DARK_MAP_CODES


def set_rule(spot: Entrance, rule: Callable[[CollectionState], bool]) -> None:
    spot.access_rule = rule


def _make_access_rule(
    player: int,
    item_keys: tuple[str, ...],
    badge_names: tuple[str, ...],
    event_names: tuple[str, ...],
) -> Callable[[CollectionState], bool]:
    item_labels = tuple(ITEMS[key]["label"] for key in item_keys)
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
    require_flash: bool = False,
) -> None:
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
        items = tuple(requirement["items"])
        if require_flash and is_dark_entry(src, dest) and FLASH_ITEM not in items:
            items += (FLASH_ITEM,)
        rule = _make_access_rule(player, items, tuple(requirement["badges"]), events)
        set_rule(entrance, rule)
    if require_flash:
        for src, region in regions.items():
            if src not in REGIONS:
                continue
            for entrance in region.exits:
                dest = entrance.connected_region.name if entrance.connected_region else None
                if dest in REGIONS and (src, dest) not in EXIT_RULES and is_dark_entry(src, dest):
                    set_rule(entrance, _make_access_rule(player, (FLASH_ITEM,), (), ()))
