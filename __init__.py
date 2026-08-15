# __init__.py
#
# Registers the "Pokemon HGSS" Archipelago World: wires together
# items.py/locations.py/regions.py/rules.py/options.py/species.py into
# the World subclass Archipelago's worlds.AutoWorld plugin loader
# instantiates.
#
# species.py's randomizers have no Location/Item of their own in this
# project's v1 data model -- set_rules() below runs them (seeded from
# self.random) and stores their output on self (generated_encounters/
# generated_trainer_parties/generated_species/generated_moves) for
# patch_gen.py's apply_* functions to consume at generate_output time.

from __future__ import annotations

import os
import sys
from typing import Any, ClassVar

# Every sibling module uses plain, absolute imports so they stay
# importable as flat top-level modules for their own standalone unit
# tests. Once this file is loaded by Archipelago as
# worlds.pokemon_hgss, those absolute imports would otherwise raise
# ImportError -- bootstrapping this directory onto sys.path first fixes
# that. Regenerating data/ here (if missing, dev checkout only) avoids a
# pytest collection race; see NOTES.md for the two fix attempts that
# didn't work before this one.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

if os.path.isdir(_THIS_DIR) and not os.path.isdir(os.path.join(_THIS_DIR, "data")):
    import subprocess

    subprocess.run([sys.executable, os.path.join(_THIS_DIR, "data_gen.py")], cwd=_THIS_DIR, check=True)

import settings  # noqa: E402
from BaseClasses import CollectionState, Item, Region, Tutorial  # noqa: E402
from worlds.AutoWorld import AutoWorldRegister, WebWorld, World  # noqa: E402

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
    badge_item_label,
    create_location_label_to_code_map,
    create_locations,
)
from options import OPTION_GROUPS, GameVersion, Goal, HeartGoldOptions  # noqa: E402

from output_patch import HeartGoldProcedurePatch  # noqa: E402, F401 -- import side effect only
from output_patch import generate_output as write_output_patch  # noqa: E402
from regions import create_regions as build_region_graph  # noqa: E402
from rom import HEARTGOLD_US_MD5, SOULSILVER_US_MD5  # noqa: E402
from rules import set_rules as apply_exit_rules  # noqa: E402
from species import (  # noqa: E402
    convert_trade_and_friendship_evolutions,
    disable_ohko_moves,
    neutralize_trapping_abilities,
    randomize_base_stats,
    randomize_evolutions,
    randomize_move_stats,
    randomize_move_types,
    randomize_species_types,
    randomize_starters,
    randomize_trainer_parties,
    randomize_wild_encounters,
    scale_trainer_levels,
    species_encounter_methods,
)
from universal_tracker import (  # noqa: E402
    SLOT_DATA_OPTIONS_KEY,
    build_ut_slot_data,
    load_ut_slot_data,
)

ORIGIN_REGION_NAME = "new_bark"  # HGSS's own starting region, New Bark Town

# Every real-AP-location entry contributes exactly one HeartGoldItem to
# the pool (create_items() below) so the pool and the unfilled-location
# count always match 1:1 -- an original_item's own HeartGoldItem for most
# types (type = 'badge' included: each has a real, synthetic badge_*
# original_item, see locations.py's own docstring), a random filler item
# for type = 'trainer', 'dexsanity', or 'static_pokemon' (none of the
# three has a vanilla item to displace). Only type = 'event' locations
# carry no original_item at all and never enter the real item pool (locked
# progression events, see locations.py's create_locations).
_ID_ASSIGNABLE_LOCATION_KEYS = tuple(
    sorted(
        key
        for key, data in LOCATIONS.items()
        if data["type"] != "event" and data["type"] not in SHELVED_LOCATION_TYPES
    )
)

_FILLER_ITEM_LABELS = tuple(sorted(data["label"] for data in ITEMS.values() if data["classification"] == "filler"))

# AP label -> data/items.py key. Inverse of create_item_label_to_code_map.
_LABEL_TO_ITEM_KEY = {data["label"]: key for key, data in ITEMS.items()}

# Reachability proxies for the goal option -- see NOTES.md.
_ELITE_FOUR_GOAL_REGION = "pokemon_league_hall_of_fame"
_CHAMPION_RED_GOAL_REGION = "mount_silver_cave_summit"


def _constrain_undetectable_locations(player: int, multiworld) -> None:
    """30 of 128 npc_gift/hm_tm locations have no vanilla savedata flag
    this client can read -- constrain to this player's own (incl. item
    link groups), non-progression items only. See NOTES.md for why."""
    from BaseClasses import ItemClassification

    local_players = {player} | multiworld.get_player_groups(player)

    def rule(item: Item) -> bool:
        return item.player in local_players and item.classification != ItemClassification.progression

    for location_key in location_flags.unsupported_location_keys():
        multiworld.get_location(location_key, player).item_rule = rule


