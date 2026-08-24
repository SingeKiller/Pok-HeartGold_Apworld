# rom/startlocation.py
#
# `randomize_start_location`: a single door-redirect edit, no ASM, no
# spawn-point patch (see "Redesign, 2026-08-17" below for why the earlier
# spawn-point version was replaced, and "Scope reduction, 2026-08-24" for
# why the second edit this module used to make is gone).
#
# 1. Exit warp: Elm's Lab (New Bark, MAP_NEW_BARK_ELMS_LAB_1F, map id 61)
#    has exactly one door, whose destination is a plain data record inside
#    the map's own zone_event entry (NitroFS a/0/3/2, NARC sub-file
#    index 58 -- see rom/eventdata.py) -- word index 91 (byte offset
#    364) holds the target map id as a plain u32 (vanilla: 60 =
#    MAP_NEW_BARK). Live-verified twice with two different real targets
#    (Cherrygrove, Goldenrod): overwriting this one word redirects the
#    door to any other town, landing at that town's own anchor-0 warp-in
#    point (both tests landed just outside that town's Pokemon Center --
#    anchor 0 is assumed a "main entrance" convention shared across town
#    maps, not independently confirmed for every candidate town below).
#
#    This same record is also anchor 0 of Elm's Lab's own `warp_events`
#    array -- confirmed via the decomp's own static zone_event JSON dump
#    (files/fielddata/eventdata/zone_event/058_T20R0101.json), which lists
#    exactly one warp entry: x=4, z=14, header=MAP_NEW_BARK, anchor=0 (the
#    header/anchor pair is this same word-91 u32 write_exit_warp_target
#    already patches). It is Elm's Lab's *only* warp entry -- a single,
#    bidirectional door record: its `header`/`anchor` are read on the way
#    OUT (this door's own destination), and its `x`/`z` are read on the
#    way IN by whoever warps into this map via anchor 0 (in vanilla, and
#    again since the scope reduction below, that is outdoor New Bark's own
#    door record for the Lab), per src/field_warp_tasks.c's sub_02052F94
#    (`location->x = warp->x; location->y = warp->z`). (4, 14) sits right
#    at/next to the door -- see section 2 below for the real bug this
#    caused and why it's deliberately left unfixed.
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
# init table, `VAR_SCENE_PLAYERS_HOUSE_1F == 0`), and everything from the
# bedroom up to the starter choice is left exactly as a vanilla save
# plays it. FLAG_GOT_POKEDEX/_POKEGEAR still can't be reached this way
# (their own vanilla grants sit behind content this redesign still skips
# -- Route 30's Mr. Pokemon, and Mom's own later revisit conversation)
# and still go through client.py's existing fake-grant/gating mechanism,
# unchanged.
#
# Scope reduction, 2026-08-24 (user decision, after a real player report
# of 2026-08-18): this module used to make a second edit, redirecting
# Player's House 1F's own front door (New Bark, zone_event entry 60,
# `struct WarpEvent`'s header/anchor at byte offsets 148/150) to Elm's Lab
# so that leaving Mom's room led straight to the starter choice. That edit
# is gone; the front door is plain vanilla again. It was never necessary:
# New Bark's west exit is already blocked by the neighbour until the
# player owns a Pokemon (scr_seq_0842_T20.s:269,
# `VAR_SCENE_NEW_BARK_WEST_EXIT`), so there is no sequence break to guard
# against, and Elm's Lab is a twenty-step walk from the front door. What
# it did cost was permanent, which is what the report described: being a
# static edit to a NitroFS record it could not be revoked at runtime, so a
# player coming home after picking a starter kept walking into Elm's Lab
# through their own front door for the rest of that save. The route is now
# vanilla end to end: house 1F (vanilla spawn) -> Mom's scene -> front
# door -> New Bark -> on foot to Elm's Lab -> starter choice -> lab door
# -> the YAML's town.
#
# Former known limitation, FIXED at runtime (2026-08-24): the one edit
# that remains used to have exactly the same permanence. Elm's Lab's exit
# door led to the chosen town for the whole save, so a player who walked
# back into the Lab later in the run was sent to their starting town again
# on the way out instead of to New Bark. A savedata write cannot fix that
# (src/map_events.c's `Field_InitMapEvents`/`MapEvents_ReadFromNarc`
# re-read this exact NARC entry fresh from NitroFS into a heap-allocated
# `FieldSystem.mapEvents` on every single map load), but a write into
# BizHawk's live ROM buffer is picked up by that very same re-read on the
# next map load -- and BizHawk's melonDS core does mark its "ROM" memory
# domain writable, which was the one unanswered fact blocking this. Live-
# confirmed on 2026-08-24 with patches/diag_rom_domain_writable.lua: the
# probe wrote a genuinely different byte, read it back changed, then
# restored the original -- not a silently-ignored no-op.
#
# So client.py now writes `_VANILLA_WARP_TARGET` back over that word once
# the player is demonstrably past the redirect (see section 4 below for
# the handover mechanism, and client.py's own
# `_revoke_start_location_redirect` for the trigger condition and for why
# FLAG_GOT_STARTER alone is the wrong trigger). Two consequences worth
# stating plainly: the write lands on the emulator's in-memory ROM copy,
# never on the .nds file, so every fresh BizHawk launch starts from the
# patched ROM again and the client simply re-applies the revocation; and
# a ROM patched by a build without section 4's record (or played without
# the client) keeps the old permanent behaviour rather than breaking.

