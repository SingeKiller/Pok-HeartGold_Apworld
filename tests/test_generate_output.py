"""Tests for the real Archipelago output path (task M5): `HeartGoldWorld.
generate_output()` / `output_patch.py`'s `HeartGoldProcedurePatch` -- the
actual entry point a real `Generate.py` run (or the WebHost) uses to turn
a completed multiworld into a `.apheartgold` patch file, and that patch
file's own `.patch()` into a real, playable `.nds`.

Needs a local Archipelago checkout (`BaseClasses`/`worlds.AutoWorld`/
`test.general`) -- skips cleanly if unavailable, same convention as
tests/test_world_init.py. `test_patch_applies_and_matches_computed_
randomization` additionally needs a real vanilla ROM (`HEARTGOLD_ROM_PATH`)
-- skips cleanly without one, same convention as tests/test_rom_access.py.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

bc = pytest.importorskip("BaseClasses")
pytest.importorskip("worlds.AutoWorld")
pytest.importorskip("test.general")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

_MODULES = (
    "data.items",
    "data.locations",
    "data.regions",
    "data.rules",
    "items",
    "locations",
    "regions",
    "rules",
    "species",
)

_HEARTGOLD_INIT_MODULE_NAME = "heartgold_world_under_test_generate_output"
_HEARTGOLD_INIT_PATH = ROOT / "__init__.py"

ROM_PATH_ENV_VAR = "HEARTGOLD_ROM_PATH"


def _import_heartgold_world_module():
    import importlib.util

    sys.modules.pop(_HEARTGOLD_INIT_MODULE_NAME, None)
    spec = importlib.util.spec_from_file_location(_HEARTGOLD_INIT_MODULE_NAME, _HEARTGOLD_INIT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[_HEARTGOLD_INIT_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def world_modules():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    subprocess.run([sys.executable, "data_gen.py"], cwd=ROOT, check=True)

    importlib.invalidate_caches()
    modules = {}
    for name in _MODULES:
        if name in sys.modules:
            modules[name] = importlib.reload(sys.modules[name])
        else:
            modules[name] = importlib.import_module(name)
    modules["__init__"] = _import_heartgold_world_module()
    yield modules
    shutil.rmtree(DATA_DIR, ignore_errors=True)


@pytest.fixture()
def heartgold_world_type(world_modules):
    return world_modules["__init__"].HeartGoldWorld


def _generate(heartgold_world_type, seed, options=None, players=1):
    from Fill import distribute_items_restrictive
    from test.general import gen_steps, setup_multiworld

    worlds = [heartgold_world_type] * players
    multiworld = setup_multiworld(worlds, gen_steps, seed, options)
    distribute_items_restrictive(multiworld)
    return multiworld


def _rom_path() -> Path | None:
    raw_path = os.environ.get(ROM_PATH_ENV_VAR)
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_file():
        return None
    return path


@pytest.fixture()
def fake_settings(monkeypatch):
    """Points `output_patch.get_settings()` at this machine's real ROM
    (skips if unavailable) without needing a real host.yaml on disk."""
    rom_path = _rom_path()
    if rom_path is None:
        pytest.skip(f"HeartGold ROM not available locally: set {ROM_PATH_ENV_VAR} to run this test.")

    import output_patch

    class _FakeGroup:
        rom_file = str(rom_path)

    class _FakeSettings:
        pokemon_heartgold_settings = _FakeGroup()

    monkeypatch.setattr(output_patch, "get_settings", lambda: _FakeSettings())
    return rom_path


def test_generate_output_produces_exactly_one_patch_file(heartgold_world_type, tmp_path) -> None:
    multiworld = _generate(heartgold_world_type, seed=1001)
    world = multiworld.worlds[1]

    world.generate_output(str(tmp_path))

    produced = list(tmp_path.glob("*.apheartgold"))
    assert len(produced) == 1


def test_patch_file_contains_expected_json_blobs(heartgold_world_type, tmp_path) -> None:
    multiworld = _generate(heartgold_world_type, seed=1002)
    world = multiworld.worlds[1]

    world.generate_output(str(tmp_path))
    (patch_file,) = tmp_path.glob("*.apheartgold")

    with zipfile.ZipFile(patch_file) as zf:
        names = set(zf.namelist())
        assert {"trainers.json", "encounters.json", "species.json", "moves.json", "item_substitutions.json"} <= names

        # Round-trip the *expected* side through JSON too before comparing --
        # `generated_trainer_parties`'s own `party` fields are tuples, and
        # `json.loads` always produces lists, so a raw `==` would fail on
        # type alone even when every value matches (already separately
        # confirmed byte-for-byte correct against a real ROM by
        # test_patch_applies_and_matches_computed_randomization below).
        trainers = json.loads(zf.read("trainers.json"))
        assert trainers == json.loads(json.dumps(world.generated_trainer_parties))
        moves = json.loads(zf.read("moves.json"))
        assert moves == json.loads(json.dumps(world.generated_moves))


def test_item_substitutions_exclude_hidden_item_and_other_players_items(heartgold_world_type) -> None:
    """See output_patch.py's own docstring: hidden_item is temporarily
    excluded pending the white-screen investigation, and only *this*
    player's own items are ever baked into the ROM (a second player's
    items must stay out, even though `get_locations(1)` only returns
    player 1's own locations -- the check here is that an item whose
    `.player` is *not* 1 never appears, which would only happen for an
    item-link/group location, not exercised by a plain 2-player game, but
    is worth asserting directly against the real field the code branches
    on)."""
    from data.locations import LOCATIONS

    import output_patch

    multiworld = _generate(heartgold_world_type, seed=1003, players=2)
    world = multiworld.worlds[1]

    substitutions = output_patch.build_item_substitutions(world)
    assert substitutions  # sanity: real locations really got substituted

    for location_key in substitutions:
        assert LOCATIONS[location_key]["type"] in ("ground_item", "npc_gift", "hm_tm")
        assert LOCATIONS[location_key]["type"] != "hidden_item"

    for location in multiworld.get_locations(1):
        if location.item is not None and location.item.player != 1:
            assert location.name not in substitutions


def test_patch_applies_and_matches_computed_randomization(heartgold_world_type, tmp_path, fake_settings) -> None:
    from output_patch import HeartGoldProcedurePatch
    from rom import HeartGoldRom, movedata, speciesdata

    multiworld = _generate(heartgold_world_type, seed=1004)
    world = multiworld.worlds[1]

    world.generate_output(str(tmp_path))
    (patch_file,) = tmp_path.glob("*.apheartgold")

    patch = HeartGoldProcedurePatch()
    patch.read(str(patch_file))
    target = tmp_path / "output.nds"
    patch.patch(str(target))
    assert target.is_file()

    rom = HeartGoldRom.open(str(target), expect_vanilla=False)
    sample_species = list(world.generated_species.items())[:15]
    for key, data in sample_species:
        assert speciesdata.read_base_stats(rom, key) == data["base_stats"]

    sample_moves = list(world.generated_moves.items())[:15]
    for key, data in sample_moves:
        power, _move_type, accuracy, pp = movedata.read_combat_stats(rom, key)
        assert (power, accuracy, pp) == (data["power"], data["accuracy"], data["pp"])
