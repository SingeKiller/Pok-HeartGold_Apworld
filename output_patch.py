from __future__ import annotations

import json
import os
import pkgutil
from typing import TYPE_CHECKING, Any

from settings import get_settings
from worlds.Files import APAutoPatchInterface

import patch_gen
from options import GameVersion
from rom import HEARTGOLD_US_MD5, SOULSILVER_US_MD5, HeartGoldRom, RomError
from rom.worldsignature import stamp_deathlink_scripts, stamp_slot_auth, stamp_world_signature

if TYPE_CHECKING:
    from __init__ import HeartGoldWorld

_SUBSTITUTABLE_LOCATION_TYPES = ("ground_item", "npc_gift", "hm_tm", "hidden_item")


def _installed_world_version() -> str:
    data = pkgutil.get_data(__name__, "archipelago.json")
    if data is None:
        raise RomError(
            "Could not read this world's own archipelago.json to determine "
            "its version -- this should not happen for a correctly packaged "
            ".apworld; please report this."
        )
    manifest = json.loads(data.decode("utf-8"))
    return manifest["world_version"]

_VERSION_NAME_BY_OPTION_VALUE = {
    GameVersion.option_heartgold: "heartgold",
    GameVersion.option_soulsilver: "soulsilver",
}


class HeartGoldProcedurePatch(APAutoPatchInterface):
    game = "Pokemon HGSS Singe"
    hashes = [HEARTGOLD_US_MD5, SOULSILVER_US_MD5]
    patch_file_ending = ".appokehgss"
    result_file_ending = ".nds"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.files: dict[str, bytes] = {}

    def get_file(self, name: str) -> bytes:
        return self.files[name]

    def write_file(self, name: str, data: bytes) -> None:
        self.files[name] = data

    def read_contents(self, opened_zipfile) -> dict[str, Any]:
        manifest = super().read_contents(opened_zipfile)
        for name in opened_zipfile.namelist():
            if name != self.manifest_path:
                self.files[name] = opened_zipfile.read(name)

        if "world_version.json" in self.files:
            generated_version = json.loads(self.files["world_version.json"])
            installed_version = _installed_world_version()
            if generated_version != installed_version:
                raise RomError(
                    f"This patch was generated with Pokemon HGSS Singe APWorld "
                    f"version {generated_version}, but version "
                    f"{installed_version} is currently installed -- the patch "
                    "data format may not match what this version expects. "
                    f"Install APWorld version {generated_version} to apply "
                    "this exact patch, or regenerate the patch with the "
                    f"currently-installed version ({installed_version})."
                )

        return manifest

    def write_contents(self, opened_zipfile) -> None:
        super().write_contents(opened_zipfile)
        for name, data in self.files.items():
            opened_zipfile.writestr(name, data)

    def patch(self, target: str) -> None:
        self.read()
        declared_version = json.loads(self.get_file("game_version.json"))

        settings_group = get_settings().pokemon_heartgold_settings
        rom_path = (
            settings_group.soulsilver_rom_file
            if declared_version == "soulsilver"
            else settings_group.heartgold_rom_file
        )
        rom = HeartGoldRom.open(rom_path)

        if rom.version is not None and declared_version != rom.version:
            raise RomError(
                f"This patch was generated for {declared_version}, but the ROM "
                f"configured in host.yaml is {rom.version} -- the wild-encounter "
                "data (and potentially other version-specific data) would not "
                f"match. Regenerate with the game_version option set to "
                f"{rom.version}, or configure the correct ROM in host.yaml."
            )

        trainers = json.loads(self.get_file("trainers.json"))
        patch_gen.apply_trainer_randomization(rom, trainers)

        encounters = json.loads(self.get_file("encounters.json"))
        patch_gen.apply_encounter_randomization(rom, encounters)

        species = json.loads(self.get_file("species.json"))
        patch_gen.apply_evolution_and_stat_randomization(rom, species)

        patch_gen.apply_trainer_movesets(rom, trainers)

        moves = json.loads(self.get_file("moves.json"))
        patch_gen.apply_move_randomization(rom, moves)

        tm_hm_moves = json.loads(self.get_file("tm_hm_moves.json"))
        patch_gen.apply_tm_hm_randomization(rom, tm_hm_moves)

        type_chart = json.loads(self.get_file("type_chart.json"))
        patch_gen.apply_type_chart_randomization(rom, type_chart)

        start_location_town = json.loads(self.get_file("start_location_town.json"))
        if start_location_town is not None:
            patch_gen.apply_start_location(rom, start_location_town)

        substitutions = json.loads(self.get_file("item_substitutions.json"))
        patch_gen.apply_local_item_substitutions(rom, substitutions)

        patch_gen.apply_badge_neutralization(rom)

        patch_gen.apply_badge_gate_regating(rom)

        patch_gen.apply_npc_gift_duplication_gate_fix(rom)

        patch_gen.apply_gift_flags(rom)

        patch_gen.apply_wing_monk_regate(rom)

        patch_gen.apply_new_bark_east_exit_fix(rom)

        patch_gen.apply_lighthouse_fix(rom)

        patch_gen.apply_timed_events(rom)

        patch_gen.apply_deathlink_scripts(rom)

        exp_settings = json.loads(self.get_file("exp_settings.json"))
        patch_gen.apply_exp_settings(rom, exp_settings["global_exp_share"], exp_settings["multiplier"])

        patch_gen.apply_placeholder_text_fix(rom)

        starters = json.loads(self.get_file("starters.json"))
        starters = tuple(starters)
        patch_gen.apply_starter_randomization(rom, starters)
        patch_gen.apply_starter_selection_text_fix(rom, starters)

        packed = bytearray(rom.save_bytes())
        if start_location_town is not None:
            patch_gen.stamp_start_location_revocation(packed)
        stamp_world_signature(packed)
        stamp_deathlink_scripts(packed)
        stamp_slot_auth(packed, bytes.fromhex(json.loads(self.get_file("slot_auth.json"))))
        with open(target, "wb") as out_file:
            out_file.write(packed)


