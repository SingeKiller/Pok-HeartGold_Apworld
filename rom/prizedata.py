from __future__ import annotations

import struct

from data.charmap import CHARMAP
from rom import HeartGoldRom, msgdata
from rom.eventscriptdata import NITROFS_PATH
from rom.foreignnamedata import clean_text

PRIZE_COST = 50
LABEL_LINE_MAX = 16

BLOCK_SIZE = 139
_NEWLINE_CODE = 0xE000
_WAIT_CODE = 0x25BC
_TAG_CODE = 0xFFFE

_SET_VAR = 41
_COMPARE = 17
_GOTO = 22
_GOTO_IF = 28
_SET_FLAG = 30
_CHECK_FLAG = 32
_NOOP = 0
_X8004 = 0x8004
_X8005 = 0x8005
_X8006 = 0x8006
_RESULT = 0x800C


class PrizeDataError(Exception):
    pass


COUNTERS: dict[str, dict] = {
    "goldenrod": {
        "file": 910,
        "bank": 603,
        "first_index": 0,
        "flags": tuple(range(0x544, 0x54E)),
        "labels": 14,
        "headings": (12, 13),
        "confirm": 3,
        "sold_out": 5,
        "claimed": 10,
        "blocks": (
            (834, 417, 2000), (973, 402, 4000), (1112, 371, 6000), (1251, 362, 10000), (1390, 340, 10000),
            (1529, 351, 10000), (1668, 251, 1000), (1807, 265, 1000), (1946, 276, 1000), (2085, 277, 1000),
        ),
    },
    "celadon": {
        "file": 804,
        "bank": 509,
        "first_index": 10,
        "flags": tuple(range(0x832, 0x83C)),
        "labels": 23,
        "headings": (21, 22),
        "confirm": 12,
        "sold_out": 14,
        "claimed": 19,
        "blocks": (
            (654, 385, 2000), (793, 359, 4000), (932, 337, 6000), (1071, 356, 10000), (1210, 401, 10000),
            (1349, 395, 15000), (1488, 251, 1000), (1627, 265, 1000), (1766, 276, 1000), (1905, 277, 1000),
        ),
    },
}

PRIZE_FLAGS: dict[int, int] = {
    counter["first_index"] + slot: flag
    for counter in COUNTERS.values()
    for slot, flag in enumerate(counter["flags"])
}


def _expect(data: bytes, offset: int, fmt: str, values: tuple, what: str) -> tuple:
    found = struct.unpack_from(fmt, data, offset)
    for got, want in zip(found, values):
        if want is not None and got != want:
            raise PrizeDataError(f"unexpected {what} at offset {offset}: {found} (wanted {values})")
    return found


def check_block(data: bytes, start: int, item: int, cost: int) -> int:
    _expect(data, start, "<HHH", (_SET_VAR, _X8004, item), "item id")
    _expect(data, start + 6, "<HHH", (_SET_VAR, _X8005, 1), "quantity")
    _expect(data, start + 12, "<HHHH", (127, _X8004, _X8005, _RESULT), "space check")
    _expect(data, start + 20, "<HHH", (_COMPARE, _RESULT, 0), "space compare")
    _, cond, rel = _expect(data, start + 26, "<HBi", (_GOTO_IF, 1, None), "no-space jump")
    _expect(data, start + 33, "<HBH", (194, 0, _X8004), "item name buffer")
    _expect(data, start + 38, "<HB", (45, None), "confirm message")
    _expect(data, start + 41, "<HH", (748, _RESULT), "menu choice")
    _expect(data, start + 45, "<HHH", (_COMPARE, _RESULT, 0), "choice compare")
    _expect(data, start + 51, "<HB", (_GOTO_IF, 1), "choice jump")
    _expect(data, start + 58, "<H", (53,), "close message")
    _expect(data, start + 60, "<HHH", (_COMPARE, _RESULT, 1), "cancel compare")
    _expect(data, start + 66, "<HB", (_GOTO_IF, 1), "cancel jump")
    _expect(data, start + 73, "<HH", (119, _X8006), "coin amount")
    _expect(data, start + 77, "<HHH", (_COMPARE, _X8006, cost), "coin compare")
    _expect(data, start + 83, "<HB", (_GOTO_IF, 0), "not enough coins jump")
    _expect(data, start + 90, "<HB", (45, None), "here you go message")
    _expect(data, start + 97, "<HH", (121, cost), "take coins")
    _expect(data, start + 101, "<HB", (118, 0), "coin box update")
    _expect(data, start + 104, "<HBH", (194, 0, _X8004), "item name buffer")
    _expect(data, start + 109, "<HHH", (130, _X8004, _RESULT), "pocket lookup")
    _expect(data, start + 115, "<HBH", (195, 1, _RESULT), "pocket name buffer")
    _expect(data, start + 120, "<HB", (45, None), "claimed message")
    _expect(data, start + 123, "<HHHH", (125, _X8004, 1, _RESULT), "give item")
    _expect(data, start + 131, "<H", (_GOTO,), "back to menu")
    _expect(data, start + 137, "<H", (2,), "end")
    return start + 26 + 7 + rel


