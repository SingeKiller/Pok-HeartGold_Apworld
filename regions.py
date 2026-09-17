# regions.py
#
# Builds the Archipelago region graph (Region + Entrance) from the generated
# data/regions.py. Locations are attached separately by
# locations.create_locations; access rules by rules.py.

from __future__ import annotations

from BaseClasses import MultiWorld, Region
from data.regions import REGIONS

# `johto_only` option support. Derived (not hand-curated) by a graph
# flood-fill from `new_bark` over data/regions.py's own exits, blocking the
# 4 real Johto<->Kanto crossing edges: `viridian <-> route_22` (the
# Indigo Plateau/Victory Road approach doubles as the Kanto mainland
# border -- Route 22 itself and everything beyond it toward Indigo
# Plateau/Mount Silver stays Johto-side, only Viridian and beyond is
# Kanto), `cerulean <-> route_24` (the Bill's-house/Nugget-Bridge
# approach), the S.S. Aqua ferry's Olivine-side gate (`items =
# ["s_s_ticket"]` in data_gen/rules.toml), and, since the 2026-08-23
# Magnet Train fix, `goldenrod_magnet_train_station_2f <->
# saffron_magnet_train_station_2f` (the rail link, gated on the Magnet
# Train Pass -- before that fix each city's platform was split across two
# regions and the link was unreachable from either end, so it crossed
# nothing). Notably NOT numeric-map-code-
# based: Kanto/Johto towns and routes are numbered from the same shared
# T*/R* pools (e.g. indigo_plateau is T10, in the "Kanto" numeric range,
# but is genuinely Johto's own Elite Four complex) -- only real graph
# topology reliably separates them. To re-derive after a data_gen/
# regions.toml change: BFS from "new_bark" blocking the 4 edges above,
# the unreached region set is this constant.
KANTO_REGION_KEYS: frozenset[str] = frozenset(
    {
        "celadon", "celadon_condominiums_1f", "celadon_condominiums_2f", "celadon_condominiums_3f",
        "celadon_condominiums_left_elevator", "celadon_condominiums_right_elevator", "celadon_condominiums_roof", "celadon_condominiums_roof_room",
        "celadon_department_store_1f", "celadon_department_store_2f", "celadon_department_store_3f", "celadon_department_store_4f",
        "celadon_department_store_5f", "celadon_department_store_elevator", "celadon_department_store_roof", "celadon_game_corner",
        "celadon_game_corner_jp", "celadon_gym", "celadon_pokecenter_1f", "celadon_pokecenter_b1f",
        "celadon_prize_corner", "celadon_restaurant", "cerulean", "cerulean_bike_maniac_house",
        "cerulean_cave_1f", "cerulean_cave_2f", "cerulean_cave_b1f", "cerulean_east_house",
        "cerulean_gym", "cerulean_north_house", "cerulean_pokecenter_1f", "cerulean_pokecenter_b1f",
        "cerulean_pokemart", "cerulean_west_house", "cinnabar_island", "cinnabar_island_pokecenter_1f",
        "cinnabar_island_pokecenter_b1f", "diglett_cave", "fuchsia", "fuchsia_gym",
        "fuchsia_pal_park_entrance", "fuchsia_pokecenter_1f", "fuchsia_pokecenter_b1f", "fuchsia_pokemart",
        "fuchsia_safari_zone_warden_house", "fuchsia_southwest_house", "lavender",
        "lavender_house_of_memories", "lavender_name_rater", "lavender_pokecenter_1f", "lavender_pokecenter_b1f",
        "lavender_pokemart", "lavender_radio_station", "lavender_southwest_house", "lavender_volunteer_pokemon_house",
        "mount_moon", "mount_moon_square", "mount_moon_square_clefairy_event", "mount_moon_square_entrance",
        "mount_moon_square_shop", "pal_park", "pallet", "pallet_town_blues_house_1f",
        "pallet_town_blues_house_2f", "pallet_town_oaks_lab", "pallet_town_reds_house_1f", "pallet_town_reds_house_2f",
        "pewter", "pewter_gym", "pewter_museum_of_science", "pewter_northeast_house",
        "pewter_pokecenter_1f", "pewter_pokecenter_b1f", "pewter_pokemart", "pewter_southwest_house",
        "rock_tunnel_1f", "rock_tunnel_b1f", "route_1", "route_10",
        "route_10_pokecenter_1f", "route_10_pokecenter_b1f", "route_10_power_plant_broken", "route_10_power_plant_repaired",
        "route_10_south", "route_11", "route_12", "route_12_fishing_brother_house",
        "route_13", "route_14", "route_15", "route_15_fuchsia_gatehouse",
        "route_16", "route_16_east", "route_16_gatehouse", "route_16_house",
        "route_17", "route_18", "route_18_gatehouse", "route_19",
        "route_19_fuchsia_gatehouse", "route_19_route_12_gatehouse", "route_2", "route_20",
        "route_21", "route_24", "route_25", "route_25_sea_cottage",
        "route_2_east", "route_2_house", "route_2_southeast_gatehouse", "route_2_viridian_forest_north_gatehouse",
        "route_2_viridian_forest_south_gatehouse", "route_3", "route_3_pokecenter_1f", "route_3_pokecenter_b1f",
        "route_4", "route_5", "route_5_house", "route_5_saffron_gatehouse",
        "route_5_underground_path", "route_5_underground_path_gate", "route_6", "route_6_saffron_gatehouse",
        "route_6_underground_path_gate", "route_7", "route_7_saffron_gatehouse", "route_8",
        "route_8_saffron_gatehouse", "route_9", "saffron", "saffron_copycat_house_1f",
        "saffron_copycat_house_2f", "saffron_fighting_dojo", "saffron_gym", "saffron_magnet_train_station_1f",
        "saffron_magnet_train_station_2f", "saffron_mr_psychic_house", "saffron_pokecenter_1f",
        "saffron_pokecenter_2f", "saffron_pokemart", "saffron_silph_co_elevator", "saffron_silph_co_hq",
        "saffron_silph_co_rotom_room", "seafoam_islands_1f", "seafoam_islands_b1f", "seafoam_islands_b2f",
        "seafoam_islands_b3f", "seafoam_islands_b4f", "seafoam_islands_cinnabar_gym", "ss_aqua_1f",
        "ss_aqua_1f_northeast_rooms", "ss_aqua_1f_northwest_rooms", "ss_aqua_1f_southeast_rooms", "ss_aqua_1f_southwest_rooms",
        "ss_aqua_b1f", "ss_aqua_captain_room", "ss_aqua_olivine_port_exterior", "ss_aqua_vermilion_port_exterior",
        "ss_aqua_vermilion_port_interior", "vermilion", "vermilion_central_house", "vermilion_fishing_dude_house",
        "vermilion_gym", "vermilion_pokecenter_1f", "vermilion_pokecenter_b1f", "vermilion_pokemart",
        "vermilion_pokemon_fan_club", "vermilion_south_house", "viridian", "viridian_forest",
        "viridian_gym", "viridian_northeast_house", "viridian_pokecenter_1f", "viridian_pokecenter_b1f",
        "viridian_pokemart", "viridian_route_1_gatehouse", "viridian_trainer_house_1f", "viridian_trainer_house_b1f",
    }
)

