from __future__ import annotations

from rom import HeartGoldRom

ARM9_TABLE_RAM_ADDRESS = 0x020FA558

ENTRY_COUNT = 231
ENTRY_SIZE = 8
_ITEM_ID_OFFSET = 0
_QUANTITY_OFFSET = 2
_INDEX_OFFSET = 6


class HiddenItemDataError(Exception):
    pass


def _table_file_offset(rom: HeartGoldRom) -> int:
    return ARM9_TABLE_RAM_ADDRESS - rom.arm9_ram_address


def read_all(rom: HeartGoldRom) -> list[bytes]:
    decompressed = rom.read_main_code_decompressed()
    base = _table_file_offset(rom)
    return [decompressed[base + i * ENTRY_SIZE : base + (i + 1) * ENTRY_SIZE] for i in range(ENTRY_COUNT)]


def read_entry(rom: HeartGoldRom, position: int) -> bytes:
    if not (0 <= position < ENTRY_COUNT):
        raise ValueError(f"position {position} out of range (0..{ENTRY_COUNT - 1})")
    decompressed = rom.read_main_code_decompressed()
    offset = _table_file_offset(rom) + position * ENTRY_SIZE
    return decompressed[offset : offset + ENTRY_SIZE]


def write_item_id(rom: HeartGoldRom, position: int, item_id: int) -> None:
    if not (0 <= position < ENTRY_COUNT):
        raise ValueError(f"position {position} out of range (0..{ENTRY_COUNT - 1})")
    if not (0 <= item_id <= 0xFFFF):
        raise ValueError(f"item id {item_id} does not fit the table's itemId field (an unsigned 16-bit value).")
    offset = _table_file_offset(rom) + position * ENTRY_SIZE + _ITEM_ID_OFFSET
    rom.write_main_code_region(offset, item_id.to_bytes(2, "little"))


def _find_position_by_index(rom: HeartGoldRom, index: int) -> int:
    entries = read_all(rom)
    for position, entry in enumerate(entries):
        entry_index = int.from_bytes(entry[_INDEX_OFFSET : _INDEX_OFFSET + 2], "little")
        if entry_index == index:
            return position
    raise HiddenItemDataError(f"no hidden-item table entry has index {index}")


def _positions_by_index(rom: HeartGoldRom) -> dict[int, int]:
    positions: dict[int, int] = {}
    for position, entry in enumerate(read_all(rom)):
        positions.setdefault(int.from_bytes(entry[_INDEX_OFFSET : _INDEX_OFFSET + 2], "little"), position)
    return positions


def write_hidden_item_substitution(rom: HeartGoldRom, location_key: str, item_key: str) -> None:
    from data.items import ITEMS
    from data.locations import LOCATIONS

    location = LOCATIONS.get(location_key)
    if location is None:
        raise KeyError(f"unknown location key: {location_key!r}")
    if location["type"] != "hidden_item":
        raise HiddenItemDataError(
            f"location {location_key!r} is type {location['type']!r}, not 'hidden_item' -- "
            "this module only patches the hidden-item table (ground_item/npc_gift/hm_tm/badge "
            "are out of scope, see rom/eventscriptdata.py/rom/npcgiftdata.py instead)."
        )
    item = ITEMS.get(item_key)
    if item is None:
        raise KeyError(f"unknown item key: {item_key!r}")

    position = _find_position_by_index(rom, location["id"])
    write_item_id(rom, position, item["id"])


def write_hidden_item_substitutions(
    rom: HeartGoldRom, substitutions: dict[str, str | None], name_ids: dict[str, int] | None = None
) -> None:
    from data.items import ITEMS
    from data.locations import LOCATIONS

    edits: list[tuple[int, bytes]] = []
    table_base = ARM9_TABLE_RAM_ADDRESS - rom.arm9_ram_address
    positions = _positions_by_index(rom)
    for location_key, item_key in substitutions.items():
        location = LOCATIONS.get(location_key)
        if location is None:
            raise KeyError(f"unknown location key: {location_key!r}")
        if location["type"] != "hidden_item":
            raise HiddenItemDataError(
                f"location {location_key!r} is type {location['type']!r}, not 'hidden_item' -- "
                "this module only patches the hidden-item table (ground_item/npc_gift/hm_tm/badge "
                "are out of scope, see rom/eventscriptdata.py/rom/npcgiftdata.py instead)."
            )
        if item_key is None:
            item_id = 0
        else:
            item = ITEMS.get(item_key)
            if item is None:
                raise KeyError(f"unknown item key: {item_key!r}")
            item_id = item["id"]
        if not (0 <= item_id <= 0xFFFF):
            raise ValueError(f"item id {item_id} does not fit the table's itemId field (an unsigned 16-bit value).")

        position = positions.get(location["id"])
        if position is None:
            raise HiddenItemDataError(f"no hidden-item table entry has index {location['id']}")
        offset = table_base + position * ENTRY_SIZE + _ITEM_ID_OFFSET
        if item_key is None:
            name_id = (name_ids or {}).get(location_key, 0)
            edits.append((offset, name_id.to_bytes(2, "little") + bytes(1)))
        else:
            edits.append((offset, item_id.to_bytes(2, "little")))

    rom.write_main_code_regions(edits)
