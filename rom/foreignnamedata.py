from __future__ import annotations

import struct
import unicodedata

from data.charmap import CHARMAP
from rom import HeartGoldRom, msgdata
from rom.deathlinkdata import scrdef_offsets
from rom.eventscriptdata import NITROFS_PATH

FIRST_NAME_ID = 537

ITEMBALL_FILE = 141
HIDDEN_ITEM_FILE = 145
STD_SCRIPTS_FILE = 3
SCRIPT_ITEMBALL_COMMON = 255
SCRIPT_HIDDEN_ITEM_COMMON = 255
SCRIPT_STD_OBTAIN_ITEM_VERBOSE = 8
SCRIPT_STD_GIVE_ITEM_VERBOSE = 33

_VAR_X8004 = 0x8004
_VAR_X8005 = 0x8005
_VAR_X8006 = 0x8006
_VAR_RESULT = 0x800C

_END = 2
_COMPARE_VAR_TO_VALUE = 17
_GOTO = 22
_CALL = 26
_RETURN = 27
_GOTO_IF = 28
_GE = 4
_SET_FLAG_VAR = 33
_NPC_MSG = 45
_WAIT_BUTTON = 50
_CLOSE_MSG = 53
_WAIT_FANFARE = 79
_RELEASE_ALL = 97
_GIVE_ITEM = 125
_BUFFER_PLAYERS_NAME = 190
_BUFFER_ITEM_NAME_PLURAL = 844
_BUFFER_ITEM_NAME_INDEF = 843

GIVE_ITEM = struct.pack("<HHHH", _GIVE_ITEM, _VAR_X8004, _VAR_X8005, _VAR_RESULT)
_NOOP = struct.pack("<H", 0)

_ONE_LINE = 26
_FIRST_LINE = 18
_ITEM_MAX = 18
_PLAYER_MAX = 16
_PLAYER_SHORT = 10
_ARTICLES = ("a", "an", "some")


class ForeignNameError(Exception):
    pass


def _goto(source: int, target: int) -> bytes:
    return struct.pack("<Hi", _GOTO, target - (source + 2) - 4)


def _goto_if_ge(source: int, target: int) -> bytes:
    return struct.pack("<HBi", _GOTO_IF, _GE, target - (source + 3) - 4)


def _found_tail(msg_found: int, set_hidden_flag: bool, release: bool) -> bytes:
    out = struct.pack("<HB", _BUFFER_PLAYERS_NAME, 0)
    out += struct.pack("<HBH", _BUFFER_ITEM_NAME_INDEF, 1, _VAR_X8004)
    out += struct.pack("<HB", _NPC_MSG, msg_found)
    out += struct.pack("<H", _WAIT_FANFARE)
    if set_hidden_flag:
        out += struct.pack("<HH", _SET_FLAG_VAR, _VAR_X8006)
    out += struct.pack("<HH", _WAIT_BUTTON, _CLOSE_MSG)
    if release:
        out += struct.pack("<H", _RELEASE_ALL)
    return out + struct.pack("<H", _END)


def _obtained_tail(msg_obtained: int) -> bytes:
    out = struct.pack("<HBH", _BUFFER_ITEM_NAME_PLURAL, 0, _VAR_X8004)
    out += struct.pack("<HB", _NPC_MSG, msg_obtained)
    return out + struct.pack("<HHH", _WAIT_FANFARE, _WAIT_BUTTON, _RETURN)


def patch_give_site(data: bytes, site: int, tail: bytes) -> bytes:
    if data[site : site + len(GIVE_ITEM)] != GIVE_ITEM:
        raise ForeignNameError(f"no `GiveItem VAR_SPECIAL_x8004, VAR_SPECIAL_x8005, VAR_SPECIAL_RESULT` at {site:#x}")
    out = bytearray(data)
    if len(out) % 2:
        out.append(0)
    routine = len(out)
    compare = struct.pack("<HHH", _COMPARE_VAR_TO_VALUE, _VAR_X8004, FIRST_NAME_ID)
    jump_back = routine + len(compare) + 7 + len(GIVE_ITEM)
    foreign = jump_back + 6
    out += compare
    out += _goto_if_ge(routine + len(compare), foreign)
    out += GIVE_ITEM
    out += _goto(jump_back, site + len(GIVE_ITEM))
    out += tail
    out[site : site + len(GIVE_ITEM)] = _goto(site, routine) + _NOOP
    return bytes(out)


