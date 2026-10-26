from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from typing import Any, ClassVar

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

if os.path.isdir(_THIS_DIR) and not os.path.isdir(os.path.join(_THIS_DIR, "data")):
    import subprocess

    subprocess.run([sys.executable, os.path.join(_THIS_DIR, "data_gen.py")], cwd=_THIS_DIR, check=True)

import settings
from BaseClasses import CollectionState, Item, Region, Tutorial
from Options import OptionError
from worlds.AutoWorld import AutoWorldRegister, WebWorld, World

import location_flags
from client import HeartGoldClient
from data import GAME_VERSION
from data.encounters import ENCOUNTERS_HEARTGOLD, ENCOUNTERS_SOULSILVER
from data.items import ITEMS
from data.locations import LOCATIONS
from data.rules import BADGES
from items import create_item, create_item_label_to_code_map, create_item_name_groups
from locations import (
    DOWSING_MACHINE_ITEM_LABEL,
    POWER_PLANT_PRERESTORED_SKIPPED_LOCATION_KEYS,
    SHELVED_LOCATION_TYPES,
    badge_item_label,
    create_location_label_to_code_map,
    create_locations,
    DEXSANITY_UNUSABLE_ZONE_METHODS,
    dexsanity_source_requirements,
    dexsanity_sources_within_regions,
    location_region_key,
)
from options import OPTION_GROUPS, GameVersion, Goal, HeartGoldOptions

from output_patch import HeartGoldProcedurePatch
from output_patch import generate_output as write_output_patch
from regions import create_regions as build_region_graph
from regions import johto_only_excluded_region_keys
from rom import HEARTGOLD_US_MD5, SOULSILVER_US_MD5
from rules import MAGNET_TRAIN_PASS_ITEM_LABEL
from rules import set_rules as apply_exit_rules
from species import (
    convert_trade_and_friendship_evolutions,
    ensure_evolution_moves_learnable,
    disable_ohko_moves,
    neutralize_trapping_abilities,
    randomize_base_stats,
    randomize_evolutions,
    randomize_learnsets,
    randomize_move_categories,
    randomize_move_stats,
    randomize_move_types,
    randomize_species_types,
    randomize_starters,
    randomize_tm_hm_moves,
    randomize_trainer_parties,
    randomize_type_chart,
    randomize_wild_encounters,
    scale_trainer_levels,
    scale_trainer_levels_by_sphere,
    species_encounter_sources,
)
from rom.encounterdata import zone_method_is_written
from universal_tracker import (
    SLOT_DATA_OPTIONS_KEY,
    build_ut_slot_data,
    load_ut_slot_data,
)

ORIGIN_REGION_NAME = "new_bark"

_ID_ASSIGNABLE_LOCATION_KEYS = tuple(
    sorted(
        key
        for key, data in LOCATIONS.items()
        if data["type"] != "event" and data["type"] not in SHELVED_LOCATION_TYPES
    )
)

_FILLER_ITEM_LABELS = tuple(sorted(data["label"] for data in ITEMS.values() if data["classification"] == "filler"))

_LABEL_TO_ITEM_KEY = {data["label"]: key for key, data in ITEMS.items()}

_ELITE_FOUR_GOAL_REGION = "pokemon_league_hall_of_fame"
_CHAMPION_RED_GOAL_REGION = "mount_silver_cave_summit"

_JOHTO_BADGE_COUNT = 8


def _compute_region_spheres(multiworld, player: int, region_keys) -> dict[str, int]:
    from BaseClasses import CollectionState

    state = CollectionState(multiworld)
    remaining = set(region_keys)
    result: dict[str, int] = {}

    def _record_reachable(sphere_index: int) -> None:
        for region_key in list(remaining):
            if state.can_reach_region(region_key, player):
                result[region_key] = sphere_index
                remaining.discard(region_key)

    _record_reachable(0)
    locations = set(multiworld.get_filled_locations())
    sphere_index = 0
    while locations and remaining:
        sphere_index += 1
        newly_reachable = {location for location in locations if location.can_reach(state)}
        if not newly_reachable:
            break
        for location in newly_reachable:
            state.collect(location.item, True, location)
        locations -= newly_reachable
        _record_reachable(sphere_index)

    return result