from __future__ import annotations

from rom import HeartGoldRom

# -- 1. Exit warp ---------------------------------------------------------

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
#
# Lake of Rage (T29, map id 88) was a candidate until 2026-08-24 and is
# deliberately not one any more -- see _TOWN_ENTRANCE_ANCHORS below for the
# collision reading that removed it.
TOWN_MAP_IDS: dict[str, int] = {
    "cherrygrove": 67,
    "violet": 73,
    "azalea": 74,
    "cianwood": 75,
    "goldenrod": 76,
    "olivine": 77,
    "ecruteak": 78,
    "mahogany": 87,
    "blackthorn": 89,
}

# Which entrance of the destination town the player lands at: the `anchor`
# half of the same u32 write_exit_warp_target patches (WarpEvent.header at
# byte 364, WarpEvent.anchor at 366 -- see this module's docstring). An
# anchor is an index into the destination map's own `warps` array, and the
# player materialises at that entry's x/z, so it is the only lever this
# design has over *where* in a town they arrive.
#
# Anchor 0 is the default and every town in TOWN_MAP_IDS uses it; it was
# live-verified for Cherrygrove and Goldenrod (both landed just outside the
# Pokemon Center).
#
# EMPTY since 2026-08-24, and the reason is the whole story of why Lake of
# Rage is no longer a candidate town at all. T29 has exactly two warps
# (zone_event 085_T29.json): anchor 0 = the Hidden Power house door at
# (497, 42), anchor 1 = the Fishing Guru house door at (536, 89). A player
# who started there on 2026-08-23 landed on anchor 0 and could not leave:
# the Hidden Power house's bank is a 16-tile patch of land ringed by the
# lake (see data_gen/regions.toml's comment on the Lake of Rage split, and
# `lake_of_rage_north`, the region that bank now belongs to). The fix
# attempted that day was to override this town to anchor 1, on the
# assumption that the Fishing Guru's shore is the one the Route 43 path
# opens onto. Reading the ROM's own land_data says otherwise: flooding T29
# on foot from Route 43's northern corridor reaches the shore holding Pryce
# and the hidden Full Restore, not the Fishing Guru's. With only two anchors
# in the map, that leaves T29 with no anchor at all that drops a player on a
# shore they can walk off, so the town was removed from TOWN_MAP_IDS (and
# from options.py's StartingTown) instead of guessing at a third.
#
# Kept as an empty mapping rather than deleted, with write_exit_warp_target
# still reading it: it is the module's only record of what an anchor is and
# of the anchor-0 convention every remaining town relies on, and an empty
# dict behind a `.get(town_key, 0)` is honest about doing nothing (unlike
# the section-3 constants that were deleted precisely because they *looked*
# active while equalling vanilla). A future town whose anchor 0 turns out to
# be wrong goes here.
_TOWN_ENTRANCE_ANCHORS: dict[str, int] = {}


def write_exit_warp_target(rom: HeartGoldRom, town_key: str) -> None:
    """Redirect Elm's Lab's own exit door to `town_key` (a TOWN_MAP_IDS
    key) instead of vanilla's New Bark outdoors, landing the player at that
    town's `_TOWN_ENTRANCE_ANCHORS` entrance (anchor 0 unless listed)."""
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
    anchor = _TOWN_ENTRANCE_ANCHORS.get(town_key, 0)
    struct.pack_into(
        "<I", entry, _WARP_TARGET_BYTE_OFFSET, TOWN_MAP_IDS[town_key] | (anchor << 16)
    )
    eventdata.write_entry(rom, _ZONE_EVENT_ELMS_LAB_INDEX, bytes(entry))


