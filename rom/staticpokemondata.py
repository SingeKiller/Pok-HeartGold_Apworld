from __future__ import annotations

import struct
from typing import NamedTuple

from rom import HeartGoldRom, msgdata
from rom.eventscriptdata import NITROFS_PATH

SPECIES_NAME_BANK = 237
FOSSIL_OVERLAY = 21
FOSSIL_TABLE_OFFSET = 304
FOSSIL_ENTRY_SIZE = 4
FOSSIL_ITEM_IDS = (103, 101, 102, 99, 100, 104, 105)
MAX_NATIONAL_DEX = 493

_NEWLINE_CODE = 0xE000

OPERAND_PREFIXES: dict[str, bytes] = {
    "wild": struct.pack("<H", 589),
    "give": struct.pack("<H", 137),
    "cry": struct.pack("<H", 76),
    "preview": struct.pack("<H", 452),
    "set_temp": struct.pack("<HH", 41, 0x400A),
    "set_choice": struct.pack("<HH", 41, 0x8004),
    "cmp_choice": struct.pack("<HH", 17, 0x8004),
}


class StaticPokemonPatchError(Exception):
    pass


class TextEdit(NamedTuple):
    bank: int
    messages: tuple[int, ...]
    strip: str = ""


class StaticSite(NamedTuple):
    key: str
    label: str
    vanilla: str
    script: int | None
    ops: tuple[tuple[str, int], ...]
    texts: tuple[TextEdit, ...] = ()
    fossil: int | None = None