_GYM_LEADER_REGION_OVERRIDES = {"leader_clair_clair": "blackthorn_gym"}


def _sphere_map_for_type(
    multiworld, player: int, location_type: str, excluded_region_keys: frozenset[str] = frozenset()
) -> dict[str, int]:
    trainer_regions = {
        data["trainer"]: _GYM_LEADER_REGION_OVERRIDES.get(data["trainer"], data["region"])
        for data in LOCATIONS.values()
        if data["type"] == location_type
    }
    trainer_regions = {
        trainer_key: region_key
        for trainer_key, region_key in trainer_regions.items()
        if region_key not in excluded_region_keys
    }
    region_spheres = _compute_region_spheres(multiworld, player, set(trainer_regions.values()))
    return {
        trainer_key: region_spheres[region_key]
        for trainer_key, region_key in trainer_regions.items()
        if region_key in region_spheres
    }


def _constrain_undetectable_locations(player: int, multiworld, excluded_region_keys: frozenset[str]) -> None:
    from BaseClasses import ItemClassification

    local_players = {player} | multiworld.get_player_groups(player)

    def rule(item: Item) -> bool:
        return item.player in local_players and not (item.classification & ItemClassification.progression)

    for location_key in location_flags.unsupported_location_keys():
        if LOCATIONS[location_key]["region"] in excluded_region_keys:
            continue
        multiworld.get_location(location_key, player).item_rule = rule


def _goal_rule(player: int, goal: int, badge_count: int):
    if goal == Goal.option_n_badges:
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
    option_groups = list(OPTION_GROUPS)
    tutorials: list[Tutorial] = [_setup_en]


def _validate_rom_setting(path: str, version: str, setting: str) -> None:
    from rom import describe_rom, identify_rom

    with open(path, "rb") as rom_file:
        data = rom_file.read()
    found, _ = identify_rom(data)
    if found == version:
        return
    names = {"heartgold": "HeartGold (USA, game code IPKE)", "soulsilver": "SoulSilver (USA, game code IPGE)"}
    raise ValueError(
        f"{path} is {describe_rom(data) if found is None else 'Pokemon ' + names[found]}, "
        f"but this patch needs an unmodified Pokemon {names[version]}. Delete that file (or fix "
        f"pokemon_heartgold_settings.{setting} in host.yaml), then open the patch again to pick the right ROM."
    )


class HeartGoldSettings(settings.Group):
    """Per-machine settings -- distinct from HeartGoldOptions (per-player,
    YAML-configured). Two separate rom_file settings, not one shared
    between both versions (real player report, 2026-08-17): a single
    shared `rom_file` made it impossible to configure a HeartGold ROM and
    a SoulSilver ROM at the same time -- switching which version you were
    testing/generating for meant deleting/re-pointing the setting (and
    the copied ROM file, since both versions defaulted to the same
    "HeartGold" filename) every time. Same two-setting pattern other
    multi-version worlds already use (e.g. pokemon_bw's black_rom/
    white_rom, pokemon_frlg's firered_rom_file/leafgreen_rom_file).
    output_patch.py's own .patch() picks whichever of these two matches
    this patch's own declared game_version, instead of always reading one
    shared field. Breaking host.yaml change: an old `rom_file:` entry is
    simply ignored now: reconfigure with `heartgold_rom_file`/
    `soulsilver_rom_file` instead."""

    class HeartGoldRomFile(settings.UserFilePath):
        description = "Pokemon HeartGold (USA) ROM file"
        copy_to = "Pokemon - HeartGold Version (USA).nds"
        md5s = [HEARTGOLD_US_MD5]

        @classmethod
        def validate(cls, path: str) -> None:
            _validate_rom_setting(path, "heartgold", "heartgold_rom_file")

    class SoulSilverRomFile(settings.UserFilePath):
        description = "Pokemon SoulSilver (USA) ROM file"
        copy_to = "Pokemon - SoulSilver Version (USA).nds"
        md5s = [SOULSILVER_US_MD5]

        @classmethod
        def validate(cls, path: str) -> None:
            _validate_rom_setting(path, "soulsilver", "soulsilver_rom_file")

    heartgold_rom_file: HeartGoldRomFile = HeartGoldRomFile(HeartGoldRomFile.copy_to)
    soulsilver_rom_file: SoulSilverRomFile = SoulSilverRomFile(SoulSilverRomFile.copy_to)


