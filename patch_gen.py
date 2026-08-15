#!/usr/bin/env python3
"""patch_gen.py

Ground-item check mechanism proof of concept: assembles
patches/ground_item_hook.s with armips and appends the result to a
Pokemon HeartGold (US) ROM's ARM9 binary. Scaffolding only -- proves the
armips + patch_gen.py + rom/ pipeline works end-to-end, but does not hook
any real in-game call site yet (see NOTES.md). Also home to the species/
move/trainer/encounter/item-substitution ROM-write orchestration used by
the real Archipelago output path (output_patch.py).

`armips` path read from the ARMIPS_PATH env var, falling back to
ressources/armips/build/armips.exe.

Usage:
    python patch_gen.py --rom <path to vanilla HeartGold (US) .nds> --out <output .nds>
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from rom import HeartGoldRom
from rom import badgedata as rom_badgedata
from rom import encounterdata as rom_encounterdata
from rom import eventscriptdata as rom_eventscriptdata
from rom import msgdata as rom_msgdata
from rom import evodata as rom_evodata
from rom import hiddenitemdata as rom_hiddenitemdata
from rom import movedata as rom_movedata
from rom import npcgiftdata as rom_npcgiftdata
from rom import speciesdata as rom_speciesdata
from rom import starterdata as rom_starterdata
from rom import trainerdata as rom_trainerdata

ROOT = Path(__file__).resolve().parent
PATCH_SOURCE = ROOT / "patches" / "ground_item_hook.s"

ARMIPS_PATH_ENV_VAR = "ARMIPS_PATH"
_DEFAULT_ARMIPS_PATH = ROOT / "ressources" / "armips" / "build" / "armips.exe"

# Fixed EWRAM scratch address for the AP protocol struct -- see
# patches/ground_item_hook.s's header comment.
PROTOCOL_ADDRESS = 0x023FF800
PROTOCOL_STRUCT_SIZE = 0x14
PROTOCOL_MAGIC = b"HGAP"


class ArmipsError(Exception):
    """`armips` could not be run, or reported an assembly error."""


def armips_path() -> Path:
    """Resolve the `armips` executable path: `ARMIPS_PATH` env var if set,
    else this repository's own local build (see this module's docstring)."""
    raw = os.environ.get(ARMIPS_PATH_ENV_VAR)
    return Path(raw) if raw else _DEFAULT_ARMIPS_PATH


def assemble_ground_item_hook(hook_load_address: int, *, armips_exe: Path | None = None,
                               protocol_address: int = PROTOCOL_ADDRESS) -> bytes:
    """Render `patches/ground_item_hook.s` for the given load address and
    assemble it with `armips`. Returns the raw assembled machine code
    bytes (a flat binary, no headers) -- the caller decides where in the
    ROM those bytes end up (see `apply_ground_item_hook` below)."""
    exe = armips_exe or armips_path()
    if not exe.is_file():
        raise ArmipsError(
            f"armips executable not found at {exe} -- set {ARMIPS_PATH_ENV_VAR} to "
            "a valid armips build (see docs/architecture.md, '## ROM code "
            "injection strategy')."
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
    """Assemble and append the ground-item hook scaffolding to rom's ARM9
    binary in place. Returns the RAM address the appended code now lives
    at. Does not wire up any call site."""
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


# -- Local item substitution ---------------------------------------------
#
# Plain NitroFS data edits (rom/eventscriptdata.py, rom/npcgiftdata.py,
# rom/hiddenitemdata.py) -- no unknown ROM addresses involved, a different
# risk profile from the ARM-hooks path above. Covers ground_item, npc_gift,
# hm_tm, hidden_item. badge is out of scope (not an item at all).


def apply_local_item_substitutions(rom: HeartGoldRom, substitutions: dict[str, str | None]) -> None:
    """Apply a {location_key: item_key} mapping to `rom` in place, for
    ground_item/npc_gift/hm_tm/hidden_item locations. Locations not
    present in `substitutions` are left untouched.

    `None` is the "empty" sentinel for a location whose item belongs to
    another player: writes item id 0, so picking it up still fires
    check-detection but never hands the player a real, unearned item.

    hidden_item entries are batched into one write call -- see NOTES.md
    for why (34 minutes vs. seconds for all 225 real locations)."""
    from data.locations import LOCATIONS

    hidden_item_substitutions: dict[str, str | None] = {}

    for location_key, item_key in substitutions.items():
        location = LOCATIONS.get(location_key)
        if location is None:
            raise KeyError(f"unknown location key: {location_key!r}")
        location_type = location["type"]
        if location_type == "ground_item":
            if item_key is None:
                rom_eventscriptdata.write_ground_item_empty(rom, location_key)
            else:
                rom_eventscriptdata.write_ground_item_substitution(rom, location_key, item_key)
        elif location_type == "npc_gift":
            if item_key is None:
                rom_npcgiftdata.write_npc_gift_empty(rom, location_key)
            else:
                rom_npcgiftdata.write_npc_gift_substitution(rom, location_key, item_key)
        elif location_type == "hidden_item":
            hidden_item_substitutions[location_key] = item_key
        elif location_type == "hm_tm":
            is_itemball = location["id"] in rom_eventscriptdata.BLOCK_INDEX_BY_ITEMBALL_FLAG_ID
            if item_key is None:
                if is_itemball:
                    rom_eventscriptdata.write_ground_item_empty(rom, location_key)
                else:
                    rom_npcgiftdata.write_npc_gift_empty(rom, location_key)
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
        rom_hiddenitemdata.write_hidden_item_substitutions(rom, hidden_item_substitutions)


def apply_badge_neutralization(rom: HeartGoldRom) -> None:
    """Neutralize every gym script's own vanilla `GiveBadge` call (see
    rom/badgedata.py). Unconditional -- always applied regardless of this
    seed's fill result, unlike apply_local_item_substitutions above."""
    rom_badgedata.write_all_badges_neutralized(rom)