SITES: tuple[StaticSite, ...] = (
    StaticSite("mewtwo", "Mewtwo (Cerulean Cave)", "mewtwo", 11, (("cry", 45), ("wild", 57))),
    StaticSite("articuno", "Articuno (Seafoam Islands)", "articuno", 14, (("cry", 45), ("wild", 57))),
    StaticSite("moltres", "Moltres (Mt. Silver)", "moltres", 106, (("cry", 45), ("wild", 57))),
    StaticSite(
        "zapdos", "Zapdos (Route 10)", "zapdos", 191, (("cry", 617), ("wild", 629)), (TextEdit(341, (7,)),)
    ),
    StaticSite("suicune_burned_tower", "Suicune (Burned Tower)", "suicune", 24, (("cry", 786), ("wild", 798))),
    StaticSite("suicune_route_25", "Suicune (Route 25)", "suicune", 216, (("cry", 1766), ("wild", 1798))),
    StaticSite("lapras", "Lapras (Union Cave)", "lapras", 58, (("cry", 95), ("wild", 107))),
    StaticSite("electrode_1", "Electrode 1 (Rocket HQ)", "electrode", 90, (("wild", 1922),)),
    StaticSite("electrode_2", "Electrode 2 (Rocket HQ)", "electrode", 90, (("wild", 2022),)),
    StaticSite("electrode_3", "Electrode 3 (Rocket HQ)", "electrode", 90, (("wild", 2122),)),
    StaticSite(
        "snorlax_route_11",
        "Snorlax (Route 11)",
        "snorlax",
        197,
        (("cry", 106), ("wild", 123)),
        (TextEdit(346, (3,)),),
    ),
    StaticSite(
        "snorlax_route_12",
        "Snorlax (Route 12)",
        "snorlax",
        199,
        (("cry", 616), ("wild", 633)),
        (TextEdit(348, (3,)),),
    ),
    StaticSite("sudowoodo", "Sudowoodo (Route 36)", "sudowoodo", 243, (("wild", 329), ("wild", 763))),
    StaticSite(
        "red_gyarados",
        "Red Gyarados (Lake of Rage)",
        "gyarados",
        938,
        (("cry", 971), ("wild", 988)),
        (TextEdit(626, (0,)),),
    ),
    StaticSite(
        "rayquaza",
        "Rayquaza (Embedded Tower)",
        "rayquaza",
        135,
        (("cry", 96), ("cry", 150), ("cry", 216), ("wild", 233)),
        (TextEdit(150, (0, 1, 2)),),
    ),
    StaticSite(
        "lugia",
        "Lugia (Whirl Islands)",
        "lugia",
        104,
        (("set_temp", 260),),
        (TextEdit(125, (4,)),),
    ),
    StaticSite(
        "latios",
        "Latios (Pewter City)",
        "latios",
        750,
        (("set_temp", 1203),),
        (TextEdit(460, (6, 8, 10, 12, 16)),),
    ),
    StaticSite(
        "latias",
        "Latias (Pewter City)",
        "latias",
        750,
        (("set_temp", 1224),),
        (TextEdit(460, (7, 9, 11, 13, 17)),),
    ),
    StaticSite(
        "tyrogue", "Tyrogue (Mt. Mortar)", "tyrogue", 98, (("give", 111),), (TextEdit(121, (2, 3, 5)),)
    ),
    StaticSite(
        "dratini", "Dratini (Dragon's Den)", "dratini", 112, (("give", 1231),), (TextEdit(130, (26, 27, 32)),)
    ),
    StaticSite(
        "eevee", "Eevee (Bill's House)", "eevee", 892, (("give", 95),), (TextEdit(586, (0, 2, 3, 7)),)
    ),
    StaticSite(
        "tentacool",
        "Tentacool (Cianwood Pokecenter)",
        "tentacool",
        878,
        (("give", 142),),
        (TextEdit(575, (4, 5, 6)),),
    ),
    StaticSite(
        "kanto_bulbasaur",
        "Bulbasaur (Prof. Oak)",
        "bulbasaur",
        740,
        (("preview", 1645), ("cry", 1651), ("set_choice", 1681), ("cmp_choice", 2068), ("cmp_choice", 2232)),
        (TextEdit(451, (45,), "Grass "),),
    ),
    StaticSite(
        "kanto_charmander",
        "Charmander (Prof. Oak)",
        "charmander",
        740,
        (("preview", 1993), ("cry", 1999), ("set_choice", 2029)),
        (TextEdit(451, (43,), "Fire "),),
    ),
    StaticSite(
        "kanto_squirtle",
        "Squirtle (Prof. Oak)",
        "squirtle",
        740,
        (("preview", 1819), ("cry", 1825), ("set_choice", 1855), ("cmp_choice", 2095), ("cmp_choice", 2259)),
        (TextEdit(451, (44,), "Water "),),
    ),
    StaticSite("hoenn_treecko", "Treecko (Steven)", "treecko", 837, (("set_choice", 651),)),
    StaticSite("hoenn_torchic", "Torchic (Steven)", "torchic", 837, (("set_choice", 676),)),
    StaticSite("hoenn_mudkip", "Mudkip (Steven)", "mudkip", 837, (("set_choice", 688),)),
    StaticSite("fossil_old_amber", "Old Amber revival", "aerodactyl", None, (), fossil=0),
    StaticSite("fossil_helix", "Helix Fossil revival", "omanyte", None, (), fossil=1),
    StaticSite("fossil_dome", "Dome Fossil revival", "kabuto", None, (), fossil=2),
    StaticSite("fossil_root", "Root Fossil revival", "lileep", None, (), fossil=3),
    StaticSite("fossil_claw", "Claw Fossil revival", "anorith", None, (), fossil=4),
    StaticSite("fossil_armor", "Armor Fossil revival", "shieldon", None, (), fossil=5),
    StaticSite("fossil_skull", "Skull Fossil revival", "cranidos", None, (), fossil=6),
)

SITE_KEYS: tuple[str, ...] = tuple(site.key for site in SITES)
SITES_BY_KEY: dict[str, StaticSite] = {site.key: site for site in SITES}


def species_name_codes(rom: HeartGoldRom, raw_index: int) -> list[int]:
    return msgdata.read_message_codes(rom, SPECIES_NAME_BANK, raw_index)


def _phrase_codes(text: str) -> list[int]:
    from data.charmap import CHARMAP

    return [_NEWLINE_CODE if char == "\n" else CHARMAP[char] for char in text]


def _replace_run(codes: list[int], old: list[int], new: list[int]) -> tuple[list[int], int]:
    out: list[int] = []
    count = 0
    index = 0
    while index < len(codes):
        if old and codes[index : index + len(old)] == old:
            out.extend(new)
            index += len(old)
            count += 1
        else:
            out.append(codes[index])
            index += 1
    return out, count


def _operand_offset(kind: str, instruction: int) -> int:
    return instruction + len(OPERAND_PREFIXES[kind])


def operand_offsets(site: StaticSite) -> list[int]:
    return [_operand_offset(kind, instruction) for kind, instruction in site.ops]


def _raw_index(species_key: str) -> int:
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    raw = SPECIES_KEY_TO_RAW_INDEX[species_key]
    if not 1 <= raw <= MAX_NATIONAL_DEX:
        raise StaticPokemonPatchError(f"species {species_key} (raw {raw}) is outside the National Dex")
    return raw


