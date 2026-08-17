# output_patch.py
#
# HeartGoldWorld.generate_output() builds a HeartGoldProcedurePatch storing
# this player's generated_* randomizer output plus local item substitutions
# as JSON blobs inside a .apheartgold zip. Archipelago's own
# Patch.create_rom_file later calls .patch(target) on whichever machine
# actually has the ROM (not necessarily the one that ran generation),
# applying everything via patch_gen.py's apply_* functions.
#
# Never embeds/transmits the vanilla ROM's own bytes -- patch() reads it
# fresh from settings.rom_file every time, same convention every other
# ROM-patching Archipelago world follows.

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

if TYPE_CHECKING:
    from __init__ import HeartGoldWorld

# hidden_item history: see NOTES.md.
_SUBSTITUTABLE_LOCATION_TYPES = ("ground_item", "npc_gift", "hm_tm", "hidden_item")

# Read via pkgutil.get_data (loader-agnostic: works for both a loose dev
# checkout and a zipimport-ed .apworld) rather than a plain filesystem
# path, and rather than relying on World.world_version/AutoWorldRegister
# internals (populated inconsistently between custom_worlds/ and a real
# .apworld). Lets .patch() tell a player "wrong APWorld version" instead
# of a raw KeyError on a field a newer/older generate_output() did or
# didn't write. Exact-match, not a minimum-version floor -- see NOTES.md.


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

# options.GameVersion's int value -> the same version-name strings
# rom.HeartGoldRom.version uses, so the two can be compared directly at
# patch time (see .patch()'s version-mismatch check below).
_VERSION_NAME_BY_OPTION_VALUE = {
    GameVersion.option_heartgold: "heartgold",
    GameVersion.option_soulsilver: "soulsilver",
}


class HeartGoldProcedurePatch(APAutoPatchInterface):
    game = "Pokemon HGSS"
    hashes = [HEARTGOLD_US_MD5, SOULSILVER_US_MD5]
    patch_file_ending = ".apheartgold"
    result_file_ending = ".nds"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.files: dict[str, bytes] = {}

    def get_file(self, name: str) -> bytes:
        return self.files[name]

    def write_file(self, name: str, data: bytes) -> None:
        self.files[name] = data

    def read_contents(self, opened_zipfile) -> dict[str, Any]:  # noqa: ANN001
        manifest = super().read_contents(opened_zipfile)
        for name in opened_zipfile.namelist():
            if name != self.manifest_path:
                self.files[name] = opened_zipfile.read(name)

        # Absent = a patch predating this check -- proceed rather than
        # blocking on metadata that didn't exist yet.
        if "world_version.json" in self.files:
            generated_version = json.loads(self.files["world_version.json"])
            installed_version = _installed_world_version()
            if generated_version != installed_version:
                raise RomError(
                    f"This patch was generated with Pokemon HGSS APWorld "
                    f"version {generated_version}, but version "
                    f"{installed_version} is currently installed -- the patch "
                    "data format may not match what this version expects. "
                    f"Install APWorld version {generated_version} to apply "
                    "this exact patch, or regenerate the patch with the "
                    f"currently-installed version ({installed_version})."
                )

        return manifest

    def write_contents(self, opened_zipfile) -> None:  # noqa: ANN001
        super().write_contents(opened_zipfile)
        for name, data in self.files.items():
            opened_zipfile.writestr(name, data)

    def patch(self, target: str) -> None:
        """Called by Archipelago's own Patch.create_rom_file on whichever
        machine has the player's real ROM."""
        self.read()
        rom_path = get_settings().pokemon_heartgold_settings.rom_file
        rom = HeartGoldRom.open(rom_path)

        declared_version = json.loads(self.get_file("game_version.json"))
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

        patch_gen.apply_placeholder_text_fix(rom)

        starters = json.loads(self.get_file("starters.json"))
        starters = tuple(starters)
        patch_gen.apply_starter_randomization(rom, starters)
        patch_gen.apply_starter_selection_text_fix(rom, starters)

        rom.save(target)


def build_item_substitutions(world: HeartGoldWorld) -> dict[str, str | None]:
    """{location_key: item_key} for every one of this player's own
    ground_item/npc_gift/hm_tm/hidden_item locations.

    A location whose item belongs to this same player, or to an item-link
    group this player is a member of, gets its real item key --
    ROM-substituted so picking it up hands over exactly that item. "Local"
    here must match `__init__.py::_constrain_undetectable_locations`'s own
    definition exactly: that function is what lets the fill algorithm place
    an item-link item on one of the 30 undetectable locations
    (location_flags.unsupported_location_keys(), no real savedata flag this
    client can read) in the first place, on the assumption that ROM
    substitution is the only delivery path for those specific locations
    (no check-detection means no client-side remote-item delivery either).
    Treating that same item-link item as "belongs to another player" here
    would substitute it away as empty, permanently losing it for everyone in
    the group (found via code audit, task M1.2).
    A location whose item genuinely belongs to another player gets None:
    leaving the vanilla item in the ROM would silently hand the player a
    real, unearned item (found via a real playtest, see NOTES.md).
    `patch_gen.apply_local_item_substitutions` writes the "empty"
    substitution for None -- the location still fires check-detection,
    grants nothing physically.

    `remote_items` (options.RemoteItems, off by default, 2026-08-17): when
    on, this player's own items get None too (same as another player's),
    routing delivery through the normal network path
    (client.py's _apply_received_items) instead of embedding them in the
    ROM -- lets a corrupted/reset save recover everything on reconnect,
    or a slot be shared between multiple players. The 30 undetectable
    locations above are the one exception: ROM substitution is their
    *only* possible delivery path regardless of remote_items, so they
    keep their real item_key even then -- see location_flags.
    build_locally_substituted_ap_location_ids's own docstring, which
    client.py uses to recognize this same exception on the receiving end."""
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
        if item_key is not None:
            substitutions[location.name] = item_key
    return substitutions


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
    patch.write_file("item_substitutions.json", json.dumps(build_item_substitutions(world)).encode())

    out_file_name = world.multiworld.get_out_file_name_base(world.player)
    patch.write(os.path.join(output_directory, f"{out_file_name}{patch.patch_file_ending}"))
