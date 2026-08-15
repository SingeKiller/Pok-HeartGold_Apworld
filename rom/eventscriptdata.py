# rom/eventscriptdata.py
#
# Read/write access to the shared item-ball script bank: the one NARC
# sub-file, scr_seq_0141.bin, that every "std_itemball_*" object in the
# game runs when the player picks it up. Local-item substitution is a
# plain NitroFS data edit, no ARM hook needed.
#
# NitroFS path a/0/1/2 (arc_strip_name) verified readable against the
# real ROM: parses as a NARC with 965 sub-files, one per scr_seq_NNNN.s
# source file, in filename-sorted (== index) order.
#
# scr_seq_0141.bin binary format (derived from the decomp source plus
# asm/macros/script.inc's macro bodies, cross-checked byte-for-byte
# against the real ROM -- see NOTES.md for the full byte layout).
#
# Which of the 255 blocks belongs to which Archipelago location is not
# recoverable from data_gen/locations.toml alone -- see NOTES.md for how
# BLOCK_INDEX_BY_ITEMBALL_FLAG_ID below was derived and its one known gap
# (block 58, an NPC-delivered item mislabeled as an itemball scriptId).
#
# No dependency on data/ at import time -- write_ground_item_substitution,
# the one function that accepts data/locations.py/data/items.py keys,
# imports both lazily inside the function body.

from __future__ import annotations

import struct

from rom import HeartGoldRom

NITROFS_PATH = "a/0/1/2"
SCR_SEQ_0141_INDEX = 141

# 256 ScrDef entries (4 bytes each) + one ScrDefEnd marker (2 bytes).
HEADER_ENTRY_COUNT = 256
HEADER_SIZE = HEADER_ENTRY_COUNT * 4 + 2
SCRDEF_END_MARKER = 0xFD13
SCRDEF_END_OFFSET = HEADER_ENTRY_COUNT * 4

# scr_seq_0141_000 .. _254 -- the 255 fixed-size per-itemball blocks.
# scr_seq_0141_255 (the shared tail) is *not* one of these and is never
# touched by this module.
BLOCK_COUNT = 255
BLOCK_SIZE = 20
ITEM_ID_OPERAND_OFFSET = 4
QUANTITY_OPERAND_OFFSET = 10

