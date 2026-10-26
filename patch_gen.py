#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from rom import HeartGoldRom
from rom import badgedata as rom_badgedata
from rom import badgegatedata as rom_badgegatedata
from rom import deathlinkdata as rom_deathlinkdata
from rom import encounterdata as rom_encounterdata
from rom import expshare as rom_expshare
from rom import foreignnamedata as rom_foreignnamedata
from rom import giftflagdata as rom_giftflagdata
from rom import eventscriptdata as rom_eventscriptdata
from rom import msgdata as rom_msgdata
from rom import newbarkexitdata as rom_newbarkexitdata
from rom import evodata as rom_evodata
from rom import hiddenitemdata as rom_hiddenitemdata
from rom import learnsetdata as rom_learnsetdata
from rom import lighthousedata as rom_lighthousedata
from rom import movedata as rom_movedata
from rom import npcgiftdata as rom_npcgiftdata
from rom import npcgiftgatedata as rom_npcgiftgatedata
from rom import speciesdata as rom_speciesdata
from rom import startlocation as rom_startlocation
from rom import starterdata as rom_starterdata
from rom import timedeventdata as rom_timedeventdata
from rom import tmhmdata as rom_tmhmdata
from rom import trainerdata as rom_trainerdata
from rom import typechart as rom_typechart
from rom import wingmonkdata as rom_wingmonkdata

ROOT = Path(__file__).resolve().parent
PATCH_SOURCE = ROOT / "patches" / "ground_item_hook.s"

ARMIPS_PATH_ENV_VAR = "ARMIPS_PATH"
_DEFAULT_ARMIPS_PATH = ROOT / "ressources" / "armips" / "build" / "armips.exe"

PROTOCOL_ADDRESS = 0x023FF800
PROTOCOL_STRUCT_SIZE = 0x14
PROTOCOL_MAGIC = b"HGAP"


class ArmipsError(Exception):
    pass


def armips_path() -> Path:
    raw = os.environ.get(ARMIPS_PATH_ENV_VAR)
    return Path(raw) if raw else _DEFAULT_ARMIPS_PATH


