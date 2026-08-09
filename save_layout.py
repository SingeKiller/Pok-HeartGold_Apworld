# save_layout.py
#
# Task C16 -- static (source-derived) model of Pokemon HeartGold/SoulSilver's
# runtime `SaveData` struct layout: where `SaveVarsFlags` (check-detection
# flags, see docs/architecture.md's "## C14" section) and `Bag` (item
# injection) live *inside* the save data a running game keeps in RAM.
# Consumed by `client.py`.
#
# Pure Python, no BizHawk/Archipelago imports -- every constant here is
# derived directly from `ressources/Decomposition/pokeheartgold` C headers
# (cited inline), following the exact chunk-framing algorithm the game
# itself uses (`SaveData_InitSubstructs`/`GetSaveChunkSizePlusCRC`,
# `src/save.c`). See docs/architecture.md's "## C16" section for the full,
# field-by-field derivation this module implements, and -- importantly --
# for the one genuinely open question it could NOT resolve from source
# alone: how the actual retail MWCC 2.0/sp2p2 ARM9 compiler aligns 8-byte
# (`s64`/`u64`) struct members. That ambiguity only affects `SysInfo`
# (chunk id 0, the very first chunk) among the structs this module cares
# about, so it is modeled explicitly as exactly two named candidate cases
# (`CANDIDATE_CASES` / `CANDIDATE_OFFSETS`) rather than guessed away -- see
# `client.py`'s own docstring for how the case is selected (a required,
# explicitly user-confirmed setting, never silently defaulted).
#
# Independent of that ambiguity: the `Bag`/`SaveVarsFlags` structs' own
# *internal* layouts (pocket order/sizes, vars/flags array sizes) have no
# such ambiguity (no 8-byte members, no bitfields spanning byte
# boundaries) and are used directly.

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

# Hidden-item locations (`data/locations.py` type "hidden_item") store the
# small `HIDDENITEM_*` index (0-based) as their `id`, not a flag id directly
# -- the real savedata flag is `HIDDEN_ITEMS_FLAG_BASE + id`
# (Decomposition include/constants/flags.h: `HIDDEN_ITEMS_FLAG_BASE = 800`,
# `FLAG_HIDDENITEM_* = 800 + HIDDENITEM_*`). `ground_item`/`npc_gift`/`hm_tm`
# locations, by contrast, already store the real flag id directly (verified
# against `rom/eventscriptdata.py`'s own `BLOCK_INDEX_BY_ITEMBALL_FLAG_ID`
# keys, e.g. 1081/1056/... -- real `FLAG_HIDE_ITEMBALL_*` values, not small
# indices). See `location_flags.py`.
HIDDEN_ITEMS_FLAG_BASE = 800


def flag_byte_and_bit(flag_id: int) -> tuple[int, int]:
    """(byte index into `SaveVarsFlags.flags[]`, bit index within that byte)
    for `flag_id` -- mirrors `Save_VarsFlags_CheckFlagInArray`
    (`flags[flagId / 8] & (1 << (flagId & 7))`, see docs/architecture.md's
    "## C14" section, which already used this exact formula)."""
    return flag_id // 8, flag_id % 8


def is_flag_set(flags_bytes: bytes, flag_id: int) -> bool:
    """`flags_bytes` is exactly `SaveVarsFlags.flags[]` (`FLAGS_ARRAY_SIZE`
    bytes, e.g. read directly from RAM at
    `vars_flags_offset_in_savedata + FLAGS_ARRAY_OFFSET`). Returns False
    (rather than raising) for an out-of-range `flag_id`, matching
    `Save_VarsFlags_CheckFlagInArray`'s own defensive bounds behavior."""
    byte_index, bit_index = flag_byte_and_bit(flag_id)
    if byte_index < 0 or byte_index >= len(flags_bytes):
        return False
    return (flags_bytes[byte_index] & (1 << bit_index)) != 0


# -- Bag (Decomposition include/bag_types_def.h, include/constants/items.h) --
# typedef struct ItemSlot { u16 id; u16 quantity; } ItemSlot; -- 4 bytes,
# no padding ambiguity (include/item.h).
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
# (bag_types_def.h) -- order matters, it directly determines each pocket's
# byte offset within Bag.
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

