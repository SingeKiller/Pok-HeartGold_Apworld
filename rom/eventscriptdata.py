from __future__ import annotations

import struct

from rom import HeartGoldRom

NITROFS_PATH = "a/0/1/2"
SCR_SEQ_0141_INDEX = 141

HEADER_ENTRY_COUNT = 256
HEADER_SIZE = HEADER_ENTRY_COUNT * 4 + 2
SCRDEF_END_MARKER = 0xFD13
SCRDEF_END_OFFSET = HEADER_ENTRY_COUNT * 4

BLOCK_COUNT = 255
BLOCK_SIZE = 20
ITEM_ID_OPERAND_OFFSET = 4
QUANTITY_OPERAND_OFFSET = 10

BLOCK_INDEX_BY_ITEMBALL_FLAG_ID: dict[int, int] = {
    1081: 0,
    1056: 1,
    1088: 2,
    1057: 3,
    1058: 4,
    1059: 5,
    1060: 6,
    1061: 7,
    1062: 8,
    1063: 9,
    1064: 10,
    1146: 11,
    1147: 12,
    1128: 13,
    1129: 14,
    1130: 15,
    1131: 16,
    1132: 17,
    1133: 18,
    1134: 19,
    1135: 20,
    1136: 21,
    1137: 22,
    1138: 23,
    1139: 24,
    1140: 25,
    1141: 26,
    1142: 27,
    1143: 28,
    1065: 29,
    1066: 30,
    1273: 31,
    1239: 32,
    1067: 33,
    1068: 34,
    1069: 35,
    1070: 36,
    1071: 37,
    1072: 38,
    1082: 39,
    1083: 40,
    1075: 41,
    1076: 42,
    1077: 43,
    1084: 44,
    1085: 45,
    1086: 46,
    1087: 47,
    1274: 48,
    1078: 49,
    1079: 50,
    1094: 51,
    1090: 52,
    1091: 53,
    1092: 54,
    1093: 55,
    1095: 56,
    1096: 57,
    1200: 59,
    1089: 60,
    1097: 61,
    1275: 62,
    1144: 63,
    1145: 64,
    1286: 65,
    1276: 66,
    1291: 67,
    1073: 68,
    1074: 69,
    1148: 70,
    1149: 71,
    1150: 72,
    1151: 73,
    1152: 74,
    1153: 75,
    1154: 76,
    1155: 77,
    1156: 78,
    1157: 79,
    1158: 80,
    1159: 81,
    1277: 82,
    1278: 83,
    1279: 84,
    1310: 85,
    1160: 86,
    1098: 87,
    1099: 88,
    1100: 89,
    1101: 90,
    1266: 91,
    1161: 92,
    1162: 93,
    1163: 94,
    1164: 95,
    1165: 96,
    1166: 97,
    1167: 98,
    1168: 99,
    1169: 100,
    1170: 101,
    1171: 102,
    1267: 103,
    1281: 104,
    1282: 105,
    1283: 106,
    1284: 107,
    1172: 108,
    1193: 109,
    1285: 110,
    1173: 111,
    1174: 112,
    1175: 113,
    1176: 114,
    1177: 115,
    1178: 116,
    1179: 117,
    1180: 118,
    1181: 119,
    1194: 120,
    1195: 121,
    1182: 122,
    1183: 123,
    1184: 124,
    1185: 125,
    1186: 126,
    1187: 127,
    1188: 128,
    1189: 129,
    1190: 130,
    1191: 131,
    1192: 132,
    1102: 133,
    1103: 134,
    1104: 135,
    1105: 136,
    1106: 137,
    1107: 138,
    1108: 139,
    1109: 140,
    1196: 141,
    1198: 142,
    1288: 143,
    1289: 144,
    1290: 145,
    1201: 146,
    1202: 147,
    1203: 148,
    1111: 149,
    1204: 150,
    1205: 151,
    1206: 152,
    1207: 153,
    1208: 154,
    1110: 155,
    1209: 156,
    1210: 157,
    1211: 158,
    1112: 159,
    1212: 160,
    1213: 161,
    1214: 162,
    1215: 163,
    1216: 164,
    1217: 165,
    1113: 166,
    1114: 167,
    1218: 168,
    1219: 169,
    1220: 170,
    1221: 171,
    1292: 172,
    1116: 173,
    1117: 174,
    1118: 175,
    1293: 176,
    1115: 177,
    1119: 178,
    1120: 179,
    1121: 180,
    1122: 181,
    1123: 182,
    1124: 183,
    1125: 184,
    1126: 185,
    1127: 186,
    1294: 187,
    1295: 188,
    1297: 189,
    1298: 190,
    1299: 191,
    1287: 192,
    1300: 193,
    1222: 194,
    1223: 195,
    1224: 196,
    1225: 197,
    1226: 198,
    1296: 199,
    1301: 200,
    1302: 201,
    1303: 202,
    1304: 203,
    1227: 204,
    1197: 205,
    1305: 206,
    1228: 207,
    1229: 208,
    1230: 209,
    1306: 210,
    1307: 211,
    1232: 212,
    1233: 213,
    1234: 214,
    1235: 215,
    1237: 216,
    1238: 217,
    1308: 218,
    1309: 219,
    1240: 220,
    1236: 221,
    1251: 222,
    1256: 223,
    1252: 224,
    1253: 225,
    1254: 226,
    1255: 227,
    1258: 228,
    1199: 229,
    1280: 230,
    1231: 231,
    1241: 232,
    1242: 233,
    1243: 234,
    1244: 235,
    1245: 236,
    1246: 237,
    1247: 238,
    1248: 239,
    1249: 240,
    1250: 241,
    1257: 242,
    1259: 243,
    1260: 244,
    1261: 245,
    1262: 246,
    1263: 247,
    1264: 248,
    1265: 249,
    1268: 250,
    1269: 251,
    1270: 252,
    1271: 253,
    1272: 254,
}


