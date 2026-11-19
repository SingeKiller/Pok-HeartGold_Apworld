from __future__ import annotations

import random
import struct

from rom import HeartGoldRom, itemdata, msgdata
from rom.foreignnamedata import clean_text

BLOCK_START = 0x020FBA54
BLOCK_END = 0x020FBC82
QUANTITY_CAP_ADDRESS = 0x020FBC52
SLOT_BOUGHT_ADDRESS = 0x020FBC2E
SLOT_BOUGHT_SITE = 0x41BC
SLOT_BOUGHT_VANILLA = bytes.fromhex("a62104208900605010bd")
SHOP_LEAVE_FUNCTION = 0x022586CC
KEPT_RANGES = ((0x020FBBA4, 0x020FBBB4), (SLOT_BOUGHT_ADDRESS, BLOCK_END))
POINTER_TABLE = 0x0210FA3C
LIST_COUNT = 30
TERMINATOR = 0xFFFF
ITEM_NARC_IDS = 0x02100194
ITEM_NARC_ROW_SIZE = 8
ITEM_DESCRIPTIONS_SUBFILE_INDEX = 221
SLOTS_PER_MART = 2
NAME_MAX = 12
DESCRIPTION_LINE_MAX = 20
TOWN_MART_LISTS = {
    0: "cherrygrove_pokemart",
    1: "violet_pokemart",
    2: "azalea_pokemart",
    9: "ecruteak_pokemart",
    10: "olivine_pokemart",
    12: "blackthorn_pokemart",
    14: "vermilion_pokemart",
    15: "saffron_pokemart",
    16: "lavender_pokemart",
    17: "cerulean_pokemart",
    24: "fuchsia_pokemart",
    25: "pewter_pokemart",
    26: "viridian_pokemart",
}
CARRIERS = tuple(range(505, 531))
POKEATHLON_CARD_LISTS = (0x020FBCBA, 0x020FBD0E, 0x020FBD9A, 0x020FBC9E, 0x020FBBA4)
POKEATHLON_REPLACEMENT_ITEM = 17
CONSUMABLE_POCKETS = ("balls", "medicine", "battle_items")
ANY_POCKETS = (*CONSUMABLE_POCKETS, "tm_hm", "items", "berries")
POKE_BALL_ID = 4
HM_IDS = range(420, 428)
HM_PRICE = 3000
APRICORN_IDS = range(485, 492)
KEY_ITEM_PRICE = 500
KEY_ITEM_PROGRESSION_PRICE = 1000
KEY_ITEMS_NEVER_SOLD = (
    429, 430, 431, 433, 436, 438, 439, 440, 441, 442, 443, 448, 449, 451,
    452, 453, 454, 455, 457, 458, 459, 460, 461, 462, 463, 467, 473, 533,
)
SINGLE_PURCHASE_IDS = (*range(328, 485), *range(501, 537))
ICON_NARC = "a/0/1/8"
SHOP_OVERLAY = 3
SHOP_OVERLAY_ADDRESS = 0x02253E20
QUANTITY_CLAMP_OFFSET = 0x3AE2
QUANTITY_CLAMP_VANILLA = bytes.fromhex("6852685a632801d963206852")
QUANTITY_CAP_CODE = bytes.fromhex(
    "a12292008a5a52239b00d21a9c2a09d9ad3a232a06d91f3a042a03d9632802d9632000e00120a222920088527047"
)
_THUMB_MOV_R1_R5 = bytes.fromhex("291c")
_THUMB_NOP = bytes.fromhex("c046")
_ICON_PIXELS_OFFSET = 0x30
_ICON_PALETTE_OFFSET = 0x28
ICON_PIXELS = bytes.fromhex(
    "0000000000000000000000000000000000000000000040440040111100141111000000690000696600606666"
    "0069666600606666090069661104606611410066960000006696000066660600666696006666060066960090"
    "6609902266002922000000000000000000000000000000000000000022090000222202002222220090111111"
    "1011111110111111101111111011040010040000000080880080777711110069111104601111016011110160"
    "4911019000400400080000007708000096002222062022220620222206202222092022920020020000000070"
    "0000705522222209222222022222220222222202009022020000900255070000555505000078777790777777"
    "7077777770777777707777777077777780777777007777777787000077770900777700007708009087003933"
    "0790333309303333003433330000575500905555000055550900705533930055333309503333037033334300"
    "5555550055555509555555055555550555555505555555055555550555555500007877770090777700000099"
    "0000000000000000000000000000000000000000003333330033333300333333003433330039333300403333"
    "0000343300000044333333003333330033333300333343003333930033330400334300004400000055558500"
    "55550900990000000000000000000000000000000000000000000000"
)
ICON_PALETTE = bytes.fromhex(
    "00009e4b0f3b9b42973e595ef9451156ed4d4e2da41401000000000000000000"
)
_PRICE_OFFSET = 0
_FIELD_USE_OFFSET = 10
_BATTLE_USE_OFFSET = 11
_POCKET_BITS_OFFSET = 8
_POCKET_BITS_MASK = 0x780
_KEY_POCKET_BITS = 0x380


