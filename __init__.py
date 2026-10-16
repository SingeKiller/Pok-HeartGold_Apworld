# __init__.py
#
# Registers the "Pokemon HGSS Singe" Archipelago World: wires together
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

import base64
import hashlib
import os
import sys
from typing import Any, ClassVar

# Every sibling module uses plain, absolute imports so they stay
# importable as flat top-level modules for their own standalone unit
# tests. Once this file is loaded by Archipelago as
# worlds.poke_hgss, those absolute imports would otherwise raise
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
from Options import OptionError  # noqa: E402
from worlds.AutoWorld import AutoWorldRegister, WebWorld, World  # noqa: E402

import location_flags  # noqa: E402
from client import HeartGoldClient  # noqa: E402, F401
from data import GAME_VERSION  # noqa: E402
from data.encounters import ENCOUNTERS_HEARTGOLD, ENCOUNTERS_SOULSILVER  # noqa: E402
from data.items import ITEMS  # noqa: E402
from data.locations import LOCATIONS  # noqa: E402
from data.rules import BADGES  # noqa: E402
from items import create_item, create_item_label_to_code_map, create_item_name_groups  # noqa: E402
from locations import (  # noqa: E402
    DOWSING_MACHINE_ITEM_LABEL,
    POWER_PLANT_PRERESTORED_SKIPPED_LOCATION_KEYS,
    SHELVED_LOCATION_TYPES,
    badge_item_label,
    create_location_label_to_code_map,
    create_locations,
    DEXSANITY_UNUSABLE_ZONE_METHODS,
    dexsanity_source_requirement,
    dexsanity_sources_within_regions,
    location_region_key,
)
from options import OPTION_GROUPS, GameVersion, Goal, HeartGoldOptions  # noqa: E402

from output_patch import HeartGoldProcedurePatch  # noqa: E402, F401 -- import side effect only
from output_patch import generate_output as write_output_patch  # noqa: E402
from regions import create_regions as build_region_graph  # noqa: E402
from regions import johto_only_excluded_region_keys  # noqa: E402
from rom import HEARTGOLD_US_MD5, SOULSILVER_US_MD5  # noqa: E402
from rules import MAGNET_TRAIN_PASS_ITEM_LABEL  # noqa: E402
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
    species_encounter_sources,
)
from rom.encounterdata import zone_method_is_written  # noqa: E402
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
        # A bit test, not `!= progression` (2026-09-24, player report): an
        # item reclassified `useful | progression` (the Dowsing Machine with
        # hidden_items_require_dowsing_machine) passed the old comparison.
        # Unused since the same day (every location has a check flag), kept
        # for any location that ever loses its flag again.
        return item.player in local_players and not (item.classification & ItemClassification.progression)

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


def _validate_rom_setting(path: str, version: str, setting: str) -> None:
    """Archipelago checks the configured ROM on every use (its default check
    is the exact MD5, the "File hash does not match" error). Accepts trimmed
    US dumps too (rom.identify_rom), and otherwise says what the file is and
    how to get out: Archipelago keeps the file it was first given (copied
    under the US name), so picking the right ROM again needs it removed.
    Player reports 2026-09-29: an EU ROM, and a US one that kept failing."""
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


# pytest's own Package collector imports this file once as a setup side
# effect before test fixtures get a chance to; AutoWorldRegister.__new__
# refuses a second registration of the same game name. Drop any prior
# registration first -- a no-op for a real Archipelago load. See NOTES.md.
AutoWorldRegister.world_types.pop("Pokemon HGSS Singe", None)