def read_site_species(rom: HeartGoldRom) -> dict[str, int]:
    narc = rom.read_narc(NITROFS_PATH)
    overlay = rom.read_overlay(FOSSIL_OVERLAY)
    result: dict[str, int] = {}
    for site in SITES:
        if site.fossil is not None:
            offset = FOSSIL_TABLE_OFFSET + site.fossil * FOSSIL_ENTRY_SIZE + 2
            result[site.key] = struct.unpack_from("<H", overlay, offset)[0]
        else:
            data = narc.files[site.script]
            kind, instruction = site.ops[0]
            result[site.key] = struct.unpack_from("<H", data, _operand_offset(kind, instruction))[0]
    return result


def _check_op(data: bytes, site: StaticSite, kind: str, instruction: int, vanilla_raw: int) -> int:
    prefix = OPERAND_PREFIXES[kind]
    if data[instruction : instruction + len(prefix)] != prefix:
        raise StaticPokemonPatchError(f"{site.key}: no {kind} instruction at offset {instruction} of script {site.script}")
    offset = instruction + len(prefix)
    (current,) = struct.unpack_from("<H", data, offset)
    if current != vanilla_raw:
        raise StaticPokemonPatchError(
            f"{site.key}: expected species {vanilla_raw} at offset {offset} of script {site.script}, found {current}"
        )
    return offset


def _write_script_sites(rom: HeartGoldRom, chosen: dict[StaticSite, int]) -> None:
    narc = rom.read_narc(NITROFS_PATH)
    blobs: dict[int, bytearray] = {}
    for site, new_raw in chosen.items():
        if site.fossil is not None:
            continue
        vanilla_raw = _raw_index(site.vanilla)
        blob = blobs.setdefault(site.script, bytearray(narc.files[site.script]))
        for kind, instruction in site.ops:
            offset = _check_op(bytes(blob), site, kind, instruction, vanilla_raw)
            struct.pack_into("<H", blob, offset, new_raw)
    for index, blob in blobs.items():
        narc.files[index] = bytes(blob)
    rom.write_narc(NITROFS_PATH, narc)


def _write_fossil_sites(rom: HeartGoldRom, chosen: dict[StaticSite, int]) -> None:
    fossils = {site: raw for site, raw in chosen.items() if site.fossil is not None}
    if not fossils:
        return
    overlay = bytearray(rom.read_overlay(FOSSIL_OVERLAY))
    for site, new_raw in fossils.items():
        base = FOSSIL_TABLE_OFFSET + site.fossil * FOSSIL_ENTRY_SIZE
        item_id, current = struct.unpack_from("<HH", overlay, base)
        if item_id != FOSSIL_ITEM_IDS[site.fossil] or current != _raw_index(site.vanilla):
            raise StaticPokemonPatchError(f"{site.key}: fossil table entry {site.fossil} is not where it should be")
        struct.pack_into("<H", overlay, base + 2, new_raw)
    rom.write_overlay(FOSSIL_OVERLAY, bytes(overlay))


def _write_texts(rom: HeartGoldRom, chosen: dict[StaticSite, int]) -> None:
    for site, new_raw in chosen.items():
        if site.fossil is not None:
            continue
        old_name = species_name_codes(rom, _raw_index(site.vanilla))
        new_name = species_name_codes(rom, new_raw)
        for edit in site.texts:
            strip = _phrase_codes(edit.strip) if edit.strip else []
            replaced: dict[int, list[int]] = {}
            for message in edit.messages:
                codes = msgdata.read_message_codes(rom, edit.bank, message)
                if strip:
                    codes, _ = _replace_run(codes, strip, [])
                codes, count = _replace_run(codes, old_name, new_name)
                if not count:
                    raise StaticPokemonPatchError(
                        f"{site.key}: message {message} of bank {edit.bank} does not name {site.vanilla}"
                    )
                replaced[message] = codes
            msgdata.replace_message_codes(rom, edit.bank, replaced)


def write_static_pokemon(rom: HeartGoldRom, assignments: dict[str, str]) -> None:
    unknown = sorted(set(assignments) - set(SITE_KEYS))
    if unknown:
        raise StaticPokemonPatchError(f"unknown static Pokemon sites: {', '.join(unknown)}")
    chosen = {SITES_BY_KEY[key]: _raw_index(species) for key, species in assignments.items()}
    if not chosen:
        return
    _write_script_sites(rom, chosen)
    _write_fossil_sites(rom, chosen)
    _write_texts(rom, chosen)