# flag id (data/locations.py[location]['id'] for a ground_item location)
# -> scr_seq_0141.bin block index. See NOTES.md for the derivation and
# its one known gap (block 58).
BLOCK_INDEX_BY_ITEMBALL_FLAG_ID: dict[int, int] = {
    1081: 0,  # FLAG_HIDE_ITEMBALL_R29_POTION
    1056: 1,  # FLAG_HIDE_ITEMBALL_R30_ANTIDOTE
    1088: 2,  # FLAG_HIDE_ITEMBALL_R30_POTION
    1057: 3,  # FLAG_HIDE_ITEMBALL_R31_POTION
    1058: 4,  # FLAG_HIDE_ITEMBALL_R31_POKE_BALL
    1059: 5,  # FLAG_HIDE_ITEMBALL_T22_RARE_CANDY
    1060: 6,  # FLAG_HIDE_ITEMBALL_T22_PP_UP
    1061: 7,  # FLAG_HIDE_ITEMBALL_D15R0101_PARLYZ_HEAL
    1062: 8,  # FLAG_HIDE_ITEMBALL_D15R0102_X_ACCURACY
    1063: 9,  # FLAG_HIDE_ITEMBALL_D15R0103_POTION
    1064: 10,  # FLAG_HIDE_ITEMBALL_D15R0103_ESCAPE_ROPE
    1146: 11,  # FLAG_HIDE_ITEMBALL_D24R0101_POTION
    1147: 12,  # FLAG_HIDE_ITEMBALL_D24R0101_HYPER_POTION
    1128: 13,  # FLAG_HIDE_ITEMBALL_D24R0212_HEAL_POWDER
    1129: 14,  # FLAG_HIDE_ITEMBALL_D24R0212_ENERGYPOWDER
    1130: 15,  # FLAG_HIDE_ITEMBALL_D24R0212_ORAN_BERRY
    1131: 16,  # FLAG_HIDE_ITEMBALL_D24R0212_PECHA_BERRY
    1132: 17,  # FLAG_HIDE_ITEMBALL_D24R0213_HEAL_POWDER
    1133: 18,  # FLAG_HIDE_ITEMBALL_D24R0213_ENERGY_ROOT
    1134: 19,  # FLAG_HIDE_ITEMBALL_D24R0213_SITRUS_BERRY
    1135: 20,  # FLAG_HIDE_ITEMBALL_D24R0213_MOON_STONE
    1136: 21,  # FLAG_HIDE_ITEMBALL_D24R0215_STARDUST
    1137: 22,  # FLAG_HIDE_ITEMBALL_D24R0215_STAR_PIECE
    1138: 23,  # FLAG_HIDE_ITEMBALL_D24R0215_LEPPA_BERRY
    1139: 24,  # FLAG_HIDE_ITEMBALL_D24R0215_MYSTIC_WATER
    1140: 25,  # FLAG_HIDE_ITEMBALL_D24R0214_REVIVAL_HERB
    1141: 26,  # FLAG_HIDE_ITEMBALL_D24R0214_CHARCOAL
    1142: 27,  # FLAG_HIDE_ITEMBALL_D24R0214_LIFE_ORB
    1143: 28,  # FLAG_HIDE_ITEMBALL_D24R0214_LEPPA_BERRY
    1065: 29,  # FLAG_HIDE_ITEMBALL_R32_REPEL
    1066: 30,  # FLAG_HIDE_ITEMBALL_R32_GREAT_BALL
    1273: 31,  # FLAG_HIDE_ITEMBALL_R32_TM09
    1239: 32,  # FLAG_HIDE_ITEMBALL_R32_SHELL_BELL
    1067: 33,  # FLAG_HIDE_ITEMBALL_D25R0101_X_ATTACK
    1068: 34,  # FLAG_HIDE_ITEMBALL_D25R0101_GREAT_BALL
    1069: 35,  # FLAG_HIDE_ITEMBALL_D25R0101_POTION
    1070: 36,  # FLAG_HIDE_ITEMBALL_D25R0101_AWAKENING
    1071: 37,  # FLAG_HIDE_ITEMBALL_D25R0102_X_DEFENSE
    1072: 38,  # FLAG_HIDE_ITEMBALL_D25R0102_TM39
    1082: 39,  # FLAG_HIDE_ITEMBALL_D25R0103_ELIXIR
    1083: 40,  # FLAG_HIDE_ITEMBALL_D25R0103_HYPER_POTION
    1075: 41,  # FLAG_HIDE_ITEMBALL_D26R0102_SUPER_POTION
    1076: 42,  # FLAG_HIDE_ITEMBALL_D26R0103_TM18
    1077: 43,  # FLAG_HIDE_ITEMBALL_D36R0101_REVIVE
    1084: 44,  # FLAG_HIDE_ITEMBALL_D36R0101_X_ATTACK
    1085: 45,  # FLAG_HIDE_ITEMBALL_D36R0101_ANTIDOTE
    1086: 46,  # FLAG_HIDE_ITEMBALL_D36R0101_ETHER
    1087: 47,  # FLAG_HIDE_ITEMBALL_R34_NUGGET
    1274: 48,  # FLAG_HIDE_ITEMBALL_R34_TM63
    1078: 49,  # FLAG_HIDE_ITEMBALL_D37R0105_TM82
    1079: 50,  # FLAG_HIDE_ITEMBALL_D37R0105_MAX_ETHER
    1094: 51,  # FLAG_HIDE_ITEMBALL_D37R0105_ULTRA_BALL
    1090: 52,  # FLAG_HIDE_ITEMBALL_D37R0103_BURN_HEAL
    1091: 53,  # FLAG_HIDE_ITEMBALL_D37R0103_AMULET_COIN
    1092: 54,  # FLAG_HIDE_ITEMBALL_D37R0103_ETHER
    1093: 55,  # FLAG_HIDE_ITEMBALL_D37R0103_ULTRA_BALL
    1095: 56,  # FLAG_HIDE_ITEMBALL_D37R0104_FULL_HEAL
    1096: 57,  # FLAG_HIDE_ITEMBALL_D37R0104_SMOKE_BALL
    # 58: no ground_item location placed (orphan script, see module docstring) -- std_itemball_d37r0102_coin_case
    1200: 59,  # FLAG_HIDE_ITEMBALL_T25R1101_TM78
    1089: 60,  # FLAG_HIDE_ITEMBALL_D23R0104_ULTRA_BALL
    1097: 61,  # FLAG_HIDE_ITEMBALL_R35_TM66
    1275: 62,  # FLAG_HIDE_ITEMBALL_R35_PARLYZ_HEAL
    1144: 63,  # FLAG_HIDE_ITEMBALL_D22R0101_SOOTHE_BELL
    1145: 64,  # FLAG_HIDE_ITEMBALL_D22R0101_TM28
    1286: 65,  # FLAG_HIDE_ITEMBALL_D22R0101_SHINY_STONE
    1276: 66,  # FLAG_HIDE_ITEMBALL_R36_HYPER_POTION
    1291: 67,  # FLAG_HIDE_ITEMBALL_D18R0101_ANTIDOTE
    1073: 68,  # FLAG_HIDE_ITEMBALL_D18R0101_HP_UP
    1074: 69,  # FLAG_HIDE_ITEMBALL_D18R0102_TM12
    1148: 70,  # FLAG_HIDE_ITEMBALL_D17R0103_FULL_HEAL
    1149: 71,  # FLAG_HIDE_ITEMBALL_D17R0104_ESCAPE_ROPE
    1150: 72,  # FLAG_HIDE_ITEMBALL_D17R0104_ULTRA_BALL
    1151: 73,  # FLAG_HIDE_ITEMBALL_D17R0104_PP_UP
    1152: 74,  # FLAG_HIDE_ITEMBALL_D17R0105_RARE_CANDY
    1153: 75,  # FLAG_HIDE_ITEMBALL_D17R0106_MAX_POTION
    1154: 76,  # FLAG_HIDE_ITEMBALL_D17R0106_FULL_HEAL
    1155: 77,  # FLAG_HIDE_ITEMBALL_D17R0107_MAX_REVIVE
    1156: 78,  # FLAG_HIDE_ITEMBALL_D17R0108_FULL_RESTORE
    1157: 79,  # FLAG_HIDE_ITEMBALL_D17R0108_MAX_ELIXIR
    1158: 80,  # FLAG_HIDE_ITEMBALL_D17R0108_NUGGET
    1159: 81,  # FLAG_HIDE_ITEMBALL_D17R0109_HP_UP
    1277: 82,  # FLAG_HIDE_ITEMBALL_R38_MAX_POTION
    1278: 83,  # FLAG_HIDE_ITEMBALL_R38_LAX_INCENSE
    1279: 84,  # FLAG_HIDE_ITEMBALL_R39_TM60
    1310: 85,  # FLAG_HIDE_ITEMBALL_T26_TM57
    1160: 86,  # FLAG_HIDE_ITEMBALL_D27R0103_RARE_CANDY
    1098: 87,  # FLAG_HIDE_ITEMBALL_D27R0104_ETHER
    1099: 88,  # FLAG_HIDE_ITEMBALL_D27R0105_TM87
    1100: 89,  # FLAG_HIDE_ITEMBALL_D27R0106_SUPER_REPEL
    1101: 90,  # FLAG_HIDE_ITEMBALL_D27R0107_SUPER_POTION
    1266: 91,  # FLAG_HIDE_ITEMBALL_W40_TM88
    1161: 92,  # FLAG_HIDE_ITEMBALL_D40R0101_ULTRA_BALL
    1162: 93,  # FLAG_HIDE_ITEMBALL_D40R0101_ULTRA_BALL_2
    1163: 94,  # FLAG_HIDE_ITEMBALL_D40R0102_ESCAPE_ROPE
    1164: 95,  # FLAG_HIDE_ITEMBALL_D40R0102_CARBOS
    1165: 96,  # FLAG_HIDE_ITEMBALL_D40R0102_FULL_RESTORE
    1166: 97,  # FLAG_HIDE_ITEMBALL_D40R0102_NUGGET
    1167: 98,  # FLAG_HIDE_ITEMBALL_D40R0102_CALCIUM
    1168: 99,  # FLAG_HIDE_ITEMBALL_D40R0104_MAX_REVIVE
    1169: 100,  # FLAG_HIDE_ITEMBALL_D40R0104_FULL_RESTORE
    1170: 101,  # FLAG_HIDE_ITEMBALL_D40R0104_MAX_ELIXIR
    1171: 102,  # FLAG_HIDE_ITEMBALL_D40R0106_RARE_CANDY
    1267: 103,  # FLAG_HIDE_ITEMBALL_R47_REVIVE
    1281: 104,  # FLAG_HIDE_ITEMBALL_R47_LAGGING_TAIL
    1282: 105,  # FLAG_HIDE_ITEMBALL_R47_WAVE_INCENSE
    1283: 106,  # FLAG_HIDE_ITEMBALL_R47_WHITE_FLUTE
    1284: 107,  # FLAG_HIDE_ITEMBALL_R48_NUGGET
    1172: 108,  # FLAG_HIDE_ITEMBALL_R42_SUPER_POTION
    1193: 109,  # FLAG_HIDE_ITEMBALL_R42_DUBIOUS_DISC
    1285: 110,  # FLAG_HIDE_ITEMBALL_R42_TM65
    1173: 111,  # FLAG_HIDE_ITEMBALL_D38R0101_ETHER
    1174: 112,  # FLAG_HIDE_ITEMBALL_D38R0101_REVIVE
    1175: 113,  # FLAG_HIDE_ITEMBALL_D38R0102_ESCAPE_ROPE
    1176: 114,  # FLAG_HIDE_ITEMBALL_D38R0102_NUGGET
    1177: 115,  # FLAG_HIDE_ITEMBALL_D38R0102_IRON_BALL
    1178: 116,  # FLAG_HIDE_ITEMBALL_D38R0102_MAX_POTION
    1179: 117,  # FLAG_HIDE_ITEMBALL_D38R0102_IRON
    1180: 118,  # FLAG_HIDE_ITEMBALL_D38R0102_MAX_REVIVE
    1181: 119,  # FLAG_HIDE_ITEMBALL_D38R0102_ULTRA_BALL
    1194: 120,  # FLAG_HIDE_ITEMBALL_D38R0102_FULL_INCENSE
    1195: 121,  # FLAG_HIDE_ITEMBALL_D38R0102_PROTECTOR
    1182: 122,  # FLAG_HIDE_ITEMBALL_D38R0103_RARE_CANDY
    1183: 123,  # FLAG_HIDE_ITEMBALL_D38R0103_MAX_POTION
    1184: 124,  # FLAG_HIDE_ITEMBALL_D38R0103_TM40
    1185: 125,  # FLAG_HIDE_ITEMBALL_D38R0103_ELIXIR
    1186: 126,  # FLAG_HIDE_ITEMBALL_D38R0103_DRAGON_SCALE
    1187: 127,  # FLAG_HIDE_ITEMBALL_D38R0103_ESCAPE_ROPE
    1188: 128,  # FLAG_HIDE_ITEMBALL_D38R0104_CARBOS
    1189: 129,  # FLAG_HIDE_ITEMBALL_D38R0104_PP_UP
    1190: 130,  # FLAG_HIDE_ITEMBALL_D38R0104_FULL_RESTORE
    1191: 131,  # FLAG_HIDE_ITEMBALL_D38R0104_MAX_ETHER
    1192: 132,  # FLAG_HIDE_ITEMBALL_D38R0104_HYPER_POTION
    1102: 133,  # FLAG_HIDE_ITEMBALL_D35R0102_HYPER_POTION
    1103: 134,  # FLAG_HIDE_ITEMBALL_D35R0102_GUARD_SPEC_
    1104: 135,  # FLAG_HIDE_ITEMBALL_D35R0102_NUGGET
    1105: 136,  # FLAG_HIDE_ITEMBALL_D35R0103_TM46
    1106: 137,  # FLAG_HIDE_ITEMBALL_D35R0104_TM49
    1107: 138,  # FLAG_HIDE_ITEMBALL_D35R0104_FULL_HEAL
    1108: 139,  # FLAG_HIDE_ITEMBALL_D35R0104_PROTEIN
    1109: 140,  # FLAG_HIDE_ITEMBALL_D35R0104_X_SPECIAL
    1196: 141,  # FLAG_HIDE_ITEMBALL_D35R0104_ULTRA_BALL
    1198: 142,  # FLAG_HIDE_ITEMBALL_R43_MAX_ETHER
    1288: 143,  # FLAG_HIDE_ITEMBALL_T29_TM43
    1289: 144,  # FLAG_HIDE_ITEMBALL_T29_CHOICE_SPECS
    1290: 145,  # FLAG_HIDE_ITEMBALL_T29_RED_FLUTE
    1201: 146,  # FLAG_HIDE_ITEMBALL_R44_MAX_REPEL
    1202: 147,  # FLAG_HIDE_ITEMBALL_R44_MAX_REVIVE
    1203: 148,  # FLAG_HIDE_ITEMBALL_R44_ULTRA_BALL
    1111: 149,  # FLAG_HIDE_ITEMBALL_D39R0101_HM07
    1204: 150,  # FLAG_HIDE_ITEMBALL_D39R0101_PROTEIN
    1205: 151,  # FLAG_HIDE_ITEMBALL_D39R0101_PP_UP
    1206: 152,  # FLAG_HIDE_ITEMBALL_D39R0103_FULL_HEAL
    1207: 153,  # FLAG_HIDE_ITEMBALL_D39R0103_MAX_POTION
    1208: 154,  # FLAG_HIDE_ITEMBALL_D39R0104_NEVERMELTICE
    1110: 155,  # FLAG_HIDE_ITEMBALL_D39R0103_TM72
    1209: 156,  # FLAG_HIDE_ITEMBALL_D39R0102_IRON
    1210: 157,  # FLAG_HIDE_ITEMBALL_D44R0102_CALCIUM
    1211: 158,  # FLAG_HIDE_ITEMBALL_D44R0102_MAX_ELIXIR
    1112: 159,  # FLAG_HIDE_ITEMBALL_D44R0102_DRAGON_FANG
    1212: 160,  # FLAG_HIDE_ITEMBALL_R45_ELIXIR
    1213: 161,  # FLAG_HIDE_ITEMBALL_R45_MAX_POTION
    1214: 162,  # FLAG_HIDE_ITEMBALL_R45_FULL_HEAL
    1215: 163,  # FLAG_HIDE_ITEMBALL_R45_NUGGET
    1216: 164,  # FLAG_HIDE_ITEMBALL_R45_REVIVE
    1217: 165,  # FLAG_HIDE_ITEMBALL_R46_X_SPEED
    1113: 166,  # FLAG_HIDE_ITEMBALL_D42R0101_TM54
    1114: 167,  # FLAG_HIDE_ITEMBALL_D42R0101_REVIVE
    1218: 168,  # FLAG_HIDE_ITEMBALL_D42R0102_POTION
    1219: 169,  # FLAG_HIDE_ITEMBALL_D42R0102_HYPER_POTION
    1220: 170,  # FLAG_HIDE_ITEMBALL_D42R0102_FULL_HEAL
    1221: 171,  # FLAG_HIDE_ITEMBALL_D42R0102_DIRE_HIT
    1292: 172,  # FLAG_HIDE_ITEMBALL_D42R0102_BLACK_FLUTE
    1116: 173,  # FLAG_HIDE_ITEMBALL_D45R0101_MOON_STONE
    1117: 174,  # FLAG_HIDE_ITEMBALL_R27_RARE_CANDY
    1118: 175,  # FLAG_HIDE_ITEMBALL_R27_TM02
    1293: 176,  # FLAG_HIDE_ITEMBALL_R27_DESTINY_KNOT
    1115: 177,  # FLAG_HIDE_ITEMBALL_R26_MAX_ELIXIR
    1119: 178,  # FLAG_HIDE_ITEMBALL_D43R0101_MAX_REVIVE
    1120: 179,  # FLAG_HIDE_ITEMBALL_D43R0101_FULL_HEAL
    1121: 180,  # FLAG_HIDE_ITEMBALL_D43R0101_POTION
    1122: 181,  # FLAG_HIDE_ITEMBALL_D43R0102_TM26
    1123: 182,  # FLAG_HIDE_ITEMBALL_D43R0102_HP_UP
    1124: 183,  # FLAG_HIDE_ITEMBALL_D43R0102_FULL_RESTORE
    1125: 184,  # FLAG_HIDE_ITEMBALL_D43R0103_ULTRA_BALL
    1126: 185,  # FLAG_HIDE_ITEMBALL_D43R0103_TM79
    1127: 186,  # FLAG_HIDE_ITEMBALL_D43R0103_RARE_CANDY
    1294: 187,  # FLAG_HIDE_ITEMBALL_T06_LUCK_INCENSE
    1295: 188,  # FLAG_HIDE_ITEMBALL_T06_STICKY_BARB
    1297: 189,  # FLAG_HIDE_ITEMBALL_D01R0101_PP_MAX
    1298: 190,  # FLAG_HIDE_ITEMBALL_D01R0101_ROCK_INCENSE
    1299: 191,  # FLAG_HIDE_ITEMBALL_R06_TM62
    1287: 192,  # FLAG_HIDE_ITEMBALL_R08_TM41
    1300: 193,  # FLAG_HIDE_ITEMBALL_R10R0101_TM69
    1222: 194,  # FLAG_HIDE_ITEMBALL_D05R0101_ELIXIR
    1223: 195,  # FLAG_HIDE_ITEMBALL_D05R0101_TM56
    1224: 196,  # FLAG_HIDE_ITEMBALL_D05R0102_IRON
    1225: 197,  # FLAG_HIDE_ITEMBALL_D05R0102_PP_UP
    1226: 198,  # FLAG_HIDE_ITEMBALL_D05R0102_REVIVE
    1296: 199,  # FLAG_HIDE_ITEMBALL_D05R0102_OVAL_STONE
    1301: 200,  # FLAG_HIDE_ITEMBALL_R09_TM91
    1302: 201,  # FLAG_HIDE_ITEMBALL_R09_FULL_RESTORE
    1303: 202,  # FLAG_HIDE_ITEMBALL_R09_LIGHT_CLAY
    1304: 203,  # FLAG_HIDE_ITEMBALL_R09_MAX_POTION
    1227: 204,  # FLAG_HIDE_ITEMBALL_R25_PROTEIN
    1197: 205,  # FLAG_HIDE_ITEMBALL_R07_MENTAL_HERB
    1305: 206,  # FLAG_HIDE_ITEMBALL_T07_TM67
    1228: 207,  # FLAG_HIDE_ITEMBALL_R12_CALCIUM
    1229: 208,  # FLAG_HIDE_ITEMBALL_R12_YELLOW_FLUTE
    1230: 209,  # FLAG_HIDE_ITEMBALL_R15_PP_UP
    1306: 210,  # FLAG_HIDE_ITEMBALL_R15_ROSE_INCENSE
    1307: 211,  # FLAG_HIDE_ITEMBALL_R11_TM86
    1232: 212,  # FLAG_HIDE_ITEMBALL_R02R0101_CARBOS
    1233: 213,  # FLAG_HIDE_ITEMBALL_R02_ELIXIR
    1234: 214,  # FLAG_HIDE_ITEMBALL_D46R0101_DIRE_HIT
    1235: 215,  # FLAG_HIDE_ITEMBALL_D46R0101_BLUE_FLUTE
    1237: 216,  # FLAG_HIDE_ITEMBALL_D46R0101_LEAF_STONE
    1238: 217,  # FLAG_HIDE_ITEMBALL_D46R0101_TM77
    1308: 218,  # FLAG_HIDE_ITEMBALL_T03_WISE_GLASSES
    1309: 219,  # FLAG_HIDE_ITEMBALL_R03_BIG_ROOT
    1240: 220,  # FLAG_HIDE_ITEMBALL_R04_HP_UP
    1236: 221,  # FLAG_HIDE_ITEMBALL_T09_MAGMARIZER
    1251: 222,  # FLAG_HIDE_ITEMBALL_D11R0102_ICE_HEAL
    1256: 223,  # FLAG_HIDE_ITEMBALL_D11R0102_GRIP_CLAW
    1252: 224,  # FLAG_HIDE_ITEMBALL_D11R0103_WATER_STONE
    1253: 225,  # FLAG_HIDE_ITEMBALL_D11R0104_REVIVE
    1254: 226,  # FLAG_HIDE_ITEMBALL_D11R0104_BIG_PEARL
    1255: 227,  # FLAG_HIDE_ITEMBALL_D11R0105_ULTRA_BALL
    1258: 228,  # FLAG_HIDE_ITEMBALL_D11R0105_TM13
    1199: 229,  # FLAG_HIDE_ITEMBALL_W19_TM55
    1280: 230,  # FLAG_HIDE_ITEMBALL_R28_TM35
    1231: 231,  # FLAG_HIDE_ITEMBALL_T31_REAPER_CLOTH
    1241: 232,  # FLAG_HIDE_ITEMBALL_D41R0101_FULL_RESTORE
    1242: 233,  # FLAG_HIDE_ITEMBALL_D41R0102_PURE_INCENSE
    1243: 234,  # FLAG_HIDE_ITEMBALL_D41R0102_DAWN_STONE
    1244: 235,  # FLAG_HIDE_ITEMBALL_D41R0103_ESCAPE_ROPE
    1245: 236,  # FLAG_HIDE_ITEMBALL_D41R0103_TM76
    1246: 237,  # FLAG_HIDE_ITEMBALL_D41R0104_EXPERT_BELT
    1247: 238,  # FLAG_HIDE_ITEMBALL_D41R0106_MAX_ELIXIR
    1248: 239,  # FLAG_HIDE_ITEMBALL_D41R0106_CALCIUM
    1249: 240,  # FLAG_HIDE_ITEMBALL_D41R0106_PROTEIN
    1250: 241,  # FLAG_HIDE_ITEMBALL_D41R0106_MAX_REVIVE
    1257: 242,  # FLAG_HIDE_ITEMBALL_D03R0101_MAX_ELIXIR
    1259: 243,  # FLAG_HIDE_ITEMBALL_D03R0101_FULL_RESTORE
    1260: 244,  # FLAG_HIDE_ITEMBALL_D03R0101_NUGGET
    1261: 245,  # FLAG_HIDE_ITEMBALL_D03R0101_SEA_INCENSE
    1262: 246,  # FLAG_HIDE_ITEMBALL_D03R0102_PP_UP
    1263: 247,  # FLAG_HIDE_ITEMBALL_D03R0102_ULTRA_BALL
    1264: 248,  # FLAG_HIDE_ITEMBALL_D03R0102_TM24
    1265: 249,  # FLAG_HIDE_ITEMBALL_D03R0102_ODD_INCENSE
    1268: 250,  # FLAG_HIDE_ITEMBALL_D03R0103_MAX_REVIVE
    1269: 251,  # FLAG_HIDE_ITEMBALL_D03R0103_ULTRA_BALL
    1270: 252,  # FLAG_HIDE_ITEMBALL_D03R0103_DUSK_STONE
    1271: 253,  # FLAG_HIDE_ITEMBALL_D03R0103_ELECTIRIZER
    1272: 254,  # FLAG_HIDE_ITEMBALL_D03R0103_BLACK_SLUDGE
}


