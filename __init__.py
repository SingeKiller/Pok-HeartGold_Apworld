# __init__.py
#
# Registers the "Pokemon HeartGold" Archipelago World (task C12): wires
# together everything already built by items.py/locations.py/regions.py/
# rules.py/options.py/species.py into the `World` subclass Archipelago's
# `worlds.AutoWorld` plugin loader actually instantiates.
#
# Unlike every other root module in this project, this file *must* import
# `worlds.AutoWorld` (to subclass `World`) -- there is no way around the
# full world-plugin autoload documented by items.py/locations.py/regions.py/
# rules.py/options.py's own docstrings for avoiding it: this file *is* the
# thing that gets autoloaded once dropped into an Archipelago `worlds/` (or
# `custom_worlds/`) folder as a package/`.apworld`. Every other root module
# deliberately avoids that import so it stays testable without a local
# Archipelago checkout; this one cannot -- tests/test_world_init.py
# accordingly needs a local Archipelago checkout too (see tests/conftest.py).
#
# Species randomization (species.py) has no Location/Item of its own yet in
# this project's v1 data model (data/locations.py only models ground items /
# hidden items / HMs-TMs / NPC gifts / badges -- wild encounters, trainer
# parties, evolutions, base stats and move stats are not placed on any
# Location, see docs/scope.md), so set_rules() below only *runs*
# species.py's randomizers (seeded from self.random, matching species.py's
# own documented contract: "the caller is expected to pass world.random ...
# here") and stores their output on `self` (generated_encounters/
# generated_trainer_parties/generated_species/generated_moves) for
# `patch_gen.py`'s `apply_trainer_randomization`/
# `apply_encounter_randomization`/`apply_evolution_and_stat_randomization`/
# `apply_move_randomization` (task M4.5, see CLAUDE.md's "building ROMS"
# section) to consume -- the same division of labour species.py's own
# module docstring describes for itself ("a later task wires these
# functions' output into the actual world").

from __future__ import annotations

import os
import sys
from typing import Any, ClassVar

# Every sibling module in this project (items.py/locations.py/regions.py/
# rules.py/options.py/species.py, and the generated data/ package) uses
# plain, absolute imports (`from data.items import ITEMS`, `from items
# import ...`, ...) so they stay importable as flat top-level modules for
# their own standalone unit tests (see e.g. items.py's/rules.py's own
# docstrings) -- exactly the "package flat à la racine du dépôt" layout
# CLAUDE.md's Repository Structure section documents as an Archipelago
# constraint, not a choice. But once this file is actually loaded by
# Archipelago as `worlds.pokemon_heartgold` (a real subpackage, whether from
# a plain folder drop or a zipimport-ed `.apworld` -- see worlds/__init__.py
# in the local Archipelago clone), those absolute imports would otherwise
# raise `ImportError: cannot import name ... from 'data'`, because nothing
# on `sys.path` resolves bare `data`/`items`/`locations` names to *this*
# package's own directory. Bootstrapping this file's own directory onto
# `sys.path` first (mirroring tests/conftest.py's own `sys.path.insert(0,
# ROOT)` for the exact same reason) fixes that without having to change any
# of those other modules' own import style, which would break their
# standalone testability.
#
# This file assumes `BaseClasses`/`worlds.AutoWorld` are already importable
# (true in a real Archipelago load, since that's what's importing it). The
# generated `data/` package is a different story: it's bundled into a real
# built `.apworld`, but in a dev/test checkout it's git-ignored and pytest's
# own package-root resolution (`_pytest.pathlib.resolve_pkg_root_and_module_
# name`, active even under `--import-mode=importlib`) can end up importing
# *this* file before any test fixture gets a chance to regenerate `data/` --
# confirmed flaky (not "never happens", an earlier revision's claim here was
# wrong): reproduces intermittently across otherwise-identical cold pytest
# runs, root-caused to Python's own namespace-package candidate walk, not to
# anything in this project's own test files.
#
# Two earlier revisions of this fix were tried and both failed differently:
# (1) an unconditional `os.path.isdir(.../data)` check broke loading a real
#     zipimport-ed `.apworld` outright: `isdir` on a path *inside* a zip is
#     always False, so the fallback fired even when `data/` was genuinely
#     present in the archive (see M3's R2 review).
# (2) a `try: import data / except ImportError: regenerate, retry` pattern
#     -- gated correctly this time on `os.path.isdir(_THIS_DIR)` itself
#     (reliably False inside a zip, unlike a path *under* it, so still
#     zip-safe) -- still failed the retry identically. Root cause: Python's
#     `FileFinder` caches the directory listing of `_THIS_DIR` the moment
#     the *first* (failing) `from data import ...` is attempted, and
#     `importlib.invalidate_caches()` (which `tests/test_data_gen.py`'s own
#     `test_data_gen_produces_importable_data_package` needs for the exact
#     same reason) did not resolve it here -- pytest's own assertion-
#     rewriting import hook sits ahead of the standard path finder and
#     appears to cache independently of it.
#
# This revision avoids a first failing import ever happening at all: the
# existence check and regeneration run *before* `data` is imported for the
# first time, gated behind the same zip-safe `os.path.isdir(_THIS_DIR)`
# (never true inside a zipimport-ed `.apworld`) so this whole block is a
# no-op there, and a real, correctly-built `.apworld` missing `data/` still
# fails loudly at the plain `from data import GAME_VERSION` below instead of
# silently trying (and failing) to run a `data_gen.py` that isn't bundled.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