def _goal_rule(player: int, goal: int, badge_count: int):
    """Build the multiworld.completion_condition[player] callable for the
    goal option's chosen value."""
    if goal == Goal.option_n_badges:
        # Badges are real, tradeable items (task "Badges comme vrais items
        # AP", 2026-08-15) -- state.has counts however many of the 16
        # badge_* items this player has actually received, from anywhere in
        # the multiworld, not a locked per-region event.
        badge_labels = tuple(badge_item_label(name) for name in BADGES)

        def rule(state: CollectionState) -> bool:
            return sum(state.has(label, player) for label in badge_labels) >= badge_count

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
    option_groups = list(OPTION_GROUPS)  # a copy, not an alias -- see NOTES.md
    tutorials: list[Tutorial] = [_setup_en]


class HeartGoldSettings(settings.Group):
    """Per-machine settings -- distinct from HeartGoldOptions (per-player,
    YAML-configured). rom_file is where this machine's own copy of the
    ROM lives, read fresh every time .patch() runs."""

    class RomFile(settings.UserFilePath):
        description = "Pokemon HeartGold or SoulSilver (USA) ROM file"
        copy_to = "Pokemon - HeartGold Version (USA).nds"
        md5s = [HEARTGOLD_US_MD5, SOULSILVER_US_MD5]

    rom_file: RomFile = RomFile(RomFile.copy_to)


# pytest's own Package collector imports this file once as a setup side
# effect before test fixtures get a chance to; AutoWorldRegister.__new__
# refuses a second registration of the same game name. Drop any prior
# registration first -- a no-op for a real Archipelago load. See NOTES.md.
AutoWorldRegister.world_types.pop("Pokemon HGSS", None)