class ScriptDataError(Exception):
    """Base class for every error this module raises."""


def _block_offset(block_index: int) -> int:
    if not (0 <= block_index < BLOCK_COUNT):
        raise ValueError(
            f"block index {block_index} out of range -- scr_seq_0141.bin "
            f"only has {BLOCK_COUNT} per-itemball blocks (0..{BLOCK_COUNT - 1})."
        )
    return HEADER_SIZE + block_index * BLOCK_SIZE


def read_itemball_script_blob(rom: HeartGoldRom) -> bytes:
    """Return the raw bytes of `scr_seq_0141.bin` (the shared item-ball
    script bank), unparsed."""
    return rom.read_narc(NITROFS_PATH).files[SCR_SEQ_0141_INDEX]


def write_itemball_script_blob(rom: HeartGoldRom, blob: bytes) -> None:
    """Replace scr_seq_0141.bin's raw bytes wholesale. Prefer
    write_itemball_item_id/write_ground_item_substitution for the common
    case of patching a single item-id operand."""
    narc = rom.read_narc(NITROFS_PATH)
    narc.files[SCR_SEQ_0141_INDEX] = blob
    rom.write_narc(NITROFS_PATH, narc)


def read_itemball_item_id(rom: HeartGoldRom, block_index: int) -> int:
    """Read the native item id a given itemball script block
    (`scr_seq_0141_<block_index:03d>`) currently grants."""
    blob = read_itemball_script_blob(rom)
    offset = _block_offset(block_index) + ITEM_ID_OPERAND_OFFSET
    return struct.unpack_from("<H", blob, offset)[0]


