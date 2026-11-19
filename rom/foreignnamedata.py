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
_HAS_SPACE_FOR_ITEM = 127
_PLAY_FANFARE = 78
_SET_VAR = 41
_SEQ_ME_ITEM = 1185
_BUFFER_PLAYERS_NAME = 190
_BUFFER_ITEM_NAME_PLURAL = 844
_BUFFER_ITEM_NAME_INDEF = 843

GIVE_ITEM = struct.pack("<HHHH", _GIVE_ITEM, _VAR_X8004, _VAR_X8005, _VAR_RESULT)
HAS_SPACE = struct.pack("<HHHH", _HAS_SPACE_FOR_ITEM, _VAR_X8004, _VAR_X8005, _VAR_RESULT)
GET_ITEM_POCKET = struct.pack("<HHH", 130, _VAR_X8004, _VAR_RESULT)
_NOOP = struct.pack("<H", 0)

NAME_CHARS_LIMIT = 63
BANK_BYTES_LIMIT = 0x42000

_ONE_LINE = 26
_FIRST_LINE = 18
_ITEM_MAX = 18
_PLAYER_MAX = 16
_PLAYER_SHORT = 10
_ARTICLES = ("a", "an", "some")

SPACE_CHECK_SITES: dict[int, tuple[int, ...]] = {
    15: (385,),
    25: (867,),
    30: (400,),
    31: (282,),
    32: (266,),
    61: (44,),
    92: (4546, 4726),
    108: (40,),
    111: (534,),
    157: (668,),
    161: (201,),
    171: (40,),
    172: (48,),
    183: (44,),
    202: (1574,),
    216: (1309,),
    222: (77,),
    224: (269,),
    225: (227,),
    229: (338,),
    232: (301, 542),
    233: (100, 239),
    239: (50,),
    243: (1083,),
    246: (178,),
    250: (372,),
    256: (489,),
    741: (298,),
    743: (252,),
    752: (376,),
    760: (787,),
    776: (537,),
    778: (917,),
    782: (107,),
    786: (392,),
    800: (84,),
    809: (1883,),
    829: (270,),
    833: (40,),
    837: (317,),
    843: (1534, 1769),
    859: (306,),
    869: (322,),
    873: (135,),
    875: (115,),
    877: (187,),
    881: (106,),
    886: (464,),
    896: (433,),
    913: (474,),
    918: (76,),
    922: (423,),
    928: (1259, 1348),
    929: (85,),
    930: (190, 512),
    932: (330,),
    938: (756, 1071),
    939: (40,),
    941: (354,),
    943: (424,),
    962: (202,),
}


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
    out = struct.pack("<HH", _PLAY_FANFARE, _SEQ_ME_ITEM)
    out += struct.pack("<HBH", _BUFFER_ITEM_NAME_PLURAL, 0, _VAR_X8004)
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


def patch_space_site(data: bytes, site: int) -> bytes:
    if data[site : site + len(HAS_SPACE)] != HAS_SPACE:
        raise ForeignNameError(f"no `HasSpaceForItem VAR_SPECIAL_x8004, VAR_SPECIAL_x8005, VAR_SPECIAL_RESULT` at {site:#x}")
    out = bytearray(data)
    if len(out) % 2:
        out.append(0)
    routine = len(out)
    compare = struct.pack("<HHH", _COMPARE_VAR_TO_VALUE, _VAR_X8004, FIRST_NAME_ID)
    has_space = routine + len(compare) + 7
    back = has_space + len(HAS_SPACE)
    foreign = back + 6
    set_result = struct.pack("<HHH", _SET_VAR, _VAR_RESULT, 1)
    out += compare
    out += _goto_if_ge(routine + len(compare), foreign)
    out += HAS_SPACE
    out += _goto(back, site + len(HAS_SPACE))
    out += set_result
    out += _goto(foreign + len(set_result), site + len(HAS_SPACE))
    out[site : site + len(HAS_SPACE)] = _goto(site, routine) + _NOOP
    return bytes(out)


def patch_call_site(data: bytes, site: int, tail: bytes) -> bytes:
    opcode, rel = struct.unpack_from("<Hi", data, site)
    if opcode != _CALL:
        raise ForeignNameError(f"no `Call` at {site:#x}")
    target = site + 6 + rel
    out = bytearray(data)
    if len(out) % 2:
        out.append(0)
    routine = len(out)
    compare = struct.pack("<HHH", _COMPARE_VAR_TO_VALUE, _VAR_X8004, FIRST_NAME_ID)
    call_at = routine + len(compare) + 7
    jump_back = call_at + 6
    foreign = jump_back + 6
    out += compare
    out += _goto_if_ge(routine + len(compare), foreign)
    out += struct.pack("<Hi", _CALL, target - (call_at + 6))
    out += _goto(jump_back, site + 6)
    out += tail
    out[site : site + 6] = _goto(site, routine)
    return bytes(out)


def _first_after(data: bytes, pattern: bytes, start: int, what: str) -> int:
    site = data.find(pattern, start)
    if site < 0:
        raise ForeignNameError(f"no `{what}` after {start:#x}")
    return site


def _first_give_after(data: bytes, start: int) -> int:
    return _first_after(data, GIVE_ITEM, start, "GiveItem")


