from __future__ import annotations

import struct

from data.charmap import CHARMAP
from rom import HeartGoldRom, msgdata

NITROFS_PATH = "a/1/1/2"
TRADE_COUNT = 13
TRADE_SIZE = 0x54
GIVE_SPECIES_OFFSET = 0x00
ASK_SPECIES_OFFSET = 0x4C
NICKNAME_BANK = 200
SPECIES_NAME_BANK = 237
RANDOMIZABLE_TRADES = (0, 1, 2, 3, 4, 8, 9, 11, 12)
MAX_NATIONAL_DEX = 493
FONT_PATH = "a/0/1/6"
MAX_LINE_WIDTH = 220
PLAYER_NAME_WIDTH = 42
DEFAULT_GLYPH_WIDTH = 6

TRADE_TEXTS: dict[int, tuple[tuple[int, tuple[int, ...]], ...]] = {
    0: ((562, (1, 2, 3, 5)),),
    1: ((596, (9, 10, 11, 13)),),
    2: ((608, (0, 1, 2, 4)),),
    3: ((634, (0, 1, 2, 4)),),
    8: ((344, (9, 10, 11, 13)), (345, (8, 9, 10, 12))),
    9: ((463, (3, 5, 6, 7)),),
    11: ((47, (11, 12, 15, 16, 17, 18)),),
    12: ((537, (7, 8, 11, 12, 13)),),
}

_COMMAND = 0xFFFE
_PLAYER_NAME_COMMAND = 0x0103
_BREAKS = (0xE000, 0x25BC, 0x25BD)
_PAGE_BREAK = 0x25BC
_SPACE = CHARMAP[" "]
_LETTER_A = CHARMAP["a"]
_LETTER_N = CHARMAP["n"]
_LETTERS = frozenset(code for char, code in CHARMAP.items() if len(char) == 1 and char.isalnum())
_VOWELS = frozenset(CHARMAP[char] for char in "AEIOU")


class TradePatchError(Exception):
    pass


def _glyph_widths(rom: HeartGoldRom) -> bytes:
    font = rom.read_narc(FONT_PATH).files[0]
    start, count = struct.unpack_from("<II", font, 4)
    return bytes(font[start : start + count])


def _split_lines(codes: list[int]) -> tuple[list[list[int]], list[int]]:
    lines: list[list[int]] = [[]]
    breaks: list[int] = []
    index = 0
    while index < len(codes):
        code = codes[index]
        if code == _COMMAND:
            size = 3 + codes[index + 2]
            lines[-1].extend(codes[index : index + size])
            index += size
        elif code in _BREAKS:
            breaks.append(code)
            lines.append([])
            index += 1
        else:
            lines[-1].append(code)
            index += 1
    return lines, breaks


def _measure(line: list[int], widths: bytes) -> tuple[int, list[tuple[int, int]]]:
    total = 0
    spaces: list[tuple[int, int]] = []
    index = 0
    while index < len(line):
        code = line[index]
        if code == _COMMAND:
            if line[index + 1] == _PLAYER_NAME_COMMAND:
                total += PLAYER_NAME_WIDTH
            index += 3 + line[index + 2]
            continue
        if code == _SPACE:
            spaces.append((index, total))
        total += widths[code] if code < len(widths) else DEFAULT_GLYPH_WIDTH
        index += 1
    return total, spaces


def _fit_line(line: list[int], limit: int, widths: bytes) -> list[list[int]]:
    pieces: list[list[int]] = []
    while True:
        total, spaces = _measure(line, widths)
        cuts = [index for index, before in spaces if before <= limit]
        if total <= limit or not cuts:
            pieces.append(line)
            return pieces
        pieces.append(line[: cuts[-1]])
        line = line[cuts[-1] + 1 :]