class HeartGoldWorld(World):
    """Pokemon HeartGold & SoulSilver -- registered game name "Pokemon
    HGSS Singe" (renamed 2026-08-15 from "Pokemon HeartGold" now that both
    versions are equally first-class, see docs/architecture.md's
    "SoulSilver support" entry; renamed again for v0.2.5 because another
    HGSS apworld already registers "Pokemon HGSS", and Archipelago refuses
    two worlds with the same game name)."""

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

    # Universal Tracker -- see universal_tracker.py. Every logic-relevant
    # option round-trips through slot data, so UT needs no YAML.
    ut_can_gen_without_yaml = True
    is_universal_tracker: bool

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Set by UT on the MultiWorld it re-generates with; absent otherwise.
        self.is_universal_tracker = getattr(self.multiworld, "generation_is_fake", False)

    @property
    def slot_auth(self) -> bytes:
        """16 bytes stamped into this slot's ROM so the client logs in on
        its own (rom/worldsignature.py). Derived from the seed name and the
        slot number rather than drawn from self.random, so it consumes no
        randomness and is ready before generate_output and the multidata
        writer, which Archipelago runs concurrently."""
        digest = hashlib.sha256(f"poke_hgss:{self.multiworld.seed_name}:{self.player}".encode()).digest()
        return digest[:16]

    def modify_multidata(self, multidata: dict[str, Any]) -> None:
        # base64 of 16 bytes is 24 characters, longer than any slot name
        # (16 max), so it can never collide with a real one.
        connect_names = multidata["connect_names"]
        connect_names[base64.b64encode(self.slot_auth).decode("ascii")] = connect_names[self.player_name]

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

        # Mt. Silver only opens once Blue is beaten and Oak has been seen in
        # Pallet Town (data_gen/rules.toml, the route_28 gate), both in
        # Kanto: with johto_only, Red cannot be reached, in vanilla either.
        # Refused here with a clear message rather than a KeyError on the
        # excluded summit region (2026-09-27 logic audit).
        if bool(self.options.johto_only.value) and self.options.goal.value == Goal.option_champion_red:
            raise OptionError(
                f"{self.player_name}: goal champion_red cannot be reached with johto_only "
                "(Mt. Silver opens from Kanto); use elite_four or n_badges."
            )

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
        # dexsanity_encounter_types restricts which methods count at all --
        # a species left with no allowed source after this filter simply
        # gets no Dexsanity location this seed (same as one this seed's
        # own wild tables never place anywhere). A no-op when every method
        # is still allowed (the option's own default).
        #
        # zone_method_is_written is the other, non-optional half (added
        # 2026-08-22, after a real seed died): it drops every (zone,
        # method) pair patch_gen never writes into the ROM -- the headbutt
        # tables and the 3 zones with no NARC entry -- so a Dexsanity
        # location can never exist for a species the player could not
        # possibly find. It lives in rom/encounterdata.py next to the code
        # that does the writing, so the two cannot drift apart.
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
        # Narrowed to the Regions that actually exist for this player
        # (johto_only drops Kanto's) *before* create_locations, so
        # create_items below can use the exact same dict and the item pool
        # can never outnumber the created Dexsanity locations.
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
        # trainersanity_count / dexsanity_count: a random subset, drawn from
        # sorted keys so the same seed always draws the same one.
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
        # type = 'trainer' (task M3.3) and type = 'dexsanity' (task M3.4)
        # locations have no original_item -- neither a trainer battle nor a
        # Dexsanity catch drops a vanilla item -- so they each contribute a
        # random filler item to the pool instead, and only for the entries
        # create_regions() above actually created (trainersanity/dexsanity
        # off, or -- dexsanity only -- that species absent from this seed's
        # own wild tables, from the tables the ROM patcher writes, or from
        # every Region that exists this seed), so the pool size matches the
        # created, unfilled location count exactly. `dexsanity_species_
        # sources` is the exact dict create_regions() passed to
        # create_locations, region-narrowed included, so the two agree by
        # construction rather than by two parallel filters.
        trainersanity = bool(self.options.trainersanity.value)
        dexsanity = bool(self.options.dexsanity.value)
        legendarysanity = bool(self.options.legendarysanity.value)
        bicycle_enabled = bool(self.options.randomize_bicycle.value)
        power_plant_prerestored = bool(self.options.magnet_train.value)
        pool = []
        for key in _ID_ASSIGNABLE_LOCATION_KEYS:
            data = LOCATIONS[key]
            if location_region_key(data, self._soulsilver) in self._excluded_region_keys:
                # johto_only: create_regions() already skipped this
                # location's own Region/Location objects entirely -- must
                # not contribute a matching item either, or the item pool
                # would outnumber the created locations.
                continue
            if key == "goldenrod_bike_shop_bicycle" and not bicycle_enabled:
                # randomize_bicycle off (default): create_locations() above
                # already skipped this location entirely -- must not
                # contribute its item either, same reasoning as the
                # excluded_region_keys check above. A plain type =
                # 'npc_gift' entry otherwise, so without this check it
                # would fall through to the generic else branch below and
                # get added unconditionally.
                continue
            if power_plant_prerestored and key in POWER_PLANT_PRERESTORED_SKIPPED_LOCATION_KEYS:
                # magnet_train on: the TM57 scene never plays, create_
                # locations() skipped the location, same reasoning as above.
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
                # No vanilla item to displace (the "reward" is the
                # encounter itself).
                if not legendarysanity:
                    continue
                item_key = _LABEL_TO_ITEM_KEY[self.get_filler_item_name()]
                pool.append(create_item(item_key, self.player))
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

        if not bool(self.options.magnet_train.value):
            # Mirror image of the Dowsing Machine case above. Off, the ride
            # needs `power_plant_restored` on top of the Pass (rules.py), and
            # that event is only ever granted inside Kanto, so the train is
            # never a way into Kanto any more: at best a shortcut back to
            # Goldenrod for a player who is already there. The Pass is kept
            # a real item (the player can still ride with it) but not
            # progression. Logic then simply never counts the ride, which
            # is the safe direction (stricter than the game), and the fill
            # stops reserving a good spot for a key item that opens nothing
            # a seed needs.
            from BaseClasses import ItemClassification

            for item in pool:
                if item.name == MAGNET_TRAIN_PASS_ITEM_LABEL:
                    item.classification = ItemClassification.useful
                    break

        if not bicycle_enabled:
            # randomize_bicycle off (default): the Goldenrod Bike Shop is
            # left vanilla, so the player is handed the Bicycle in-game and
            # no Bicycle item ever enters the pool (see the skip above).
            # Both Cycling Road gatehouses now require it in logic (verrou
            # D8, data_gen/rules.toml), so it has to be precollected or
            # Route 16's southern half, Route 17 and Route 18 -- and the 16
            # locations on them -- would be unreachable on the default
            # settings.
            self.multiworld.push_precollected(create_item("bicycle", self.player))

        self.multiworld.itempool += pool

    def create_item(self, name: str) -> Item:
        """Required AP World API -- distinct from the module-level
        create_item imported above, which this delegates to."""
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
            # None unless randomize_start_location is on. Read by the
            # client to repair the blackout spawn (client.py's
            # _apply_start_location_blackout_spawn).
            "starting_town": self.generated_start_location_town,
            # Read by the client to pre-set FLAG_RESTORED_POWER (client.py's
            # _apply_power_plant_prerestored).
            "magnet_train": bool(self.options.magnet_train.value),
            "remote_items": bool(self.options.remote_items.value),
            # Where this seed put each Dexsanity species, for the trackers
            # (they cannot know it otherwise and used to show every species
            # as catchable; player report 2026-10-04).
            "dexsanity_logic": self._dexsanity_logic_for_trackers(),
            SLOT_DATA_OPTIONS_KEY: build_ut_slot_data(self),
        }

    def _dexsanity_logic_for_trackers(self) -> dict[str, list[list]]:
        """{AP location id: [[region, item keys, other regions], ...]} for
        every Dexsanity location, one entry per place the species can be
        caught (any one is enough), see locations.dexsanity_source_requirement."""
        result: dict[str, list[list]] = {}
        for location in self.multiworld.get_locations(self.player):
            data = LOCATIONS.get(location.name)
            if location.address is None or data is None or data["type"] != "dexsanity":
                continue
            sources = self.dexsanity_species_sources.get(data["species"], ())
            requirements = sorted({dexsanity_source_requirement(source) for source in sources})
            # The location's own parent region counts too (a random start
            # may begin away from it).
            parent = location.parent_region.name
            result[str(location.address)] = [
                [region, list(items), sorted(set(regions) | {parent})] for region, items, regions in requirements
            ]
        return result

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