if os.path.isdir(_THIS_DIR) and not os.path.isdir(os.path.join(_THIS_DIR, "data")):
    import subprocess

    subprocess.run([sys.executable, os.path.join(_THIS_DIR, "data_gen.py")], cwd=_THIS_DIR, check=True)

import settings  # noqa: E402
from BaseClasses import CollectionState, Item, Region, Tutorial  # noqa: E402
from worlds.AutoWorld import AutoWorldRegister, WebWorld, World  # noqa: E402

# Unused, but required to register HeartGoldClient with BizHawkClient (task
# C16) -- same convention worlds/pokemon_emerald/__init__.py's own `from
# .client import PokemonEmeraldClient` comment documents: AutoBizHawkClient
# Register (worlds/_bizhawk/client.py) only learns about a client the moment
# its defining module is imported, and nothing else in this file's own
# import chain ever imports client.py.
import location_flags  # noqa: E402
from client import HeartGoldClient  # noqa: E402, F401
from data import GAME_VERSION  # noqa: E402
from data.encounters import ENCOUNTERS_HEARTGOLD, ENCOUNTERS_SOULSILVER  # noqa: E402
from data.items import ITEMS  # noqa: E402
from data.locations import LOCATIONS  # noqa: E402
from data.rules import BADGES  # noqa: E402
from items import create_item, create_item_label_to_code_map  # noqa: E402
from locations import (  # noqa: E402
    SHELVED_LOCATION_TYPES,
    badge_event_item_name,
    create_location_label_to_code_map,
    create_locations,
)
from options import OPTION_GROUPS, GameVersion, Goal, HeartGoldOptions  # noqa: E402

# HeartGoldProcedurePatch itself is never referenced by name below -- the
# import's side effect (AutoPatchRegister's metaclass registers it by
# patch_file_ending at class-definition time) is what actually matters,
# same convention this file's own `from client import HeartGoldClient`
# import above already uses for the same reason.
from output_patch import HeartGoldProcedurePatch  # noqa: E402, F401
from output_patch import generate_output as write_output_patch  # noqa: E402
from regions import create_regions as build_region_graph  # noqa: E402
from rom import HEARTGOLD_US_MD5, SOULSILVER_US_MD5  # noqa: E402
from rules import set_rules as apply_exit_rules  # noqa: E402
from species import (  # noqa: E402
    disable_ohko_moves,
    neutralize_trapping_abilities,
    randomize_base_stats,
    randomize_evolutions,
    randomize_move_stats,
    randomize_move_types,
    randomize_species_types,
    randomize_trainer_parties,
    randomize_wild_encounters,
    scale_trainer_levels,
)

# HGSS's own starting region (New Bark Town, see data/regions.py / the New
# Bark Town-rooted BFS tests/test_rules.py::test_graph_connected_with_full_
# inventory already exercises).
ORIGIN_REGION_NAME = "new_bark"

# Each real-AP-location data/locations.py entry (i.e. not "badge" and not a
# SHELVED_LOCATION_TYPES type, see locations.py) carries an `original_item`
# (see locations.py's own module docstring) -- create_items() below places
# exactly that item's `HeartGoldItem` into the pool per such location, so
# the pool and the unfilled-location count always match 1:1, whatever item
# the AP fill algorithm actually ends up placing at any given location.
_NON_BADGE_LOCATION_KEYS = tuple(
    sorted(
        key
        for key, data in LOCATIONS.items()
        if data["type"] != "badge" and data["type"] not in SHELVED_LOCATION_TYPES
    )
)

_FILLER_ITEM_LABELS = tuple(sorted(data["label"] for data in ITEMS.values() if data["classification"] == "filler"))

# AP label (e.g. "MASTER_BALL", what `start_inventory`/`item_links`/
# `plando_items`/panic-fill name items by) -> `data/items.py` key (e.g.
# "master_ball", what `items.create_item` takes). Inverse of
# `create_item_label_to_code_map`'s own mapping.
_LABEL_TO_ITEM_KEY = {data["label"]: key for key, data in ITEMS.items()}

