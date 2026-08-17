# rom/startlocation.py
#
# `randomize_start_location`: two door-redirect edits, no ASM, no spawn-
# point patch (see "Redesign, 2026-08-17" below for why the earlier
# spawn-point version was replaced).
#
# 1. Player's House 1F's own front door (New Bark, MAP_NEW_BARK_PLAYER_
#    HOUSE_1F) -- a plain data record inside the map's own zone_event
#    entry (NitroFS a/0/3/2, NARC sub-file index 60 -- see
#    rom/eventdata.py). This record is a `struct WarpEvent` (include/
#    map_events_internal.h: x, z, header, anchor, y -- 12 bytes), packed
#    at byte offset 144 in this entry: x/z (the door tile position, (3,
#    10) in vanilla) at 144/146, `header` (destination map id, u16) at
#    148, `anchor` (destination entrance/spawn-point index within that
#    map's own anchor table, u16) at 150 -- live-verified against the
#    real US HeartGold ROM: a byte-pattern search for the u16 value 60
#    (MAP_NEW_BARK) anywhere in this 172-byte record found exactly one
#    match, at offset 148.
#
#    2026-08-17 live playtest bug: the first version of this redirect
#    only patched `header` (offset 148), leaving `anchor` (offset 150) at
#    its vanilla value -- an index into outdoor New Bark's own anchor
#    table (a big multi-entrance map). Applied to Elm's Lab's own anchor
#    table instead (a single-room interior, presumably one entry), that
#    stale index resolves to nothing sane, and the game shows a black
#    screen after the door transition instead of loading the Lab. Fixed
#    by also patching `anchor` to 0 -- the same "anchor 0 = primary
#    entrance" convention already relied on (and live-verified for two
#    real towns) by write_exit_warp_target below.
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
#    This same record is also anchor 0 of Elm's Lab's own `warp_events`
#    array -- confirmed via the decomp's own static zone_event JSON dump
#    (files/fielddata/eventdata/zone_event/058_T20R0101.json), which lists
#    exactly one warp entry: x=4, z=14, header=MAP_NEW_BARK, anchor=0 (the
#    header/anchor pair is this same word-91 u32 write_exit_warp_target
#    already patches). It is Elm's Lab's *only* warp entry -- a single,
#    bidirectional door record: its `header`/`anchor` are read on the way
#    OUT (this door's own destination), and its `x`/`z` are read on the
#    way IN by whoever warps into this map via anchor 0 (write_house_
#    exit_to_elms_lab above), per src/field_warp_tasks.c's sub_02052F94
#    (`location->x = warp->x; location->y = warp->z`). (4, 14) sits right
#    at/next to the door -- see write_elms_lab_entrance_position below for
#    the real bug this caused and the fix.
#
# Redesign, 2026-08-17 (real bug report, live playtest): the original
# design instead patched sLocation_PlayerRoom to spawn the player
# directly inside Elm's Lab, skipping New Bark (and Mom's own scene)
# entirely, with client.py's _apply_start_location_flags directly poking
# FLAG_GOT_BAG/_TRAINER_CARD/_SAVE_BUTTON/_OPTIONS_BUTTON into savedata to
# compensate. Live-verified in isolation (spawn point, unmodified
# ChooseStarter scene, exit-door redirect) -- but a real player later
# found the Save menu option did nothing at all (no prompt opened), and
# that quitting and relaunching lost Bag/Save/Options entirely, meaning
# whatever the real save-execution path actually checks is NOT simply the
# same flag bit CheckGotMenuIconI reads for icon visibility, and poking
# that bit directly does not satisfy it. The real, correctly-functioning
# mechanism for granting these has only ever been Mom's own vanilla scene
# (scr_seq_0845_T20R0201.s's scr_seq_T20R0201_000, which every real
# vanilla player's save relies on) -- so this redesign spawns the player
# at the ordinary vanilla position instead (no edit at all -- Mom's scene
# auto-fires on room entry the normal way, per New Bark's own zone_event
# init table, `VAR_SCENE_PLAYERS_HOUSE_1F == 0`) and only redirects the
# house's own front door to Elm's Lab afterward, once Mom has already
# granted everything for real. FLAG_GOT_POKEDEX/_POKEGEAR still can't be
# reached this way (their own vanilla grants sit behind content this
# redesign still skips -- Route 30's Mr. Pokemon, and Mom's own later
# revisit conversation) and still go through client.py's existing
# fake-grant/gating mechanism, unchanged.

from __future__ import annotations

from rom import HeartGoldRom

# -- 1. Player's House 1F's front door -----------------------------------

_ZONE_EVENT_PLAYER_HOUSE_1F_INDEX = 60
_HOUSE_EXIT_TARGET_BYTE_OFFSET = 148  # WarpEvent.header
_HOUSE_EXIT_ANCHOR_BYTE_OFFSET = 150  # WarpEvent.anchor, immediately after header
_VANILLA_HOUSE_EXIT_TARGET = 60  # MAP_NEW_BARK
MAP_NEW_BARK_ELMS_LAB_1F = 61
_ELMS_LAB_ENTRANCE_ANCHOR = 0  # single-room interior, one entrance


