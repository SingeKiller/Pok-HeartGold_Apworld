#!/usr/bin/env python3
"""patch_gen.py

Task C14 -- ground-item check mechanism proof of concept. Assembles
`patches/ground_item_hook.s` with `armips` and applies the result to a
Pokemon HeartGold (US) ROM via `rom/`'s append-only ARM9 access
(`HeartGoldRom.append_to_arm9`, see that module for the safety rationale).

Read docs/architecture.md, "## C14 -- Ground item check mechanism (proof of
concept)" before relying on this for anything beyond what it actually is:
this patch is scaffolding that proves the armips + patch_gen.py + rom/
pipeline works end-to-end (assembles real ARM code, appends it to the ARM9
binary without touching the DS secure area, leaves the ROM structurally
valid) -- it does **not** yet hook any real in-game call site (that hook
point's ROM address could not be safely determined in this task's session;
see docs/architecture.md for the full investigation and why). The two
functions this patch adds (`HeartGoldAP_Init`,
`HeartGoldAP_RecordGroundItemCheck`) are present in the patched ROM's ARM9
binary but are not called from anywhere yet.

`armips` is not on `PATH` in this project's dev environment (see
docs/architecture.md, "## ROM code injection strategy"); its path is read
from the `ARMIPS_PATH` environment variable, following the same convention
already used for `ARCHIPELAGO_PATH` (tests/conftest.py) and
`HEARTGOLD_ROM_PATH` (tests/test_rom_roundtrip.py, tests/test_rom_access.py),
falling back to this repository's own local build,
`ressources/armips/build/armips.exe`.

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
from rom import encounterdata as rom_encounterdata
from rom import eventscriptdata as rom_eventscriptdata
from rom import evodata as rom_evodata
from rom import hiddenitemdata as rom_hiddenitemdata
from rom import movedata as rom_movedata
from rom import npcgiftdata as rom_npcgiftdata
from rom import speciesdata as rom_speciesdata
from rom import trainerdata as rom_trainerdata

ROOT = Path(__file__).resolve().parent
PATCH_SOURCE = ROOT / "patches" / "ground_item_hook.s"

ARMIPS_PATH_ENV_VAR = "ARMIPS_PATH"
_DEFAULT_ARMIPS_PATH = ROOT / "ressources" / "armips" / "build" / "armips.exe"

# Fixed EWRAM scratch address for the AP protocol struct -- see
# patches/ground_item_hook.s's header comment and docs/architecture.md for
# the struct layout and why this address was chosen (near-top-of-EWRAM
# convention, same idea as ljtpetersen/platinum_archipelago's own
# `AP_STRUCT_PTR_ADDRESS`).
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
    """Assemble and append the ground-item hook scaffolding (see this
    module's docstring for exactly what that is and isn't) to `rom`'s ARM9
    binary in place. Returns the RAM address the appended code now lives
    at.

    Does not wire up any call site -- see docs/architecture.md and
    patches/ground_item_hook.s for why."""
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


# -- Local item substitution (tasks C15/C16) ----------------------------------
#
# Unlike the ground-item hook scaffolding above (ARM9 code, not wired to any
# call site yet -- see this module's own docstring and docs/architecture.md),
# this is the piece of the "revised after C14" ROM strategy that is actually
# live: plain NitroFS data edits (rom/eventscriptdata.py,
# rom/npcgiftdata.py) with no unknown ROM addresses involved. See
# docs/architecture.md, "## ROM code injection strategy (revised after C14)"
# for why this is a different risk profile from the ARM-hooks path, and
# each module's own docstring for the binary format it patches.
#
# Covers `ground_item`, `npc_gift`, `hm_tm` (routed to whichever of the two
# modules above actually implements that specific `hm_tm` location's
# vanilla delivery mechanism -- see rom/eventscriptdata.py's
# `write_ground_item_substitution` and rom/npcgiftdata.py's
# `write_npc_gift_substitution` docstrings), and `hidden_item` (task M4.5 --
# originally out of scope because its vanilla item ids live in a compiled
# ARM9 static data table rather than a NitroFS script, a fundamentally
# different patch shape; resolved once that table's real RAM address was
# found via a live BizHawk memory-write breakpoint + instruction trace, see
# rom/hiddenitemdata.py's own docstring for the full story). `badge` is
# still out of scope (not an item at all, see data/items.py).


def apply_local_item_substitutions(rom: HeartGoldRom, substitutions: dict[str, str | None]) -> None:
    """Apply a `{location_key: item_key}` mapping (both `data/locations.py`/
    `data/items.py` keys) to `rom` in place, for `ground_item`/`npc_gift`/
    `hm_tm`/`hidden_item` locations -- badge is out of scope for this pass
    (see this module's own section header comment above). Locations not
    present in `substitutions` are left untouched (keep their vanilla
    `original_item`).

    A `None` value (JSON `null`) instead of a real item key is the "empty"
    sentinel for a location whose placed item belongs to *another*
    multiworld player (see `output_patch.build_item_substitutions`'s own
    docstring): writes item id 0 instead of a real item, so picking it up
    still fires this project's flag-read check-detection but never hands
    the player a real, unearned vanilla item (live-verified 2026-08-11, see
    `rom/eventscriptdata.write_ground_item_empty`/`rom/npcgiftdata.
    write_npc_gift_empty`'s own docstrings). hidden_item has no `_empty`
    counterpart -- it stays fully excluded from substitution regardless of
    `item_key` (see this module's own section header comment)."""
    from data.locations import LOCATIONS

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
            if item_key is None:
                raise ValueError(
                    f"location {location_key!r} is type 'hidden_item', which has no "
                    "'_empty' substitution -- hidden_item locations should never appear "
                    "in a substitutions mapping at all right now (see this module's own "
                    "section header comment)."
                )
            rom_hiddenitemdata.write_hidden_item_substitution(rom, location_key, item_key)
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
                "ground_item/npc_gift/hm_tm/hidden_item (badge is out of "
                "scope, see this module's own section header comment)."
            )


# -- Species/move/trainer/encounter randomization (task M4.5) ----------------
#
# Applies `species.py`'s randomizer output (`HeartGoldWorld.generated_
# starters`/`generated_encounters`/`generated_trainer_parties`/
# `generated_species`/`generated_moves`, see `__init__.py`'s own docstring)
# to a ROM copy, via the rom/*.py write layers built for this task
# (rom/trainerdata.py's `write_party_species`, rom/encounterdata.py's
# `write_zone_encounters`, rom/evodata.py's `write_species_evolutions`,
# rom/speciesdata.py's `write_base_stats`, rom/movedata.py's
# `write_combat_stats`). Every one of these was round-trip verified against
# the real ROM this same task (write, save, reopen, read back) -- see
# docs/architecture.md's "## M4.5" section for that verification.
#
# `rom/starterdata.py` is deliberately **not** called here -- see that
# module's own docstring: its target address is a well-evidenced candidate,
# not a live-verified one, and this project's standing policy (learned the
# hard way this same session for `client.py`'s RAM addresses) is to never
# wire an unverified address into the normal patch path.

# Decomposition `include/constants/pokemon.h`'s `EvoMethod` enum -- see
# docs/architecture.md's "## M4.5" section for how this was cross-checked
# against a real evolution read live off the ROM (bulbasaur: method 4 ==
# EVO_LEVEL, matching this table exactly).
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

# Evolution methods whose `param` is a `data/items.py` key (an item to use/
# hold), a `data/moves.py` key (a move the Pokémon must know), or a
# `data/species.py` key (another party member's species) rather than a
# plain integer -- see docs/architecture.md's "## M4.5" section for the
# full param-shape survey this was derived from (every method+param pair
# actually used in `data/species.py`, one example each).
_ITEM_PARAM_METHODS = {"stone", "trade_item", "item_day", "item_night", "stone_male", "stone_female"}
_MOVE_PARAM_METHODS = {"has_move"}
_SPECIES_PARAM_METHODS = {"other_party_mon"}


def _encode_evolution_param(method: str, param: object) -> int:
    """Convert one evolution's `param` (an int, or an item/move/species key
    depending on `method`, see this module's own constants above) into the
    raw `u16` value `rom/evodata.py` writes to the ROM."""
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
    """Apply `species.py`'s `randomize_trainer_parties` output. Trainers
    with an empty party (e.g. `data/trainers.py`'s `none` entry, id 0) are
    skipped -- nothing to write."""
    for data in trainers.values():
        if not data["party"]:
            continue
        rom_trainerdata.write_party_species(rom, data["id"], data["party"])


def apply_encounter_randomization(rom: HeartGoldRom, encounters: dict) -> None:
    """Apply `species.py`'s `randomize_wild_encounters` output. Zones with
    no raw NARC entry (see `data/encounter_zone_index.py`'s own docstring:
    the 3 headbutt-only zones) are skipped -- there is nothing in
    `g_enc_data.narc` for them to patch."""
    from data.encounter_zone_index import ENCOUNTER_ZONE_KEY_TO_RAW_INDEX

    for zone_key, zone in encounters.items():
        if zone_key not in ENCOUNTER_ZONE_KEY_TO_RAW_INDEX:
            continue
        rom_encounterdata.write_zone_encounters(rom, zone_key, zone)


def apply_evolution_and_stat_randomization(rom: HeartGoldRom, species: dict) -> None:
    """Apply `species.py`'s `randomize_evolutions`/`randomize_base_stats`
    output (both live on the same `generated_species` dict, see
    `__init__.py`'s `set_rules`) -- writes both the evolution table
    (rom/evodata.py) and the base-stats table (rom/speciesdata.py) for
    every species."""
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


def apply_move_randomization(rom: HeartGoldRom, moves: dict) -> None:
    """Apply `species.py`'s `randomize_move_stats` output."""
    for move_key, data in moves.items():
        rom_movedata.write_combat_stats(rom, move_key, power=data["power"], accuracy=data["accuracy"], pp=data["pp"])


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