class ShopDataError(Exception):
    pass


def slot_carriers() -> dict[tuple[int, int], int]:
    keys = [(index, slot) for index in sorted(TOWN_MART_LISTS) for slot in range(SLOTS_PER_MART)]
    return dict(zip(keys, CARRIERS, strict=True))


def _free_ranges() -> list[tuple[int, int]]:
    ranges, start = [], BLOCK_START
    for kept_start, kept_end in sorted(KEPT_RANGES):
        ranges.append((start, kept_start))
        start = kept_end
    ranges.append((start, BLOCK_END))
    return ranges


def _read_lists(arm9: bytes, base: int) -> list[list[int]]:
    pointers = struct.unpack_from(f"<{LIST_COUNT}I", arm9, POINTER_TABLE - base)
    lists = []
    for index, pointer in enumerate(pointers):
        if not BLOCK_START <= pointer < BLOCK_END:
            raise ShopDataError(f"special mart list {index} points outside the mart block ({pointer:#x})")
        items, offset = [], pointer - base
        while True:
            (value,) = struct.unpack_from("<H", arm9, offset)
            if value == TERMINATOR:
                break
            items.append(value)
            offset += 2
        lists.append(items)
    return lists


def read_lists(rom: HeartGoldRom) -> list[list[int]]:
    return _read_lists(rom.read_main_code_decompressed(), rom.arm9_ram_address)


def _list_edits(lists: list[list[int]], base: int) -> list[tuple[int, bytes]]:
    if len(lists) != LIST_COUNT:
        raise ShopDataError(f"expected {LIST_COUNT} special mart lists, got {len(lists)}")
    ranges = [[start, end, bytearray()] for start, end in _free_ranges()]
    pointers = []
    for index, items in enumerate(lists):
        encoded = struct.pack(f"<{len(items) + 1}H", *items, TERMINATOR)
        target = next((r for r in ranges if r[0] + len(r[2]) + len(encoded) <= r[1]), None)
        if target is None:
            raise ShopDataError(f"special mart list {index} does not fit in the mart block")
        pointers.append(target[0] + len(target[2]))
        target[2] += encoded
    edits = []
    for start, end, blob in ranges:
        edits.append((start - base, bytes(blob) + b"\xff" * (end - start - len(blob))))
    edits.append((POINTER_TABLE - base, struct.pack(f"<{LIST_COUNT}I", *pointers)))
    return edits


def write_lists(rom: HeartGoldRom, lists: list[list[int]]) -> None:
    rom.write_main_code_regions(_list_edits(lists, rom.arm9_ram_address))


def shop_pools(key_items: bool = False) -> dict[str, list[int]]:
    from data.items import ITEMS

    pools: dict[str, list[int]] = {pocket: [] for pocket in ANY_POCKETS}
    if key_items:
        pools["key_items"] = []
    for data in ITEMS.values():
        item = data["id"]
        if data["pocket"] == "key_items":
            if key_items and item not in CARRIERS and item not in KEY_ITEMS_NEVER_SOLD:
                pools["key_items"].append(item)
        elif data["pocket"] in pools and item not in APRICORN_IDS and (data["price"] > 0 or item in HM_IDS):
            pools[data["pocket"]].append(item)
    return pools


def randomize_lists(lists: list[list[int]], rng: random.Random, key_items: bool = False) -> list[list[int]]:
    pools = shop_pools(key_items)
    any_pockets = tuple(pools)
    randomized = [list(items) for items in lists]
    for index in TOWN_MART_LISTS:
        chosen: list[int] = []
        for slot in range(len(lists[index])):
            pocket = rng.choice(CONSUMABLE_POCKETS if slot == 0 else any_pockets)
            candidates = [
                item for item in pools[pocket] if item not in chosen and (slot > 0 or item != POKE_BALL_ID)
            ]
            chosen.append(rng.choice(candidates))
        randomized[index] = chosen
    return randomized


