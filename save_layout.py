from __future__ import annotations

from dataclasses import dataclass

SAVE_SYSINFO = 0
SAVE_PLAYERDATA = 1
SAVE_PARTY = 2
SAVE_BAG = 3
SAVE_FLAGS = 4

NUM_VARS = 0x170
NUM_FLAGS = 2912
VARS_ARRAY_SIZE = NUM_VARS * 2
FLAGS_ARRAY_OFFSET = VARS_ARRAY_SIZE
FLAGS_ARRAY_SIZE = NUM_FLAGS // 8
SAVE_VARS_FLAGS_SIZE = VARS_ARRAY_SIZE + FLAGS_ARRAY_SIZE

HIDDEN_ITEMS_FLAG_BASE = 800


def flag_byte_and_bit(flag_id: int) -> tuple[int, int]:
    return flag_id // 8, flag_id % 8


def is_flag_set(flags_bytes: bytes, flag_id: int) -> bool:
    byte_index, bit_index = flag_byte_and_bit(flag_id)
    if byte_index < 0 or byte_index >= len(flags_bytes):
        return False
    return (flags_bytes[byte_index] & (1 << bit_index)) != 0


ITEM_SLOT_SIZE = 4

NUM_BAG_ITEMS = 165
NUM_BAG_KEY_ITEMS = 50
NUM_BAG_TMS_HMS = 101
NUM_BAG_MAIL = 12
NUM_BAG_MEDICINE = 40
NUM_BAG_BERRIES = 64
NUM_BAG_BALLS = 24
NUM_BAG_BATTLE_ITEMS = 30

BAG_POCKETS: tuple[tuple[str, int], ...] = (
    ("items", NUM_BAG_ITEMS),
    ("keyItems", NUM_BAG_KEY_ITEMS),
    ("TMsHMs", NUM_BAG_TMS_HMS),
    ("mail", NUM_BAG_MAIL),
    ("medicine", NUM_BAG_MEDICINE),
    ("berries", NUM_BAG_BERRIES),
    ("balls", NUM_BAG_BALLS),
    ("battleItems", NUM_BAG_BATTLE_ITEMS),
)
REGISTERED_ITEMS_SIZE = 2 * 2

POCKET_KEY_TO_BAG_FIELD: dict[str, str] = {
    "items": "items",
    "key_items": "keyItems",
    "tm_hm": "TMsHMs",
    "mail": "mail",
    "medicine": "medicine",
    "berries": "berries",
    "balls": "balls",
    "battle_items": "battleItems",
}

TMHM_STACK_CAP = 99
DEFAULT_STACK_CAP = 999


def _bag_pocket_offsets() -> dict[str, tuple[int, int]]:
    offsets: dict[str, tuple[int, int]] = {}
    offset = 0
    for name, count in BAG_POCKETS:
        offsets[name] = (offset, count)
        offset += count * ITEM_SLOT_SIZE
    return offsets


BAG_POCKET_OFFSETS: dict[str, tuple[int, int]] = _bag_pocket_offsets()
BAG_SIZE = sum(count for _, count in BAG_POCKETS) * ITEM_SLOT_SIZE + REGISTERED_ITEMS_SIZE


def stack_cap_for_pocket(bag_field: str) -> int:
    return TMHM_STACK_CAP if bag_field == "TMsHMs" else DEFAULT_STACK_CAP


def plan_bag_item_write(
    pocket_bytes: bytes, native_item_id: int, quantity: int, stack_cap: int, keep_free: int = 0
) -> tuple[int, bytes] | None:
    if len(pocket_bytes) % ITEM_SLOT_SIZE != 0:
        raise ValueError(f"pocket_bytes length {len(pocket_bytes)} is not a multiple of {ITEM_SLOT_SIZE}")

    first_free_offset: int | None = None
    free_slots = 0
    for offset in range(0, len(pocket_bytes), ITEM_SLOT_SIZE):
        slot_id = int.from_bytes(pocket_bytes[offset : offset + 2], "little")
        slot_qty = int.from_bytes(pocket_bytes[offset + 2 : offset + 4], "little")
        if slot_id == native_item_id:
            if quantity + slot_qty > stack_cap:
                return None
            new_qty = slot_qty + quantity
            return offset, native_item_id.to_bytes(2, "little") + new_qty.to_bytes(2, "little")
        if slot_id == 0:
            free_slots += 1
            if first_free_offset is None:
                first_free_offset = offset

    if first_free_offset is not None and free_slots > keep_free:
        return first_free_offset, native_item_id.to_bytes(2, "little") + quantity.to_bytes(2, "little")

    return None


TEXT_SPEED_MASK = 0x000F
TEXT_SPEED_FAST_VALUE = 2
BATTLE_SCENE_BIT = 0x0080


def chunk_size_with_footer(struct_size: int) -> int:
    return ((struct_size + 3) & ~3) + 4


SAVEDATA_DYNAMIC_REGION_OFFSET = 16


@dataclass(frozen=True)
class LongLongAlignmentCase:
    name: str
    sys_info_size: int


CASE_APCS_4BYTE_LONGLONG = LongLongAlignmentCase(name="apcs_4byte_longlong", sys_info_size=72)
CASE_EABI_8BYTE_LONGLONG = LongLongAlignmentCase(name="eabi_8byte_longlong", sys_info_size=80)

CANDIDATE_CASES: tuple[LongLongAlignmentCase, ...] = (CASE_APCS_4BYTE_LONGLONG, CASE_EABI_8BYTE_LONGLONG)

PLAYER_DATA_SIZE = 44

PARTY_SIZE = 1456

PLAYERDATA_MONEY_OFFSET = 24


@dataclass(frozen=True)
class SaveChunkOffsets:
    case: LongLongAlignmentCase
    sys_info_offset: int
    player_data_offset: int
    party_offset: int
    bag_offset: int
    vars_flags_offset: int

    @property
    def money_offset_in_savedata(self) -> int:
        return SAVEDATA_DYNAMIC_REGION_OFFSET + self.player_data_offset + PLAYERDATA_MONEY_OFFSET

    @property
    def bag_offset_in_savedata(self) -> int:
        return SAVEDATA_DYNAMIC_REGION_OFFSET + self.bag_offset

    @property
    def vars_flags_offset_in_savedata(self) -> int:
        return SAVEDATA_DYNAMIC_REGION_OFFSET + self.vars_flags_offset


def compute_chunk_offsets(case: LongLongAlignmentCase) -> SaveChunkOffsets:
    sys_info_offset = 0
    sys_info_chunk = chunk_size_with_footer(case.sys_info_size)

    player_data_offset = sys_info_offset + sys_info_chunk
    player_data_chunk = chunk_size_with_footer(PLAYER_DATA_SIZE)

    party_offset = player_data_offset + player_data_chunk
    party_chunk = chunk_size_with_footer(PARTY_SIZE)

    bag_offset = party_offset + party_chunk
    bag_chunk = chunk_size_with_footer(BAG_SIZE)

    vars_flags_offset = bag_offset + bag_chunk

    return SaveChunkOffsets(
        case=case,
        sys_info_offset=sys_info_offset,
        player_data_offset=player_data_offset,
        party_offset=party_offset,
        bag_offset=bag_offset,
        vars_flags_offset=vars_flags_offset,
    )


CANDIDATE_OFFSETS: dict[str, SaveChunkOffsets] = {case.name: compute_chunk_offsets(case) for case in CANDIDATE_CASES}
