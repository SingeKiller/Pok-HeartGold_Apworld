# save_layout.py
#
# Static (source-derived) model of HGSS's runtime SaveData struct layout:
# where SaveVarsFlags (check-detection flags) and Bag (item injection)
# live inside the save data a running game keeps in RAM. Consumed by
# client.py. Pure Python, no BizHawk/Archipelago imports -- every
# constant is derived directly from the decomp's C headers, following the
# game's own chunk-framing algorithm (SaveData_InitSubstructs/
# GetSaveChunkSizePlusCRC, src/save.c).
#
# One genuinely open question the source alone can't resolve: how the
# retail MWCC 2.0/sp2p2 ARM9 compiler aligns 8-byte (s64/u64) struct
# members. Only affects SysInfo (chunk id 0), modeled as two named
# candidate cases (CANDIDATE_CASES/CANDIDATE_OFFSETS) rather than guessed
# away -- the case is a required, explicitly user-confirmed setting, never
# silently defaulted.

from __future__ import annotations

from dataclasses import dataclass

# -- Save chunk ids (Decomposition include/constants/save_arrays.h) ----------
# `SaveArray_Get(saveData, id)` returns
# `&saveData->dynamic_region[saveData->arrayHeaders[id].offset]` (src/save.c)
# -- i.e. every named save substructure is a numbered "chunk" whose byte
# offset inside `dynamic_region` is computed once, deterministically, by
# `SaveData_InitSubstructs` (see `compute_chunk_offsets` below), not a fixed
# struct field.
SAVE_SYSINFO = 0
SAVE_PLAYERDATA = 1
SAVE_PARTY = 2
SAVE_BAG = 3
SAVE_FLAGS = 4

# -- SaveVarsFlags (Decomposition include/save_vars_flags.h) -----------------
# typedef struct SaveVarsFlags { u16 vars[NUM_VARS]; u8 flags[NUM_FLAGS/8]; }
# NUM_VARS/NUM_FLAGS from include/constants/vars.h / include/constants/flags.h
# (already used by docs/architecture.md's "## C14" section).
NUM_VARS = 0x170  # 368
NUM_FLAGS = 2912
VARS_ARRAY_SIZE = NUM_VARS * 2  # 736 bytes
FLAGS_ARRAY_OFFSET = VARS_ARRAY_SIZE  # flags[] immediately follows vars[]
FLAGS_ARRAY_SIZE = NUM_FLAGS // 8  # 364 bytes
SAVE_VARS_FLAGS_SIZE = VARS_ARRAY_SIZE + FLAGS_ARRAY_SIZE  # 1100 (0x44C)

# Hidden-item locations store the small HIDDENITEM_* index as their id,
# not a flag id directly -- the real savedata flag is
# HIDDEN_ITEMS_FLAG_BASE + id. See location_flags.py.
HIDDEN_ITEMS_FLAG_BASE = 800


def flag_byte_and_bit(flag_id: int) -> tuple[int, int]:
    """(byte index into SaveVarsFlags.flags[], bit index within that byte)
    -- mirrors Save_VarsFlags_CheckFlagInArray's own formula."""
    return flag_id // 8, flag_id % 8


def is_flag_set(flags_bytes: bytes, flag_id: int) -> bool:
    """flags_bytes is exactly SaveVarsFlags.flags[]. Returns False (not
    raise) for an out-of-range flag_id, matching the game's own
    defensive bounds behavior."""
    byte_index, bit_index = flag_byte_and_bit(flag_id)
    if byte_index < 0 or byte_index >= len(flags_bytes):
        return False
    return (flags_bytes[byte_index] & (1 << bit_index)) != 0


# -- Bag (Decomposition include/bag_types_def.h) -----------------------------
# struct ItemSlot { u16 id; u16 quantity; } -- 4 bytes, no padding ambiguity.
ITEM_SLOT_SIZE = 4

NUM_BAG_ITEMS = 165
NUM_BAG_KEY_ITEMS = 50
NUM_BAG_TMS_HMS = 101
NUM_BAG_MAIL = 12
NUM_BAG_MEDICINE = 40
NUM_BAG_BERRIES = 64
NUM_BAG_BALLS = 24
NUM_BAG_BATTLE_ITEMS = 30

# Field name and pocket size, in the exact order struct Bag declares them
# -- order matters, it determines each pocket's byte offset within Bag.
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
REGISTERED_ITEMS_SIZE = 2 * 2  # u16 registeredItems[2], trailing field of Bag

# data/items.py "pocket" string -> the matching Bag field name above.
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