def write_house_exit_to_elms_lab(rom: HeartGoldRom) -> None:
    """Redirect New Bark's Player's House 1F's own front door to Elm's
    Lab instead of vanilla's New Bark outdoors -- the player still spawns
    at the ordinary vanilla position and Mom's own scene still fires
    exactly as in vanilla, this only changes where the door leads once
    they're done with her.

    Patches both `header` (destination map) and `anchor` (which
    entrance-point index in that map's own anchor table) -- leaving
    `anchor` at its vanilla New Bark-outdoors value caused a real black
    screen (see module docstring)."""
    import struct

    from rom import eventdata

    entry = bytearray(eventdata.read_entry(rom, _ZONE_EVENT_PLAYER_HOUSE_1F_INDEX))
    (current,) = struct.unpack_from("<H", entry, _HOUSE_EXIT_TARGET_BYTE_OFFSET)
    if current != _VANILLA_HOUSE_EXIT_TARGET:
        raise ValueError(
            f"Player's House 1F zone_event entry's door-target half-word is {current}, expected "
            f"the vanilla value {_VANILLA_HOUSE_EXIT_TARGET} (MAP_NEW_BARK) -- data_gen/decomp "
            "source may have drifted from the real ROM, refusing to guess."
        )
    struct.pack_into("<H", entry, _HOUSE_EXIT_TARGET_BYTE_OFFSET, MAP_NEW_BARK_ELMS_LAB_1F)
    struct.pack_into("<H", entry, _HOUSE_EXIT_ANCHOR_BYTE_OFFSET, _ELMS_LAB_ENTRANCE_ANCHOR)
    eventdata.write_entry(rom, _ZONE_EVENT_PLAYER_HOUSE_1F_INDEX, bytes(entry))


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


# -- 3. Entrance position --------------------------------------------------

# WarpEvent.x/.z, immediately before .header (see write_exit_warp_target's
# own _WARP_TARGET_BYTE_OFFSET = 364 above; this record starts 4 bytes
# earlier). Byte offset independently confirmed by walking the decomp's
# own static zone_event JSON (11 BgEvents * 20 bytes + 4 ObjectEvents * 32
# bytes + 3 leading u32 counts = 360), not just backed out from the
# already-verified header offset.
_ELMS_LAB_ENTRANCE_X_BYTE_OFFSET = 360
_ELMS_LAB_ENTRANCE_Z_BYTE_OFFSET = 362
_VANILLA_ELMS_LAB_ENTRANCE_X = 4
_VANILLA_ELMS_LAB_ENTRANCE_Z = 14

# (4, 9): same x as the door's own vanilla (4, 14), moved further into
# the room (2026-08-17, user-picked after the (3, 10) alternative below).
_ELMS_LAB_ENTRANCE_X = 4
_ELMS_LAB_ENTRANCE_Z = 9

# The old (2026-08-16) sLocation_PlayerRoom spawn-point design used (3,
# 10) -- chosen to sit inside ChooseStarter's own auto-trigger strip
# (zone_event/058_T20R0101.json's {"x":3,"z":10,"w":4,"h":1} coord
# BgEvent) and live-verified safe back then. Also, coincidentally, right
# where this same JSON's own BgEvents list several interactive lab-machine
# tiles (x=1-12 at z=10) -- clearly floor space well inside the room, 4
# tiles from the door at z=14. Not used above (see _ELMS_LAB_ENTRANCE_X/Z).


def write_elms_lab_entrance_position(rom: HeartGoldRom) -> None:
    """Move Elm's Lab's own (only) warp entry's x/z from vanilla's (4, 14)
    -- right at the door, since this same record doubles as the door's own
    exit-side reference point, see module docstring -- further into the
    room. header/anchor (the exit destination, patched separately by
    write_exit_warp_target) are untouched.

    Real playtest bug, 2026-08-17: a player holding a directional input
    through the door transition immediately walked back out and re-warped,
    because the anchor-0 landing spot (4, 14) was the door tile itself."""
    import struct

    from rom import eventdata

    entry = bytearray(eventdata.read_entry(rom, _ZONE_EVENT_ELMS_LAB_INDEX))
    (current_x,) = struct.unpack_from("<H", entry, _ELMS_LAB_ENTRANCE_X_BYTE_OFFSET)
    (current_z,) = struct.unpack_from("<H", entry, _ELMS_LAB_ENTRANCE_Z_BYTE_OFFSET)
    if (current_x, current_z) != (_VANILLA_ELMS_LAB_ENTRANCE_X, _VANILLA_ELMS_LAB_ENTRANCE_Z):
        raise ValueError(
            f"Elm's Lab zone_event entry's warp x/z is ({current_x}, {current_z}), expected the "
            f"vanilla value ({_VANILLA_ELMS_LAB_ENTRANCE_X}, {_VANILLA_ELMS_LAB_ENTRANCE_Z}) -- "
            "data_gen/decomp source may have drifted from the real ROM, refusing to guess."
        )
    struct.pack_into("<H", entry, _ELMS_LAB_ENTRANCE_X_BYTE_OFFSET, _ELMS_LAB_ENTRANCE_X)
    struct.pack_into("<H", entry, _ELMS_LAB_ENTRANCE_Z_BYTE_OFFSET, _ELMS_LAB_ENTRANCE_Z)
    eventdata.write_entry(rom, _ZONE_EVENT_ELMS_LAB_INDEX, bytes(entry))


def write_start_location(rom: HeartGoldRom, town_key: str) -> None:
    """Apply all three edits: New Bark's own house exit to Elm's Lab,
    Elm's Lab's own exit to `town_key`, and Elm's Lab's own entrance
    position (away from the door -- see write_elms_lab_entrance_position).
    Spawn position within New Bark itself (before the player's house) is
    left completely vanilla."""
    write_house_exit_to_elms_lab(rom)
    write_exit_warp_target(rom, town_key)
    write_elms_lab_entrance_position(rom)