# `data/items.py` "pocket" string (data_gen/items.toml's own convention,
# lowercased items.h POCKET_* constant) -> the matching Bag field name above.
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
# stackable in-game (always exactly 1 per slot); every other pocket caps at
# 99 (Bag_HasSpaceForItem/Bag_AddItem, src/bag.c -- not itself decompiled in
# this project's read of the decomp, so this is the well-established,
# publicly documented Gen IV convention, not a decomp citation -- flagged
# here rather than silently assumed).
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
    """Decide what to write into one Bag pocket's raw bytes (a flat array of
    `ItemSlot { u16 id; u16 quantity; }`, `ITEM_SLOT_SIZE`-aligned) to add
    `quantity` of `native_item_id`.

    Prefers stacking onto an existing slot already holding the same item (if
    it has room under `stack_cap`); otherwise uses the first free (`id ==
    0`) slot. Returns `(byte_offset_within_pocket, new_4_byte_item_slot)`,
    or `None` if the pocket is genuinely full (no matching slot with room,
    no free slot) -- callers must not write anything in that case.

    Deliberately simple (does not replicate `Bag_AddItem`'s TM/HM/Berry
    pocket re-sort, see docs/architecture.md's "## C16" section) -- an
    accepted v1 simplification: the added item still lands in a valid,
    correctly-typed slot, just not necessarily where vanilla sorting would
    have put it."""
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


# -- Chunk framing (Decomposition src/save.c) --------------------------------


def chunk_size_with_footer(struct_size: int) -> int:
    """`GetSaveChunkSizePlusCRC` (src/save.c): round the raw struct size up
    to a multiple of 4, then add 4 (trailing CRC/pad word) -- this, not the
    bare struct size, is how much each chunk actually advances the running
    offset by in `SaveData_InitSubstructs`."""
    return ((struct_size + 3) & ~3) + 4


# `SaveData` (Decomposition include/save.h): 3 `BOOL` (`flashChipDetected`,
# `saveFileExists`, `isNewGame`, each a plain 4-byte `int` typedef) + `u32
# statusFlags`, all 4-byte fields with no bitfields/64-bit members -- no
# alignment ambiguity, unlike SysInfo below.
SAVEDATA_DYNAMIC_REGION_OFFSET = 16


@dataclass(frozen=True)
class LongLongAlignmentCase:
    """One candidate assumption for how the retail MWCC 2.0/sp2p2 ARM9
    compiler aligns 8-byte (`s64`/`u64`) struct members -- see this module's
    own docstring. Only `SysInfo` (chunk id 0) is affected among the chunks
    this module models; `PlayerData`/`Party`/`Bag` have none."""

    name: str
    sys_info_size: int


# `SysInfo` (Decomposition include/sav_system_info.h) field-by-field
# derivation (see docs/architecture.md's "## C16" section for the full
# byte-by-byte walkthrough this summarizes):
#
#   struct SysInfo_RTC { BOOL initialized; RTCDate date; RTCTime time;
#       s32 days_since_nitro_epoch; s64 seconds_since_nitro_epoch;
#       s64 seconds_at_game_clear; u32 penaltyInMinutes; }
#   struct SysInfo { s64 rtc_offset; u8 mac_address[6]; u8 birth_month;
#       u8 birth_day; SysInfo_RTC rtc_info; u8 mysteryGiftActive;
#       s32 dwcProfileId; u8 padding_50[0xC]; }
#
# "4-byte" case (older ARM APCS convention: 64-bit members align like any
# other 4-byte-or-smaller member, no extra padding): SysInfo_RTC = 36 bytes,
# SysInfo = 72 bytes.
# "8-byte" case (AAPCS/EABI convention: 64-bit members force 8-byte
# alignment, including of the *enclosing* struct's own size): SysInfo_RTC =
# 40 bytes, SysInfo = 80 bytes.
CASE_APCS_4BYTE_LONGLONG = LongLongAlignmentCase(name="apcs_4byte_longlong", sys_info_size=72)
CASE_EABI_8BYTE_LONGLONG = LongLongAlignmentCase(name="eabi_8byte_longlong", sys_info_size=80)

CANDIDATE_CASES: tuple[LongLongAlignmentCase, ...] = (CASE_APCS_4BYTE_LONGLONG, CASE_EABI_8BYTE_LONGLONG)