# Vanilla per-slot stack cap. Key items, TMs/HMs and Mail are never
# stackable (always exactly 1 per slot); every other pocket caps at 99 --
# the well-established Gen IV convention, not itself decompiled here.
_UNSTACKABLE_BAG_FIELDS = {"keyItems", "TMsHMs", "mail"}
DEFAULT_STACK_CAP = 99
UNSTACKABLE_STACK_CAP = 1


def _bag_pocket_offsets() -> dict[str, tuple[int, int]]:
    """Bag field name -> (byte offset from the start of `Bag`, capacity in
    `ItemSlot`s)."""
    offsets: dict[str, tuple[int, int]] = {}
    offset = 0
    for name, count in BAG_POCKETS:
        offsets[name] = (offset, count)
        offset += count * ITEM_SLOT_SIZE
    return offsets


BAG_POCKET_OFFSETS: dict[str, tuple[int, int]] = _bag_pocket_offsets()
BAG_SIZE = sum(count for _, count in BAG_POCKETS) * ITEM_SLOT_SIZE + REGISTERED_ITEMS_SIZE  # 1948 (0x79C)


def stack_cap_for_pocket(bag_field: str) -> int:
    return UNSTACKABLE_STACK_CAP if bag_field in _UNSTACKABLE_BAG_FIELDS else DEFAULT_STACK_CAP


def plan_bag_item_write(
    pocket_bytes: bytes, native_item_id: int, quantity: int, stack_cap: int
) -> tuple[int, bytes] | None:
    """Decide what to write into one Bag pocket's raw bytes to add
    `quantity` of `native_item_id`. Prefers stacking onto an existing slot
    with room; otherwise the first free slot. Returns None if the pocket
    is genuinely full. Deliberately simple: doesn't replicate
    Bag_AddItem's TM/HM/Berry pocket re-sort -- the item still lands in a
    valid, correctly-typed slot, just not necessarily where vanilla
    sorting would put it."""
    if len(pocket_bytes) % ITEM_SLOT_SIZE != 0:
        raise ValueError(f"pocket_bytes length {len(pocket_bytes)} is not a multiple of {ITEM_SLOT_SIZE}")

    first_free_offset: int | None = None
    for offset in range(0, len(pocket_bytes), ITEM_SLOT_SIZE):
        slot_id = int.from_bytes(pocket_bytes[offset : offset + 2], "little")
        slot_qty = int.from_bytes(pocket_bytes[offset + 2 : offset + 4], "little")
        if slot_id == native_item_id and slot_qty < stack_cap:
            new_qty = min(slot_qty + quantity, stack_cap)
            return offset, native_item_id.to_bytes(2, "little") + new_qty.to_bytes(2, "little")
        if slot_id == 0 and first_free_offset is None:
            first_free_offset = offset

    if first_free_offset is not None:
        new_qty = min(quantity, stack_cap)
        return first_free_offset, native_item_id.to_bytes(2, "little") + new_qty.to_bytes(2, "little")

    return None


# -- Options bitfield -----------------------------------------------------
#
# A `fast_text_speed`/`skip_battle_animations` QoL pair briefly lived here
# (2026-08-11), read-modify-writing `PLAYERDATA`'s `Options.textSpeed`/
# `battleScene` bits directly. Pulled the same day: live BizHawk testing
# showed neither option actually changed anything in-game. The in-word bit
# order it relied on (standard little-endian ARM bitfield packing,
# first-declared member in the low bits) was a reasoned assumption from the
# decomp source, never independently confirmed against a live session --
# exactly the kind of thing that turned out to matter. Revisit only with a
# real live-BizHawk verification step (dump the actual `Options` word,
# toggle the setting in-game, diff) before re-adding either option.

# -- Chunk framing (Decomposition src/save.c) --------------------------------


def chunk_size_with_footer(struct_size: int) -> int:
    """`GetSaveChunkSizePlusCRC` (src/save.c): round the raw struct size up
    to a multiple of 4, then add 4 (trailing CRC/pad word) -- this, not the
    bare struct size, is how much each chunk actually advances the running
    offset by in `SaveData_InitSubstructs`."""
    return ((struct_size + 3) & ~3) + 4


# SaveData: 3 BOOL + u32 statusFlags, all 4-byte fields, no alignment
# ambiguity (unlike SysInfo below).
SAVEDATA_DYNAMIC_REGION_OFFSET = 16