# -- 2. Entrance position: 4 attempts, all reverted, closed --------------
#
# WarpEvent.x/.z (byte offsets 360/362, immediately before .header at 364
# -- see write_exit_warp_target's own _WARP_TARGET_BYTE_OFFSET above;
# independently confirmed by walking the decomp's own static zone_event
# JSON: 11 BgEvents * 20 bytes + 4 ObjectEvents * 32 bytes + 3 leading
# u32 counts = 360) is vanilla (4, 14) -- right at the door, since this
# same record doubles as the door's own exit-side reference point (see
# section 1's own comment above). A real player held a directional input
# through the door transition and immediately walked back out and
# re-warped, because the anchor-0 landing spot (4, 14) IS the door tile.
#
# 2026-08-17 live-test history -- 4 values tried, all reverted, none
# shipped: (4, 9) (an unverified guess) left the player unable to move
# usefully at all; (3, 10) (the old sLocation_PlayerRoom design's own
# spawn point -- a genuinely different, ASM-free raw position override,
# not a real warp transition at all, so it never depended on the
# mechanism here) sits exactly inside the aide-greeting scene's own
# CoordEvent trigger strip (zone_event/058_T20R0101.json's {"x":3,
# "z":10,"w":4,"h":1}, driving scr_seq_0843_T20R0101.s's scr_seq_
# T20R0101_011); (4, 12) (same x as vanilla, 2 tiles further in, on the
# theory that a value on the same side of the trigger strip as vanilla
# would let a normal forward walk cross into it exactly like vanilla
# does); and (4, 13) (same theory, 1 tile closer) -- all four broke the
# Lab's own aide-greeting scene (never fires) and left the exit door
# unusable once movement was tested. The "cross into the CoordEvent zone
# from the correct side" theory does not fully explain the (4, 12)/(4,
# 13) failures either, so the real root cause is still unconfirmed.
#
# Closed, 2026-08-17 (user call after the 4th failed attempt): stop
# testing new values. A player holding a direction through the door
# transition can still walk straight back out -- accepted as a minor,
# avoidable annoyance, far better than a hard block on ever leaving the
# Lab. No function/constants for this left in the module (an unused
# function whose docstring claimed to move the entrance, but whose
# target constants equalled vanilla, would be a silent no-op if ever
# re-enabled without care -- this comment block is the record instead).


# -- 3. Greeting-scene trigger zone (EXPERIMENTAL, different approach) ----
#
# Different idea from section 2 above: instead of moving where the
# player lands (4 failed attempts, all reverted), keep the proven-safe
# vanilla landing spot (4, 14) and instead widen the CoordEvent step-on
# zone that fires the aide-greeting scene (scr_seq_0843_T20R0101.s's
# scr_seq_T20R0101_011, LockAll as its very first real action) so it
# covers the door tile itself, firing the instant the player arrives
# instead of after a few steps toward the room's middle. Since the
# script LockAlls immediately, this should also absorb/override a
# held-direction input that would otherwise walk the player straight
# back out through the door -- fixing the original "walk back out"
# annoyance without touching the warp landing position at all.
#
# CoordEvent struct (include/map_events_internal.h): scriptId, x, z, w,
# h, y, val, var -- 16 bytes. Two CoordEvents exist in this map (decomp's
# own static zone_event JSON, confirmed byte offsets by walking bg/
# object/warp counts the same way section 2 above did): index 0 at
# (x=3, z=11, w=4, h=1), fires scr_seq_T20R0101_003 only when
# VAR_SCENE_ELMS_LAB == 1 (the *other* CoordEvent, progresses the room's
# own state 1 -> 2 after a starter is chosen -- unrelated, untouched);
# index 1 at (x=3, z=10, w=4, h=1), fires scr_seq_T20R0101_011 only when
# VAR_SCENE_ELMS_LAB == 0 (the initial greeting -- this is the one being
# widened). Trigger zones use a [x, x+w) x [z, z+h) rectangle (confirmed
# by scr_seq_T20R0101_011's own GetPlayerCoords/Compare chain testing
# exactly x=3/4/5/6, matching w=4 precisely).
_ELMS_LAB_GREETING_COORD_H_BYTE_OFFSET = 400  # coord_events[1].h
_VANILLA_ELMS_LAB_GREETING_COORD_H = 1
# 6 covers z=10..15 inclusive -- one tile past the door itself (z=14),
# on the theory that the player isn't exactly at z=14 by the time this
# zone is checked (a real player report: holding a direction on arrival
# walked the character one step further before the check happened). The
# two CoordEvents can safely overlap z=11..13 since each only ever fires
# for its own, mutually exclusive VAR_SCENE_ELMS_LAB value (0 vs 1).
_ELMS_LAB_GREETING_COORD_H = 6