def patch_block(data: bytearray, start: int, flag: int, item: int, cost: int, messages: tuple[int, int]) -> None:
    target = check_block(bytes(data), start, item, cost)
    if (data[start + 40], data[start + 122]) != messages:
        raise PrizeDataError(f"unexpected prize messages at offset {start}")
    check = struct.pack("<HH", _CHECK_FLAG, flag)
    jump = struct.pack("<HBi", _GOTO_IF, 1, target - (start + 16 + 7))
    head = check + jump + struct.pack("<H", _NOOP) * 5
    claimed = data[start + 120 : start + 123]
    tail = struct.pack("<H", _NOOP) * 6 + struct.pack("<HH", _SET_FLAG, flag) + bytes(claimed)
    data[start + 12 : start + 33] = head
    struct.pack_into("<H", data, start + 81, PRIZE_COST)
    struct.pack_into("<H", data, start + 99, PRIZE_COST)
    data[start + 104 : start + 123] = tail
    data[start + 123 : start + 131] = struct.pack("<H", _NOOP) * 4
    if len(head) != 21 or len(tail) != 19:
        raise PrizeDataError("prize block patch has the wrong size")


def encode_codes(text: str) -> list[int]:
    codes = []
    for char in text:
        if char == "\n":
            codes.append(_NEWLINE_CODE)
        elif char in CHARMAP:
            codes.append(CHARMAP[char])
        else:
            raise PrizeDataError(f"character {char!r} has no data/charmap.py entry")
    return codes


def label_text(name: str, player: str | None) -> str:
    second = "for you" if player is None else f"for {player}"
    return f"{clean_text(name, LABEL_LINE_MAX)}\n{clean_text(second, LABEL_LINE_MAX)}"


def _confirm_codes(original: list[int]) -> list[int]:
    if _TAG_CODE not in original:
        raise PrizeDataError("confirm message has no control code")
    tail = original[len(original) - original[::-1].index(_TAG_CODE) - 1 :]
    return encode_codes(f"This prize costs {PRIZE_COST} Coins.\nIs that right? ") + tail


def _sold_out_codes(original: list[int]) -> list[int]:
    codes = encode_codes("Sorry. You already took\nthis prize.")
    if original and original[-1] == _WAIT_CODE:
        codes.append(_WAIT_CODE)
    return codes


def apply_prizes(rom: HeartGoldRom, slots: list[dict]) -> None:
    if not slots:
        return
    by_counter: dict[str, dict[int, dict]] = {name: {} for name in COUNTERS}
    for slot in slots:
        index = int(slot["index"])
        for name, counter in COUNTERS.items():
            position = index - counter["first_index"]
            if 0 <= position < len(counter["blocks"]):
                by_counter[name][position] = slot
                break
        else:
            raise PrizeDataError(f"no prize counter for slot {index}")
    narc = rom.read_narc(NITROFS_PATH)
    for name, chosen in by_counter.items():
        if not chosen:
            continue
        counter = COUNTERS[name]
        data = bytearray(narc.files[counter["file"]])
        for position in sorted(chosen):
            start, item, cost = counter["blocks"][position]
            patch_block(data, start, counter["flags"][position], item, cost, (counter["confirm"], counter["claimed"]))
        narc.files[counter["file"]] = bytes(data)
    rom.write_narc(NITROFS_PATH, narc)
    for name, chosen in by_counter.items():
        if not chosen:
            continue
        counter = COUNTERS[name]
        bank = counter["bank"]
        texts = {
            counter["labels"] + position: label_text(slot["name"], slot.get("player"))
            for position, slot in chosen.items()
        }
        texts[counter["headings"][0]] = "PRIZES 1-6"
        texts[counter["headings"][1]] = "PRIZES 7-10"
        texts[counter["claimed"]] = "Prize claimed!\nIt is on its way."
        msgdata.replace_messages(rom, bank, texts)
        codes = {
            counter["confirm"]: _confirm_codes(msgdata.read_message_codes(rom, bank, counter["confirm"])),
            counter["sold_out"]: _sold_out_codes(msgdata.read_message_codes(rom, bank, counter["sold_out"])),
        }
        msgdata.replace_message_codes(rom, bank, codes)