# Reachability proxies for the `goal` option (docs/scope.md: "exact
# condition TBD at implementation time" -- this is that implementation).
# data/regions.py has no Elite Four/Red trainer battle of its own to gate on
# (trainer battles aren't modeled as Locations in this project's v1 scope,
# see docs/scope.md) -- `pokemon_league_hall_of_fame` is only reachable
# through `pokemon_league_lance_room` (itself only reachable via the other
# Elite Four rooms), and `mount_silver_cave_summit` is where Red is actually
# fought in vanilla, so both stand in as the closest graph-level proxy for
# "beat them" available from data/regions.py's own exits.
_ELITE_FOUR_GOAL_REGION = "pokemon_league_hall_of_fame"
_CHAMPION_RED_GOAL_REGION = "mount_silver_cave_summit"


def _constrain_undetectable_locations(player: int, multiworld) -> None:
    """30 of 128 npc_gift/hm_tm locations have no vanilla savedata flag
    this client can read (location_flags.unsupported_location_keys() --
    a synthetic id band, see that module's own docstring). Local delivery
    still works fine there (ROM substitution); the real risk is a
    *remote* item stuck at one of these spots, which this client could
    never report as checked, permanently stalling whichever other player
    it belonged to. Constrain these locations to this player's own,
    non-progression items only -- keeps all 30 as real, randomized checks
    (unlike excluding them from the pool entirely) with no risk to anyone
    (community feedback round, 2026-08-11, see docs/architecture.md).

    "Own" includes this player's item link groups: a linked item belongs to
    the synthetic group player, and is still delivered to every group
    member, so it is not the stalled-remote case above. Excluding those
    deadlocks the fill under `link_replacement` (test_items.test_item_links)."""
    from BaseClasses import ItemClassification

    local_players = {player} | multiworld.get_player_groups(player)

    def rule(item: Item) -> bool:
        return item.player in local_players and item.classification != ItemClassification.progression

    for location_key in location_flags.unsupported_location_keys():
        multiworld.get_location(location_key, player).item_rule = rule


def _goal_rule(player: int, goal: int, badge_count: int):
    """Build the `multiworld.completion_condition[player]` callable for the
    `goal` option's chosen value (see this module's docstring above for why
    `elite_four`/`champion_red` are reachability checks rather than a
    trainer-battle check)."""
    if goal == Goal.option_n_badges:
        badge_events = tuple(badge_event_item_name(name) for name in BADGES)

        def rule(state: CollectionState) -> bool:
            return sum(state.has(event, player) for event in badge_events) >= badge_count

        return rule

    target_region = _CHAMPION_RED_GOAL_REGION if goal == Goal.option_champion_red else _ELITE_FOUR_GOAL_REGION

    def rule(state: CollectionState) -> bool:
        return state.can_reach_region(target_region, player)

    return rule


_setup_en = Tutorial(
    "Multiworld Setup Guide",
    "A guide to playing Pokémon HeartGold with Archipelago",
    "English",
    "setup_en.md",
    "setup/en",
    ["SingeKiller"],
)


class HeartGoldWebWorld(WebWorld):
    theme = "ocean"
    # A copy, not an alias: Archipelago's WebWorld/AutoWorld registration
    # appends a synthetic "Item & Location Options" group to whatever list
    # is assigned here, in place. Sharing options.py's own OPTION_GROUPS
    # object would leak that mutation back into it, corrupting it for
    # anything else in the same process that imports options.py directly
    # (e.g. tests/test_options.py) -- confirmed by reproducing the mutation.
    option_groups = list(OPTION_GROUPS)
    tutorials: list[Tutorial] = [_setup_en]


class HeartGoldSettings(settings.Group):
    """Per-machine settings (`host.yaml`'s `pokemon_heartgold_options`) --
    distinct from `HeartGoldOptions` (per-player, YAML-configured game
    options): `rom_file` is *where this machine's own copy of the ROM
    lives*, read fresh every time `HeartGoldProcedurePatch.patch()` runs
    (see `output_patch.py`'s own docstring for why the ROM itself is never
    embedded in a generated patch file)."""

    class RomFile(settings.UserFilePath):
        description = "Pokemon HeartGold or SoulSilver (USA) ROM file"
        copy_to = "Pokemon - HeartGold Version (USA).nds"
        md5s = [HEARTGOLD_US_MD5, SOULSILVER_US_MD5]

    rom_file: RomFile = RomFile(RomFile.copy_to)