def write_itemball_item_id(rom: HeartGoldRom, block_index: int, item_id: int) -> None:
    """Overwrite a single itemball script block's item-id operand in
    place, leaving the rest of scr_seq_0141.bin byte-identical."""
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
    """Overwrite a single itemball script block's quantity operand in
    place, leaving the rest of scr_seq_0141.bin byte-identical. Must be
    paired with write_itemball_item_id whenever the item id changes --
    the vanilla quantity left in place otherwise still gets granted
    alongside the new item id (task M1.3)."""
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
    """Shared validation for write_ground_item_substitution/
    write_ground_item_empty: resolve location_key to its scr_seq_0141.bin
    block index, or raise."""
    from data.locations import LOCATIONS

    location = LOCATIONS.get(location_key)
    if location is None:
        raise KeyError(f"unknown location key: {location_key!r}")
    # hm_tm locations are accepted too, but only the itemball-shaped half
    # (whose flag id is a real block, see BLOCK_INDEX_BY_ITEMBALL_FLAG_ID)
    # -- the NPC-delivered half belongs to rom/npcgiftdata.py instead.
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
    """Patch the itemball script block for a ground_item location (or an
    itemball-shaped hm_tm location) so it grants a different item instead
    of its vanilla original_item. Also pins the quantity operand to 1 --
    an AP location grants exactly one of its placed item regardless of
    what quantity vanilla happened to give at that same spot (task M1.3;
    leaving the vanilla quantity in place would hand over e.g. 5 Master
    Balls if the original itemball there was a 5-Potion stack)."""
    from data.items import ITEMS

    block_index = _resolve_ground_item_block_index(location_key)
    item = ITEMS.get(item_key)
    if item is None:
        raise KeyError(f"unknown item key: {item_key!r}")

    write_itemball_item_id(rom, block_index, item["id"])
    write_itemball_item_quantity(rom, block_index, 1)


def write_ground_item_empty(rom: HeartGoldRom, location_key: str) -> None:
    """Patch the itemball script block for location_key so it grants item
    id 0 instead of its vanilla original_item -- for locations whose
    placed item belongs to another multiworld player. Live-verified:
    picking up an item id 0 itemball shows a garbled "Found ???!" message
    but adds nothing real to the Bag, while still setting the location's
    real vanilla savedata flag, so check-detection keeps working. Also
    zeroes the quantity operand (task M1.3): leaving the vanilla quantity
    in place produces a real, visible {id: 0, quantity: N} Bag slot once
    picked up (src/bag.c's Pocket_GetItemSlotForAdd matches the first
    id-0 slot and does `slot->quantity += N` unconditionally), a blank-
    named stack the player can see and move around."""
    block_index = _resolve_ground_item_block_index(location_key)
    write_itemball_item_id(rom, block_index, 0)
    write_itemball_item_quantity(rom, block_index, 0)