def apply_shop_randomizer(rom: HeartGoldRom, seed: int, key_items: bool = False) -> None:
    from data.items import ITEMS

    arm9 = rom.read_main_code_decompressed()
    base = rom.arm9_ram_address
    lists = randomize_lists(_read_lists(arm9, base), random.Random(seed), key_items)
    rom.write_main_code_regions(_list_edits(lists, base))
    entries = [bytearray(entry) for entry in itemdata.read_all(rom)]
    for hm in HM_IDS:
        struct.pack_into("<H", entries[carrier_data_index(arm9, base, hm)], _PRICE_OFFSET, HM_PRICE)
    by_id = {data["id"]: data for data in ITEMS.values()}
    for item in {item for index in TOWN_MART_LISTS for item in lists[index]}:
        if by_id[item]["pocket"] == "key_items":
            progression = by_id[item]["classification"] == "progression"
            price = KEY_ITEM_PROGRESSION_PRICE if progression else KEY_ITEM_PRICE
            struct.pack_into("<H", entries[carrier_data_index(arm9, base, item)], _PRICE_OFFSET, price)
    itemdata.write_all(rom, [bytes(entry) for entry in entries])


def _thumb_bl(source: int, target: int) -> bytes:
    offset = target - (source + 4)
    return struct.pack("<HH", 0xF000 | (offset >> 12 & 0x7FF), 0xF800 | (offset >> 1 & 0x7FF))


def slot_bought_code() -> bytes:
    head = bytes.fromhex("00b5a6218900042242501439415aff39ae39662904d80d211022")
    call = _thumb_bl(SLOT_BOUGHT_ADDRESS + len(head), SHOP_LEAVE_FUNCTION)
    return head + call + bytes.fromhex("00bd042000bd")