# pytest's own `Package` collector (any directory with an `__init__.py`,
# including this project's own repository root once this file exists --
# see `pytest.Package`'s own docstring in the local venv's
# `_pytest/python.py`) imports this exact file once, as a setup side
# effect, before any of this project's own test fixtures get a chance to
# import it themselves (see tests/test_world_init.py's own docstring for
# the full story) -- `worlds.AutoWorld.AutoWorldRegister.__new__` refuses a
# second registration of the same `game` name outright, so drop any such
# prior registration right before (re-)defining the class below. A real
# Archipelago load only ever imports this file once per process, so this
# is a no-op there; multiple imports within one Python process (test-only)
# simply end up with the *last* one registered, which is exactly what
# `tests/test_world_init.py` (re-generating `data/` first) wants anyway.
AutoWorldRegister.world_types.pop("Pokemon HeartGold", None)


class HeartGoldWorld(World):
    """Pokemon HeartGold & SoulSilver."""

    game = "Pokemon HeartGold"
    web = HeartGoldWebWorld()
    topology_present = True

    settings_key = "pokemon_heartgold_settings"
    settings: ClassVar[HeartGoldSettings]

    options_dataclass = HeartGoldOptions
    options: HeartGoldOptions

    item_name_to_id = create_item_label_to_code_map()
    location_name_to_id = create_location_label_to_code_map()

    origin_region_name = ORIGIN_REGION_NAME

    regions: dict[str, Region]

    def create_regions(self) -> None:
        self.regions = build_region_graph(self.player, self.multiworld)
        create_locations(self.player, self.regions)

    def create_items(self) -> None:
        pool = [create_item(LOCATIONS[key]["original_item"], self.player) for key in _NON_BADGE_LOCATION_KEYS]
        self.multiworld.itempool += pool

    def create_item(self, name: str) -> Item:
        """Required AP `World` API (`start_inventory`, `item_links`,
        `plando_items`, and the panic-fill path all call this directly with
        an AP item label) -- distinct from the module-level `create_item`
        imported above, which this delegates to via `_LABEL_TO_ITEM_KEY`."""
        return create_item(_LABEL_TO_ITEM_KEY[name], self.player)

    def set_rules(self) -> None:
        apply_exit_rules(self.player, self.multiworld, self.regions)
        _constrain_undetectable_locations(self.player, self.multiworld)

        # Wild encounters genuinely differ between HeartGold and SoulSilver
        # (e.g. Route 29's morning Sentret/Rattata swap, see data_gen/
        # encounters.toml's header) -- pick the table matching the declared
        # `game_version` option before randomizing, so a SoulSilver player
        # who leaves `randomize_wild_pokemon` at its `vanilla` default gets
        # genuinely vanilla SoulSilver encounters, not HeartGold's.
        if self.options.game_version.value == GameVersion.option_soulsilver:
            version_encounters = ENCOUNTERS_SOULSILVER
        else:
            version_encounters = ENCOUNTERS_HEARTGOLD
        self.generated_encounters = randomize_wild_encounters(
            self.random, self.options.randomize_wild_pokemon.value, encounters=version_encounters
        )
        self.generated_trainer_parties = randomize_trainer_parties(
            self.random, bool(self.options.randomize_trainers.value)
        )
        self.generated_trainer_parties = scale_trainer_levels(
            self.options.trainer_level_scaling.value, trainers=self.generated_trainer_parties
        )
        self.generated_species = randomize_evolutions(self.random, self.options.randomize_evolutions.value)
        self.generated_species = randomize_base_stats(
            self.random, self.options.randomize_base_stats.value, species=self.generated_species
        )
        self.generated_species = randomize_species_types(
            self.random, bool(self.options.randomize_species_types.value), species=self.generated_species
        )
        self.generated_species = neutralize_trapping_abilities(
            bool(self.options.disable_trapping_abilities.value), species=self.generated_species
        )
        self.generated_moves = randomize_move_stats(self.random, self.options.randomize_moves.value)
        self.generated_moves = randomize_move_types(
            self.random, bool(self.options.randomize_move_types.value), moves=self.generated_moves
        )
        self.generated_moves = disable_ohko_moves(
            bool(self.options.disable_ohko_moves.value), moves=self.generated_moves
        )

        self.multiworld.completion_condition[self.player] = _goal_rule(
            self.player, self.options.goal.value, self.options.goal_badge_count.value
        )

    def get_filler_item_name(self) -> str:
        return self.random.choice(_FILLER_ITEM_LABELS)

    def fill_slot_data(self) -> dict[str, Any]:
        return {
            "game_version": GAME_VERSION["name"],
            "goal": self.options.goal.value,
            "goal_badge_count": self.options.goal_badge_count.value,
        }

    def generate_output(self, output_directory: str) -> None:
        """The real per-player output step (task M5): builds a
        `HeartGoldProcedurePatch` from this player's own `generated_*`
        randomizer output (computed in `set_rules()` above) plus local
        item substitutions, and writes it to `output_directory` as a
        `.apheartgold` file -- see `output_patch.py`'s own docstring for
        why the actual ROM patching happens later, in `.patch()`, not
        here."""
        write_output_patch(self, output_directory)