def write_elms_lab_greeting_zone_extension(rom: HeartGoldRom) -> None:
    """Widen the aide-greeting scene's own CoordEvent step-on zone
    (scr_seq_T20R0101_011, only active while VAR_SCENE_ELMS_LAB == 0)
    from its vanilla single row (z=10 only) to also cover the door tile
    and one tile past it -- see section 3's own comment above.

    NOT called from write_start_location (2026-08-17, live-tested and
    paused): a real player report of holding a direction on arrival
    walking the character *through* the door and ending up off-map is a
    worse failure mode than the original "walk back out" annoyance this
    was meant to fix, and widening the zone one tile further (to z=15)
    didn't resolve it either. Left defined, not deleted, in case the
    real cause (likely an overlap with the exit door's own trigger,
    unconfirmed) is found later."""
    import struct

    from rom import eventdata

    entry = bytearray(eventdata.read_entry(rom, _ZONE_EVENT_ELMS_LAB_INDEX))
    (current_h,) = struct.unpack_from("<H", entry, _ELMS_LAB_GREETING_COORD_H_BYTE_OFFSET)
    if current_h != _VANILLA_ELMS_LAB_GREETING_COORD_H:
        raise ValueError(
            f"Elm's Lab zone_event entry's greeting-CoordEvent h is {current_h}, expected the "
            f"vanilla value {_VANILLA_ELMS_LAB_GREETING_COORD_H} -- data_gen/decomp source may "
            "have drifted from the real ROM, refusing to guess."
        )
    struct.pack_into("<H", entry, _ELMS_LAB_GREETING_COORD_H_BYTE_OFFSET, _ELMS_LAB_GREETING_COORD_H)
    eventdata.write_entry(rom, _ZONE_EVENT_ELMS_LAB_INDEX, bytes(entry))


def write_start_location(rom: HeartGoldRom, town_key: str) -> None:
    """Apply the one door redirect this option needs: Elm's Lab's own exit
    to `town_key`. Everything before that door is untouched vanilla, from
    the bedroom spawn to Mom's scene to the walk across New Bark (see the
    module docstring's "Scope reduction, 2026-08-24" for the house-door
    redirect that used to live here and why it was dropped).

    Entrance position within Elm's Lab stays at exact vanilla (4, 14), and
    the aide-greeting trigger zone stays at its vanilla size -- see
    sections 2 and 3's own comments above for the combined 5 live-tested
    attempts at fixing the "walk back out if holding a direction on
    arrival" annoyance, all reverted (the last one made things actively
    worse -- a player ended up off-map). A player holding a direction
    through the door transition can still walk straight back out --
    accepted, for now, as a minor, avoidable annoyance far preferable to
    any of the failure modes tried so far."""
    write_exit_warp_target(rom, town_key)