def assemble_ground_item_hook(hook_load_address: int, *, armips_exe: Path | None = None,
                               protocol_address: int = PROTOCOL_ADDRESS) -> bytes:
    exe = armips_exe or armips_path()
    if not exe.is_file():
        raise ArmipsError(
            f"armips executable not found at {exe} -- set {ARMIPS_PATH_ENV_VAR} to "
            "a valid armips build."
        )

    source = PATCH_SOURCE.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="heartgold_patch_gen_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        output_path = tmp_path / "ground_item_hook.bin"
        rendered = (
            source
            .replace("__OUTPUT_PATH__", output_path.as_posix())
            .replace("__HOOK_LOAD_ADDRESS__", f"0x{hook_load_address:08X}")
            .replace("__PROTOCOL_ADDRESS__", f"0x{protocol_address:08X}")
        )
        source_path = tmp_path / "ground_item_hook.s"
        source_path.write_text(rendered, encoding="utf-8")

        try:
            result = subprocess.run(
                [str(exe), str(source_path)],
                cwd=tmp_path,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise ArmipsError(f"could not run armips ({exe}): {exc}") from exc

        if result.returncode != 0:
            raise ArmipsError(
                f"armips failed (exit code {result.returncode}) assembling "
                f"{PATCH_SOURCE.name}:\n{result.stdout}\n{result.stderr}"
            )
        if not output_path.is_file():
            raise ArmipsError(
                f"armips exited successfully but produced no output at {output_path} "
                f"-- stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return output_path.read_bytes()


def apply_ground_item_hook(rom: HeartGoldRom, *, armips_exe: Path | None = None,
                            protocol_address: int = PROTOCOL_ADDRESS) -> int:
    load_address = rom.arm9_ram_address + len(rom.arm9)
    code = assemble_ground_item_hook(
        load_address, armips_exe=armips_exe, protocol_address=protocol_address
    )
    actual_address = rom.append_to_arm9(code)
    assert actual_address == load_address, (
        f"ARM9 binary changed length between computing the load address "
        f"({load_address:#x}) and appending to it ({actual_address:#x}) -- "
        "this should never happen for a single-threaded, single-call use."
    )
    return actual_address


def apply_local_item_substitutions(
    rom: HeartGoldRom, substitutions: dict[str, str | None], name_ids: dict[str, int] | None = None
) -> None:
    from data.locations import LOCATIONS

    from data.items import ITEMS

    hidden_item_substitutions: dict[str, str | None] = {}

    for location_key, item_key in substitutions.items():
        if item_key is not None and ITEMS.get(item_key, {}).get("pocket") == "badge":
            item_key = None
        location = LOCATIONS.get(location_key)
        if location is None:
            raise KeyError(f"unknown location key: {location_key!r}")
        location_type = location["type"]
        name_id = (name_ids or {}).get(location_key, 0)
        if location_type == "ground_item":
            if item_key is None:
                rom_eventscriptdata.write_ground_item_empty(rom, location_key, name_id)
            else:
                rom_eventscriptdata.write_ground_item_substitution(rom, location_key, item_key)
        elif location_type == "npc_gift":
            if item_key is None:
                rom_npcgiftdata.write_npc_gift_empty(rom, location_key, name_id)
            else:
                rom_npcgiftdata.write_npc_gift_substitution(rom, location_key, item_key)
        elif location_type == "hidden_item":
            hidden_item_substitutions[location_key] = item_key
        elif location_type == "hm_tm":
            is_itemball = location["id"] in rom_eventscriptdata.BLOCK_INDEX_BY_ITEMBALL_FLAG_ID
            if item_key is None:
                if is_itemball:
                    rom_eventscriptdata.write_ground_item_empty(rom, location_key, name_id)
                else:
                    rom_npcgiftdata.write_npc_gift_empty(rom, location_key, name_id)
            elif is_itemball:
                rom_eventscriptdata.write_ground_item_substitution(rom, location_key, item_key)
            else:
                rom_npcgiftdata.write_npc_gift_substitution(rom, location_key, item_key)
        else:
            raise ValueError(
                f"location {location_key!r} is type {location_type!r} -- "
                "apply_local_item_substitutions only supports "
                "ground_item/npc_gift/hm_tm/hidden_item (badge has its own, "
                "unconditional patch path, see apply_badge_neutralization/"
                "rom/badgedata.py -- it is never seed-dependent, so it is "
                "never routed through this per-seed substitutions dict)."
            )

    if hidden_item_substitutions:
        rom_hiddenitemdata.write_hidden_item_substitutions(rom, hidden_item_substitutions, name_ids)


def apply_foreign_item_names(rom: HeartGoldRom, names: dict[str, list]) -> dict[str, int]:
    return rom_foreignnamedata.write_foreign_names(rom, {key: tuple(value) for key, value in names.items()})


def apply_badge_neutralization(rom: HeartGoldRom) -> None:
    rom_badgedata.write_all_badges_neutralized(rom)


def apply_badge_gate_regating(rom: HeartGoldRom) -> None:
    rom_badgegatedata.write_all_badge_gates_regated(rom)


PLACEHOLDER_ITEM_MSG_NO = 0
PLACEHOLDER_ITEM_TEXT = "Item sent to another player!"
PLACEHOLDER_ITEM_INDEF_TEXT = "an Item sent to another player"
PLACEHOLDER_ITEM_PLURAL_TEXT = "Items sent to another player"


def apply_wing_monk_regate(rom: HeartGoldRom) -> None:
    rom_wingmonkdata.write_wing_monk_regate(rom)


def apply_gift_flags(rom: HeartGoldRom) -> None:
    rom_giftflagdata.write_gift_flags(rom)


def apply_deathlink_scripts(rom: HeartGoldRom) -> None:
    rom_deathlinkdata.write_deathlink_scripts(rom)


def apply_timed_events(rom: HeartGoldRom) -> None:
    rom_timedeventdata.write_timed_events(rom)


def apply_lighthouse_fix(rom: HeartGoldRom) -> None:
    rom_lighthousedata.write_lighthouse_fix(rom)


def apply_new_bark_east_exit_fix(rom: HeartGoldRom) -> None:
    rom_newbarkexitdata.write_new_bark_east_exit_open(rom)


def apply_exp_settings(rom: HeartGoldRom, global_exp_share: bool, multiplier: int) -> None:
    if rom_expshare.is_vanilla_setting(global_exp_share, multiplier):
        return
    data = rom.read_overlay(rom_expshare.OVERLAY_ID)
    rom.write_overlay(
        rom_expshare.OVERLAY_ID, rom_expshare.patch_overlay_data(data, global_exp_share, multiplier)
    )


def apply_npc_gift_duplication_gate_fix(rom: HeartGoldRom) -> None:
    rom_npcgiftgatedata.write_all_npc_gift_duplication_gates(rom)


def apply_placeholder_text_fix(rom: HeartGoldRom) -> None:
    for subfile_index, text in (
        (rom_msgdata.ITEM_NAMES_SUBFILE_INDEX, PLACEHOLDER_ITEM_TEXT),
        (rom_msgdata.ITEM_NAMES_INDEF_SUBFILE_INDEX, PLACEHOLDER_ITEM_INDEF_TEXT),
        (rom_msgdata.ITEM_NAMES_PLURAL_SUBFILE_INDEX, PLACEHOLDER_ITEM_PLURAL_TEXT),
    ):
        rom_msgdata.write_message_text(rom, subfile_index, PLACEHOLDER_ITEM_MSG_NO, text)


def apply_starter_randomization(rom: HeartGoldRom, starters: tuple[str, str, str]) -> None:
    from data.species import SPECIES

    raw_ids = tuple(SPECIES[key]["id"] for key in starters)
    rom_starterdata.write_starters(rom, raw_ids)


STARTER_SELECTION_QUESTION_MSG_NOS = (1, 2, 3)
STARTER_SELECTION_CONFIRM_MSG_NOS = (4, 5, 6)
_STARTER_SELECTION_QUESTION_TEMPLATES = (
    "Professor Elm: So, you like {name}, the {type}-type Pokémon?",
    "Professor Elm: How about {name}, the {type}-type Pokémon?",
    "Professor Elm: Do you want {name}, the {type}-type Pokémon?",
)
_STARTER_SELECTION_CONFIRM_TEMPLATE = "{name}, the {type}-type Pokémon, is in this Poké Ball!"

_SPECIES_LABEL_DISPLAY_OVERRIDES: dict[str, str] = {
    "NIDORAN_F": "Nidoran-F",
    "NIDORAN_M": "Nidoran-M",
    "MR_MIME": "Mr. Mime",
    "HO_OH": "Ho-Oh",
    "MIME_JR": "Mime Jr.",
    "PORYGON_Z": "Porygon-Z",
    "DEOXYS_ATK": "Deoxys (Attack)",
    "DEOXYS_DEF": "Deoxys (Defense)",
    "DEOXYS_SPD": "Deoxys (Speed)",
    "WORMADAM_SANDY": "Wormadam (Sandy)",
    "WORMADAM_TRASH": "Wormadam (Trash)",
    "GIRATINA_ORIGIN": "Giratina (Origin)",
    "SHAYMIN_SKY": "Shaymin (Sky)",
    "ROTOM_HEAT": "Rotom (Heat)",
    "ROTOM_WASH": "Rotom (Wash)",
    "ROTOM_FROST": "Rotom (Frost)",
    "ROTOM_FAN": "Rotom (Fan)",
    "ROTOM_MOW": "Rotom (Mow)",
}


def _species_display_name(label: str) -> str:
    return _SPECIES_LABEL_DISPLAY_OVERRIDES.get(label, label)


def apply_starter_selection_text_fix(rom: HeartGoldRom, starters: tuple[str, str, str]) -> None:
    from species import VANILLA_STARTERS

    if tuple(starters) == VANILLA_STARTERS:
        return

    from data.species import SPECIES

    for slot, species_key in enumerate(starters):
        data = SPECIES[species_key]
        name = _species_display_name(data["label"])
        type_name = data["types"][0].capitalize()
        question = _STARTER_SELECTION_QUESTION_TEMPLATES[slot].format(name=name, type=type_name)
        confirm = _STARTER_SELECTION_CONFIRM_TEMPLATE.format(name=name, type=type_name)
        rom_msgdata.write_message_text(
            rom, rom_msgdata.STARTER_SELECTION_SUBFILE_INDEX, STARTER_SELECTION_QUESTION_MSG_NOS[slot], question
        )
        rom_msgdata.write_message_text(
            rom, rom_msgdata.STARTER_SELECTION_SUBFILE_INDEX, STARTER_SELECTION_CONFIRM_MSG_NOS[slot], confirm
        )


_EVOLUTION_METHOD_TO_RAW: dict[str, int] = {
    "friendship": 1,
    "friendship_day": 2,
    "friendship_night": 3,
    "level": 4,
    "trade": 5,
    "trade_item": 6,
    "stone": 7,
    "level_atk_gt_def": 8,
    "level_atk_eq_def": 9,
    "level_atk_lt_def": 10,
    "level_pid_lo": 11,
    "level_pid_hi": 12,
    "level_ninjask": 13,
    "level_shedinja": 14,
    "beauty": 15,
    "stone_male": 16,
    "stone_female": 17,
    "item_day": 18,
    "item_night": 19,
    "has_move": 20,
    "other_party_mon": 21,
    "level_male": 22,
    "level_female": 23,
    "coronet": 24,
    "eterna": 25,
    "route217": 26,
}

_ITEM_PARAM_METHODS = {"stone", "trade_item", "item_day", "item_night", "stone_male", "stone_female"}
_MOVE_PARAM_METHODS = {"has_move"}
_SPECIES_PARAM_METHODS = {"other_party_mon"}


def _encode_evolution_param(method: str, param: object) -> int:
    if method in _ITEM_PARAM_METHODS:
        from data.items import ITEMS

        return ITEMS[param]["id"]
    if method in _MOVE_PARAM_METHODS:
        from data.moves import MOVES

        return MOVES[param]["id"]
    if method in _SPECIES_PARAM_METHODS:
        from data.species_index import SPECIES_KEY_TO_RAW_INDEX

        return SPECIES_KEY_TO_RAW_INDEX[param]
    return int(param)


def apply_trainer_randomization(rom: HeartGoldRom, trainers: dict) -> None:
    for data in trainers.values():
        if not data["party"]:
            continue
        rom_trainerdata.write_party_species(rom, data["id"], data["party"])
        rom_trainerdata.write_party_levels(rom, data["id"], data["party"])


def default_moveset(learnset: list[tuple[int, int]], level: int) -> list[int]:
    moves: list[int] = []
    for learn_level, move_id in learnset:
        if learn_level > level:
            break
        if move_id in moves:
            continue
        if len(moves) == 4:
            moves.pop(0)
        moves.append(move_id)
    return moves


def apply_trainer_movesets(rom: HeartGoldRom, trainers: dict) -> None:
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX
    from data.trainers import TRAINERS

    learnsets: dict[int, list[tuple[int, int]]] = {}
    for key, data in trainers.items():
        vanilla = TRAINERS.get(key)
        if not data["party"] or vanilla is None or not rom_trainerdata.trainer_has_custom_moves(rom, data["id"]):
            continue
        movesets: list[list[int] | None] = []
        for mon, vanilla_mon in zip(data["party"], vanilla["party"]):
            if mon["species"] == vanilla_mon["species"]:
                movesets.append(None)
                continue
            raw_index = SPECIES_KEY_TO_RAW_INDEX[mon["species"]]
            if raw_index not in learnsets:
                learnsets[raw_index] = rom_learnsetdata.read_species_learnset(rom, raw_index)
            movesets.append(default_moveset(learnsets[raw_index], mon["level"]))
        if any(moves is not None for moves in movesets):
            rom_trainerdata.write_party_moves(rom, data["id"], movesets)


def apply_encounter_randomization(rom: HeartGoldRom, encounters: dict) -> None:
    for zone_key, zone in encounters.items():
        if not rom_encounterdata.zone_is_written(zone_key):
            continue
        rom_encounterdata.write_zone_encounters(rom, zone_key, zone)
    rom_encounterdata.write_headbutt_tables(rom, encounters)


def apply_evolution_and_stat_randomization(rom: HeartGoldRom, species: dict) -> None:
    from data.moves import MOVES
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

    from species import restore_shadowed_time_evolutions

    species = restore_shadowed_time_evolutions(species)
    for species_key, data in species.items():
        raw_index = SPECIES_KEY_TO_RAW_INDEX[species_key]

        raw_evolutions = [
            (
                _EVOLUTION_METHOD_TO_RAW[evo["method"]],
                _encode_evolution_param(evo["method"], evo["param"]),
                SPECIES_KEY_TO_RAW_INDEX[evo["target"]],
            )
            for evo in data["evolutions"]
        ]
        rom_evodata.write_species_evolutions(rom, raw_index, raw_evolutions)
        rom_speciesdata.write_base_stats(rom, species_key, data["base_stats"])

        types = data["types"]
        type1 = rom_movedata.TYPE_NAME_TO_ID[types[0]]
        type2 = rom_movedata.TYPE_NAME_TO_ID[types[1]] if len(types) > 1 else type1
        rom_speciesdata.write_types(rom, species_key, type1, type2)

        ability1, ability2 = data["abilities"]
        rom_speciesdata.write_abilities(rom, species_key, ability1, ability2)

        raw_learnset = [(level, MOVES[move_key]["id"]) for level, move_key in data["level_learnset"]]
        if raw_learnset != rom_learnsetdata.read_species_learnset(rom, raw_index):
            try:
                rom_learnsetdata.write_species_learnset(rom, raw_index, raw_learnset)
            except ValueError as error:
                print(
                    f"warning: could not write randomized learnset for {species_key!r} "
                    f"({error}); leaving this species' learnset vanilla.",
                    file=sys.stderr,
                )


def apply_move_randomization(rom: HeartGoldRom, moves: dict) -> None:
    from data.moves import MOVES as VANILLA_MOVES

    for move_key, data in moves.items():
        if VANILLA_MOVES[move_key]["effect"] == "one_hit_ko" and data["effect"] != "one_hit_ko":
            rom_movedata.write_ohko_neutralization(rom, move_key)
        rom_movedata.write_combat_stats(rom, move_key, power=data["power"], accuracy=data["accuracy"], pp=data["pp"])
        rom_movedata.write_type(rom, move_key, rom_movedata.TYPE_NAME_TO_ID[data["type"]])
        rom_movedata.write_category(rom, move_key, rom_movedata.CATEGORY_NAME_TO_ID[data["category"]])


def apply_tm_hm_randomization(rom: HeartGoldRom, tm_hm_moves: dict) -> None:
    from data.moves import MOVES

    machine_to_move_id = {machine: MOVES[move_key]["id"] for machine, move_key in tm_hm_moves.items()}
    rom_tmhmdata.write_tm_hm_moves(rom, machine_to_move_id)


def apply_type_chart_randomization(rom: HeartGoldRom, type_chart: list) -> None:
    rom_typechart.write_type_chart(rom, type_chart)


def apply_start_location(rom: HeartGoldRom, town_key: str) -> None:
    rom_startlocation.write_start_location(rom, town_key)


def stamp_start_location_revocation(packed: bytearray) -> int:
    return rom_startlocation.stamp_revocation_record(packed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assemble and apply the C14 ground-item hook scaffolding to a HeartGold (US) ROM copy."
    )
    parser.add_argument("--rom", required=True, help="Path to a vanilla Pokemon HeartGold (US) ROM.")
    parser.add_argument("--out", required=True, help="Path to write the patched ROM to.")
    parser.add_argument("--armips", default=None, help=f"Override {ARMIPS_PATH_ENV_VAR}/the default armips path.")
    args = parser.parse_args(argv)

    rom = HeartGoldRom.open(args.rom)
    hook_address = apply_ground_item_hook(
        rom, armips_exe=Path(args.armips) if args.armips else None
    )
    rom.save(args.out)
    print(
        f"Patched ROM written to {args.out} -- ground_item_hook scaffolding "
        f"appended at ARM9 address 0x{hook_address:08X} (not yet hooked to "
        "any call site)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