# `PLAYERDATA` (Decomposition include/player_data.h) and `Party`
# (Decomposition include/pokemon_types_def.h) have no 8-byte members
# anywhere in their own field-by-field derivation (see docs/architecture.md's
# "## C16" section), so -- unlike SysInfo above -- their sizes are the same
# under both alignment cases.
#
#   struct PLAYERDATA { Options options; PlayerProfile profile; u16 coins;
#       IGT igt; }  ->  2 (Options) + 2 (padding, to 4-align PlayerProfile)
#       + 32 (PlayerProfile) + 2 (coins) + 4 (IGT) = 42, padded to the
#       struct's own 4-byte alignment -> 44.
PLAYER_DATA_SIZE = 44  # sizeof(PLAYERDATA), 0x2C

#   struct Party { PartyCore core; PartyExtra extra; }
#   PartyCore = 2 ints (8) + 6 * sizeof(Pokemon) (6 * 0xEC = 1416) = 1424
#   PartyExtra = 6 * sizeof(PartyExtraSub) (6 * 5 = 30)
#   1424 + 30 = 1454, padded to Party's own 4-byte alignment -> 1456.
#   sizeof(Pokemon) == 0xEC is stated directly in the decomp itself
#   (pokemon_types_def.h: "} Pokemon; // size: 0xEC"), not independently
#   re-derived here.
PARTY_SIZE = 1456  # sizeof(Party), 0x5B0

# Offset of `PlayerProfile.money` *within* `PLAYERDATA`: Options(2) +
# padding(2) => profile starts at PLAYERDATA+4; profile.name (16 bytes,
# u16[PLAYER_NAME_LENGTH+1]) + profile.id (u32, 4 bytes) => money at
# profile+20. 4 + 16 + 4 = 24.
PLAYERDATA_MONEY_OFFSET = 24


@dataclass(frozen=True)
class SaveChunkOffsets:
    """Byte offsets *within `dynamic_region`* (add
    `SAVEDATA_DYNAMIC_REGION_OFFSET` to get an offset from the start of the
    whole `SaveData` struct -- the `*_in_savedata` properties below already
    do that) for one `LongLongAlignmentCase`."""

    case: LongLongAlignmentCase
    sys_info_offset: int
    player_data_offset: int
    party_offset: int
    bag_offset: int
    vars_flags_offset: int

    @property
    def money_offset_in_savedata(self) -> int:
        """Offset of `PlayerProfile.money`, from the start of the RAM
        `SaveData` struct itself. A convenient, independently-checkable
        anchor for manually locating `SaveData` in a live BizHawk session
        (see docs/architecture.md's "## C16" section): search BizHawk's RAM
        Search for the player's current in-game money value (a plain,
        unencrypted `u32`), then check whether
        `candidate_money_address - money_offset_in_savedata` looks like a
        plausible `SaveData` base for this case (e.g. by then reading
        `bag_offset_in_savedata` bytes further and checking for
        sane-looking `ItemSlot` data matching the player's actual bag)."""
        return SAVEDATA_DYNAMIC_REGION_OFFSET + self.player_data_offset + PLAYERDATA_MONEY_OFFSET

    @property
    def bag_offset_in_savedata(self) -> int:
        return SAVEDATA_DYNAMIC_REGION_OFFSET + self.bag_offset

    @property
    def vars_flags_offset_in_savedata(self) -> int:
        return SAVEDATA_DYNAMIC_REGION_OFFSET + self.vars_flags_offset


def compute_chunk_offsets(case: LongLongAlignmentCase) -> SaveChunkOffsets:
    """Re-implements `SaveData_InitSubstructs`'s cumulative-offset loop
    (Decomposition src/save.c) for chunk ids 0..4 (SysInfo..SaveVarsFlags).
    All five share save "block" 0 (`gSaveChunkHeaders`, src/save_arrays.c --
    only chunk id 40, `SAVE_PCSTORAGE`, starts a new block), so no
    footer/page-boundary padding is crossed before id 4 and this
    straight-line accumulation (chunk size, in order, with no gaps) is
    exact given each chunk's size."""
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


# name -> offsets, for every candidate case -- see `client.py` for how one
# of these is selected (a required, explicitly user-confirmed setting).
CANDIDATE_OFFSETS: dict[str, SaveChunkOffsets] = {case.name: compute_chunk_offsets(case) for case in CANDIDATE_CASES}