class HeartGoldWorld(World):
    """Pokemon HeartGold & SoulSilver -- registered game name "Pokemon
    HGSS" (renamed 2026-08-15 from "Pokemon HeartGold" now that both
    versions are equally first-class; see docs/architecture.md's
    "SoulSilver support" entry)."""

    game = "Pokemon HGSS"
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

    # Universal Tracker -- see universal_tracker.py. Every logic-relevant
    # option round-trips through slot data, so UT needs no YAML.
    ut_can_gen_without_yaml = True
    is_universal_tracker: bool

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Set by UT on the MultiWorld it re-generates with; absent otherwise.
        self.is_universal_tracker = getattr(self.multiworld, "generation_is_fake", False)

    @property
    def ut_slot_data(self) -> dict[str, Any]:
        """This slot's `fill_slot_data()` output as handed back by UT for a
        re-generation; empty during a real generation."""
        passthrough = getattr(self.multiworld, "re_gen_passthrough", {})
        return passthrough.get(self.game, {})

    @staticmethod
    def interpret_slot_data(slot_data: dict[str, Any]) -> dict[str, Any]:
        """UT entry point: the return value becomes `multiworld.re_gen_
        passthrough[game]`, and returning anything at all is what tells UT
        this world can be re-generated from slot data."""
        return slot_data

    def generate_early(self) -> None:
        load_ut_slot_data(self)

        # Wild encounters must be known before create_regions()/create_items()
        # run (Dexsanity, task M3.4, scopes its locations to species that
        # genuinely appear somewhere in this seed's own table -- see
        # locations.py's create_locations) -- unlike the rest of set_rules()'s
        # ROM-only randomization, this one also has to run for a Universal
        # Tracker re-generation, since UT rebuilds the same location set
        # locally rather than reading it from the real seed. UT reproduces
        # this deterministically by re-seeding self.random identically and
        # round-tripping every option that feeds into it (game_version,
        # randomize_wild_pokemon, exclude_legendaries -- see
        # universal_tracker.TRACKED_OPTION_NAMES).
        if self.options.game_version.value == GameVersion.option_soulsilver:
            version_encounters = ENCOUNTERS_SOULSILVER
        else:
            version_encounters = ENCOUNTERS_HEARTGOLD
        self.generated_encounters = randomize_wild_encounters(
            self.random,
            self.options.randomize_wild_pokemon.value,
            encounters=version_encounters,
            exclude_legendaries=bool(self.options.exclude_legendaries.value),
        )
        self.dexsanity_species_methods = species_encounter_methods(self.generated_encounters)

    def create_regions(self) -> None:
        self.regions = build_region_graph(self.player, self.multiworld)
        create_locations(
            self.player,
            self.regions,
            trainersanity=bool(self.options.trainersanity.value),
            dexsanity=bool(self.options.dexsanity.value),
            dexsanity_species_methods=self.dexsanity_species_methods,
            legendarysanity=bool(self.options.legendarysanity.value),
        )

    def create_items(self) -> None:
        # type = 'trainer' (task M3.3) and type = 'dexsanity' (task M3.4)
        # locations have no original_item -- neither a trainer battle nor a
        # Dexsanity catch drops a vanilla item -- so they each contribute a
        # random filler item to the pool instead, and only for the entries
        # create_regions() above actually created (trainersanity/dexsanity
        # off, or -- dexsanity only -- that species absent from this seed's
        # own wild tables), so the pool size matches the created, unfilled
        # location count exactly.
        trainersanity = bool(self.options.trainersanity.value)
        dexsanity = bool(self.options.dexsanity.value)
        legendarysanity = bool(self.options.legendarysanity.value)
        pool = []
        for key in _ID_ASSIGNABLE_LOCATION_KEYS:
            data = LOCATIONS[key]
            if data["type"] == "trainer":
                if not trainersanity:
                    continue
                item_key = _LABEL_TO_ITEM_KEY[self.get_filler_item_name()]
                pool.append(create_item(item_key, self.player))
            elif data["type"] == "dexsanity":
                if not dexsanity or data["species"] not in self.dexsanity_species_methods:
                    continue
                item_key = _LABEL_TO_ITEM_KEY[self.get_filler_item_name()]
                pool.append(create_item(item_key, self.player))
            elif data["type"] == "static_pokemon":
                # No vanilla item to displace (the "reward" is the
                # encounter itself).
                if not legendarysanity:
                    continue
                item_key = _LABEL_TO_ITEM_KEY[self.get_filler_item_name()]
                pool.append(create_item(item_key, self.player))
            else:
                pool.append(create_item(data["original_item"], self.player))
        self.multiworld.itempool += pool

    def create_item(self, name: str) -> Item:
        """Required AP World API -- distinct from the module-level
        create_item imported above, which this delegates to."""
        return create_item(_LABEL_TO_ITEM_KEY[name], self.player)

    def set_rules(self) -> None:
        apply_exit_rules(self.player, self.multiworld, self.regions)
        _constrain_undetectable_locations(self.player, self.multiworld)

        self.multiworld.completion_condition[self.player] = _goal_rule(
            self.player, self.options.goal.value, self.options.goal_badge_count.value
        )

        # Everything below is ROM-only randomization for `generate_output()`
        # -- no v1 Location is gated on it (docs/scope.md; generated_encounters
        # is the one exception, and is already computed in generate_early()
        # since Dexsanity's location set depends on it), and a Universal
        # Tracker re-run never writes a ROM, so skip it there.
        if self.is_universal_tracker:
            return

        self.generated_starters = randomize_starters(
            self.random,
            bool(self.options.randomize_starters.value),
            exclude_legendaries=bool(self.options.exclude_legendaries.value),
        )
        self.generated_trainer_parties = randomize_trainer_parties(
            self.random, bool(self.options.randomize_trainers.value)
        )
        self.generated_trainer_parties = scale_trainer_levels(
            self.options.trainer_level_scaling.value, trainers=self.generated_trainer_parties
        )
        self.generated_species = randomize_evolutions(self.random, self.options.randomize_evolutions.value)
        self.generated_species = convert_trade_and_friendship_evolutions(
            self.generated_species,
            bool(self.options.convert_trade_evolutions.value),
            self.options.trade_evolution_level.value,
        )
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

    def get_filler_item_name(self) -> str:
        return self.random.choice(_FILLER_ITEM_LABELS)

    def fill_slot_data(self) -> dict[str, Any]:
        # "game_version" here is data/'s GAME_VERSION constant, not the
        # option of the same name (that's in the nested snapshot, see
        # universal_tracker.py).
        return {
            "game_version": GAME_VERSION["name"],
            "goal": self.options.goal.value,
            "goal_badge_count": self.options.goal_badge_count.value,
            "fast_text_speed": bool(self.options.fast_text_speed.value),
            "skip_battle_animations": bool(self.options.skip_battle_animations.value),
            "reusable_tms": bool(self.options.reusable_tms.value),
            "death_link": bool(self.options.death_link.value),
            SLOT_DATA_OPTIONS_KEY: build_ut_slot_data(self),
        }

    def generate_output(self, output_directory: str) -> None:
        write_output_patch(self, output_directory)