# Item id 0 ("None") is what write_npc_gift_empty/write_ground_item_empty/
# write_hidden_item_substitutions already write for a location whose item
# belongs to another player (see apply_local_item_substitutions above) --
# picking it up previously showed a garbled "???" (task "Replace the ???
# placeholder", 2026-08-15; msg_0222 entry 0 genuinely decodes to "None",
# not blank -- the "???" was this game's own generic label for a picked-up
# item id 0 shows in that specific dialogue context, not a missing/corrupt
# string this project introduced). Unconditional, like badge neutralization
# above: always applied regardless of this seed's fill result.
PLACEHOLDER_ITEM_MSG_NO = 0
PLACEHOLDER_ITEM_TEXT = "Item sent to another player!"


def apply_placeholder_text_fix(rom: HeartGoldRom) -> None:
    """Replace msg_0222's item-name entry for id 0 with a clearer message
    than the vanilla default (see rom/msgdata.py for the binary format)."""
    rom_msgdata.write_message_text(
        rom, rom_msgdata.ITEM_NAMES_SUBFILE_INDEX, PLACEHOLDER_ITEM_MSG_NO, PLACEHOLDER_ITEM_TEXT
    )


# -- Species/move/trainer/encounter randomization ----------------------------
#
# Applies species.py's randomizer output to a ROM copy via the rom/*.py
# write layers, every one round-trip verified against the real ROM.


def apply_starter_randomization(rom: HeartGoldRom, starters: tuple[str, str, str]) -> None:
    """Apply species.py's randomize_starters output (3 data/species.py
    keys) to rom/starterdata.py's live-confirmed species[] address (task
    "Randomize Starters", 2026-08-15 -- see that module's own docstring
    for the derivation/live-verification writeup)."""
    from data.species import SPECIES

    raw_ids = tuple(SPECIES[key]["id"] for key in starters)
    rom_starterdata.write_starters(rom, raw_ids)


# msg_0190 (choose_starter_app.c's own text bank): entries 1-3 are the
# "So, you like X?" question for each of the 3 starter-choice slots,
# entries 4-6 the "X is in this Poke Ball!" confirmation, same slot
# order -- see NOTES.md for the color-code tradeoff.
STARTER_SELECTION_QUESTION_MSG_NOS = (1, 2, 3)
STARTER_SELECTION_CONFIRM_MSG_NOS = (4, 5, 6)
_STARTER_SELECTION_QUESTION_TEMPLATES = (
    "Professor Elm: So, you like {name}, the {type}-type Pokémon?",
    "Professor Elm: How about {name}, the {type}-type Pokémon?",
    "Professor Elm: Do you want {name}, the {type}-type Pokémon?",
)
_STARTER_SELECTION_CONFIRM_TEMPLATE = "{name}, the {type}-type Pokémon, is in this Poké Ball!"