@dataclass(frozen=True)
class LongLongAlignmentCase:
    """One candidate assumption for how the retail MWCC 2.0/sp2p2 ARM9
    compiler aligns 8-byte struct members. Only SysInfo (chunk id 0) is
    affected; PlayerData/Party/Bag have none."""

    name: str
    sys_info_size: int


# SysInfo field-by-field derivation:
#   struct SysInfo_RTC { BOOL initialized; RTCDate date; RTCTime time;
#       s32 days_since_nitro_epoch; s64 seconds_since_nitro_epoch;
#       s64 seconds_at_game_clear; u32 penaltyInMinutes; }
#   struct SysInfo { s64 rtc_offset; u8 mac_address[6]; u8 birth_month;
#       u8 birth_day; SysInfo_RTC rtc_info; u8 mysteryGiftActive;
#       s32 dwcProfileId; u8 padding_50[0xC]; }
#
# "4-byte" case (older ARM APCS: 64-bit members align like any 4-byte-or-
# smaller member): SysInfo_RTC = 36 bytes, SysInfo = 72 bytes.
# "8-byte" case (AAPCS/EABI: 64-bit members force 8-byte alignment,
# including the enclosing struct's own size): SysInfo_RTC = 40 bytes,
# SysInfo = 80 bytes.
CASE_APCS_4BYTE_LONGLONG = LongLongAlignmentCase(name="apcs_4byte_longlong", sys_info_size=72)
CASE_EABI_8BYTE_LONGLONG = LongLongAlignmentCase(name="eabi_8byte_longlong", sys_info_size=80)

CANDIDATE_CASES: tuple[LongLongAlignmentCase, ...] = (CASE_APCS_4BYTE_LONGLONG, CASE_EABI_8BYTE_LONGLONG)

# PLAYERDATA and Party have no 8-byte members, so unlike SysInfo their
# sizes are the same under both alignment cases.
#   struct PLAYERDATA { Options options; PlayerProfile profile; u16 coins;
#       IGT igt; } -> 2+2(pad)+32+2+4 = 42, padded to 4-byte align -> 44.
PLAYER_DATA_SIZE = 44  # sizeof(PLAYERDATA), 0x2C

#   struct Party { PartyCore core; PartyExtra extra; }
#   PartyCore = 2 ints (8) + 6*sizeof(Pokemon) (6*0xEC=1416) = 1424
#   PartyExtra = 6*sizeof(PartyExtraSub) (6*5=30)
#   1424+30 = 1454, padded to 4-byte align -> 1456. sizeof(Pokemon)==0xEC
#   is stated directly in the decomp itself.
PARTY_SIZE = 1456  # sizeof(Party), 0x5B0

# Offset of PlayerProfile.money within PLAYERDATA: Options(2)+pad(2) =>
# profile starts at +4; profile.name(16)+profile.id(4) => money at +20.
# 4+16+4 = 24.
PLAYERDATA_MONEY_OFFSET = 24


@dataclass(frozen=True)
class SaveChunkOffsets:
    """Byte offsets within dynamic_region (the *_in_savedata properties
    add SAVEDATA_DYNAMIC_REGION_OFFSET) for one LongLongAlignmentCase."""

    case: LongLongAlignmentCase
    sys_info_offset: int
    player_data_offset: int
    party_offset: int
    bag_offset: int
    vars_flags_offset: int

    @property
    def money_offset_in_savedata(self) -> int:
        """Offset of PlayerProfile.money from the start of the RAM
        SaveData struct -- a convenient, independently-checkable anchor
        for manually locating SaveData in a live BizHawk session."""
        return SAVEDATA_DYNAMIC_REGION_OFFSET + self.player_data_offset + PLAYERDATA_MONEY_OFFSET

    @property
    def bag_offset_in_savedata(self) -> int:
        return SAVEDATA_DYNAMIC_REGION_OFFSET + self.bag_offset

    @property
    def vars_flags_offset_in_savedata(self) -> int:
        return SAVEDATA_DYNAMIC_REGION_OFFSET + self.vars_flags_offset


def compute_chunk_offsets(case: LongLongAlignmentCase) -> SaveChunkOffsets:
    """Re-implements SaveData_InitSubstructs's cumulative-offset loop for
    chunk ids 0..4 (SysInfo..SaveVarsFlags). All five share save "block"
    0, so no footer/page-boundary padding is crossed before id 4 and this
    straight-line accumulation is exact."""
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


# name -> offsets, for every candidate case (see this module's own
# docstring for how the case is selected).
CANDIDATE_OFFSETS: dict[str, SaveChunkOffsets] = {case.name: compute_chunk_offsets(case) for case in CANDIDATE_CASES}
