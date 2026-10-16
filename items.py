# items.py
#
# Archipelago item id map and Item factory, built from the generated
# data/items.py. HGSS's 16 gym badges are save-data flags, not bag items,
# so they never appear here -- they're locked AP event items placed on
# their badge Location instead (see locations.py).

from __future__ import annotations

from BaseClasses import Item, ItemClassification
from data.items import ITEMS

HEARTGOLD_ITEM_ID_BASE = 200_000_000

_CLASSIFICATIONS: dict[str, ItemClassification] = {
    "progression": ItemClassification.progression,
    "useful": ItemClassification.useful,
    "filler": ItemClassification.filler,
}


class HeartGoldItem(Item):
    game: str = "Pokemon HGSS Singe"


def create_item_label_to_code_map() -> dict[str, int]:
    """`data/items.py` `label` (e.g. "MASTER_BALL") -> id, unique within
    this world. `data/items.py`'s own `id` field is already unique across
    all 513 real items (unlike `data/locations.py`'s, see `locations.py`),
    so it is reused directly, only offset by `HEARTGOLD_ITEM_ID_BASE`."""
    return {data["label"]: HEARTGOLD_ITEM_ID_BASE + data["id"] for data in ITEMS.values()}


def get_item_classification(key: str) -> ItemClassification:
    """`key` is a `data/items.py` key, e.g. "master_ball"."""
    return _CLASSIFICATIONS[ITEMS[key]["classification"]]


def create_item(key: str, player: int) -> HeartGoldItem:
    """Build one `HeartGoldItem` for the item pool, keyed by its
    `data/items.py` key (e.g. "master_ball")."""
    data = ITEMS[key]
    return HeartGoldItem(data["label"], get_item_classification(key), HEARTGOLD_ITEM_ID_BASE + data["id"], player)


# Field moves by name, so `!hint Surf` or `!hint Flash` works as well as the
# item's own name (TM70 is Flash in every seed, see species.py).
_FIELD_MOVE_ITEMS = {
    "Cut": "hm01", "Fly": "hm02", "Surf": "hm03", "Strength": "hm04", "Whirlpool": "hm05",
    "Rock Smash": "hm06", "Waterfall": "hm07", "Rock Climb": "hm08", "Flash": "tm70",
}
_JOHTO_BADGES = ("zephyr", "hive", "plain", "fog", "storm", "mineral", "glacier", "rising")
_KANTO_BADGES = ("boulder", "cascade", "thunder", "rainbow", "soul", "marsh", "volcano", "earth")


def create_item_name_groups() -> dict[str, set[str]]:
    """Item groups for hints: every HM, every field move by its own name,
    and the badges by region."""
    label = lambda key: ITEMS[key]["label"]  # noqa: E731
    groups = {name: {label(key)} for name, key in _FIELD_MOVE_ITEMS.items()}
    groups["HMs"] = {label(f"hm0{i}") for i in range(1, 9)}
    groups["Field Moves"] = {label(key) for key in _FIELD_MOVE_ITEMS.values()}
    groups["Johto Badges"] = {label(f"badge_{b}") for b in _JOHTO_BADGES}
    groups["Kanto Badges"] = {label(f"badge_{b}") for b in _KANTO_BADGES}
    groups["Badges"] = groups["Johto Badges"] | groups["Kanto Badges"]
    groups["Wings"] = {label("rainbow_wing"), label("silver_wing")}
    return groups
