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
# generated_trainer_parties/generated_species/generated_moves/
# generated_tm_hm_moves/generated_type_chart) for patch_gen.py's apply_*
# functions to consume at generate_output time.

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
    DOWSING_MACHINE_ITEM_LABEL,
    SHELVED_LOCATION_TYPES,
    badge_item_label,
    create_location_label_to_code_map,
    create_locations,
)
from options import OPTION_GROUPS, GameVersion, Goal, HeartGoldOptions  # noqa: E402

from output_patch import HeartGoldProcedurePatch  # noqa: E402, F401 -- import side effect only
from output_patch import generate_output as write_output_patch  # noqa: E402
from regions import KANTO_REGION_KEYS  # noqa: E402
from regions import create_regions as build_region_graph  # noqa: E402
from rom import HEARTGOLD_US_MD5, SOULSILVER_US_MD5  # noqa: E402
from rules import set_rules as apply_exit_rules  # noqa: E402
from species import (  # noqa: E402
    convert_trade_and_friendship_evolutions,
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

# johto_only: only this many badges exist once Kanto's 8 are excluded.
_JOHTO_BADGE_COUNT = 8


def _compute_region_spheres(multiworld, player: int, region_keys) -> dict[str, int]:
    """0-indexed sphere at which each of `region_keys` (this player's own
    region-graph keys) first becomes reachable, from the real, fully-
    filled multiworld's own item-collection order -- not vanilla story
    position. A region string absent from the result was never reached
    (dead-end past an unreachable item, or a graph bug). Mirrors
    MultiWorld.get_spheres()'s own sweep, but tracks region reachability
    instead of location reachability."""
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


# A `badge` location's own `region` is where its flag is *detected*, which
# for 15 of 16 Gym Leaders is simply their own gym -- Clair is the one
# exception (her badge is detected at Dragon's Den Shrine's puzzle-
# completion cutscene, not her real battle at Blackthorn Gym, see
# data_gen/locations.toml's own note on this).
_GYM_LEADER_REGION_OVERRIDES = {"leader_clair_clair": "blackthorn_gym"}


def _sphere_map_for_type(
    multiworld, player: int, location_type: str, excluded_region_keys: frozenset[str] = frozenset()
) -> dict[str, int]:
    """data/trainers.py key -> 0-indexed sphere, for every `location_type`
    LOCATIONS entry's own `trainer`/`region` fields (`_GYM_LEADER_REGION_
    OVERRIDES` applied for `location_type == "badge"`), joined against
    `_compute_region_spheres` -- used by sphere-based trainer leveling.
    Independent of the `trainersanity`/badge-always-on status: every
    trainer/Leader has a region regardless of whether its own Location
    was actually created this seed. A trainer whose region is never
    reached is simply absent from the result. `excluded_region_keys`
    (`johto_only`'s KANTO_REGION_KEYS, or empty) must be passed whenever
    it was also passed to `create_regions` -- a trainer/Leader whose own
    region was skipped there has no matching Region object at all, and
    `_compute_region_spheres`'s `state.can_reach_region` would otherwise
    raise `KeyError` trying to look one up (real bug, found by code
    review 2026-08-17: `johto_only` + `sphere_based_trainer_leveling`
    crashed generation after a full multiworld fill)."""
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
    """30 of 128 npc_gift/hm_tm locations have no vanilla savedata flag
    this client can read -- constrain to this player's own (incl. item
    link groups), non-progression items only. See NOTES.md for why.
    `excluded_region_keys` (`johto_only`'s KANTO_REGION_KEYS, or empty)
    skips any of these whose own region was never created -- 5 of the 30
    are in Kanto."""
    from BaseClasses import ItemClassification

    local_players = {player} | multiworld.get_player_groups(player)

    def rule(item: Item) -> bool:
        return item.player in local_players and item.classification != ItemClassification.progression

    for location_key in location_flags.unsupported_location_keys():
        if LOCATIONS[location_key]["region"] in excluded_region_keys:
            continue
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
        # dexsanity_encounter_types restricts which methods count at all --
        # a species left with no allowed method after this filter simply
        # gets no Dexsanity location this seed (same as one this seed's
        # own wild tables never place anywhere). A no-op when every method
        # is still allowed (the option's own default).
        allowed_methods = set(self.options.dexsanity_encounter_types.value)
        self.dexsanity_species_methods = {
            species: methods & allowed_methods
            for species, methods in self.dexsanity_species_methods.items()
            if methods & allowed_methods
        }

        self.generated_start_location_town: str | None = None
        if bool(self.options.randomize_start_location.value):
            # Archipelago's own Choice option machinery already resolves
            # a YAML "random" value into one real option before this
            # runs -- self.options.starting_town is never literally
            # "random" here, so no extra RNG handling is needed.
            self.generated_start_location_town = self.options.starting_town.current_key
            # The physical spawn point is always inside Elm's Lab (see
            # rom/startlocation.py), and its one door warps straight to
            # `generated_start_location_town` -- the player never sets
            # foot in New Bark's own outdoor map at all when this option
            # is on. Overriding the *instance* attribute (shadowing the
            # class-level default set below) makes CollectionState.
            # update_reachable_regions() (BaseClasses.py) treat that town
            # as the free, always-reachable region instead of New Bark, so
            # the fill algorithm's own logic actually matches where the
            # player starts rather than just the physical ROM patch --
            # closing the "known gap" flagged in StartingTown's own
            # docstring. `starting_town`'s option keys are already the
            # exact same snake_case strings as their data/regions.py
            # region keys (see rom/startlocation.py's TOWN_MAP_IDS), so no
            # separate key/region mapping table is needed. New Bark's own
            # region (and Elm's Lab's) isn't cut off by this -- it's still
            # reachable the normal way, by walking there from wherever the
            # player actually starts, just no longer free.
            self.origin_region_name = self.generated_start_location_town

    def _enabled_menu_unlocks(self) -> frozenset[str]:
        """The set of `randomize_bag`/`randomize_trainer_card`/
        `randomize_pokedex`/`randomize_pokegear`/`randomize_save_button`/
        `randomize_options_button`/`randomize_bicycle` option keys that
        are actually turned on for this player -- 7 independent Toggle
        options (task "randomize_menu_unlocks" per-item split,
        2026-08-17), combined back into the single frozenset
        `locations.create_locations`/`create_items` (below) and
        `fill_slot_data` all expect, so the rest of the pipeline doesn't
        need to know these are 7 separate options rather than one
        multi-select. `bicycle` is included here (it shares the same
        per-key location-gating mechanism) even though it's otherwise a
        completely different delivery mechanism than the other 6 (a
        plain real npc_gift item, not a pause-menu-icon flag -- see
        options.RandomizeBicycle's own docstring); client.py's own
        `_apply_menu_unlock_gating`/`_apply_start_location_flags` simply
        never look up a "bicycle" key in their own 6-entry flag map, so
        including it in the slot_data list they read is harmless."""
        option_key_to_option = {
            "bag": self.options.randomize_bag,
            "trainer_card": self.options.randomize_trainer_card,
            "pokedex": self.options.randomize_pokedex,
            "pokegear": self.options.randomize_pokegear,
            "save_button": self.options.randomize_save_button,
            "options_button": self.options.randomize_options_button,
            "bicycle": self.options.randomize_bicycle,
        }
        return frozenset(key for key, option in option_key_to_option.items() if bool(option.value))

    def create_regions(self) -> None:
        self._excluded_region_keys = KANTO_REGION_KEYS if bool(self.options.johto_only.value) else frozenset()
        self.regions = build_region_graph(
            self.player,
            self.multiworld,
            excluded_region_keys=self._excluded_region_keys,
            extra_route_blockers=bool(self.options.extra_route_blockers.value),
        )
        create_locations(
            self.player,
            self.regions,
            trainersanity=bool(self.options.trainersanity.value),
            dexsanity=bool(self.options.dexsanity.value),
            dexsanity_species_methods=self.dexsanity_species_methods,
            legendarysanity=bool(self.options.legendarysanity.value),
            hidden_items_require_dowsing_machine=bool(self.options.hidden_items_require_dowsing_machine.value),
            excluded_region_keys=self._excluded_region_keys,
            menu_unlocks=self._enabled_menu_unlocks(),
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
        menu_unlocks = self._enabled_menu_unlocks()
        pool = []
        for key in _ID_ASSIGNABLE_LOCATION_KEYS:
            data = LOCATIONS[key]
            if data["region"] in self._excluded_region_keys:
                # johto_only: create_regions() already skipped this
                # location's own Region/Location objects entirely -- must
                # not contribute a matching item either, or the item pool
                # would outnumber the created locations.
                continue
            if key == "goldenrod_bike_shop_bicycle" and "bicycle" not in menu_unlocks:
                # randomize_bicycle off (default): create_locations() above
                # already skipped this location entirely -- must not
                # contribute its item either, same reasoning as the
                # excluded_region_keys check above. A plain type =
                # 'npc_gift' entry otherwise, so without this check it
                # would fall through to the generic else branch below and
                # get added unconditionally.
                continue
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
            elif data["type"] == "menu_unlock":
                if key.removeprefix("menu_unlock_") not in menu_unlocks:
                    continue
                pool.append(create_item(data["original_item"], self.player))
            else:
                pool.append(create_item(data["original_item"], self.player))

        if bool(self.options.hidden_items_require_dowsing_machine.value):
            # Reclassify the one real Dowsing Machine item as progression --
            # data/items.py's static classification ("useful") doesn't know
            # about this option, but every hidden_item location's own
            # access_rule now depends on it (locations.py's
            # _hidden_item_access_rule).
            from BaseClasses import ItemClassification

            for item in pool:
                if item.name == DOWSING_MACHINE_ITEM_LABEL:
                    item.classification |= ItemClassification.progression
                    break

        self.multiworld.itempool += pool

    def create_item(self, name: str) -> Item:
        """Required AP World API -- distinct from the module-level
        create_item imported above, which this delegates to."""
        return create_item(_LABEL_TO_ITEM_KEY[name], self.player)

    def set_rules(self) -> None:
        apply_exit_rules(self.player, self.multiworld, self.regions)
        _constrain_undetectable_locations(self.player, self.multiworld, self._excluded_region_keys)

        goal_badge_count = self.options.goal_badge_count.value
        if self._excluded_region_keys and goal_badge_count > _JOHTO_BADGE_COUNT:
            # johto_only: only Johto's 8 badges exist -- an n_badges goal
            # asking for more than that would never be completable.
            goal_badge_count = _JOHTO_BADGE_COUNT
        self.multiworld.completion_condition[self.player] = _goal_rule(
            self.player, self.options.goal.value, goal_badge_count
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
            "dexsanity_trigger": self.options.dexsanity_trigger.current_key,
            "starting_money": self.options.starting_money.value,
            "randomize_start_location": bool(self.options.randomize_start_location.value),
            "randomize_menu_unlocks": sorted(self._enabled_menu_unlocks()),
            SLOT_DATA_OPTIONS_KEY: build_ut_slot_data(self),
        }

    def generate_output(self, output_directory: str) -> None:
        if bool(self.options.sphere_based_trainer_leveling.value):
            # Needs the multiworld's real, final item placement -- only
            # known once fill has actually run, i.e. here, not set_rules().
            # Regular trainers and Gym Leaders are scaled against separate
            # curves (each own min/max, own max_sphere) so a Leader stays
            # boss-tier relative to the other Leaders instead of being
            # pulled toward this seed's single weakest regular trainer.
            bonus = self.options.sphere_based_trainer_leveling_bonus.value
            for location_type in ("trainer", "badge"):
                trainer_sphere = _sphere_map_for_type(
                    self.multiworld, self.player, location_type, self._excluded_region_keys
                )
                self.generated_trainer_parties = scale_trainer_levels_by_sphere(
                    self.generated_trainer_parties, trainer_sphere, bonus
                )
        write_output_patch(self, output_directory)