def build_item_substitutions(world: HeartGoldWorld) -> dict[str, str | None]:
    from data.items import ITEMS
    from data.locations import LOCATIONS
    from location_flags import unsupported_location_keys

    label_to_key = {data["label"]: key for key, data in ITEMS.items()}
    local_players = {world.player} | world.multiworld.get_player_groups(world.player)
    remote_items = bool(world.options.remote_items.value)
    always_local_keys = frozenset(unsupported_location_keys()) if remote_items else frozenset()

    substitutions: dict[str, str | None] = {}
    for location in world.multiworld.get_locations(world.player):
        if location.item is None:
            continue
        location_data = LOCATIONS.get(location.name)
        if location_data is None or location_data["type"] not in _SUBSTITUTABLE_LOCATION_TYPES:
            continue
        if location.item.player not in local_players:
            substitutions[location.name] = None
            continue
        if remote_items and location.name not in always_local_keys:
            substitutions[location.name] = None
            continue
        item_key = label_to_key.get(location.item.name)
        if item_key is None:
            raise RomError(
                f"Location {location.name!r} was filled with this player's own item "
                f"{location.item.name!r}, but no data/items.py entry has that label, so the "
                "item cannot be written into the ROM. This is an items/locations data "
                "mismatch in the Pokemon HGSS Singe world itself; please report it."
            )
        substitutions[location.name] = item_key
    return substitutions


def build_foreign_item_names(world: HeartGoldWorld, substitutions: dict[str, str | None]) -> dict[str, list]:
    from data.items import ITEMS

    badge_labels = {data["label"] for data in ITEMS.values() if data.get("pocket") == "badge"}
    native_ids = {data["label"]: data["id"] for data in ITEMS.values() if data.get("pocket") != "badge"}
    names: dict[str, list] = {}
    for location in world.multiworld.get_locations(world.player):
        if location.item is None or location.name not in substitutions:
            continue
        if substitutions[location.name] is not None and location.item.name not in badge_labels:
            continue
        player = None if location.item.player == world.player else world.multiworld.get_player_name(location.item.player)
        native_id = native_ids.get(location.item.name) if location.item.game == world.game else None
        names[location.name] = [location.item.name, player, native_id]
    return names


def generate_output(world: HeartGoldWorld, output_directory: str) -> None:
    patch = HeartGoldProcedurePatch(player=world.player, player_name=world.player_name)
    patch.write_file("world_version.json", json.dumps(_installed_world_version()).encode())
    declared_version = _VERSION_NAME_BY_OPTION_VALUE[world.options.game_version.value]
    patch.write_file("game_version.json", json.dumps(declared_version).encode())
    patch.write_file("starters.json", json.dumps(world.generated_starters).encode())
    patch.write_file("trainers.json", json.dumps(world.generated_trainer_parties).encode())
    patch.write_file("encounters.json", json.dumps(world.generated_encounters).encode())
    patch.write_file("species.json", json.dumps(world.generated_species).encode())
    patch.write_file("moves.json", json.dumps(world.generated_moves).encode())
    patch.write_file("tm_hm_moves.json", json.dumps(world.generated_tm_hm_moves).encode())
    patch.write_file("type_chart.json", json.dumps(world.generated_type_chart).encode())
    patch.write_file("start_location_town.json", json.dumps(world.generated_start_location_town).encode())
    patch.write_file("slot_auth.json", json.dumps(world.slot_auth.hex()).encode())
    patch.write_file(
        "exp_settings.json",
        json.dumps(
            {
                "global_exp_share": bool(world.options.global_exp_share.value),
                "multiplier": int(world.options.exp_multiplier.value),
            }
        ).encode(),
    )
    substitutions = build_item_substitutions(world)
    patch.write_file("item_substitutions.json", json.dumps(substitutions).encode())
    patch.write_file(
        "foreign_item_names.json", json.dumps(build_foreign_item_names(world, substitutions)).encode()
    )

    out_file_name = world.multiworld.get_out_file_name_base(world.player)
    patch.write(os.path.join(output_directory, f"{out_file_name}{patch.patch_file_ending}"))