# The two wing handover events (data_gen/rules.toml, verrous A7 and D12).
# In each version one of the two NPCs handing a wing over stands in Pewter
# City (scr_seq_0750_T03.s: the Silver Wing in HeartGold, the Rainbow Wing in
# SoulSilver), so under `johto_only` that event can never be granted and
# whatever sits behind its monk is unreachable in logic.
_WING_HANDOVER_EVENTS = ("rainbow_wing_handed_over", "silver_wing_handed_over")


def _regions_behind(gate_src: str, gate_dst: str) -> set[str]:
    """Every region reachable from `gate_dst` without walking back through
    `gate_src`, i.e. what the `gate_src -> gate_dst` edge alone opens."""
    seen = {gate_dst}
    stack = [gate_dst]
    while stack:
        for exit_name in REGIONS[stack.pop()]["exits"]:
            if exit_name == gate_src or exit_name in seen or exit_name not in REGIONS:
                continue
            seen.add(exit_name)
            stack.append(exit_name)
    return seen


def johto_only_excluded_region_keys(soulsilver: bool) -> frozenset[str]:
    """`johto_only`'s full exclusion set: KANTO_REGION_KEYS plus the Johto
    regions only the Pewter-side wing opens in this version (Bell Tower 2F
    and up in SoulSilver, the Lugia chamber in HeartGold). Leaving them in
    would create locations no logic can ever reach. Derived from the event
    locations and EXIT_RULES rather than hardcoded, so it follows
    data_gen/rules.toml."""
    from data.locations import LOCATIONS
    from data.rules import EXIT_RULES

    from locations import location_region_key

    kanto_events = {
        data["event"]
        for data in LOCATIONS.values()
        if data["type"] == "event"
        and data["event"] in _WING_HANDOVER_EVENTS
        and location_region_key(data, soulsilver) in KANTO_REGION_KEYS
    }
    excluded = set(KANTO_REGION_KEYS)
    for (src, dst), requirement in EXIT_RULES.items():
        if not kanto_events.intersection(requirement.get("events", ())):
            continue
        behind = _regions_behind(src, dst)
        # Rules are bidirectional by default, so EXIT_RULES also holds the
        # way back out (dst -> src), whose "behind" side is the rest of the
        # world. Same anchor as KANTO_REGION_KEYS' own derivation.
        if "new_bark" in behind:
            continue
        excluded |= behind
    return frozenset(excluded)


def create_regions(
    player: int,
    multiworld: MultiWorld,
    *,
    excluded_region_keys: frozenset[str] = frozenset(),
) -> dict[str, Region]:
    """Create one Region per data/regions.py entry not in
    `excluded_region_keys` (`johto_only`'s KANTO_REGION_KEYS, or empty)
    and connect them per each entry's exits. An exit pointing at a region
    key outside v1 scope (Pokeathlon Dome, Safari Zone gate, Battle
    Frontier, Union Room -- see docs/scope.md) or excluded this way is
    skipped: no Entrance is created, exactly as a real player would find a
    dead end there."""
    regions: dict[str, Region] = {
        name: Region(name, player, multiworld) for name in REGIONS if name not in excluded_region_keys
    }
    multiworld.regions.extend(regions.values())

    for name, data in REGIONS.items():
        if name not in regions:
            continue
        source = regions[name]
        for exit_name in data["exits"]:
            if exit_name not in regions:
                continue
            source.connect(regions[exit_name], f"{name} -> {exit_name}")

    return regions
