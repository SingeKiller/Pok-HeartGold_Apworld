from __future__ import annotations

import struct

from data.charmap import CHARMAP
from rom import HeartGoldRom

NITROFS_PATH = "a/0/2/7"
ITEM_NAMES_SUBFILE_INDEX = 222

ITEM_NAMES_INDEF_SUBFILE_INDEX = 223
ITEM_NAMES_PLURAL_SUBFILE_INDEX = 224

STARTER_SELECTION_SUBFILE_INDEX = 190

_ENTRY_TERMINATOR = 0xFFFF
_MAT_HEADER_SIZE = 4
_MAT_ENTRY_SIZE = 8


class MsgDataError(Exception):
    pass


def _entry_header_offset(msg_no: int) -> int:
    return _MAT_HEADER_SIZE + _MAT_ENTRY_SIZE * msg_no


def _xor_entry_header(raw_offset: int, raw_length: int, msg_no: int, key: int) -> tuple[int, int]:
    seed = (key * 765 * (msg_no + 1)) & 0xFFFF
    seed |= seed << 16
    return (raw_offset ^ seed) & 0xFFFFFFFF, (raw_length ^ seed) & 0xFFFFFFFF


def _xor_text(data: bytes, msg_no: int) -> bytes:
    seed = ((msg_no + 1) * 596947) & 0xFFFF
    out = bytearray(len(data))
    for i in range(0, len(data), 2):
        value = struct.unpack_from("<H", data, i)[0] ^ seed
        struct.pack_into("<H", out, i, value)
        seed = (seed + 18749) & 0xFFFF
    return bytes(out)


def read_message_text(rom: HeartGoldRom, subfile_index: int, msg_no: int) -> str:
    code_to_char = {code: char for char, code in CHARMAP.items()}
    narc = rom.read_narc(NITROFS_PATH)
    blob = narc.files[subfile_index]
    count, key = struct.unpack_from("<HH", blob, 0)
    if msg_no >= count:
        raise MsgDataError(f"message {msg_no} out of range (bank has {count} messages)")

    raw_offset, raw_length = struct.unpack_from("<II", blob, _entry_header_offset(msg_no))
    offset, length = _xor_entry_header(raw_offset, raw_length, msg_no, key)
    if length == 0:
        return ""
    if offset < 0 or offset + length * 2 > len(blob):
        raise MsgDataError(f"message {msg_no} has an out-of-bounds entry (offset={offset}, length={length})")

    text_bytes = _xor_text(blob[offset : offset + length * 2], msg_no)
    chars: list[str] = []
    for i in range(0, len(text_bytes), 2):
        code = struct.unpack_from("<H", text_bytes, i)[0]
        if code == _ENTRY_TERMINATOR:
            break
        chars.append(code_to_char.get(code, f"<{code:04X}>"))
    return "".join(chars)


def write_message_text(rom: HeartGoldRom, subfile_index: int, msg_no: int, text: str) -> None:
    try:
        codes = [CHARMAP[char] for char in text]
    except KeyError as exc:
        raise MsgDataError(f"character {exc.args[0]!r} has no data/charmap.py entry") from exc
    codes.append(_ENTRY_TERMINATOR)

    plain = bytearray(len(codes) * 2)
    for i, code in enumerate(codes):
        struct.pack_into("<H", plain, i * 2, code)

    narc = rom.read_narc(NITROFS_PATH)
    blob = bytearray(narc.files[subfile_index])
    count, key = struct.unpack_from("<HH", blob, 0)
    if msg_no >= count:
        raise MsgDataError(f"message {msg_no} out of range (bank has {count} messages)")

    new_offset = len(blob)
    new_length = len(codes)
    blob.extend(_xor_text(bytes(plain), msg_no))

    enc_offset, enc_length = _xor_entry_header(new_offset, new_length, msg_no, key)
    struct.pack_into("<II", blob, _entry_header_offset(msg_no), enc_offset, enc_length)

    narc.files[subfile_index] = bytes(blob)
    rom.write_narc(NITROFS_PATH, narc)


_NEWLINE_CODE = 0xE000


def _encode_text(text: str) -> bytes:
    codes = []
    for char in text:
        if char == "\n":
            codes.append(_NEWLINE_CODE)
        elif char in CHARMAP:
            codes.append(CHARMAP[char])
        else:
            raise MsgDataError(f"character {char!r} has no data/charmap.py entry")
    codes.append(_ENTRY_TERMINATOR)
    return struct.pack(f"<{len(codes)}H", *codes)


def append_messages(rom: HeartGoldRom, subfile_index: int, texts: list[str]) -> int:
    narc = rom.read_narc(NITROFS_PATH)
    blob = bytes(narc.files[subfile_index])
    count, key = struct.unpack_from("<HH", blob, 0)
    new_count = count + len(texts)
    if new_count > 0xFFFF:
        raise MsgDataError(f"a bank holds at most 65535 messages, not {new_count}")
    shift = _MAT_ENTRY_SIZE * len(texts)
    entries = [
        _xor_entry_header(*struct.unpack_from("<II", blob, _entry_header_offset(n)), n, key) for n in range(count)
    ]

    out = bytearray(struct.pack("<HH", new_count, key))
    out += bytes(_MAT_ENTRY_SIZE * new_count)
    out += blob[_entry_header_offset(count) :]
    for n, (offset, length) in enumerate(entries):
        struct.pack_into("<II", out, _entry_header_offset(n), *_xor_entry_header(offset + shift, length, n, key))
    for i, text in enumerate(texts):
        n = count + i
        plain = _encode_text(text)
        if len(out) % 2:
            out.append(0)
        offset = len(out)
        out += _xor_text(plain, n)
        struct.pack_into("<II", out, _entry_header_offset(n), *_xor_entry_header(offset, len(plain) // 2, n, key))

    narc.files[subfile_index] = bytes(out)
    rom.write_narc(NITROFS_PATH, narc)
    return count