AutoWorldRegister.world_types.pop("Pokemon HGSS Singe", None)


def _generating_world_version() -> str | None:
    import pkgutil

    try:
        data = pkgutil.get_data(__name__, "archipelago.json")
    except (OSError, ValueError):
        return None
    return None if data is None else json.loads(data.decode("utf-8")).get("world_version")


class HeartGoldWorld(World):
    """Pokemon HeartGold and SoulSilver (US): wild encounters, trainers,
    items, gifts, TMs/HMs and more, randomized and tied into the multiworld
    logic."""

    game = "Pokemon HGSS Singe"
    web = HeartGoldWebWorld()
    topology_present = True

    settings_key = "pokemon_heartgold_settings"
    settings: ClassVar[HeartGoldSettings]

    options_dataclass = HeartGoldOptions
    options: HeartGoldOptions

    item_name_to_id = create_item_label_to_code_map()
    location_name_to_id = create_location_label_to_code_map()
    item_name_groups = create_item_name_groups()

    origin_region_name = ORIGIN_REGION_NAME

    regions: dict[str, Region]

    ut_can_gen_without_yaml = True
    is_universal_tracker: bool

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.is_universal_tracker = getattr(self.multiworld, "generation_is_fake", False)

    @property
    def slot_auth(self) -> bytes:
        digest = hashlib.sha256(f"poke_hgss:{self.multiworld.seed_name}:{self.player}".encode()).digest()
        return digest[:16]

    def modify_multidata(self, multidata: dict[str, Any]) -> None:
        connect_names = multidata["connect_names"]
        connect_names[base64.b64encode(self.slot_auth).decode("ascii")] = connect_names[self.player_name]

    @property
    def ut_slot_data(self) -> dict[str, Any]:
        passthrough = getattr(self.multiworld, "re_gen_passthrough", {})
        return passthrough.get(self.game, {})

    @staticmethod
    def interpret_slot_data(slot_data: dict[str, Any]) -> dict[str, Any]:
        return slot_data

    def generate_early(self) -> None:
        load_ut_slot_data(self)

        if bool(self.options.johto_only.value) and self.options.goal.value == Goal.option_champion_red:
            raise OptionError(
                f"{self.player_name}: goal champion_red cannot be reached with johto_only "
                "(Mt. Silver opens from Kanto); use elite_four or n_badges."
            )

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
        allowed_methods = set(self.options.dexsanity_encounter_types.value)
        self.dexsanity_species_sources = species_encounter_sources(
            self.generated_encounters,
            source_filter=lambda zone_key, method: (
                ("headbutt" if method == "headbutt_secret" else method) in allowed_methods
                and zone_method_is_written(zone_key, method)
                and (zone_key, method) not in DEXSANITY_UNUSABLE_ZONE_METHODS
            ),
        )

        self.generated_start_location_town: str | None = None
        if bool(self.options.randomize_start_location.value):
            self.generated_start_location_town = self.options.starting_town.current_key
            self.origin_region_name = self.generated_start_location_town

    def create_regions(self) -> None:
        self._soulsilver = self.options.game_version.value == GameVersion.option_soulsilver
        self._excluded_region_keys = (
            johto_only_excluded_region_keys(self._soulsilver) if bool(self.options.johto_only.value) else frozenset()
        )
        self.regions = build_region_graph(
            self.player,
            self.multiworld,
            excluded_region_keys=self._excluded_region_keys,
        )
        available_items = None
        if self._excluded_region_keys:
            available_items = {
                data["original_item"]
                for data in LOCATIONS.values()
                if data.get("original_item")
                and location_region_key(data, self._soulsilver) not in self._excluded_region_keys
            }
        self.dexsanity_species_sources = dexsanity_sources_within_regions(
            self.dexsanity_species_sources, self.regions, available_items
        )
        self._trainer_keys = None
        trainer_pool = sorted(
            key for key, data in LOCATIONS.items()
            if data["type"] == "trainer"
            and location_region_key(data, self._soulsilver) not in self._excluded_region_keys
        )
        if self.options.trainersanity_count.value < len(trainer_pool):
            self._trainer_keys = frozenset(self.random.sample(trainer_pool, self.options.trainersanity_count.value))
        species = sorted(self.dexsanity_species_sources)
        if self.options.dexsanity_count.value < len(species):
            keep = set(self.random.sample(species, self.options.dexsanity_count.value))
            self.dexsanity_species_sources = {s: v for s, v in self.dexsanity_species_sources.items() if s in keep}
        create_locations(
            self.player,
            self.regions,
            trainersanity=bool(self.options.trainersanity.value),
            dexsanity=bool(self.options.dexsanity.value),
            dexsanity_species_sources=self.dexsanity_species_sources,
            legendarysanity=bool(self.options.legendarysanity.value),
            hidden_items_require_dowsing_machine=bool(self.options.hidden_items_require_dowsing_machine.value),
            excluded_region_keys=self._excluded_region_keys,
            bicycle_enabled=bool(self.options.randomize_bicycle.value),
            power_plant_prerestored=bool(self.options.magnet_train.value),
            soulsilver=self._soulsilver,
            trainer_keys=self._trainer_keys,
        )

    def create_items(self) -> None:
        trainersanity = bool(self.options.trainersanity.value)
        dexsanity = bool(self.options.dexsanity.value)
        legendarysanity = bool(self.options.legendarysanity.value)
        bicycle_enabled = bool(self.options.randomize_bicycle.value)
        power_plant_prerestored = bool(self.options.magnet_train.value)
        pool = []
        for key in _ID_ASSIGNABLE_LOCATION_KEYS:
            data = LOCATIONS[key]
            if location_region_key(data, self._soulsilver) in self._excluded_region_keys:
                continue
            if key == "goldenrod_bike_shop_bicycle" and not bicycle_enabled:
                continue
            if power_plant_prerestored and key in POWER_PLANT_PRERESTORED_SKIPPED_LOCATION_KEYS:
                continue
            if data["type"] == "trainer":
                if not trainersanity or (self._trainer_keys is not None and key not in self._trainer_keys):
                    continue
                item_key = _LABEL_TO_ITEM_KEY[self.get_filler_item_name()]
                pool.append(create_item(item_key, self.player))
            elif data["type"] == "dexsanity":
                if not dexsanity or data["species"] not in self.dexsanity_species_sources:
                    continue
                item_key = _LABEL_TO_ITEM_KEY[self.get_filler_item_name()]
                pool.append(create_item(item_key, self.player))
            elif data["type"] == "static_pokemon":
                if not legendarysanity:
                    continue
                item_key = _LABEL_TO_ITEM_KEY[self.get_filler_item_name()]
                pool.append(create_item(item_key, self.player))
            else:
                pool.append(create_item(data["original_item"], self.player))

        if bool(self.options.hidden_items_require_dowsing_machine.value):
            from BaseClasses import ItemClassification

            for item in pool:
                if item.name == DOWSING_MACHINE_ITEM_LABEL:
                    item.classification |= ItemClassification.progression
                    break

        if not bool(self.options.magnet_train.value):
            from BaseClasses import ItemClassification

            for item in pool:
                if item.name == MAGNET_TRAIN_PASS_ITEM_LABEL:
                    item.classification = ItemClassification.useful
                    break

        if not bicycle_enabled:
            self.multiworld.push_precollected(create_item("bicycle", self.player))

        self.multiworld.itempool += pool

    def create_item(self, name: str) -> Item:
        return create_item(_LABEL_TO_ITEM_KEY[name], self.player)

    def set_rules(self) -> None:
        apply_exit_rules(
            self.player,
            self.multiworld,
            self.regions,
            magnet_train=bool(self.options.magnet_train.value),
            require_flash=bool(self.options.require_flash.value),
        )
        _constrain_undetectable_locations(self.player, self.multiworld, self._excluded_region_keys)

        goal_badge_count = self.options.goal_badge_count.value
        if self._excluded_region_keys and goal_badge_count > _JOHTO_BADGE_COUNT:
            goal_badge_count = _JOHTO_BADGE_COUNT
        self.multiworld.completion_condition[self.player] = _goal_rule(
            self.player, self.options.goal.value, goal_badge_count
        )

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
        if not bool(self.options.sphere_based_trainer_leveling.value):
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
        self.generated_species = randomize_learnsets(
            self.random, bool(self.options.randomize_learnsets.value), species=self.generated_species
        )
        self.generated_species = ensure_evolution_moves_learnable(self.generated_species)
        self.generated_moves = randomize_move_stats(self.random, self.options.randomize_moves.value)
        self.generated_moves = randomize_move_types(
            self.random, bool(self.options.randomize_move_types.value), moves=self.generated_moves
        )
        self.generated_moves = randomize_move_categories(
            self.random, bool(self.options.randomize_move_categories.value), moves=self.generated_moves
        )
        self.generated_moves = disable_ohko_moves(
            bool(self.options.disable_ohko_moves.value), moves=self.generated_moves
        )
        self.generated_tm_hm_moves = randomize_tm_hm_moves(
            self.random, bool(self.options.randomize_tm_moves.value)
        )
        self.generated_type_chart = randomize_type_chart(
            self.random, bool(self.options.randomize_type_chart.value)
        )

    def get_filler_item_name(self) -> str:
        return self.random.choice(_FILLER_ITEM_LABELS)

    def fill_slot_data(self) -> dict[str, Any]:
        return {
            "game_version": GAME_VERSION["name"],
            "goal": self.options.goal.value,
            "goal_badge_count": self.options.goal_badge_count.value,
            "fast_text_speed": bool(self.options.fast_text_speed.value),
            "skip_battle_animations": bool(self.options.skip_battle_animations.value),
            "running_shoes_at_start": bool(self.options.running_shoes_at_start.value),
            "map_card_at_start": bool(self.options.map_card_at_start.value),
            "fly_points_at_start": bool(self.options.fly_points_at_start.value),
            "item_received_messages": bool(self.options.item_received_messages.value),
            "reusable_tms": bool(self.options.reusable_tms.value),
            "death_link": bool(self.options.death_link.value),
            "dexsanity_trigger": self.options.dexsanity_trigger.current_key,
            "starting_money": self.options.starting_money.value,
            "randomize_start_location": bool(self.options.randomize_start_location.value),
            "starting_town": self.generated_start_location_town,
            "magnet_train": bool(self.options.magnet_train.value),
            "remote_items": bool(self.options.remote_items.value),
            "world_version": _generating_world_version(),
            "dexsanity_logic": self._dexsanity_logic_for_trackers(),
            SLOT_DATA_OPTIONS_KEY: build_ut_slot_data(self),
        }

    def _dexsanity_logic_for_trackers(self) -> dict[str, list[list]]:
        result: dict[str, list[list]] = {}
        for location in self.multiworld.get_locations(self.player):
            data = LOCATIONS.get(location.name)
            if location.address is None or data is None or data["type"] != "dexsanity":
                continue
            sources = self.dexsanity_species_sources.get(data["species"], ())
            requirements = sorted(
                {req for source in sources for req in dexsanity_source_requirements(data["species"], source)}
            )
            parent = location.parent_region.name
            result[str(location.address)] = [
                [region, list(items), sorted(set(regions) | {parent})] for region, items, regions in requirements
            ]
        return result

    def generate_output(self, output_directory: str) -> None:
        if bool(self.options.sphere_based_trainer_leveling.value):
            bonus = self.options.sphere_based_trainer_leveling_bonus.value
            for location_type in ("trainer", "badge"):
                trainer_sphere = _sphere_map_for_type(
                    self.multiworld, self.player, location_type, self._excluded_region_keys
                )
                self.generated_trainer_parties = scale_trainer_levels_by_sphere(
                    self.generated_trainer_parties, trainer_sphere, bonus
                )
        write_output_patch(self, output_directory)
