from __future__ import annotations

from collections.abc import Callable

from BaseClasses import CollectionState, Entrance, MultiWorld, Region
from data.items import ITEMS
from data.regions import REGIONS
from data.rules import BADGES, EXIT_RULES

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

KANTO_LEADER_EVENTS = (
    "brock_defeated", "misty_defeated", "lt_surge_defeated", "erika_defeated",
    "janine_defeated", "sabrina_defeated", "blaine_defeated",
)
COUNT_RULES: dict[tuple[str, str], dict] = {
    ("indigo_plateau", "pokemon_league_entrance"): {
        "option": "elite_four_badges", "default": 8, "badges": tuple(BADGES),
    },
    ("viridian", "viridian_gym"): {
        "option": "blue_kanto_leaders", "default": 7, "events": KANTO_LEADER_EVENTS,
    },
    ("route_22_pokemon_league_reception_gate", "route_28"): {
        "option": "red_badges", "default": 16, "badges": tuple(BADGES), "waived_events": ("blue_defeated",),
    },
    ("route_28", "route_22_pokemon_league_reception_gate"): {
        "option": "red_badges", "default": 16, "badges": tuple(BADGES), "waived_events": ("blue_defeated",),
    },
}


def counted_requirement(
    src: str, dest: str, requirement: dict, value: int | None = None
) -> tuple[dict, dict | None]:
    count = COUNT_RULES.get((src, dest))
    if count is None:
        return requirement, None
    waived_events = set(count.get("waived_events", ()))
    if waived_events and (value is None or value >= count["default"]):
        return requirement, None
    counted_badges = set(count.get("badges", ()))
    counted_events = set(count.get("events", ())) | waived_events
    rest = {
        "items": list(requirement["items"]),
        "badges": [badge for badge in requirement["badges"] if badge not in counted_badges],
        "events": [event for event in requirement.get("events", ()) if event not in counted_events],
    }
    return rest, count


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


def _counted_access_rule(
    player: int, base: Callable[[CollectionState], bool], count: dict, needed: int
) -> Callable[[CollectionState], bool]:
    labels = tuple(badge_item_label(name) for name in count.get("badges", ())) + tuple(
        scenario_event_item_name(name) for name in count.get("events", ())
    )
    needed = min(needed, len(labels))

    def rule(state: CollectionState) -> bool:
        return base(state) and sum(state.has(label, player) for label in labels) >= needed

    return rule


def set_rules(
    player: int,
    multiworld: MultiWorld,
    regions: dict[str, Region],
    magnet_train: bool = True,
    require_flash: bool = False,
    counts: dict[str, int] | None = None,
) -> None:
    counts = counts or {}
    exit_names: dict[str, set[str]] = {}
    for (src, dest), full_requirement in EXIT_RULES.items():
        if src not in regions or dest not in regions:
            continue
        entrance_name = f"{src} -> {dest}"
        if src not in exit_names:
            exit_names[src] = {exit_.name for exit_ in regions[src].exits}
        if entrance_name not in exit_names[src]:
            continue
        entrance = multiworld.get_entrance(entrance_name, player)
        count_spec = COUNT_RULES.get((src, dest))
        count_value = counts.get(count_spec["option"], count_spec["default"]) if count_spec else None
        requirement, count = counted_requirement(src, dest, full_requirement, count_value)
        events = tuple(requirement.get("events", ()))
        if magnet_train:
            events = tuple(event for event in events if event != POWER_PLANT_EVENT)
        items = tuple(requirement["items"])
        if require_flash and is_dark_entry(src, dest) and FLASH_ITEM not in items:
            items += (FLASH_ITEM,)
        rule = _make_access_rule(player, items, tuple(requirement["badges"]), events)
        if count is not None:
            rule = _counted_access_rule(player, rule, count, counts.get(count["option"], count["default"]))
        set_rule(entrance, rule)
    if require_flash:
        for src, region in regions.items():
            if src not in REGIONS:
                continue
            for entrance in region.exits:
                dest = entrance.connected_region.name if entrance.connected_region else None
                if dest in REGIONS and (src, dest) not in EXIT_RULES and is_dark_entry(src, dest):
                    set_rule(entrance, _make_access_rule(player, (FLASH_ITEM,), (), ()))