def apply_starter_selection_text_fix(rom: HeartGoldRom, starters: tuple[str, str, str]) -> None:
    """Rewrite msg_0190's starter-choice question/confirmation text to
    name the actually-randomized species for each slot instead of the
    vanilla, hardcoded Chikorita/Cyndaquil/Totodile -- the species itself
    was already correct (rom/starterdata.py), only this display text
    lagged behind. A no-op when starters are still vanilla."""
    from species import VANILLA_STARTERS

    if tuple(starters) == VANILLA_STARTERS:
        return

    from data.species import SPECIES

    for slot, species_key in enumerate(starters):
        data = SPECIES[species_key]
        name = data["label"]
        type_name = data["types"][0].capitalize()
        question = _STARTER_SELECTION_QUESTION_TEMPLATES[slot].format(name=name, type=type_name)
        confirm = _STARTER_SELECTION_CONFIRM_TEMPLATE.format(name=name, type=type_name)
        rom_msgdata.write_message_text(
            rom, rom_msgdata.STARTER_SELECTION_SUBFILE_INDEX, STARTER_SELECTION_QUESTION_MSG_NOS[slot], question
        )
        rom_msgdata.write_message_text(
            rom, rom_msgdata.STARTER_SELECTION_SUBFILE_INDEX, STARTER_SELECTION_CONFIRM_MSG_NOS[slot], confirm
        )


# Decomposition include/constants/pokemon.h's EvoMethod enum -- cross-
# checked against a real evolution read live off the ROM (bulbasaur:
# method 4 == EVO_LEVEL, matching this table).
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

# Evolution methods whose `param` is an item/move/species key rather than
# a plain integer.
_ITEM_PARAM_METHODS = {"stone", "trade_item", "item_day", "item_night", "stone_male", "stone_female"}
_MOVE_PARAM_METHODS = {"has_move"}
_SPECIES_PARAM_METHODS = {"other_party_mon"}


def _encode_evolution_param(method: str, param: object) -> int:
    """Convert one evolution's param into the raw u16 value
    rom/evodata.py writes to the ROM."""
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
    """Apply `species.py`'s `randomize_trainer_parties`/
    `scale_trainer_levels` output (`level`/`species` per party slot).
    Trainers with an empty party (e.g. `data/trainers.py`'s `none` entry,
    id 0) are skipped -- nothing to write."""
    for data in trainers.values():
        if not data["party"]:
            continue
        rom_trainerdata.write_party_species(rom, data["id"], data["party"])
        rom_trainerdata.write_party_levels(rom, data["id"], data["party"])


def apply_encounter_randomization(rom: HeartGoldRom, encounters: dict) -> None:
    """Apply species.py's randomize_wild_encounters output (already
    resolved to rom's declared version's own vanilla base data by
    __init__.py's set_rules). Zones with no raw NARC entry (the 3
    headbutt-only zones) are skipped. rom_encounterdata.write_zone_
    encounters picks g_enc_data.narc vs s_enc_data.narc based on
    rom.version -- see that module's own notes for why."""
    from data.encounter_zone_index import ENCOUNTER_ZONE_KEY_TO_RAW_INDEX

    for zone_key, zone in encounters.items():
        if zone_key not in ENCOUNTER_ZONE_KEY_TO_RAW_INDEX:
            continue
        rom_encounterdata.write_zone_encounters(rom, zone_key, zone)


def apply_evolution_and_stat_randomization(rom: HeartGoldRom, species: dict) -> None:
    """Apply species.py's randomize_evolutions/randomize_base_stats/
    randomize_species_types/neutralize_trapping_abilities output -- writes
    the evolution table, base-stats table, types, and abilities for every
    species. Abilities are written unconditionally (data["abilities"]
    always carries some value, the vanilla pair when the option is off) --
    a harmless idempotent no-op, keeps this function option-agnostic."""
    from data.species_index import SPECIES_KEY_TO_RAW_INDEX

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


def apply_move_randomization(rom: HeartGoldRom, moves: dict) -> None:
    """Apply species.py's randomize_move_stats/randomize_move_types/
    disable_ohko_moves output. A move is routed through
    rom_movedata.write_ohko_neutralization instead of write_combat_stats
    precisely when its vanilla effect was "one_hit_ko" but no longer is --
    i.e. exactly the moves disable_ohko_moves touched. write_combat_stats
    still runs unconditionally afterwards so `pp` ends up matching
    whatever upstream randomization put there."""
    from data.moves import MOVES as VANILLA_MOVES

    for move_key, data in moves.items():
        if VANILLA_MOVES[move_key]["effect"] == "one_hit_ko" and data["effect"] != "one_hit_ko":
            rom_movedata.write_ohko_neutralization(rom, move_key)
        rom_movedata.write_combat_stats(rom, move_key, power=data["power"], accuracy=data["accuracy"], pp=data["pp"])
        rom_movedata.write_type(rom, move_key, rom_movedata.TYPE_NAME_TO_ID[data["type"]])


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
        "any call site; see docs/architecture.md)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
