# output_patch.py
#
# Archipelago's real output entry point (task M5): `HeartGoldWorld.
# generate_output()` (in `__init__.py`) builds a `HeartGoldProcedurePatch`
# storing this player's own `generated_*` randomizer output (already
# computed in `set_rules()`, see `__init__.py`'s own docstring) plus local
# item substitutions as small JSON blobs inside a `.apheartgold` zip.
# Archipelago's own `Patch.create_rom_file` later calls `.patch(target)`
# -- on whichever machine actually has the ROM, not necessarily the one
# that ran generation -- which is what actually opens the player's own
# ROM and applies everything via `patch_gen.py`'s already-tested
# `apply_*` functions.
#
# Deliberately never embeds/transmits the vanilla ROM's own bytes:
# `patch()` reads it fresh from this machine's local `settings.rom_file`
# (see `HeartGoldSettings` in `__init__.py`) every time, the same
# convention every other ROM-patching Archipelago world (pokemon_emerald,
# `ressources/platinum_archipelago`, ...) follows -- only a *description*
# of the changes (JSON diffs, not ROM bytes) ever goes in the patch file
# itself.
#
# hidden_item substitution was excluded from `build_item_substitutions`
# from 2026-08-10 to 2026-08-11: a live playtest of a ROM with ~225
# hidden_item locations patched at once produced a white screen on boot
# that was not reproduced with every *other* substitution type active. Root-
# caused and fixed 2026-08-11 (see `rom/__init__.py`'s `write_main_code_
# regions` docstring and docs/architecture.md's M6 sections): a stale ARM9
# boot-time decompression end-marker, unrelated to hidden_item's data
# itself, corrupted by *any* edit that changed the compressed ARM9's size --
# hidden_item was simply the first thing in this project to ever recompress
# that image with a real size-changing edit. "hidden_item" is back in
# `_SUBSTITUTABLE_LOCATION_TYPES` below now that the actual cause is fixed.

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

from settings import get_settings
from worlds.Files import APAutoPatchInterface

import patch_gen
from rom import HEARTGOLD_US_MD5, SOULSILVER_US_MD5, HeartGoldRom

if TYPE_CHECKING:
    from __init__ import HeartGoldWorld

# See this module's own docstring for hidden_item's history here.
_SUBSTITUTABLE_LOCATION_TYPES = ("ground_item", "npc_gift", "hm_tm", "hidden_item")


class HeartGoldProcedurePatch(APAutoPatchInterface):
    game = "Pokemon HeartGold"
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
        return manifest

    def write_contents(self, opened_zipfile) -> None:  # noqa: ANN001
        super().write_contents(opened_zipfile)
        for name, data in self.files.items():
            opened_zipfile.writestr(name, data)

    def patch(self, target: str) -> None:
        """Called by Archipelago's own `Patch.create_rom_file` (not by
        this project's own code directly -- see this module's own
        docstring) on whichever machine has the player's real ROM."""
        self.read()
        rom_path = get_settings().pokemon_heartgold_settings.rom_file
        rom = HeartGoldRom.open(rom_path)

        trainers = json.loads(self.get_file("trainers.json"))
        patch_gen.apply_trainer_randomization(rom, trainers)

        encounters = json.loads(self.get_file("encounters.json"))
        patch_gen.apply_encounter_randomization(rom, encounters)

        species = json.loads(self.get_file("species.json"))
        patch_gen.apply_evolution_and_stat_randomization(rom, species)

        moves = json.loads(self.get_file("moves.json"))
        patch_gen.apply_move_randomization(rom, moves)

        substitutions = json.loads(self.get_file("item_substitutions.json"))
        patch_gen.apply_local_item_substitutions(rom, substitutions)

        rom.save(target)


def build_item_substitutions(world: HeartGoldWorld) -> dict[str, str | None]:
    """`{location_key: item_key}` for every one of this player's own
    ground_item/npc_gift/hm_tm/hidden_item locations.

    A location whose placed item belongs to this *same* player gets its
    real item key -- ROM-substituted so picking it up in-game hands over
    exactly that item. A location whose item belongs to *another*
    multiworld player gets `None` (JSON `null`) instead of being skipped:
    this project has no way to deliver a real item to this player for a
    check that isn't theirs (unlike a remote item *received* from another
    player, which `client.py`'s runtime injection handles regardless of
    where it was found), and leaving the vanilla item in the ROM would
    silently hand the player a real, unearned item every time (found via a
    real playtest, 2026-08-11 -- see docs/architecture.md). `None` tells
    `patch_gen.apply_local_item_substitutions` to write the "empty"
    substitution instead (see that function's own docstring): the location
    still fires this project's flag-read check-detection correctly, but
    physically grants nothing."""
    from data.items import ITEMS
    from data.locations import LOCATIONS

    label_to_key = {data["label"]: key for key, data in ITEMS.items()}

    substitutions: dict[str, str | None] = {}
    for location in world.multiworld.get_locations(world.player):
        if location.item is None:
            continue
        location_data = LOCATIONS.get(location.name)
        if location_data is None or location_data["type"] not in _SUBSTITUTABLE_LOCATION_TYPES:
            continue
        if location.item.player != world.player:
            substitutions[location.name] = None
            continue
        item_key = label_to_key.get(location.item.name)
        if item_key is not None:
            substitutions[location.name] = item_key
    return substitutions


def generate_output(world: HeartGoldWorld, output_directory: str) -> None:
    patch = HeartGoldProcedurePatch(player=world.player, player_name=world.player_name)
    patch.write_file("trainers.json", json.dumps(world.generated_trainer_parties).encode())
    patch.write_file("encounters.json", json.dumps(world.generated_encounters).encode())
    patch.write_file("species.json", json.dumps(world.generated_species).encode())
    patch.write_file("moves.json", json.dumps(world.generated_moves).encode())
    patch.write_file("item_substitutions.json", json.dumps(build_item_substitutions(world)).encode())

    out_file_name = world.multiworld.get_out_file_name_base(world.player)
    patch.write(os.path.join(output_directory, f"{out_file_name}{patch.patch_file_ending}"))