def _first_give_after(data: bytes, start: int) -> int:
    site = data.find(GIVE_ITEM, start)
    if site < 0:
        raise ForeignNameError(f"no `GiveItem` after {start:#x}")
    return site


def _std_give_site(data: bytes, script: int) -> int:
    entry = scrdef_offsets(data)[script]
    opcode, rel = struct.unpack_from("<Hi", data, entry)
    if opcode != _CALL:
        raise ForeignNameError(f"std script {script} does not start with a Call")
    sub = entry + 2 + 4 + rel
    if struct.unpack_from("<H", data, sub)[0] != _CALL:
        raise ForeignNameError(f"std script {script}'s routine does not start with a Call")
    return sub + 6


def patch_item_routines(rom: HeartGoldRom) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    balls = bytes(narc.files[ITEMBALL_FILE])
    site = _first_give_after(balls, scrdef_offsets(balls)[SCRIPT_ITEMBALL_COMMON])
    narc.files[ITEMBALL_FILE] = patch_give_site(balls, site, _found_tail(3, set_hidden_flag=False, release=True))

    hidden = bytes(narc.files[HIDDEN_ITEM_FILE])
    site = _first_give_after(hidden, scrdef_offsets(hidden)[SCRIPT_HIDDEN_ITEM_COMMON])
    narc.files[HIDDEN_ITEM_FILE] = patch_give_site(hidden, site, _found_tail(3, set_hidden_flag=True, release=False))

    std = bytes(narc.files[STD_SCRIPTS_FILE])
    for script in (SCRIPT_STD_OBTAIN_ITEM_VERBOSE, SCRIPT_STD_GIVE_ITEM_VERBOSE):
        std = patch_give_site(std, _std_give_site(std, script), _obtained_tail(25))
    narc.files[STD_SCRIPTS_FILE] = std
    rom.write_narc(NITROFS_PATH, narc)


def _clean(text: str, limit: int) -> str:
    out = []
    for char in text.replace("_", " ").strip():
        if char in CHARMAP:
            out.append(char)
            continue
        plain = "".join(c for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c))
        out.extend(c if c in CHARMAP else "?" for c in plain or "?")
    cleaned = " ".join("".join(out).split())
    return cleaned[:limit].rstrip() or "?"


def name_texts(item: str, player: str | None, indefinite_item: str | None = None) -> tuple[str, str, str]:
    item = _clean(item, _ITEM_MAX)
    indefinite_item = _clean(indefinite_item, _ONE_LINE) if indefinite_item else item
    if player is None:
        return item, indefinite_item, item
    player = _clean(player, _PLAYER_MAX)
    plain = f"{item} for {player}"
    if len(plain) > _FIRST_LINE:
        plain = f"{item}\nfor {player}"
    one_line = f"{indefinite_item} for {player}"
    if len(one_line) > _ONE_LINE:
        short = player[:_PLAYER_SHORT].rstrip()
        one_line = f"{indefinite_item[: _ONE_LINE - 5 - len(short)].rstrip()} for {short}"
    return plain, one_line, plain


def write_foreign_names(rom: HeartGoldRom, names: dict[str, tuple]) -> dict[str, int]:
    if not names:
        return {}
    keys = sorted(names)

    def texts_for(item: str, player: str | None, native_id: int | None = None) -> tuple[str, str, str]:
        if native_id is not None and 0 < native_id < FIRST_NAME_ID:
            plain = msgdata.read_message_text(rom, msgdata.ITEM_NAMES_SUBFILE_INDEX, native_id)
            article = msgdata.read_message_text(rom, msgdata.ITEM_NAMES_INDEF_SUBFILE_INDEX, native_id).split(" ")[0]
            indefinite = f"{article} {plain}" if article in _ARTICLES else plain
            return name_texts(plain, player, indefinite)
        return name_texts(item, player)

    texts = [texts_for(*names[key]) for key in keys]
    firsts = {
        msgdata.append_messages(rom, bank, [t[column] for t in texts])
        for column, bank in ((1, msgdata.ITEM_NAMES_INDEF_SUBFILE_INDEX), (2, msgdata.ITEM_NAMES_PLURAL_SUBFILE_INDEX))
    }
    if firsts != {FIRST_NAME_ID}:
        raise ForeignNameError(f"item-name banks do not all hold {FIRST_NAME_ID} entries: {sorted(firsts)}")
    patch_item_routines(rom)
    return {key: FIRST_NAME_ID + i for i, key in enumerate(keys)}