# -- 4. Revocation record: telling the client where to write back --------
#
# client.py can undo the section-1 redirect at runtime (see this module's
# "Former known limitation" note above), but only if it knows the *absolute*
# byte offset of that one word in the finished .nds. It cannot work that
# out on its own: resolving "NitroFS a/0/3/2, NARC sub-file 58, byte 364"
# to an absolute offset means walking the ROM's FNT, then its FAT, then the
# NARC's own BTAF/BTNF/GMIF chunk chain, against a layout that is different
# for every seed (apnds.rom.Rom.to_bytes() re-lays-out every NitroFS file,
# and several patches in this project change file sizes, so the offset
# genuinely moves from build to build).
#
# It is not passed through slot_data either, even though that is how every
# other world -> client value travels (see __init__.py's fill_slot_data).
# It cannot be: slot_data is written at *generation* time, on a machine
# that by design never has the ROM (output_patch.py's own module docstring
# -- "patch() reads it fresh from settings on whichever machine actually
# has the ROM, not necessarily the one that ran generation"), and the
# offset only exists once a specific ROM has actually been packed.
#
# So the ROM carries the answer itself, in the one place whose absolute
# offset is fixed by the DS platform rather than by any packer: the
# cartridge header. Bytes 0x170-0x17F are "reserved (zero)" on every retail
# NTR cartridge (apnds names the field ZEROS_170; the DSi-only MBK fields
# start at 0x180 and are left alone), they sit past the header CRC-16 at
# 0x15E -- which covers 0x000-0x15D only, so stamping them does not
# invalidate it -- and far past the 0x4000-byte secure area with its own
# separate checksum. The client reads 12 bytes there, at a hardcoded
# offset, and gets both halves of what it needs. Nothing in the game or in
# melonDS reads that range.
#
# Deliberately magic-tagged rather than "nonzero means valid": an all-zero
# header field is exactly what a ROM patched by an older build (or one
# where randomize_start_location was off) has, and the client must treat
# that as "nothing to revoke" instead of as an offset of 0.
REVOCATION_RECORD_ROM_OFFSET = 0x170
REVOCATION_RECORD_MAGIC = b"HGSL"  # HeartGold Start Location
REVOCATION_RECORD_SIZE = 12  # magic (4) + u32 offset + u32 vanilla value


def build_revocation_record(warp_target_rom_offset: int) -> bytes:
    """The 12 bytes stamped at `REVOCATION_RECORD_ROM_OFFSET`: magic, the
    absolute offset of Elm's Lab's exit-warp target word in this packed
    ROM, and the vanilla value the client is to write back there."""
    import struct

    return REVOCATION_RECORD_MAGIC + struct.pack("<II", warp_target_rom_offset, _VANILLA_WARP_TARGET)


def parse_revocation_record(record: bytes) -> tuple[int, int] | None:
    """`(warp_target_rom_offset, vanilla_value)` from a
    `REVOCATION_RECORD_SIZE`-byte read at `REVOCATION_RECORD_ROM_OFFSET`,
    or None when this ROM carries no record at all (unpatched header, an
    older build, or randomize_start_location simply off) -- the caller
    then has nothing to revoke."""
    import struct

    if len(record) != REVOCATION_RECORD_SIZE or not record.startswith(REVOCATION_RECORD_MAGIC):
        return None
    warp_target_rom_offset, vanilla_value = struct.unpack_from("<II", record, len(REVOCATION_RECORD_MAGIC))
    if warp_target_rom_offset == 0:
        return None
    return warp_target_rom_offset, vanilla_value


def stamp_revocation_record(packed: bytearray) -> int:
    """Locate Elm's Lab's exit-warp target word in an already-packed ROM
    image and stamp the record describing it into that same image's
    cartridge header, in place. Returns the offset that was recorded.

    Takes the packed bytes rather than a HeartGoldRom precisely because
    the offset is a property of one serialization: it must be computed
    after the final `save_bytes()`, and the header is the only region that
    can then be edited without moving anything (it is a fixed-size prefix,
    and 0x170 is outside every checksum -- see section 4's comment).

    Refuses to stamp an offset that does not currently hold one of the
    redirect's own possible values: if the FNT/FAT/NARC walk ever pointed
    somewhere else, a client writing MAP_NEW_BARK there would corrupt an
    arbitrary ROM byte on every player's machine, so a mismatch is a hard
    error here rather than a silent bad record."""
    import struct

    from rom import eventdata

    offset = eventdata.entry_rom_offset(bytes(packed), _ZONE_EVENT_ELMS_LAB_INDEX) + _WARP_TARGET_BYTE_OFFSET
    (current,) = struct.unpack_from("<I", packed, offset)
    if (current & 0xFFFF) not in set(TOWN_MAP_IDS.values()):
        raise ValueError(
            f"packed ROM offset {offset:#x} holds {current:#x}, whose map id half is not one of this "
            f"option's destination towns {sorted(TOWN_MAP_IDS.values())} -- the computed offset for "
            "Elm's Lab's exit-warp target word does not point at that word, refusing to record it."
        )
    packed[REVOCATION_RECORD_ROM_OFFSET : REVOCATION_RECORD_ROM_OFFSET + REVOCATION_RECORD_SIZE] = (
        build_revocation_record(offset)
    )
    return offset
