# rom/msgdata.py
#
# Read/write access to HGSS's message-archive ("MAT", Message Archive
# Table) binary format (task "Replace the ??? placeholder", 2026-08-15).
# `src/msgdata.c`/`src/item.c` document the real, decomp-verified pipeline:
# `GetItemNameIntoString(dest, itemId, heap)` loads `NARC_msgdata_msg` file
# `NARC_msg_msg_0222_bin` and reads message index `itemId` from it --
# msg_0222 is HGSS's own item-name table, one entry per item id (537
# entries, 0..536, decomp source: files/msgdata/msg/msg_0222.gmm, entry 0 =
# "None", entry 1 = "Master Ball", etc. -- cross-checked against
# data/items.py's own id numbering, zero mismatch).
#
# Real NitroFS location: the decomp's own source folder is
# files/msgdata/msg.narc, but the shipped ROM's real file table has no
# path preserving that name (only a handful of top-level folders keep
# symbolic names at all -- most NitroFS content, this narc included, lives
# under a generic "a/N/X/Y" bucket path). Located by scanning every such
# bucket path for a sub-file whose message count is exactly 537 and whose
# entries 0/1 decode to "None"/"Master Ball" -- confirmed unique match at
# NITROFS_PATH below, sub-file ITEM_NAMES_SUBFILE_INDEX.
#
# Every "msg_NNNN" bank the decomp names (src/*.c's own
# NARC_msg_msg_NNNN_bin constants) lives as sub-file NNNN of this exact
# same narc -- confirmed for msg_0190 (STARTER_SELECTION_SUBFILE_INDEX
# below, the starter-choice screen's own text bank, used by
# choose_starter_app.c) by reading sub-file 190 directly off the real ROM
# and finding CHIKORITA/CYNDAQUIL/TOTODILE in the decoded text, no
# separate exhaustive scan needed a second time.
#
# -- Binary format (src/msgdata.c) -------------------------------------------
#
# One MAT blob (msg_0222 itself, i.e. narc.files[ITEM_NAMES_SUBFILE_INDEX])
# is:
#   offset 0x00  u16 count   -- number of messages in this bank
#   offset 0x02  u16 key     -- per-bank XOR key, used below
#   offset 0x04  count * 8-byte MAT_ENTRY {u32 offset, u32 length} table,
#                one per message, in message-index order
#   (padding/alignment, then) the actual message text data, u16-per-
#                character, referenced by each entry's (offset, length)
#
# Every MAT_ENTRY is XOR-"encrypted" in place (Decrypt1 in src/msgdata.c):
#   seed = (key * 765 * (msg_no + 1)) & 0xFFFF; seed |= seed << 16
#   entry.offset ^= seed; entry.length ^= seed
# -- a full 32-bit XOR mask (the same 16 bits duplicated into both halves),
# applied to the RAW {offset, length} pair read straight off disk. Pure XOR
# is its own inverse, so the same formula both decrypts and (re-)encrypts.
#
# Once decrypted, the message's own text bytes (length * 2 bytes, u16 per
# character) are read from `offset` (relative to the start of this same
# blob) and are THEMSELVES separately XOR-"encrypted" (Decrypt2):
#   seed = (u16)((msg_no + 1) * 596947)
#   for each u16 character: character ^= seed; seed += 18749
# again fully reversible by re-running the same loop. Character codes are
# HGSS's own internal charmap (data/charmap.py, extracted from the
# decomp's own charmap.txt), NOT ASCII/UTF-16 -- 0xFFFF terminates a
# message's real text.
#
# -- Editing strategy ---------------------------------------------------------
#
# write_message_text below never disturbs any *other* entry's data: the
# new (already-XOR-"encrypted") text bytes are always appended to the end
# of the blob, and only the target entry's own 8-byte {offset, length}
# pair is rewritten (re-XORed the same way) to point at the new location --
# regardless of whether the new text is longer or shorter than whatever
# was there before. This trades a few bytes of orphaned (now-unreferenced)
# old text data for a much simpler, lower-risk edit than relocating/
# compacting the whole table.

from __future__ import annotations

import struct

from data.charmap import CHARMAP
from rom import HeartGoldRom

NITROFS_PATH = "a/0/2/7"
ITEM_NAMES_SUBFILE_INDEX = 222
STARTER_SELECTION_SUBFILE_INDEX = 190

_ENTRY_TERMINATOR = 0xFFFF
_MAT_HEADER_SIZE = 4
_MAT_ENTRY_SIZE = 8


class MsgDataError(Exception):
    """Base class for every error this module raises."""


def _entry_header_offset(msg_no: int) -> int:
    return _MAT_HEADER_SIZE + _MAT_ENTRY_SIZE * msg_no


def _xor_entry_header(raw_offset: int, raw_length: int, msg_no: int, key: int) -> tuple[int, int]:
    """Decrypt1 -- see this module's own docstring. Symmetric: also used
    to (re-)encrypt a new entry header before writing it back."""
    seed = (key * 765 * (msg_no + 1)) & 0xFFFF
    seed |= seed << 16
    return (raw_offset ^ seed) & 0xFFFFFFFF, (raw_length ^ seed) & 0xFFFFFFFF


def _xor_text(data: bytes, msg_no: int) -> bytes:
    """Decrypt2 -- see this module's own docstring. Symmetric: also used
    to (re-)encrypt new plaintext character codes before writing them."""
    seed = ((msg_no + 1) * 596947) & 0xFFFF
    out = bytearray(len(data))
    for i in range(0, len(data), 2):
        value = struct.unpack_from("<H", data, i)[0] ^ seed
        struct.pack_into("<H", out, i, value)
        seed = (seed + 18749) & 0xFFFF
    return bytes(out)


def read_message_text(rom: HeartGoldRom, subfile_index: int, msg_no: int) -> str:
    """Decode message `msg_no` from a MAT blob (e.g. msg_0222's item
    names) into a plain Python string, via data/charmap.py's own code ->
    character mapping. Characters with no charmap entry (out of this
    project's extracted ASCII-equivalent subset, e.g. Japanese kana) are
    rendered as <XXXX> placeholders rather than raising."""
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
    """Overwrite message `msg_no` in a MAT blob with `text`, encoded via
    data/charmap.py. Appends the new (encrypted) text to the end of the
    blob and rewrites only that one entry's own header -- see this
    module's own docstring for why every other entry is left untouched."""
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
