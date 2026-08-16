# rom/startlocation.py
#
# `randomize_start_location`: two independent, live-verified (2026-08-17,
# real US HeartGold ROM) data edits, no ASM.
#
# 1. Spawn point: `sLocation_PlayerRoom` (src/location_backup.c), a
#    plain 5-word Location ROM constant -- mapId/warpId/x/y/direction --
#    copied into SaveData at New Game creation by
#    Save_SetPositionToPlayerRoom (called from overlay_36.c's
#    NewGame_InitSaveData, itself called from ov36_TitleScreen_
#    NewGame_AppExec, before the player even names their character).
#    RAM address 0x020FA17C (file offset from arm9_ram_address),
#    live-verified twice this project (an earlier in-room x/y shift, and
#    this session's actual "spawn inside New Bark's Elm's Lab instead of
#    the player's bedroom" target -- confirmed a real, unmodified
#    ChooseStarter scene runs normally from there).
#
# 2. Exit warp: Elm's Lab (New Bark, MAP_NEW_BARK_ELMS_LAB_1F) has
#    exactly one door, whose destination is a plain data record inside
#    the map's own zone_event entry (NitroFS a/0/3/2, NARC sub-file
#    index 58 -- see rom/eventdata.py) -- word index 91 (byte offset
#    364) holds the target map id as a plain u32 (vanilla: 60 =
#    MAP_NEW_BARK). Live-verified twice this session with two different
#    real targets (Cherrygrove, Goldenrod): overwriting this one word
#    redirects the door to any other town, landing at that town's own
#    anchor-0 warp-in point (both tests landed just outside that town's
#    Pokemon Center -- anchor 0 is assumed a "main entrance" convention
#    shared across town maps, not independently confirmed for every
#    candidate town below).
#
# Neither edit touches the vanilla ChooseStarter scene itself (still
# fully vanilla, still grants a real starter via the game's own code --
# see species.py's randomize_starters for how the *species offered* is
# separately randomized) or Elm's own dialogue.

from __future__ import annotations

from rom import HeartGoldRom

# -- 1. Spawn point ------------------------------------------------------

_LOCATION_RAM_ADDRESS = 0x020FA17C
MAP_NEW_BARK_ELMS_LAB_1F = 61

# Inside Elm's Lab, on top of the step-trigger strip
# (data_gen-independent: found directly in files/fielddata/eventdata/
# zone_event/058_T20R0101.json's own "coords" array, x=3-6/z=10) that
# auto-launches Elm's own dialogue (scr_seq_T20R0101_011) the moment the
# player enters it -- chosen deliberately inside this strip so leaving
# through the door without ever triggering ChooseStarter is not a
# straight-line option (see docs/scope.md's own safety discussion).
_SPAWN_X = 4
_SPAWN_Y = 10
_SPAWN_DIRECTION = 1


def write_spawn_in_elms_lab(rom: HeartGoldRom) -> None:
    """Redirect the New Game spawn point from the player's bedroom to
    New Bark's Elm's Lab, at a tile inside the auto-trigger strip for
    Elm's own dialogue (so the vanilla ChooseStarter scene runs before
    the player can reach the door)."""
    import struct

    file_offset = _LOCATION_RAM_ADDRESS - rom.arm9_ram_address
    location = struct.pack(
        "<IIIII", MAP_NEW_BARK_ELMS_LAB_1F, 0xFFFFFFFF, _SPAWN_X, _SPAWN_Y, _SPAWN_DIRECTION
    )
    rom.write_main_code_regions([(file_offset, location)])


# -- 2. Exit warp ---------------------------------------------------------

_ZONE_EVENT_ELMS_LAB_INDEX = 58
_WARP_TARGET_WORD_INDEX = 91
_WARP_TARGET_BYTE_OFFSET = _WARP_TARGET_WORD_INDEX * 4
_VANILLA_WARP_TARGET = 60  # MAP_NEW_BARK

# Curated candidate destination towns (community-feedback-informed, see
# docs/scope.md): every Johto town except New Bark itself (the vanilla
# spawn, not a meaningful "random" outcome) and Mount Silver/Indigo
# Plateau (already gated behind `elite_four_defeated` in this project's
# own region graph -- starting there directly would conflict with that
# gate). Kanto towns are deliberately excluded too: unreachable this
# early regardless of `johto_only`, and reaching them requires items/
# badges that can't exist yet at the very start of a fresh save.
TOWN_MAP_IDS: dict[str, int] = {
    "cherrygrove": 67,
    "violet": 73,
    "azalea": 74,
    "cianwood": 75,
    "goldenrod": 76,
    "olivine": 77,
    "ecruteak": 78,
    "mahogany": 87,
    "lake_of_rage": 88,
    "blackthorn": 89,
}


def write_exit_warp_target(rom: HeartGoldRom, town_key: str) -> None:
    """Redirect Elm's Lab's own exit door to `town_key` (a TOWN_MAP_IDS
    key) instead of vanilla's New Bark outdoors."""
    import struct

    from rom import eventdata

    if town_key not in TOWN_MAP_IDS:
        raise ValueError(f"unknown start-location town {town_key!r}, expected one of {sorted(TOWN_MAP_IDS)}")

    entry = bytearray(eventdata.read_entry(rom, _ZONE_EVENT_ELMS_LAB_INDEX))
    (current,) = struct.unpack_from("<I", entry, _WARP_TARGET_BYTE_OFFSET)
    if current != _VANILLA_WARP_TARGET:
        raise ValueError(
            f"Elm's Lab zone_event entry's warp-target word is {current}, expected the vanilla "
            f"value {_VANILLA_WARP_TARGET} (MAP_NEW_BARK) -- data_gen/decomp source may have "
            "drifted from the real ROM, refusing to guess."
        )
    struct.pack_into("<I", entry, _WARP_TARGET_BYTE_OFFSET, TOWN_MAP_IDS[town_key])
    eventdata.write_entry(rom, _ZONE_EVENT_ELMS_LAB_INDEX, bytes(entry))


def write_start_location(rom: HeartGoldRom, town_key: str) -> None:
    """Apply both edits: spawn in Elm's Lab, exit door redirected to
    `town_key`."""
    write_spawn_in_elms_lab(rom)
    write_exit_warp_target(rom, town_key)