def apply_quantity_cap(rom: HeartGoldRom) -> None:
    arm9 = rom.read_main_code_decompressed()
    base = rom.arm9_ram_address
    pointers = struct.unpack_from(f"<{LIST_COUNT}I", arm9, POINTER_TABLE - base)
    if any(pointer >= SLOT_BOUGHT_ADDRESS for pointer in pointers):
        raise ShopDataError("a special mart list still lies where the quantity cap goes")
    code = bytearray(rom.read_overlay(SHOP_OVERLAY))
    bought = SLOT_BOUGHT_SITE
    if code[bought : bought + len(SLOT_BOUGHT_VANILLA)] != SLOT_BOUGHT_VANILLA:
        raise ShopDataError(f"shop overlay: unexpected bytes at the end of a purchase at {bought:#x}")
    code[bought : bought + len(SLOT_BOUGHT_VANILLA)] = (
        bytes.fromhex("201c")
        + _thumb_bl(SHOP_OVERLAY_ADDRESS + bought + 2, SLOT_BOUGHT_ADDRESS)
        + bytes.fromhex("10bd")
        + _THUMB_NOP
    )
    site = QUANTITY_CLAMP_OFFSET
    if code[site : site + len(QUANTITY_CLAMP_VANILLA)] != QUANTITY_CLAMP_VANILLA:
        raise ShopDataError(f"shop overlay: unexpected bytes for the quantity clamp at {site:#x}")
    call = SHOP_OVERLAY_ADDRESS + site + len(_THUMB_MOV_R1_R5)
    patch = _THUMB_MOV_R1_R5 + _thumb_bl(call, QUANTITY_CAP_ADDRESS)
    code[site : site + len(QUANTITY_CLAMP_VANILLA)] = patch + _THUMB_NOP * ((len(QUANTITY_CLAMP_VANILLA) - len(patch)) // 2)
    rom.write_overlay(SHOP_OVERLAY, bytes(code))
    rom.write_main_code_regions(
        [(QUANTITY_CAP_ADDRESS - base, QUANTITY_CAP_CODE), (SLOT_BOUGHT_ADDRESS - base, slot_bought_code())]
    )


def apply_shop_icon(rom: HeartGoldRom, carriers: list[int]) -> None:
    arm9 = rom.read_main_code_decompressed()
    base = rom.arm9_ram_address
    narc = rom.read_narc(ICON_NARC)
    first = ITEM_NARC_IDS - base + carriers[0] * ITEM_NARC_ROW_SIZE
    _, ncgr_index, nclr_index = struct.unpack_from("<3H", arm9, first)
    ncgr = bytes(narc.files[ncgr_index])
    nclr = bytes(narc.files[nclr_index])
    new_ncgr = len(narc.files)
    narc.files.append(ncgr[:_ICON_PIXELS_OFFSET] + ICON_PIXELS)
    narc.files.append(
        nclr[:_ICON_PALETTE_OFFSET]
        + ICON_PALETTE
        + bytes(len(nclr) - _ICON_PALETTE_OFFSET - len(ICON_PALETTE))
    )
    rom.write_narc(ICON_NARC, narc)
    rom.write_main_code_regions(
        [
            (ITEM_NARC_IDS - base + carrier * ITEM_NARC_ROW_SIZE + 2, struct.pack("<2H", new_ncgr, new_ncgr + 1))
            for carrier in carriers
        ]
    )


def carrier_data_index(arm9: bytes, base: int, carrier: int) -> int:
    return struct.unpack_from("<H", arm9, ITEM_NARC_IDS - base + carrier * ITEM_NARC_ROW_SIZE)[0]


def shop_texts(item: str, player: str | None, game: str | None) -> tuple[str, str]:
    name = clean_text(item, NAME_MAX)
    lines = [clean_text(item, DESCRIPTION_LINE_MAX)]
    if player is not None:
        lines.append(clean_text(f"for {player}", DESCRIPTION_LINE_MAX))
    if game:
        lines.append(clean_text(game, DESCRIPTION_LINE_MAX))
    return name, "\n".join(lines)


def _pokeathlon_card_edits(arm9: bytes, base: int) -> list[tuple[int, bytes]]:
    edits = []
    for address in POKEATHLON_CARD_LISTS:
        item, price = struct.unpack_from("<HH", arm9, address - base)
        if not 505 <= item <= 531:
            raise ShopDataError(f"no Data Card list at {address:#x}")
        edits.append((address - base, struct.pack("<HHHH", POKEATHLON_REPLACEMENT_ITEM, price, TERMINATOR, 0)))
    return edits


def apply_shop_slots(rom: HeartGoldRom, slots: dict[tuple[int, int], dict]) -> None:
    carriers = slot_carriers()
    unknown = [key for key in slots if key not in carriers]
    if unknown:
        raise ShopDataError(f"no town mart slot for {unknown}")
    arm9 = rom.read_main_code_decompressed()
    base = rom.arm9_ram_address
    lists = _read_lists(arm9, base)
    for index in sorted(TOWN_MART_LISTS):
        added = [carriers[(index, slot)] for slot in range(SLOTS_PER_MART) if (index, slot) in slots]
        lists[index] = added + lists[index]
    rom.write_main_code_regions(_list_edits(lists, base) + _pokeathlon_card_edits(arm9, base))

    entries = [bytearray(entry) for entry in itemdata.read_all(rom)]
    names, descriptions = {}, {}
    for key, slot in slots.items():
        carrier = carriers[key]
        entry = entries[carrier_data_index(arm9, base, carrier)]
        struct.pack_into("<H", entry, _PRICE_OFFSET, max(0, min(int(slot["price"]), 0xFFFF)))
        entry[_FIELD_USE_OFFSET] = 0
        entry[_BATTLE_USE_OFFSET] = 0
        pocket_bits = struct.unpack_from("<H", entry, _POCKET_BITS_OFFSET)[0]
        struct.pack_into("<H", entry, _POCKET_BITS_OFFSET, pocket_bits & ~_POCKET_BITS_MASK | _KEY_POCKET_BITS)
        names[carrier] = slot["name"]
        descriptions[carrier] = slot["description"]
    itemdata.write_all(rom, [bytes(entry) for entry in entries])
    for bank in (msgdata.ITEM_NAMES_SUBFILE_INDEX, msgdata.ITEM_NAMES_INDEF_SUBFILE_INDEX, msgdata.ITEM_NAMES_PLURAL_SUBFILE_INDEX):
        msgdata.replace_messages(rom, bank, names)
    msgdata.replace_messages(rom, ITEM_DESCRIPTIONS_SUBFILE_INDEX, descriptions)
    apply_shop_icon(rom, [carriers[key] for key in sorted(slots)])