class ScriptDataError(Exception):
    pass


def _block_offset(block_index: int) -> int:
    if not (0 <= block_index < BLOCK_COUNT):
        raise ValueError(
            f"block index {block_index} out of range -- scr_seq_0141.bin "
            f"only has {BLOCK_COUNT} per-itemball blocks (0..{BLOCK_COUNT - 1})."
        )
    return HEADER_SIZE + block_index * BLOCK_SIZE


def read_itemball_script_blob(rom: HeartGoldRom) -> bytes:
    return rom.read_narc(NITROFS_PATH).files[SCR_SEQ_0141_INDEX]


def write_itemball_script_blob(rom: HeartGoldRom, blob: bytes) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[SCR_SEQ_0141_INDEX] = blob
    rom.write_narc(NITROFS_PATH, narc)


def read_itemball_item_id(rom: HeartGoldRom, block_index: int) -> int:
    blob = read_itemball_script_blob(rom)
    offset = _block_offset(block_index) + ITEM_ID_OPERAND_OFFSET
    return struct.unpack_from("<H", blob, offset)[0]


def write_itemball_item_id(rom: HeartGoldRom, block_index: int, item_id: int) -> None:
    if not (0 <= item_id <= 0xFFFF):
        raise ValueError(
            f"item id {item_id} does not fit scr_seq_0141.bin's SetVar "
            "operand (an unsigned 16-bit value, 0-65535)."
        )
    blob = bytearray(read_itemball_script_blob(rom))
    offset = _block_offset(block_index) + ITEM_ID_OPERAND_OFFSET
    struct.pack_into("<H", blob, offset, item_id)
    write_itemball_script_blob(rom, bytes(blob))


def write_itemball_item_quantity(rom: HeartGoldRom, block_index: int, quantity: int) -> None:
    if not (0 <= quantity <= 0xFFFF):
        raise ValueError(
            f"quantity {quantity} does not fit scr_seq_0141.bin's SetVar "
            "operand (an unsigned 16-bit value, 0-65535)."
        )
    blob = bytearray(read_itemball_script_blob(rom))
    offset = _block_offset(block_index) + QUANTITY_OPERAND_OFFSET
    struct.pack_into("<H", blob, offset, quantity)
    write_itemball_script_blob(rom, bytes(blob))


def _resolve_ground_item_block_index(location_key: str) -> int:
    from data.locations import LOCATIONS

    location = LOCATIONS.get(location_key)
    if location is None:
        raise KeyError(f"unknown location key: {location_key!r}")
    if location["type"] not in ("ground_item", "hm_tm"):
        raise ScriptDataError(
            f"location {location_key!r} is type {location['type']!r}, not "
            "'ground_item'/'hm_tm' -- this module only patches itemball "
            "script blocks (hidden_item/npc_gift/badge are out of scope, "
            "see this task's own brief)."
        )
    block_index = BLOCK_INDEX_BY_ITEMBALL_FLAG_ID.get(location["id"])
    if block_index is None:
        if location["type"] == "hm_tm":
            raise ScriptDataError(
                f"location {location_key!r} (flag id {location['id']}) is a "
                "NPC-delivered hm_tm location, not an itemball -- use "
                "rom/npcgiftdata.py's write_npc_gift_substitution instead."
            )
        raise ScriptDataError(
            f"location {location_key!r} (flag id {location['id']}) has no "
            "known scr_seq_0141.bin block -- see this module's docstring "
            "for the one documented gap (block 58/coin_case, which is not "
            "a ground_item location so should never reach here)."
        )
    return block_index


def write_ground_item_substitution(rom: HeartGoldRom, location_key: str, item_key: str) -> None:
    from data.items import ITEMS

    block_index = _resolve_ground_item_block_index(location_key)
    item = ITEMS.get(item_key)
    if item is None:
        raise KeyError(f"unknown item key: {item_key!r}")

    write_itemball_item_id(rom, block_index, item["id"])
    write_itemball_item_quantity(rom, block_index, 1)


def write_ground_item_empty(rom: HeartGoldRom, location_key: str, name_id: int = 0) -> None:
    block_index = _resolve_ground_item_block_index(location_key)
    write_itemball_item_id(rom, block_index, name_id)
    write_itemball_item_quantity(rom, block_index, 0)