def _swap_names(line: list[int], pairs: list[tuple[list[int], list[int]]]) -> tuple[list[int], int]:
    out: list[int] = []
    count = 0
    index = 0
    while index < len(line):
        for old, new in pairs:
            end = index + len(old)
            if (
                line[index:end] == old
                and (index == 0 or line[index - 1] not in _LETTERS)
                and (end >= len(line) or line[end] not in _LETTERS)
            ):
                for article in ([_LETTER_A, _LETTER_N, _SPACE], [_LETTER_A, _SPACE]):
                    start = len(out) - len(article)
                    if out[start:] == article and (start == 0 or out[start - 1] not in _LETTERS):
                        out[start:] = [_LETTER_A] + ([_LETTER_N] if new[0] in _VOWELS else []) + [_SPACE]
                        break
                out.extend(new)
                index = end
                count += 1
                break
        else:
            out.append(line[index])
            index += 1
    return out, count


def _rewrite_message(
    codes: list[int], pairs: list[tuple[list[int], list[int]]], widths: bytes
) -> tuple[list[int], int]:
    lines, breaks = _split_lines(codes)
    total = 0
    result: list[int] = []
    for position, line in enumerate(lines):
        new_line, count = _swap_names(line, pairs)
        total += count
        pieces = [new_line]
        if count:
            limit = max(MAX_LINE_WIDTH, _measure(line, widths)[0])
            pieces = _fit_line(new_line, limit, widths)
        for number, piece in enumerate(pieces):
            if number:
                result.append(_PAGE_BREAK)
            result.extend(piece)
        if position < len(breaks):
            result.append(breaks[position])
    return result, total


def read_trades(rom: HeartGoldRom) -> list[tuple[int, int]]:
    narc = rom.read_narc(NITROFS_PATH)
    if len(narc.files) != TRADE_COUNT:
        raise TradePatchError(f"trade table has {len(narc.files)} entries, expected {TRADE_COUNT}")
    return [
        (struct.unpack_from("<i", entry, GIVE_SPECIES_OFFSET)[0], struct.unpack_from("<i", entry, ASK_SPECIES_OFFSET)[0])
        for entry in narc.files
    ]


def write_trades(rom: HeartGoldRom, trades: dict[int, tuple[int, int]]) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    if len(narc.files) != TRADE_COUNT:
        raise TradePatchError(f"trade table has {len(narc.files)} entries, expected {TRADE_COUNT}")
    nicknames = {}
    texts: dict[int, dict[int, list[int]]] = {}
    widths = None
    for index, (give, ask) in trades.items():
        if index not in RANDOMIZABLE_TRADES:
            raise TradePatchError(f"trade {index} is a loan or a gift, not a trade")
        if not (1 <= give <= MAX_NATIONAL_DEX and 1 <= ask <= MAX_NATIONAL_DEX):
            raise TradePatchError(f"trade {index}: species {give} / {ask} outside the National Dex")
        entry = bytearray(narc.files[index])
        if len(entry) != TRADE_SIZE:
            raise TradePatchError(f"trade {index} is {len(entry)} bytes, expected {TRADE_SIZE}")
        old_give = struct.unpack_from("<i", entry, GIVE_SPECIES_OFFSET)[0]
        old_ask = struct.unpack_from("<i", entry, ASK_SPECIES_OFFSET)[0]
        if widths is None:
            widths = _glyph_widths(rom)
        pairs = [
            (msgdata.read_message_codes(rom, SPECIES_NAME_BANK, old), msgdata.read_message_codes(rom, SPECIES_NAME_BANK, new))
            for old, new in ((old_give, give), (old_ask, ask))
        ]
        for bank, messages in TRADE_TEXTS.get(index, ()):
            for message in messages:
                codes, count = _rewrite_message(msgdata.read_message_codes(rom, bank, message), pairs, widths)
                if not count:
                    raise TradePatchError(f"trade {index}: message {message} of bank {bank} names neither species")
                texts.setdefault(bank, {})[message] = codes
        struct.pack_into("<i", entry, GIVE_SPECIES_OFFSET, give)
        struct.pack_into("<i", entry, ASK_SPECIES_OFFSET, ask)
        narc.files[index] = bytes(entry)
        nicknames[index] = msgdata.read_message_codes(rom, SPECIES_NAME_BANK, give)
    rom.write_narc(NITROFS_PATH, narc)
    msgdata.replace_message_codes(rom, NICKNAME_BANK, nicknames)
    for bank, codes in texts.items():
        msgdata.replace_message_codes(rom, bank, codes)
