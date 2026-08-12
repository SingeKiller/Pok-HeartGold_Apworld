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
    game: str = "Pokemon HeartGold"


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
