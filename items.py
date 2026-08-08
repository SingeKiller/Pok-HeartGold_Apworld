# items.py
#
# Archipelago item definitions for the HeartGold & SoulSilver world: an id
# map and an `Item` factory built from the generated `data/items.py` (513
# real bag items -- see docs/architecture.md Spike 3). Follows the same
# shape as `ressources/platinum_archipelago/items.py` (read-only reference,
# not copied): a plain `label -> code` map function plus a classification
# lookup, imported from the generated `data` package rather than `data_gen`.
#
# HGSS's 16 gym badges are save-data flags, not bag items (see
# `data/items.py`'s own generation notes and `tests/test_items.py::
# test_no_badge_items`) -- they intentionally do NOT appear in this id map
# or in `create_item`'s pool. They are instead represented as locked AP
# "event" items placed directly on their badge Location by
# `locations.create_locations` (see `locations.py`), the same way any other
# non-item in-game milestone (e.g. defeating a boss) is normally modeled in
# Archipelago. `rules.py` reads their event-item names via
# `locations.badge_event_item_name`.
#
# No randomization logic lives here (see task brief) -- just the id map and
# a factory to build `Item` objects for the pool; which real items actually
# go into the pool, and where, is a separate, later concern.

from __future__ import annotations

from BaseClasses import Item, ItemClassification
from data.items import ITEMS

# Convention documented in docs/architecture.md, Spike 4: current
# Archipelago no longer strictly requires a globally-reserved, non-
# overlapping id range (ids only need to be unique within this world's own
# namespace), but this project still follows the defensive convention used
# by most currently-maintained worlds. Chosen to not collide with any
# `base_id`/offset found in the local Archipelago clone's `worlds/`
# directory at the time of Spike 4.
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