def _std_pocket_call_site(data: bytes, script: int) -> int:
    entry = scrdef_offsets(data)[script]
    opcode, rel = struct.unpack_from("<Hi", data, entry)
    if opcode != _CALL:
        raise ForeignNameError(f"std script {script} does not start with a Call")
    sub = entry + 2 + 4 + rel
    opcode, rel = struct.unpack_from("<Hi", data, sub)
    if opcode != _CALL:
        raise ForeignNameError(f"std script {script}'s routine does not start with a Call")
    pocket = sub + 6 + rel
    if data[pocket : pocket + len(GET_ITEM_POCKET)] != GET_ITEM_POCKET:
        raise ForeignNameError(f"std script {script}'s first Call does not start with `GetItemPocket VAR_SPECIAL_x8004`")
    if data[sub + 6 : sub + 6 + len(GIVE_ITEM)] != GIVE_ITEM:
        raise ForeignNameError(f"std script {script}'s routine does not give the item right after its first Call")
    return sub


def _common_sites(data: bytes, script: int, what: str) -> tuple[int, int]:
    start = scrdef_offsets(data)[script]
    space = _first_after(data, HAS_SPACE, start, f"HasSpaceForItem in {what}")
    give = _first_give_after(data, space)
    return space, give


def patch_item_routines(rom: HeartGoldRom) -> None:
    narc = rom.read_narc(NITROFS_PATH)

    balls = bytes(narc.files[ITEMBALL_FILE])
    space, give = _common_sites(balls, SCRIPT_ITEMBALL_COMMON, "the itemball script")
    balls = patch_give_site(balls, give, _found_tail(3, set_hidden_flag=False, release=True))
    narc.files[ITEMBALL_FILE] = patch_space_site(balls, space)

    hidden = bytes(narc.files[HIDDEN_ITEM_FILE])
    space, give = _common_sites(hidden, SCRIPT_HIDDEN_ITEM_COMMON, "the hidden item script")
    hidden = patch_give_site(hidden, give, _found_tail(3, set_hidden_flag=True, release=False))
    narc.files[HIDDEN_ITEM_FILE] = patch_space_site(hidden, space)

    std = bytes(narc.files[STD_SCRIPTS_FILE])
    for script in (SCRIPT_STD_OBTAIN_ITEM_VERBOSE, SCRIPT_STD_GIVE_ITEM_VERBOSE):
        std = patch_call_site(std, _std_pocket_call_site(std, script), _obtained_tail(25))
    narc.files[STD_SCRIPTS_FILE] = std

    for file_index, sites in SPACE_CHECK_SITES.items():
        data = bytes(narc.files[file_index])
        for site in sites:
            data = patch_space_site(data, site)
        narc.files[file_index] = data
    rom.write_narc(NITROFS_PATH, narc)


def clean_text(text: str, limit: int) -> str:
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
    item = clean_text(item, _ITEM_MAX)
    indefinite_item = clean_text(indefinite_item, _ONE_LINE) if indefinite_item else item
    if player is None:
        return item, indefinite_item, item
    player = clean_text(player, _PLAYER_MAX)
    plain = f"{item} for {player}"
    if len(plain) > _FIRST_LINE:
        plain = f"{item}\nfor {player}"
    one_line = f"{indefinite_item} for {player}"
    if len(one_line) > _ONE_LINE:
        short = player[:_PLAYER_SHORT].rstrip()
        one_line = f"{indefinite_item[: _ONE_LINE - 5 - len(short)].rstrip()} for {short}"
    return plain, one_line, plain


def check_name_budget(rom: HeartGoldRom, texts: list[tuple[str, str, str]]) -> None:
    if FIRST_NAME_ID + len(texts) - 1 > 0xFFFF:
        raise ForeignNameError(f"{len(texts)} names do not fit in the 16-bit item ids that start at {FIRST_NAME_ID}")
    for column, bank in ((1, msgdata.ITEM_NAMES_INDEF_SUBFILE_INDEX), (2, msgdata.ITEM_NAMES_PLURAL_SUBFILE_INDEX)):
        added = 0
        for row in texts:
            if len(row[column]) > NAME_CHARS_LIMIT:
                raise ForeignNameError(
                    f"the name {row[column]!r} is longer than the {NAME_CHARS_LIMIT} characters the script text buffer holds"
                )
            added += msgdata._MAT_ENTRY_SIZE + 2 * (len(row[column]) + 1) + 1
        size = len(rom.read_narc(msgdata.NITROFS_PATH).files[bank]) + added
        if size > BANK_BYTES_LIMIT:
            raise ForeignNameError(
                f"item-name bank {bank} would grow to {size} bytes, over the {BANK_BYTES_LIMIT} byte limit: "
                "turn foreign_item_names off or give fewer locations a name"
            )


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
    check_name_budget(rom, texts)
    firsts = {
        msgdata.append_messages(rom, bank, [t[column] for t in texts])
        for column, bank in ((1, msgdata.ITEM_NAMES_INDEF_SUBFILE_INDEX), (2, msgdata.ITEM_NAMES_PLURAL_SUBFILE_INDEX))
    }
    if firsts != {FIRST_NAME_ID}:
        raise ForeignNameError(f"item-name banks do not all hold {FIRST_NAME_ID} entries: {sorted(firsts)}")
    return {key: FIRST_NAME_ID + i for i, key in enumerate(keys)}
