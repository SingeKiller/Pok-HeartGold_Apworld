# client.py
#
# BizHawk in-game connector. Two jobs:
#   - Check detection: read the vanilla savedata flag bits directly (see
#     location_flags.py) -- no ROM patch needed.
#   - Remote items: write them into the running game's Bag savedata via
#     RAM once ctx.items_received reports them.
#
# Every read/write here is relative to the RAM address of the running
# game's SaveData struct, relocated fresh every session (see "Dynamic
# SaveData location" below) since HGSS double-buffers save data across two
# physical slots. See NOTES.md for the full derivation and history.
#
# HEARTGOLD_BAG_BASE_ADDRESS/HEARTGOLD_FLAGS_ARRAY_ADDRESS env vars are a
# manual override (skips the scan) for troubleshooting -- unset by
# default.

from __future__ import annotations

import base64
import logging
import os
import struct
from typing import TYPE_CHECKING

import worlds._bizhawk as bizhawk
from NetUtils import ClientStatus
from worlds._bizhawk.client import BizHawkClient

from data.items import ITEMS
from data.rules import BADGES
from items import HEARTGOLD_ITEM_ID_BASE
from location_flags import (
    build_dexsanity_flag_to_ap_location_id,
    build_flag_id_to_ap_location_id,
    build_locally_substituted_ap_location_ids,
)
from rom import HEARTGOLD_US_ID_CODE, SOULSILVER_US_ID_CODE
from rom.startlocation import (
    REVOCATION_RECORD_ROM_OFFSET,
    REVOCATION_RECORD_SIZE,
    parse_revocation_record,
)
from rom.worldsignature import (
    SLOT_AUTH_ROM_OFFSET,
    SLOT_AUTH_SIZE,
    WORLD_SIGNATURE_ROM_OFFSET,
    WORLD_SIGNATURE_SIZE,
    has_world_signature,
)
from save_layout import (
    BAG_POCKET_OFFSETS,
    BATTLE_SCENE_BIT,
    FLAGS_ARRAY_OFFSET,
    FLAGS_ARRAY_SIZE,
    POCKET_KEY_TO_BAG_FIELD,
    TEXT_SPEED_FAST_VALUE,
    TEXT_SPEED_MASK,
    flag_byte_and_bit,
    is_flag_set,
    plan_bag_item_write,
    stack_cap_for_pocket,
)
from universal_tracker import SLOT_DATA_OPTIONS_KEY

if TYPE_CHECKING:
    from worlds._bizhawk.context import BizHawkClientContext

# Manual override env vars -- unset by default, so the automatic scan below
# is what actually runs for players. ARM9 System Bus addresses (Main RAM
# domain + 0x02000000).
HEARTGOLD_BAG_BASE_ADDRESS_ENV = "HEARTGOLD_BAG_BASE_ADDRESS"
HEARTGOLD_FLAGS_ARRAY_ADDRESS_ENV = "HEARTGOLD_FLAGS_ARRAY_ADDRESS"


def _resolve_address_override(env_var: str) -> int | None:
    """`None` (the default) unless `env_var` is set to a parseable int
    (hex or decimal)."""
    raw = os.environ.get(env_var)
    if not raw:
        return None
    try:
        return int(raw, 0)
    except ValueError:
        return None


# -- Dynamic SaveData location -----------------------------------------------
#
# Locate SaveData fresh every session by scanning for SaveData.
# arrayHeaders[]'s own signature instead of trusting a fixed address --
# see NOTES.md for the full struct derivation.

_SAVE_ARRAY_HEADER_SIZE = 16  # include/save.h: SaveArrayHeader, 4+4+4+2+2
_SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT = 5  # SysInfo..SaveVarsFlags
_DYNAMIC_REGION_SIZE = 35 * 0x1000  # SAVE_PAGE_MAX * SAVE_SECTOR_SIZE
_SAVE_COUNTER_SIZE = 4
_BAG_CHUNK_ID = 3  # SAVE_BAG
_FLAGS_CHUNK_ID = 4  # SAVE_FLAGS
_POKEDEX_CHUNK_ID = 6  # SAVE_POKEDEX
_PARTY_CHUNK_ID = 2  # SAVE_PARTY
_GAMESTATS_CHUNK_ID = 16  # SAVE_GAMESTATS

# DeathLink send: GAME_STAT_PLAYER_MON_FAINTED counter, a real vanilla
# savedata field -- see NOTES.md for the struct derivation.
_GAME_STAT_PLAYER_MON_FAINTED_OFFSET = 338

# ...but that counter is NOT readable as a plain u16, and reading it as one
# was a real bug (player report, 2026-08-22: DeathLink fired at the *start*
# of a battle, with nothing fainted at all). `src/game_stats.c` keeps most
# of the GameStats chunk XOR-"encrypted" whenever it is not being actively
# read or written:
#
#   GameStats_Acquire(stats, idx) -> _MonDecryptSegment(secure region, ...)
#   ...read/modify one stat...
#   GameStats_Release(stats, idx) -> recompute unk_1BC (a plain byte-sum
#                                    checksum of the plaintext), then
#                                    _MonEncryptSegment(secure region, ...)
#
# Every accessor (GameStats_Inc/_Add/_SetCapped/_GetCapped/_UpdateBounded)
# is that exact Acquire/.../Release sandwich, all synchronous, so at rest
# the region is ALWAYS encrypted -- a raw read of offset 338 returns
# ciphertext, never the counter.
#
# Worse than merely wrong: the key is `unk_1BC + (unk_1BE << 16)` and
# unk_1BC is recomputed from the plaintext on every single Release, so
# *any* stat changing re-encrypts the whole region under a brand new key
# and every ciphertext halfword in it jumps to a fresh pseudo-random
# value. GAME_STAT_WILD_ENCOUNTERS (8) and GAME_STAT_TRAINER_BATTLES (9)
# are incremented exactly when a battle starts, which is precisely the
# moment the player observed -- roughly one battle in two produced a
# ciphertext that happened to compare greater than the previous one and
# sent a bogus death.
#
# So the send side decrypts, following src/math_util.c's own
# _MonEncryptSegment/MonEncryptionLCRNG:
#
#   seed = unk_1BC + (unk_1BE << 16)
#   for each u16 of the secure region, in order:
#       seed = seed * 1103515245 + 24691   (mod 2**32)
#       plaintext = ciphertext ^ (u16)(seed >> 16)
#
# The secure region starts at `offsetof(GameStats, statsWords) + 2 *
# sizeof(u32)` (statsWords[0]/[1], GAME_STAT_STEPS_WALKED/_BIKED, are left
# in the clear -- GameStats_Release/_Acquire are both no-ops for
# `statIdx <= 1`) and ends at `offsetof(GameStats, unk_1BC)`, i.e. bytes
# 8..443 of a struct laid out as u32 statsWords[72] (0..287), u16
# statsHalf[77] (288..441), u16 dummy (442), u16 unk_1BC (444), u16
# unk_1BE (446).
_GAMESTATS_SECURE_REGION_OFFSET = 8
_GAMESTATS_CHECKSUM_OFFSET = 444  # offsetof(GameStats, unk_1BC)
_GAMESTATS_KEY_HIGH_OFFSET = 446  # offsetof(GameStats, unk_1BE)
_GAMESTATS_LCRNG_MULTIPLIER = 1103515245
_GAMESTATS_LCRNG_INCREMENT = 24691

# GameStats_GetMaxValue: a statsHalf[] stat whose sIsExtraWide[] entry is
# FALSE (index 97's is) is capped at 9999 by every writer, so a decrypted
# value above that cannot come from a real save and is treated as a bad
# read (keep the old baseline, send nothing, retry next tick).
_MAX_PLAUSIBLE_PLAYER_MON_FAINTED = 9999

# A tick is roughly one second and a fainting animation is several, so a
# genuine increase is 1 (2 at the very most, in a double battle). Anything
# larger is not a real sequence of faints: re-baseline on it, but never
# send a death for it. Deliberately generous at a full party's worth --
# the point is to reject the ~65000-wide random jumps a wrong decryption
# key would produce, not to police plausible play.
_MAX_PLAUSIBLE_FAINTS_PER_TICK = 6

# DeathLink receive: PartyCore/PartyPokemon layout for zeroing current HP,
# a plain unencrypted savedata field -- see NOTES.md for the derivation.
_PARTY_CUR_COUNT_OFFSET = 4
_PARTY_MONS_OFFSET = 8
_PARTY_POKEMON_STRUCT_SIZE = 0xEC
_PARTY_POKEMON_HP_OFFSET = 0x96
_PARTY_MAX_SIZE = 6

# Pokedex.caughtSpecies -- see location_flags.dexsanity_pokedex_bit_for_species.
_POKEDEX_CAUGHT_SPECIES_OFFSET = 4
_POKEDEX_CAUGHT_SPECIES_SIZE = 64

# struct Pokedex's very first field (include/pokedex.h: `u32 magic;`, i.e.
# offset 0, immediately before caughtSpecies). POKEDEX_MAGIC is a fixed
# 32-bit constant the game writes once in Save_Pokedex_Init and asserts on
# in every single Pokedex accessor macro (src/pokedex.c) -- never a
# player-varying value, which is exactly what makes it usable as a
# "these addresses still point at this game's live SaveData" probe. See
# the check-report guard section below for how that is used.
_POKEDEX_MAGIC_OFFSET = 0
_POKEDEX_MAGIC = 0xBEEFCAFE

_PLAYERDATA_CHUNK_ID = 1  # SAVE_PLAYERDATA

# include/player_data.h PLAYERDATA/PlayerProfile layout -- see NOTES.md
# for the full field-offset derivation, including the badge-flag bit
# split (johtoBadges for badge_no < 8, kantoBadges otherwise).
_PLAYERDATA_PROFILE_OFFSET = 4

# Options sits at the start of PLAYERDATA (offset 0) -- see save_layout.py
# for the live-verified bit layout.
_PLAYERDATA_OPTIONS_OFFSET = 0
_PROFILE_MONEY_OFFSET = 20
_PROFILE_JOHTO_BADGES_OFFSET = 26
_PROFILE_KANTO_BADGES_OFFSET = 31
_MAX_MONEY = 999999  # include/player_data.h: MAX_MONEY

# Scan window for arrayHeaders -- generous but bounded (EWRAM is 4 MiB
# total). See NOTES.md for how this range was chosen.
_ARRAY_HEADERS_SCAN_START = 0x02298000
_ARRAY_HEADERS_SCAN_LENGTH = 0x10000
# Larger single reads have been observed to fail against the BizHawk
# connector -- read in bounded chunks instead.
_ARRAY_HEADERS_SCAN_READ_CHUNK = 0x4000


async def _read_chunked(ctx: BizHawkClientContext, address: int, length: int, domain: str) -> bytes:
    """Read `length` bytes starting at `address`, splitting into
    _ARRAY_HEADERS_SCAN_READ_CHUNK-sized requests."""
    out = bytearray()
    offset = 0
    while offset < length:
        step = min(_ARRAY_HEADERS_SCAN_READ_CHUNK, length - offset)
        piece = (await bizhawk.read(ctx.bizhawk_ctx, [(address + offset, step, domain)]))[0]
        out.extend(piece)
        offset += step
    return bytes(out)


def _looks_like_array_headers(data: bytes, offset: int) -> bool:
    """True if data[offset:] starts with _SAVE_ARRAY_HEADER_SIGNATURE_
    CHUNK_COUNT consecutive SaveArrayHeader records whose id fields are
    exactly 0, 1, 2, ... in order."""
    needed = _SAVE_ARRAY_HEADER_SIZE * _SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT
    if offset + needed > len(data):
        return False
    for chunk_id in range(_SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT):
        record_offset = offset + chunk_id * _SAVE_ARRAY_HEADER_SIZE
        (record_id,) = struct.unpack_from("<i", data, record_offset)
        if record_id != chunk_id:
            return False
    return True


def _find_array_headers_candidates(data: bytes) -> list[int]:
    """Every offset into `data` where `_looks_like_array_headers` matches.
    Returns every candidate (not just the first), so `_locate_save_
    addresses` can verify each against real Bag contents."""
    needed = _SAVE_ARRAY_HEADER_SIZE * _SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT
    return [offset for offset in range(0, len(data) - needed, 4) if _looks_like_array_headers(data, offset)]


async def _find_array_headers_address(ctx: BizHawkClientContext) -> int | None:
    """First plausible arrayHeaders candidate address, unverified against
    real Bag contents. `_locate_save_addresses` (the real session-start/
    reload path) uses `_find_array_headers_candidates` plus a
    plausibility check instead."""
    data = await _read_chunked(ctx, _ARRAY_HEADERS_SCAN_START, _ARRAY_HEADERS_SCAN_LENGTH, "ARM9 System Bus")
    candidates = _find_array_headers_candidates(data)
    return _ARRAY_HEADERS_SCAN_START + candidates[0] if candidates else None


async def _chunk_offset(ctx: BizHawkClientContext, array_headers_address: int, chunk_id: int) -> int:
    """Read arrayHeaders[chunk_id].offset directly (ground truth, exactly
    what the game itself uses internally)."""
    record_address = array_headers_address + chunk_id * _SAVE_ARRAY_HEADER_SIZE
    record_bytes = (
        await bizhawk.read(ctx.bizhawk_ctx, [(record_address, _SAVE_ARRAY_HEADER_SIZE, "ARM9 System Bus")])
    )[0]
    _record_id, _size, offset, _crc, _slot = struct.unpack("<iIIHH", bytes(record_bytes))
    return offset


# A real Bag "items" pocket slot (u16 id, u16 quantity) is either empty
# (id 0) or a real item id in a small stack.
_MAX_PLAUSIBLE_ITEM_ID = 536
_MAX_PLAUSIBLE_ITEM_QUANTITY = 999
_PLAUSIBILITY_CHECK_SLOT_COUNT = 8


async def _bag_looks_plausible(ctx: BizHawkClientContext, bag_address: int) -> bool:
    """Read the first _PLAUSIBILITY_CHECK_SLOT_COUNT "items"-pocket slots
    at a candidate bag_address and check every one looks like a real
    ItemSlot -- the verification step the arrayHeaders signature alone
    doesn't provide."""
    slot_bytes = (
        await bizhawk.read(ctx.bizhawk_ctx, [(bag_address, _PLAUSIBILITY_CHECK_SLOT_COUNT * 4, "ARM9 System Bus")])
    )[0]
    for i in range(_PLAUSIBILITY_CHECK_SLOT_COUNT):
        item_id, quantity = struct.unpack_from("<HH", bytes(slot_bytes), i * 4)
        if item_id == 0:
            continue
        if not (1 <= item_id <= _MAX_PLAUSIBLE_ITEM_ID and quantity <= _MAX_PLAUSIBLE_ITEM_QUANTITY):
            return False
    return True


async def _locate_save_addresses(
    ctx: BizHawkClientContext,
) -> tuple[int, int, int, int, int, int, int] | None:
    """Locate this session's real Bag/SaveVarsFlags.flags[]/Pokedex.
    caughtSpecies/PlayerProfile/Party/GameStats addresses fresh. Tries
    every scan candidate, accepting the first whose derived Bag address
    passes `_bag_looks_plausible`. Returns None if nothing plausible was
    found (caller retries next tick)."""
    data = await _read_chunked(ctx, _ARRAY_HEADERS_SCAN_START, _ARRAY_HEADERS_SCAN_LENGTH, "ARM9 System Bus")

    for candidate_offset in _find_array_headers_candidates(data):
        array_headers_address = _ARRAY_HEADERS_SCAN_START + candidate_offset
        dynamic_region_base = array_headers_address - _SAVE_COUNTER_SIZE - _DYNAMIC_REGION_SIZE
        bag_chunk_offset = await _chunk_offset(ctx, array_headers_address, _BAG_CHUNK_ID)
        bag_address = dynamic_region_base + bag_chunk_offset

        if not await _bag_looks_plausible(ctx, bag_address):
            continue

        flags_chunk_offset = await _chunk_offset(ctx, array_headers_address, _FLAGS_CHUNK_ID)
        flags_array_address = dynamic_region_base + flags_chunk_offset + FLAGS_ARRAY_OFFSET
        pokedex_chunk_offset = await _chunk_offset(ctx, array_headers_address, _POKEDEX_CHUNK_ID)
        pokedex_caught_species_address = dynamic_region_base + pokedex_chunk_offset + _POKEDEX_CAUGHT_SPECIES_OFFSET
        playerdata_chunk_offset = await _chunk_offset(ctx, array_headers_address, _PLAYERDATA_CHUNK_ID)
        playerdata_profile_address = dynamic_region_base + playerdata_chunk_offset + _PLAYERDATA_PROFILE_OFFSET
        party_chunk_offset = await _chunk_offset(ctx, array_headers_address, _PARTY_CHUNK_ID)
        party_address = dynamic_region_base + party_chunk_offset
        gamestats_chunk_offset = await _chunk_offset(ctx, array_headers_address, _GAMESTATS_CHUNK_ID)
        gamestats_address = dynamic_region_base + gamestats_chunk_offset
        return (
            bag_address,
            flags_array_address,
            pokedex_caught_species_address,
            playerdata_profile_address,
            array_headers_address,
            party_address,
            gamestats_address,
        )

    return None


async def _array_headers_still_valid(ctx: BizHawkClientContext, array_headers_address: int) -> bool:
    """Cheap per-tick check: re-read the signature bytes at a previously-
    found arrayHeaders address and confirm they still match. If this
    fails (e.g. a save reload), the caller re-runs the full scan."""
    signature_size = _SAVE_ARRAY_HEADER_SIZE * _SAVE_ARRAY_HEADER_SIGNATURE_CHUNK_COUNT
    try:
        data = (
            await bizhawk.read(ctx.bizhawk_ctx, [(array_headers_address, signature_size, "ARM9 System Bus")])
        )[0]
    except bizhawk.RequestFailedError:
        return False
    return _looks_like_array_headers(bytes(data), 0)


# Server data-storage key remembering, across client restarts, how many
# of ctx.items_received have already been written into the bag (no in-
# ROM/in-save counter exists to read this from). Known limitation: a save
# reload from before some already-applied remote items were written does
# not roll this counter back, so those items are not re-granted -- fixing
# that needs ROM/ARM-hook cooperation, out of scope for this client-only
# v1.
_APPLIED_ITEM_COUNT_KEY_TEMPLATE = "pokemon_heartgold_applied_item_count_{team}_{slot}_{trainer_id}"

# trainer_id is part of this key for exactly the same reason it is part of
# the one above, and leaving it out was a real bug (2026-08-22): the flag
# is set once, server-side, forever, but the money it guards lives in the
# dynamic save region that "New Game" wipes (src/save.c's
# Save_InitDynamicRegion_Internal MI_CpuClearFast's the whole thing). A
# player who connected, got their starting money, then started a new file
# on the same slot never saw that money again -- the server flag said
# "already applied" and self._starting_money_applied said the same.
_STARTING_MONEY_APPLIED_KEY_TEMPLATE = "pokemon_heartgold_starting_money_applied_{team}_{slot}_{trainer_id}"

# Second half of that resume point: the counter above can only express a
# *contiguous* prefix of ctx.items_received, but a full Bag pocket blocks
# exactly one pocket's worth of items and nothing else (real bug,
# 2026-08-19: one item bound for a full pocket used to freeze delivery of
# the entire queue forever, including items bound for pockets with 100
# free slots). Items delivered ahead of the counter while an earlier one
# waits for room are remembered here as a bitmask of items_received
# indices, so a client restart re-delivers none of them and loses none of
# the still-pending ones either. Stored with the "or" operation for the
# same reason the counter uses "max": it can only ever gain information,
# so no stale or out-of-order write can resurrect an already-delivered
# item.
_DELIVERED_AHEAD_KEY_TEMPLATE = "pokemon_heartgold_delivered_ahead_{team}_{slot}_{trainer_id}"


def _indices_from_mask(mask: int) -> set[int]:
    """Bit index set of `mask` (see _DELIVERED_AHEAD_KEY_TEMPLATE)."""
    return {index for index in range(mask.bit_length()) if (mask >> index) & 1}


def _mask_from_indices(indices: set[int]) -> int:
    mask = 0
    for index in indices:
        mask |= 1 << index
    return mask

# randomize_start_location: FLAG_GOT_STARTER (include/constants/flags.h,
# 0x6A) is already set by the vanilla ChooseStarter scene itself (that
# scene runs completely unmodified -- see rom/startlocation.py) --
# FLAG_GOT_BAG/_TRAINER_CARD/_SAVE_BUTTON/_OPTIONS_BUTTON are no longer
# poked directly here either (redesign, 2026-08-17, real bug report: the
# real save-execution path turned out to check something the icon-
# visibility flag alone doesn't satisfy, silently breaking Save entirely
# -- see rom/startlocation.py's own "Redesign" note). The player's house
# door now redirects to Elm's Lab only *after* Mom's own vanilla scene
# has already granted those four for real. What's left here is only
# FLAG_GOT_POKEDEX/_POKEGEAR (still skipped content -- Route 30's Mr.
# Pokemon, and Mom's own later revisit conversation, neither reachable
# from this redirected path) and advancing the rival's own flag chain so
# he still eventually appears at his next real checkpoint instead of
# never again.
_START_LOCATION_FLAG_GOT_STARTER = 0x6A
_START_LOCATION_FLAGS_TO_SET = (
    0x6B,  # FLAG_GOT_POKEDEX
    0x9C,  # FLAG_GOT_POKEGEAR
    0x190,  # FLAG_HIDE_NEW_BARK_RIVAL
)
_START_LOCATION_FLAGS_TO_CLEAR = (0x19C,)  # FLAG_HIDE_CHERRYGROVE_RIVAL

# randomize_start_location, runtime revocation of the exit redirect.
#
# The ROM patch that implements this option redirects Elm's Lab's exit
# door to the YAML's town permanently (rom/startlocation.py section 1),
# which is wrong for every later visit to the Lab: coming home and walking
# out of it should lead to New Bark, as in vanilla. The client undoes the
# redirect by writing the vanilla map id back over that same word in
# BizHawk's "ROM" memory domain -- the game re-reads the record from
# NitroFS on every map load (src/map_events.c's Field_InitMapEvents /
# MapEvents_ReadFromNarc), so the very next load picks the change up.
#
# Where to write comes out of the ROM's own cartridge header, stamped
# there at patch time -- see rom/startlocation.py section 4 for why that,
# and not slot_data, is the handover channel.
#
# WHEN to write is the delicate half, and FLAG_GOT_STARTER is emphatically
# NOT the answer on its own: the vanilla ChooseStarter scene sets it while
# the player is still standing *inside* the Lab, i.e. before they have
# used the redirected door even once. Revoking there would defeat the
# whole option -- the player would walk out into New Bark and never see
# their starting town. So the real condition is "the player is somewhere
# that is neither New Bark nor Elm's Lab", read from LocalFieldData.
# currentPosition.mapId. Elm's Lab has exactly one warp (its own exit
# door), so the only way to be on a third map at all is to have gone
# through the redirect already. FLAG_GOT_STARTER is still required on top,
# as a cheap guarantee that the opening sequence really has played out and
# that this is not some pre-game/menu state with a stale map id.
_START_LOCATION_MAP_NEW_BARK = 60  # include/constants/maps.h: MAP_NEW_BARK
_START_LOCATION_MAP_ELMS_LAB = 61  # MAP_NEW_BARK_ELMS_LAB_1F
_START_LOCATION_HOME_MAP_IDS = (_START_LOCATION_MAP_NEW_BARK, _START_LOCATION_MAP_ELMS_LAB)

# src/save_local_field_data.c: `struct LocalFieldData` opens with `Location
# currentPosition;`, itself opening with `int mapId;` (include/
# field_types_def.h) -- so the live map id is the first word of the
# SAVE_LOCAL_FIELD_DATA chunk. It is genuinely live, not a save-time
# snapshot: FieldSystem.location is a bare pointer *into* this savedata
# field (src/overlay_124.c's FieldSystem_Init), and src/field/fieldmap.c's
# FieldMap_ChangeZone assigns through it (`fieldSystem->location->mapId =
# newMapID;`) on every zone change.
_LOCAL_FIELD_DATA_CHUNK_ID = 5  # SAVE_LOCAL_FIELD_DATA (src/save_arrays.c)
_LOCAL_FIELD_DATA_CURRENT_MAP_ID_OFFSET = 0

# randomize_start_location, blackout spawn repair (real player report: a
# Goldenrod start, a whiteout before any Pokemon Center visit, and the
# player woke up in New Bark with no way back without Cut or the
# Squirtbottle).
#
# The whiteout destination is `LocalFieldData.lastSpawn`
# (src/save_local_field_data.c:21), resolved by src/blackout.c:199-201
# through sSpawnMaps (asm/unk_0203BA5C.s). It starts at GetMomSpawnId() == 1
# (Save_LocalFieldData_Init, :49) and is only rewritten on a non-connection
# map load into a map that is some entry's death-warp map
# (src/field_warp_tasks.c:268-271, MapHeader_GetSpawnIdForDeathWarp), i.e.
# a Pokemon Center 1F or the player's own house. The redirected Lab door
# lands on the town's outdoor map, which is no such map, so the value stays
# at New Bark's until the first Center.
#
# Offset: five `Location` (include/field_types_def.h: five `int`, 20 bytes
# each) = 100, then `u16 musicId` (100), `u16 weather` (102), `u16
# lastSpawn` (104).
_LOCAL_FIELD_DATA_LAST_SPAWN_OFFSET = 104
_SPAWN_ID_NEW_BARK = 1  # GetMomSpawnId(), sSpawnMaps[0] (player's house 1F)
# Spawn id = sSpawnMaps index + 1 (SpawnIdToTableIndex subtracts 1); each of
# these entries' death-warp map is that town's own Pokemon Center 1F.
_START_LOCATION_TOWN_SPAWN_IDS: dict[str, int] = {
    "cherrygrove": 2,
    "violet": 3,
    "azalea": 4,
    "cianwood": 5,
    "goldenrod": 6,
    "olivine": 7,
    "ecruteak": 8,
    "mahogany": 9,
    "blackthorn": 11,  # 10 is Lake of Rage, not a blackout spawn
}
# "Already handled on this save" latch. lastSpawn legitimately goes back to
# 1 whenever the player later walks into their own house, so the value alone
# cannot say whether the client may still write. The latch lives in the
# savedata itself, written in the same guarded write as lastSpawn, so it
# follows the save file exactly (reloading an older save restores both).
# FLAG_UNK_B5A is referenced nowhere in the decomp (scripts, C or asm) nor
# claimed anywhere else in this project (rom/npcgiftgatedata.py holds
# 0xB48-0xB4F, rom/badgedata.py 0xB50-0xB59).
_BLACKOUT_SPAWN_LATCH_FLAG = 0xB5A

# magnet_train on: the Power Plant counts as repaired from the start.
#
# A policeman blocks both Magnet Train stations until FLAG_RESTORED_POWER is
# set, and that flag is the only thing the three station-side branches
# test (scr_seq_0893_T25R0501.s:20/28/39, scr_seq_0834_T11R0601.s:21/40/51):
# OnResume moves him aside, OnTransition resets VAR_UNK_410B/411D to 0 so
# the Pass-check coord event stays armed, and talking to him no longer
# refuses. The platform map is not chosen by the flag at all: both 1F warp
# tables always lead to the *_2F_EMPTY map, and the ride itself is the
# frame script fired by VAR_UNK_411E/411F, which only the Pass check sets.
# So setting the flag is enough for the train, with no script patch.
#
# The rest reproduces the side effects of the vanilla repair block
# (scr_seq_0196_R10R0202.s:54-64) minus the TM57 hand-out, which
# locations.POWER_PLANT_PRERESTORED_SKIPPED_LOCATION_KEYS removes from the
# pool instead: FLAG_UNK_258 opens the Route 5/6 Underground Path gates,
# the Lavender radio director appears (EXPN Card), and the Copycat / Fan
# Club lost-doll chain is armed, which is also the one that gives the Pass.
_FLAG_RESTORED_POWER = 0x118
_POWER_PLANT_FLAGS_TO_SET = (
    _FLAG_RESTORED_POWER,
    0x258,  # FLAG_UNK_258, Underground Path gates
)
_POWER_PLANT_FLAGS_TO_CLEAR = (0x259,)  # FLAG_HIDE_LAVENDER_RADIO_TOWER_DIRECTOR
# Only while the Copycat's own chain has not moved yet (VAR_UNK_40FF == 0):
# she sets the doll flag back and the var to 2 herself later
# (scr_seq_0841_T11R0802.s:77/86).
_COPYCAT_CHAIN_VAR = 0x40FF  # VAR_UNK_40FF
_COPYCAT_CHAIN_FLAGS_TO_SET = (0x2FB,)  # FLAG_HIDE_SAFFRON_CITY_COPYCAT_HOUSE_CLEFAIRY_DOLL
_COPYCAT_CHAIN_FLAGS_TO_CLEAR = (0x2FC,)  # FLAG_HIDE_VERMILION_FAN_CLUB_LOST_ITEM
# Once FLAG_RESTORED_POWER is set, Route 10's door always loads the
# REPAIRED map (scr_seq_0191_R10.s:135), so the broken map's own
# first-visit scene (scr_seq_0196_R10R0202.s:93-120) can never run. That
# scene is what arms the Cerulean Gym Rocket (VAR_UNK_411C = 1, clears
# FLAG_HIDE_CERULEAN_GYM_ROCKET), whose escape is the only thing that sends
# Misty on her Route 25 date (scr_seq_0760_T04GYM0101.s:123-127), and
# Misty plus her whole gym stay hidden (FLAG_HIDE_CERULEAN_GYM_POPULATION)
# until that date is over (scr_seq_0216_R25.s:170). Without this, the
# Cascade Badge, TM03 and every Cerulean Gym trainer would be lost. Only
# written while VAR_UNK_411C is still 0.
_CERULEAN_CHAIN_VAR = 0x411C  # VAR_UNK_411C
_CERULEAN_CHAIN_VAR_VALUE = 1
_CERULEAN_CHAIN_FLAGS_TO_CLEAR = (0x254,)  # FLAG_HIDE_CERULEAN_GYM_ROCKET
_VAR_BASE = 0x4000  # include/constants/vars.h

# Vermilion Gym: withhold the Thunder Badge bit around Lt. Surge's gym until
# he is actually beaten (real player report: all 15 trash cans empty and an
# invisible wall, a permanent softlock).
#
# src/gymmick_init.c:56 InitVermilionGym, run by `VermilionGymInit` from the
# gym's OnTransition script (scr_seq_0778_T06GYM0101.s, script _021), reads
# `PlayerProfile_TestBadgeFlag(BADGE_THUNDER)` as "puzzle already solved":
# it then zeroes both switch positions and opens both gates, and never calls
# PlaceVermilionGymSwitches. But the six obj_T06GYM0101_stop objects are
# only hidden by FLAG_HIDE_VERMILION_GYM_STOPS (0x31A), set solely in
# Surge's own win branch (script _023). With badges delivered on receipt
# (see _apply_pending_badges), the bit can predate that win, and the gym
# loads with no switches and blocking stops: unsolvable.
#
# InitVermilionGym is the ONLY Init*Gym that tests a badge (gymmick_init.c),
# and BADGE_THUNDER gates no field move (src/field_move.c tests Hive, Storm,
# Fog, Plain, Zephyr, Rising, Earth and Glacier only; field_control.c's
# surf prompt tests Fog), so clearing the bit locally costs no capability.
# The gym's other two `CheckBadge BADGE_THUNDER` (scripts _024, _025) only
# pick NPC dialogue, and Surge's own battle gate is regated onto 0x31A by
# rom/badgegatedata.py. Transient side effects while withheld, all reverting
# as soon as the player leaves: PlayerProfile_CountBadges is one lower, so
# the trainer card, the continue screen, the whiteout money penalty
# (src/battle/battle_system.c CalcMoneyLoss) and, for a player at exactly 8
# badges, the obedience cap (src/battle/battle_controller_player.c) see one
# badge fewer. The n_badges goal is unaffected: it counts received AP items
# (__init__.py _goal_rule), never this bit.
#
# The bit is withheld in the city as well as in the gym because the gym's
# OnTransition runs on the warp INTO the gym: it must already read clear
# while the player is still outside. A player already stuck inside only has
# to walk out and back in. 0x31A doubles as the stop condition: nothing in
# the game ever clears it, and the badge location reads the same flag.
# Needs no slot_data key, so it also covers seeds generated before it.
_BADGE_THUNDER_INDEX = 10  # include/constants/badge.h: BADGE_THUNDER
_FLAG_HIDE_VERMILION_GYM_STOPS = 0x31A
_MAP_VERMILION = 54  # include/constants/maps.h: MAP_VERMILION (MAP_T06)
_MAP_VERMILION_GYM = 365  # MAP_VERMILION_GYM (MAP_T06GYM0101)
_THUNDER_BADGE_WITHHELD_MAP_IDS = (_MAP_VERMILION, _MAP_VERMILION_GYM)

# Goal reporting (real organizer report: "release on goal" never fired,
# because this client never sent CLIENT_GOAL at all). Values mirror
# options.Goal; slot_data has carried `goal` and `goal_badge_count` since
# before this fix, so running seeds are covered by an apworld update alone.
#
# elite_four: FLAG_GAME_CLEAR (include/constants/flags.h), set by
# CallTask_GameClear (src/game_clear.c:293) on entering the Hall of Fame.
#
# champion_red: Red's own win branch (scr_seq_0107_D41R0108.s) runs
# `SetFlag FLAG_UNK_25F` (his object's hide flag, zone_event/
# 419_D41R0108.json) and `SetVar VAR_UNK_40FD, 1`. FLAG_GAME_CLEAR cannot
# serve here: it is already set by the Elite Four win, and HOFCredits after
# Red sets it again. FLAG_UNK_25F alone is not enough either, since Oak's
# Mt. Silver scene clears it (scr_seq_0825_T10R0701.s:115): both are
# required, and VAR_UNK_40FD is written nowhere else in the decomp.
#
# n_badges: received badge_* AP items, the exact count __init__.py's
# _goal_rule uses. Never the PlayerProfile bits (the Thunder bit is
# withheld locally in Vermilion, see _BADGE_THUNDER_INDEX).
_GOAL_ELITE_FOUR = 0
_GOAL_CHAMPION_RED = 1
_GOAL_N_BADGES = 2
# johto_only caps the n_badges goal at Johto's 8 (__init__.py, set_rules).
# The flag reaches the client through the nested UT options snapshot only.
_JOHTO_BADGE_COUNT = 8
_FLAG_GAME_CLEAR = 0x964
_FLAG_RED_DEFEATED = 0x25F  # FLAG_UNK_25F
_VAR_RED_DEFEATED = 0x40FD  # VAR_UNK_40FD

# task M1.5: cap on how many pending items _apply_received_items will write
# in a single game_watcher tick -- batches a large backlog (e.g. right
# after connecting, or catching up after a big multiworld fill) down to a
# handful of ticks instead of one item per tick (roughly one per second on
# a real BizHawk session), while still bounding how long any one tick's
# run of Bag read/write RPC round trips can take.
_MAX_ITEMS_APPLIED_PER_TICK = 20

# Consecutive failed Bag writes before the save data addresses are
# re-located from scratch (v0.2.5). A player report (k0p1, 2026-09-17):
# badges kept arriving but Bag items did not until a reset, which is what a
# stale Bag address looks like -- the reset forced a fresh scan. A failed
# guarded write is otherwise treated as transient and retried forever.
_BAG_WRITE_FAILURES_BEFORE_RELOCATE = 3

# Wing item -> the flag its monk tests since v0.2.5 (rom/wingmonkdata.py).
_WING_PASS_FLAGS = {"rainbow_wing": 0xB5B, "silver_wing": 0xB5C}
# Per version: (the wing the Pewter old man hands over, the hide flag of
# the legendary that handover reveals, that legendary's caught flag).
# include/constants/flags.h: FLAG_HIDE_BELL_TOWER_HO_OH 0x242,
# FLAG_HIDE_WHIRL_ISLAND_LUGIA 0x243, FLAG_CAUGHT_HO_OH 0x116,
# FLAG_CAUGHT_LUGIA 0x117.
_PEWTER_WING_LEGENDARY = {
    "heartgold": ("silver_wing", 0x243, 0x117),
    "soulsilver": ("rainbow_wing", 0x242, 0x116),
}


def _pocket_looks_plausible(pocket_bytes: bytes) -> bool:
    """Every slot is empty or a real item id with a sane quantity. A pocket
    read that fails this is not a full pocket, it is the wrong address."""
    for offset in range(0, len(pocket_bytes), 4):
        item_id, quantity = struct.unpack_from("<HH", pocket_bytes, offset)
        if item_id == 0:
            continue
        if not (1 <= item_id <= _MAX_PLAUSIBLE_ITEM_ID and quantity <= _MAX_PLAUSIBLE_ITEM_QUANTITY):
            return False
    return True


# -- Item id <-> Bag pocket mapping ------------------------------------------


def _build_ap_item_id_to_bag_write_info() -> dict[int, tuple[int, str]]:
    """AP item id -> (native HG/SS item id, Bag field name to write it
    into)."""
    result: dict[int, tuple[int, str]] = {}
    for data in ITEMS.values():
        bag_field = POCKET_KEY_TO_BAG_FIELD.get(data["pocket"])
        if bag_field is None:
            continue
        result[HEARTGOLD_ITEM_ID_BASE + data["id"]] = (data["id"], bag_field)
    return result


_AP_ITEM_ID_TO_BAG_WRITE_INFO = _build_ap_item_id_to_bag_write_info()


def _build_ap_item_id_to_badge_index() -> dict[int, int]:
    """AP item id -> badge.h's own BADGE_* index (0-15), for the 16
    badge_<name> synthetic items. pocket = "badge" is deliberately absent
    from POCKET_KEY_TO_BAG_FIELD, so these never appear in
    _AP_ITEM_ID_TO_BAG_WRITE_INFO above -- receiving one instead sets the
    matching bit in PlayerProfile.johtoBadges/kantoBadges."""
    result: dict[int, int] = {}
    for key, data in ITEMS.items():
        if data["pocket"] != "badge":
            continue
        badge_name = key.removeprefix("badge_")
        result[HEARTGOLD_ITEM_ID_BASE + data["id"]] = BADGES[badge_name]
    return result


_AP_ITEM_ID_TO_BADGE_INDEX = _build_ap_item_id_to_badge_index()

# NOTE: the client no longer keeps a badge index -> sentinel flag map of its
# own. Until 2026-08-19 it used one to *withhold* a received badge's
# PlayerProfile bit until that gym Leader had actually been beaten; the gym
# gates are now regated onto those same sentinel flags directly in the ROM
# (rom/badgegatedata.py), so the bit is written on receipt and the client
# has no reason to read them. They are still very much in use for badge
# *check detection*, through _FLAG_ID_TO_AP_LOCATION_ID below --
# location_flags.build_flag_id_to_ap_location_id resolves each badge
# location to the exact same sentinel via _SYNTHETIC_ID_FLAG_OVERRIDES.

_FLAG_ID_TO_AP_LOCATION_ID = build_flag_id_to_ap_location_id()

# Pokedex.caughtSpecies bit -> AP location id (task M3.4, Dexsanity) -- a
# separate savedata array from SaveVarsFlags.flags[] above, so a separate
# dict and a separate read/check path (see location_flags.build_dexsanity_
# flag_to_ap_location_id's own docstring for why these can't share one map).
_DEXSANITY_FLAG_ID_TO_AP_LOCATION_ID = build_dexsanity_flag_to_ap_location_id()

# -- Untrustworthy-read guard for check reporting ----------------------------
#
# Real player report, 2026-08-19: the game froze while the player was
# picking up a hidden item in Ilex Forest, the player reloaded the save,
# and the very next client tick sent 52 locations to the multiworld at
# once. Nothing could be taken back: the items were already delivered to
# the other players and the locations already marked checked server-side.
#
# The consequences here are wildly asymmetric, and that asymmetry is the
# whole design rationale of this section. A check sent one tick late costs
# nothing at all (the next read finds the same flag still set and sends it
# about a second later); a check sent wrongly is irreversible and corrupts
# other players' games. So when a read is not clearly trustworthy, this
# client reports nothing and tries again next tick.
#
# Three independent layers, because none of them covers the whole failure
# space on its own:
#
#   1. Structural (`_save_block_signature_valid`): Pokedex.magic must
#      still read POKEDEX_MAGIC. It lives in the same located save block
#      as the flags array (both are dynamic_region_base +
#      arrayHeaders[id].offset, see _locate_save_addresses), so it is a
#      direct 32-bit test of "do the addresses cached from an earlier tick
#      still point at this game's live SaveData?" -- precisely what a save
#      reload can silently invalidate, since arrayHeaders' own 0,1,2,3,4
#      id signature can very well survive at a stale address.
#   2. Read-level absurdity (`_flags_read_looks_sane` /
#      `_pokedex_read_looks_sane`): a buffer of the wrong length, a single
#      repeated byte value, an impossible set-bit density, or a bit set in
#      a range no real save ever uses is not a state any playthrough can
#      produce.
#   3. Batch stability (`_MAX_IMMEDIATE_CHECK_BATCH`): any batch larger
#      than a normal play tick's worth must be read *identically* on two
#      consecutive ticks before it is sent. The legitimate large batches
#      (first connection on an already-advanced save, or reconnecting
#      after a long session played with the client closed) are perfectly
#      stable and simply arrive one tick later; transient garbage read
#      during a freeze or a reload does not reproduce bit-for-bit and
#      never confirms.
#
# Note what is deliberately NOT a rejection reason: volume. A large batch
# is exactly what the two legitimate cases above look like, so rejecting
# on size alone would break them permanently. Size only ever buys a
# one-tick delay here, never a refusal.
#
# Known limits, stated rather than hidden:
#   - a stale address pointing at memory that happens not to change would
#     pass layers 2 and 3; layer 1 is what covers that case, and layer 1
#     is skipped when the manual bag/flags override env vars leave the
#     Pokedex address unlocated (that override path is a troubleshooting
#     escape hatch, and remains as unguarded as it was before).
#   - a bogus read of at most _MAX_IMMEDIATE_CHECK_BATCH locations that
#     also passes layer 1 is still sent immediately. That budget is the
#     price of keeping normal play latency-free, which is a hard
#     requirement: the overwhelmingly common tick reports one single check.
_MAX_IMMEDIATE_CHECK_BATCH = 4

# flags[] is 364 bytes / 2912 bits, of which include/constants/flags.h
# names 2181 (every id outside FLAG_TEMP_*'s own 0x4000 space, which is not
# part of this array at all). A save with every single named flag set would
# still only reach 75% density, so this ceiling can only ever fire on
# saturated garbage -- an 0xFF fill being the classic one -- and never on a
# real endgame save.
_MAX_PLAUSIBLE_FLAG_DENSITY = 0.85

# Pokedex.caughtSpecies/seenSpecies are 16 u32 words each
# (NUM_DEX_FLAG_WORDS = CEILDIV(NATIONAL_DEX_COUNT + 8, 32), include/
# pokedex.h) = 512 bits for NATIONAL_DEX_COUNT = 493 species, which occupy
# bits 0-492 (see location_flags.dexsanity_pokedex_bit_for_species). The
# last byte is NOT padding: it holds the Deoxys form-history nibbles
# (SetDex4Flag writes flags[15]'s top byte, src/pokedex.c) and
# Save_Pokedex_Init fills it with 0xFF from the start. Bits 493-503 are the
# only genuinely unused ones, and no real save ever sets them.
_DEXSANITY_UNUSED_BITS = range(493, 504)


def _flags_read_looks_sane(flags_bytes: bytes) -> bool:
    """False for a SaveVarsFlags.flags[] read no real save can produce.
    Coarse by construction (see the section comment above): it catches
    fills and saturation, not plausible-looking garbage -- that is what
    the other two layers are for."""
    if len(flags_bytes) != FLAGS_ARRAY_SIZE:
        return False
    if len(set(flags_bytes)) == 1 and flags_bytes[0] != 0:
        # A single repeated non-zero byte is a fill pattern, not a save.
        # An all-zero read is left alone on purpose: it is what a brand
        # new save legitimately looks like, and it reports nothing anyway.
        return False
    set_bits = sum(byte.bit_count() for byte in flags_bytes)
    return set_bits <= _MAX_PLAUSIBLE_FLAG_DENSITY * len(flags_bytes) * 8


def _pokedex_read_looks_sane(pokedex_bytes: bytes) -> bool:
    """False for a Pokedex.caughtSpecies/seenSpecies read no real save can
    produce -- see _DEXSANITY_UNUSED_BITS for the exact invariant."""
    if len(pokedex_bytes) != _POKEDEX_CAUGHT_SPECIES_SIZE:
        return False
    return not any(is_flag_set(pokedex_bytes, bit) for bit in _DEXSANITY_UNUSED_BITS)


def _decrypt_gamestats_halfword(raw_value: int, checksum: int, key_high: int, byte_offset: int) -> int:
    """Plaintext value of the u16 GameStats field at `byte_offset` (from
    the start of the GameStats chunk), given the ciphertext halfword read
    there plus GameStats.unk_1BC/unk_1BE read at the same time -- see the
    _GAMESTATS_SECURE_REGION_OFFSET block above for the decomp derivation.

    Only the one halfword of interest is decrypted: the keystream is a
    plain LCG run over the secure region in order, so reaching word index
    N costs N+1 iterations and nothing else needs to be read."""
    seed = (checksum + (key_high << 16)) & 0xFFFFFFFF
    word_index = (byte_offset - _GAMESTATS_SECURE_REGION_OFFSET) // 2
    for _ in range(word_index + 1):
        seed = (seed * _GAMESTATS_LCRNG_MULTIPLIER + _GAMESTATS_LCRNG_INCREMENT) & 0xFFFFFFFF
    return raw_value ^ ((seed >> 16) & 0xFFFF)


# AP location ids already covered by ROM substitution -- see NOTES.md for
# the double-delivery bug this prevents. Two variants, picked per-connection
# from ctx.slot_data["remote_items"] (_apply_received_items below) -- see
# build_locally_substituted_ap_location_ids's own docstring for why
# remote_items changes this set.
_LOCALLY_SUBSTITUTED_AP_LOCATION_IDS_NORMAL = build_locally_substituted_ap_location_ids(remote_items=False)
_LOCALLY_SUBSTITUTED_AP_LOCATION_IDS_REMOTE = build_locally_substituted_ap_location_ids(remote_items=True)


logger = logging.getLogger("Client")


def _item_display_name(ctx, item_id: int) -> str:
    try:
        return ctx.item_names.lookup_in_game(item_id)
    except Exception:  # noqa: BLE001 -- only used for log text
        return f"item {item_id}"


def cmd_pending(self) -> None:
    """List the items the server sent that are not in your game yet."""
    ctx = self.ctx
    handler = ctx.client_handler
    if ctx.game != HeartGoldClient.game or not isinstance(handler, HeartGoldClient):
        logger.warning("This command only works while playing Pokemon HGSS Singe.")
        return
    if not ctx.server or not ctx.slot:
        logger.warning("Connect to the server first.")
        return
    pending = handler.pending_item_indices(ctx)
    if not pending:
        logger.info(f"All {len(ctx.items_received)} received items are in your game.")
        return
    names = [_item_display_name(ctx, ctx.items_received[index].item) for index in pending]
    logger.info(f"{len(pending)} received item(s) not in your game yet: " + ", ".join(names))
    logger.info(
        "If this list does not shrink within a few seconds, close any open menu. "
        "A full Bag pocket also holds its items back until you make room."
    )


def cmd_restore_power(self) -> None:
    """Repair the Kanto Power Plant in your save (Magnet Train fallback)."""
    ctx = self.ctx
    if ctx.game != HeartGoldClient.game or not isinstance(ctx.client_handler, HeartGoldClient):
        logger.warning("This command only works while playing Pokemon HGSS Singe.")
        return
    if not ctx.server or not ctx.slot:
        logger.warning("Connect to the server first.")
        return
    ctx.client_handler._power_restore_requested = True
    logger.info(
        "Restoring the Kanto Power Plant: the Magnet Train will run once you hold the Pass. "
        "Save in-game afterwards to keep it."
    )
    if not bool(ctx.slot_data.get("magnet_train", False)):
        # The broken-plant scene is what hands over TM57 (see
        # locations.POWER_PLANT_PRERESTORED_SKIPPED_LOCATION_KEYS).
        logger.warning(
            "magnet_train is off in this seed: the Power Plant manager's TM57 check can no longer "
            "be collected. Ask the host to /send_location it if needed."
        )


# game_watcher ticks (watcher_timeout 1 s) without a server before warning.
_OFFLINE_WARNING_TICKS = 5


class HeartGoldClient(BizHawkClient):
    game = "Pokemon HGSS Singe"
    system = "NDS"
    # Must match output_patch.HeartGoldProcedurePatch.patch_file_ending --
    # this is what makes the Launcher's "Open Patch" dialog recognize a
    # real .appokehgss file.
    patch_suffix = ".appokehgss"

    local_checked_locations: set[int]
    _pending_check_batch: set[int] | None
    bag_base_address: int | None
    flags_array_address: int | None
    pokedex_caught_species_address: int | None
    playerdata_profile_address: int | None
    party_address: int | None
    gamestats_address: int | None
    _array_headers_address: int | None
    _manual_bag_base_override: int | None
    _manual_flags_array_override: int | None
    _applied_item_count: int
    _delivered_ahead: set[int]
    _qol_applied: bool
    _known_tm_quantities: dict[int, int] | None
    _known_player_mon_fainted: int | None
    _previous_death_link: float | None
    _ignore_next_death_link: bool
    _death_link_tag_set: bool
    _starting_money_applied: bool
    _known_trainer_id: int | None
    _pending_trainer_id: int | None
    _start_location_revocation_target: tuple[int, int] | None
    _start_location_revocation_probed: bool
    _goal_pending: bool

    def __init__(self) -> None:
        super().__init__()
        self.local_checked_locations = set()
        self._pending_check_batch = None
        self.bag_base_address = None
        self.flags_array_address = None
        self.pokedex_caught_species_address = None
        self.playerdata_profile_address = None
        self.party_address = None
        self.gamestats_address = None
        self._array_headers_address = None
        self._manual_bag_base_override = None
        self._manual_flags_array_override = None
        self._previous_death_link = None
        self._ignore_next_death_link = False
        self._death_link_tag_set = False
        self._known_trainer_id = None
        self._pending_trainer_id = None
        self._start_location_revocation_target = None
        self._start_location_revocation_probed = False
        self._offline_ticks = 0
        self._reset_save_scoped_progress()

    def _warn_if_offline(self, ctx: BizHawkClientContext) -> None:
        """The slot name comes from the ROM, but the server address cannot
        (it is not known when the ROM is generated): a player who never
        types it plays with no check ever reaching the server. Say so once,
        a few seconds after the emulator link is up without a server."""
        self._offline_ticks += 1
        if self._offline_ticks == _OFFLINE_WARNING_TICKS:
            logger.warning(
                "Connected to the emulator, but not to an Archipelago server: your checks are not being sent. "
                "Enter the server address at the top of this window (or /connect <address>). "
                "The slot name is read from your ROM."
            )

    async def set_auth(self, ctx: BizHawkClientContext) -> None:
        """Log in with the slot auth the patcher stamped into the ROM
        (rom/worldsignature.py), so the player never has to type a slot
        name. Left unset (the framework then asks) if the read fails or the
        field is empty."""
        try:
            raw = (await bizhawk.read(ctx.bizhawk_ctx, [(SLOT_AUTH_ROM_OFFSET, SLOT_AUTH_SIZE, "ROM")]))[0]
        except bizhawk.RequestFailedError:
            return
        if any(raw):
            ctx.auth = base64.b64encode(bytes(raw)).decode("ascii")

    async def validate_rom(self, ctx: BizHawkClientContext) -> bool:
        try:
            id_code, signature = await bizhawk.read(
                ctx.bizhawk_ctx,
                [(0x0C, 4, "ROM"), (WORLD_SIGNATURE_ROM_OFFSET, WORLD_SIGNATURE_SIZE, "ROM")],
            )
        except bizhawk.RequestFailedError:
            return False

        if bytes(id_code) not in (HEARTGOLD_US_ID_CODE, SOULSILVER_US_ID_CODE):
            return False
        if not has_world_signature(bytes(signature)):
            # An unpatched ROM, or one patched by another HGSS world (see
            # rom/worldsignature.py): leave it to whichever handler owns it.
            return False

        if "restore_power" not in ctx.command_processor.commands:
            ctx.command_processor.commands["restore_power"] = cmd_restore_power
        if "pending" not in ctx.command_processor.commands:
            ctx.command_processor.commands["pending"] = cmd_pending

        ctx.game = self.game
        ctx.items_handling = 0b111  # locations + remote items + start inventory
        ctx.want_slot_data = True
        ctx.watcher_timeout = 1.0

        self.local_checked_locations = set()
        self._pending_check_batch = None
        self._manual_bag_base_override = _resolve_address_override(HEARTGOLD_BAG_BASE_ADDRESS_ENV)
        self._manual_flags_array_override = _resolve_address_override(HEARTGOLD_FLAGS_ARRAY_ADDRESS_ENV)
        self.bag_base_address = self._manual_bag_base_override
        self.flags_array_address = self._manual_flags_array_override
        self.pokedex_caught_species_address = None
        self.playerdata_profile_address = None
        self.party_address = None
        self.gamestats_address = None
        self._array_headers_address = None
        self._previous_death_link = None
        self._ignore_next_death_link = False
        self._death_link_tag_set = False
        self._known_trainer_id = None
        self._pending_trainer_id = None
        # Connection-scoped, not save-scoped: the record describes the ROM
        # image currently loaded in the emulator, which is exactly what
        # this method has just (re-)identified.
        self._start_location_revocation_target = None
        self._start_location_revocation_probed = False
        self._offline_ticks = 0
        self._reset_save_scoped_progress()

        return True

    def _reset_save_scoped_progress(self) -> None:
        """Drop every piece of session bookkeeping that describes ONE save
        file, so the next tick rebuilds it from scratch.

        Called from __init__/validate_rom, and -- the reason it exists as
        its own method -- whenever the observed PlayerProfile.id changes
        (see game_watcher). Real bug, 2026-08-22, items lost forever:

          1. The client can reach a plausible-looking Bag/flags/Pokedex
             address before any save file exists at all. Nothing rejects
             that: src/save.c's Save_Init calls Save_InitDynamicRegion
             at boot, so Pokedex.magic already reads POKEDEX_MAGIC,
             _bag_looks_plausible skips empty slots, and
             _flags_read_looks_sane deliberately accepts an all-zero read.
          2. So start_inventory got written into that RAM and
             _applied_item_count rose to N.
          3. "New Game" then calls Save_InitDynamicRegion_Internal, whose
             MI_CpuClearFast(dynamic_region, SAVE_PAGE_MAX *
             SAVE_SECTOR_SIZE) erases bag, flags and Pokedex alike. It does
             NOT erase SaveData.arrayHeaders[], which lives in the static
             part of the struct -- so _array_headers_still_valid kept
             returning True and nothing was ever re-scanned or re-checked.
          4. A real trainer_id appeared, which correctly produced a brand
             new (and therefore 0-valued) Datastorage key... but
             _restore_item_delivery_progress only ever merges upward
             (max/union), and nothing reset the in-memory counter. max(N, 0)
             is N, so every one of those N items stayed "already
             delivered" and none of them was ever written again.

        Everything reset here is save-file scoped in exactly that way:
        _applied_item_count/_delivered_ahead index into a Bag that no
        longer exists, _starting_money_applied guards a PlayerProfile.money
        that was zeroed, _qol_applied guards an Options word that was
        zeroed, and _known_tm_quantities/_known_player_mon_fainted are
        baselines taken against a different save's numbers (re-baselining
        costs one tick and prevents a cross-save comparison).

        Deliberately NOT reset here: _previous_death_link,
        _ignore_next_death_link and _death_link_tag_set, which are scoped
        to the *connection*, not to the save file."""
        self._applied_item_count = 0
        self._delivered_ahead = set()
        self._reported_stuck_items: set[int] = set()
        self._bag_write_failures = 0
        self._power_restore_requested = False
        self._starting_money_applied = False
        self._qol_applied = False
        self._known_tm_quantities = None
        self._known_player_mon_fainted = None
        self._goal_pending = False

    async def _ensure_addresses_located(self, ctx: BizHawkClientContext) -> bool:
        """Make sure bag_base_address/flags_array_address are current,
        relocating via SaveData.arrayHeaders[] if needed. Returns whether
        both addresses are currently usable. pokedex_caught_species_address/
        playerdata_profile_address are best-effort: the manual bag/flags
        override env vars predate Dexsanity/badges and skip the scan
        entirely, so that override combination leaves them None forever
        (_check_locations/_apply_received_items skip the Dexsanity check
        and badge delivery respectively in that case, rather than failing
        the whole tick)."""
        if self._manual_bag_base_override is not None and self._manual_flags_array_override is not None:
            return True

        if self._array_headers_address is not None and await _array_headers_still_valid(
            ctx, self._array_headers_address
        ):
            return True

        located = await _locate_save_addresses(ctx)
        if located is None:
            self.bag_base_address = self._manual_bag_base_override
            self.flags_array_address = self._manual_flags_array_override
            self.pokedex_caught_species_address = None
            self.playerdata_profile_address = None
            self.party_address = None
            self.gamestats_address = None
            self._array_headers_address = None
            return False

        (
            bag_address,
            flags_array_address,
            pokedex_caught_species_address,
            playerdata_profile_address,
            array_headers_address,
            party_address,
            gamestats_address,
        ) = located
        self.bag_base_address = (
            bag_address if self._manual_bag_base_override is None else self._manual_bag_base_override
        )
        self.flags_array_address = (
            flags_array_address if self._manual_flags_array_override is None else self._manual_flags_array_override
        )
        self.pokedex_caught_species_address = pokedex_caught_species_address
        self.playerdata_profile_address = playerdata_profile_address
        self.party_address = party_address
        self.gamestats_address = gamestats_address
        self._array_headers_address = array_headers_address
        return True

    async def _apply_qol_options(self, ctx: BizHawkClientContext) -> None:
        """Set Text Speed/Battle Scene from this player's `fast_text_
        speed`/`skip_battle_animations` options, once per connection. A
        plain read-modify-write of the Options word -- other bits are
        preserved untouched, and the player can still change either
        setting freely afterward from the in-game Options menu."""
        if self._qol_applied or self.playerdata_profile_address is None:
            return

        fast_text_speed = bool(ctx.slot_data.get("fast_text_speed", False))
        skip_battle_animations = bool(ctx.slot_data.get("skip_battle_animations", False))
        if not fast_text_speed and not skip_battle_animations:
            self._qol_applied = True
            return

        playerdata_base_address = self.playerdata_profile_address - _PLAYERDATA_PROFILE_OFFSET
        options_address = playerdata_base_address + _PLAYERDATA_OPTIONS_OFFSET
        current = (await bizhawk.read(ctx.bizhawk_ctx, [(options_address, 2, "ARM9 System Bus")]))[0]
        (value,) = struct.unpack("<H", bytes(current))

        new_value = value
        if fast_text_speed:
            new_value = (new_value & ~TEXT_SPEED_MASK) | TEXT_SPEED_FAST_VALUE
        if skip_battle_animations:
            new_value |= BATTLE_SCENE_BIT

        if new_value != value:
            await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(options_address, struct.pack("<H", new_value), "ARM9 System Bus")],
                [(options_address, bytes(current), "ARM9 System Bus")],
            )
        self._qol_applied = True

    async def _apply_starting_money(self, ctx: BizHawkClientContext, money_applied_key: str) -> None:
        """Set PlayerProfile.money from this player's `starting_money`
        option, exactly once ever for this slot. Guarded by a flag this
        world stores server-side (money_applied_key, set via the same
        "Set"+"max" Datastorage pattern _store_applied_item_count uses) --
        deliberately not a "money still looks vanilla" heuristic, since
        the player's money changes constantly during play and could
        coincidentally pass back through any fixed value later, which
        would make a value-based guard misfire and wipe out money the
        player has since earned or spent."""
        if self._starting_money_applied or self.playerdata_profile_address is None:
            return

        starting_money = ctx.slot_data.get("starting_money")
        if starting_money is None:
            self._starting_money_applied = True
            return

        money_address = self.playerdata_profile_address + _PROFILE_MONEY_OFFSET
        current = (await bizhawk.read(ctx.bizhawk_ctx, [(money_address, 4, "ARM9 System Bus")]))[0]
        new_value = min(int(starting_money), _MAX_MONEY)

        write_succeeded = await bizhawk.guarded_write(
            ctx.bizhawk_ctx,
            [(money_address, struct.pack("<I", new_value), "ARM9 System Bus")],
            [(money_address, bytes(current), "ARM9 System Bus")],
        )
        if not write_succeeded:
            return  # retry next tick

        self._starting_money_applied = True
        ctx.stored_data[money_applied_key] = 1
        await ctx.send_msgs(
            [
                {
                    "cmd": "Set",
                    "key": money_applied_key,
                    "default": 0,
                    "want_reply": False,
                    "operations": [{"operation": "max", "value": 1}],
                }
            ]
        )

    async def _apply_start_location_flags(self, ctx: BizHawkClientContext) -> None:
        """randomize_start_location: once FLAG_GOT_STARTER is observed
        set (the vanilla ChooseStarter scene, itself untouched, sets it
        the moment the player picks a starter -- see rom/startlocation.
        py), fake-grant Pokedex/Pokegear (their own real vanilla trigger
        -- Route 30's Mr. Pokemon, Mom's later revisit conversation --
        sits behind New Bark content this feature skips, unlike Bag/
        Trainer Card/Save/Options, which Mom's own real scene still
        grants normally regardless of this option, see rom/
        startlocation.py's module docstring), and advance the rival's
        own flag chain so he still eventually appears at his next real
        checkpoint instead of never again (see docs/scope.md).

        SET-list (FLAGS_TO_SET) idempotency is driven by the real flag
        state every tick (is the bit already set?), not server-stored
        bookkeeping -- real player report, 2026-08-17: that guard
        persisted across a save restart on the same slot. Safe because
        these bits (0x6B FLAG_GOT_POKEDEX, 0x9C FLAG_GOT_POKEGEAR, 0x190
        FLAG_HIDE_NEW_BARK_RIVAL) are only ever set by this function and
        Mom's own real vanilla scene, never by anything else -- monotonic.

        CLEAR-list (FLAGS_TO_CLEAR) is more nuanced: the only member,
        FLAG_HIDE_CHERRYGROVE_RIVAL (0x19C), is itself SET by vanilla
        game code AFTER the Cherrygrove rival encounter completes
        (decomp-verified: scr_seq_0850_T21.s:607-608) -- NOT monotonic.
        Clearing it unconditionally every tick would re-trigger the NPC
        respawn. Instead, this function only clears it while
        VAR_SCENE_CHERRYGROVE_CITY_OW < 3 (the game's own scene-progress
        counter, before the moment when the vanilla code sets the flag
        itself). Once the VAR reaches 3+, the game has passed that point
        and set the flag; we stop clearing and let it stay set."""
        if self.flags_array_address is None:
            return

        if not bool(ctx.slot_data.get("randomize_start_location", False)):
            return

        starter_byte_index, starter_bit_index = flag_byte_and_bit(_START_LOCATION_FLAG_GOT_STARTER)
        starter_byte_address = self.flags_array_address + starter_byte_index
        starter_byte = (await bizhawk.read(ctx.bizhawk_ctx, [(starter_byte_address, 1, "ARM9 System Bus")]))[0]
        if not (starter_byte[0] & (1 << starter_bit_index)):
            return  # hasn't picked a starter yet on this save -- retry next tick

        touched_bytes: dict[int, int] = {}
        original_bytes: dict[int, int] = {}

        async def _byte_at(byte_index: int) -> int:
            if byte_index not in touched_bytes:
                address = self.flags_array_address + byte_index
                current = (await bizhawk.read(ctx.bizhawk_ctx, [(address, 1, "ARM9 System Bus")]))[0]
                touched_bytes[byte_index] = current[0]
                original_bytes[byte_index] = current[0]
            return touched_bytes[byte_index]

        for flag_id in _START_LOCATION_FLAGS_TO_SET:
            byte_index, bit_index = flag_byte_and_bit(flag_id)
            touched_bytes[byte_index] = (await _byte_at(byte_index)) | (1 << bit_index)

        # Only clear FLAG_HIDE_CHERRYGROVE_RIVAL while the game hasn't yet
        # reached the point where it sets the flag itself. Read
        # VAR_SCENE_CHERRYGROVE_CITY_OW (0x4073) to check game progress.
        vars_array_address = self.flags_array_address - 736  # VARS_ARRAY_SIZE
        var_scene_cherrygrove_index = 0x73  # VAR_SCENE_CHERRYGROVE_CITY_OW - VAR_BASE (0x4000)
        var_address = vars_array_address + var_scene_cherrygrove_index * 2
        var_bytes = (await bizhawk.read(ctx.bizhawk_ctx, [(var_address, 2, "ARM9 System Bus")]))[0]
        (var_scene_cherrygrove,) = struct.unpack("<H", bytes(var_bytes))

        if var_scene_cherrygrove < 3:
            # Cherrygrove rival scene hasn't progressed to the point where
            # the game sets FLAG_HIDE_CHERRYGROVE_RIVAL; OK to clear it.
            for flag_id in _START_LOCATION_FLAGS_TO_CLEAR:
                byte_index, bit_index = flag_byte_and_bit(flag_id)
                touched_bytes[byte_index] = (await _byte_at(byte_index)) & ~(1 << bit_index)

        # Nothing left to do this tick if every flag already matches its
        # desired value -- the common case, every tick, once a save has
        # genuinely been fully applied.
        if all(touched_bytes[byte_index] == original_bytes[byte_index] for byte_index in touched_bytes):
            return

        # Guard against the exact same snapshot the new values were
        # computed from (original_bytes), not a fresh re-read -- a flag
        # the game sets in the gap between the two would otherwise pass a
        # fresh guard while still getting clobbered by a new_value
        # computed from stale data (real bug, found by code review,
        # 2026-08-17; byte 13 holds both FLAG_GOT_STARTER and
        # FLAG_GOT_POKEDEX, so this window is not purely theoretical).
        writes = [
            (self.flags_array_address + byte_index, bytes([new_value]), "ARM9 System Bus")
            for byte_index, new_value in touched_bytes.items()
            if new_value != original_bytes[byte_index]
        ]
        guards = [
            (self.flags_array_address + byte_index, bytes([original_bytes[byte_index]]), "ARM9 System Bus")
            for byte_index in touched_bytes
            if touched_bytes[byte_index] != original_bytes[byte_index]
        ]

        await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, guards)
        # No local/server "applied" bookkeeping needed -- next tick's own
        # fresh read-and-compare is the only source of truth, and a
        # failed guarded_write is retried automatically that way too.

    async def _read_start_location_revocation_target(
        self, ctx: BizHawkClientContext
    ) -> tuple[int, int] | None:
        """`(rom_offset, vanilla_value)` this ROM's own cartridge-header
        record describes, or None if it carries no record (an older build,
        or a ROM patched with randomize_start_location off). Read once per
        connection and remembered: a ROM image cannot change under a live
        connection without validate_rom running again.

        The "already probed" flag is only raised on a *successful* read, so
        a transient failure (mid-reconnect, the same condition every other
        bizhawk call in this client tolerates) costs one tick rather than
        silently disabling this feature for the whole session. A core with
        no usable "ROM" domain at all just re-fails one cheap read per
        tick, and only while this option is on."""
        if self._start_location_revocation_probed:
            return self._start_location_revocation_target

        try:
            record = (
                await bizhawk.read(
                    ctx.bizhawk_ctx, [(REVOCATION_RECORD_ROM_OFFSET, REVOCATION_RECORD_SIZE, "ROM")]
                )
            )[0]
        except bizhawk.RequestFailedError:
            return None

        self._start_location_revocation_probed = True
        self._start_location_revocation_target = parse_revocation_record(bytes(record))
        return self._start_location_revocation_target

    async def _current_map_id(self, ctx: BizHawkClientContext) -> int | None:
        """This save's live `LocalFieldData.currentPosition.mapId` (see
        _LOCAL_FIELD_DATA_CHUNK_ID), or None when it cannot be derived --
        the manual bag/flags override env vars skip the arrayHeaders scan
        entirely, and every other consumer of a scan-derived address in
        this client treats that case as "skip this feature", not as an
        error."""
        if self._array_headers_address is None:
            return None
        dynamic_region_base = self._array_headers_address - _SAVE_COUNTER_SIZE - _DYNAMIC_REGION_SIZE
        chunk_offset = await _chunk_offset(ctx, self._array_headers_address, _LOCAL_FIELD_DATA_CHUNK_ID)
        address = dynamic_region_base + chunk_offset + _LOCAL_FIELD_DATA_CURRENT_MAP_ID_OFFSET
        raw = (await bizhawk.read(ctx.bizhawk_ctx, [(address, 4, "ARM9 System Bus")]))[0]
        (map_id,) = struct.unpack("<i", bytes(raw))
        return map_id

    async def _revoke_start_location_redirect(self, ctx: BizHawkClientContext) -> None:
        """randomize_start_location: write the vanilla exit target back
        over Elm's Lab's redirected exit-warp word in BizHawk's "ROM"
        domain, once the player has demonstrably used the redirect. See
        the _START_LOCATION_MAP_NEW_BARK block above for the full
        rationale, including why FLAG_GOT_STARTER on its own is the wrong
        trigger (it fires while the player is still inside the Lab, before
        the redirected door has been used at all).

        Idempotent and cheap in the steady state: the already-vanilla
        check below is the very first read, and once the write has landed
        every later tick stops right there. Deliberately re-checked every
        tick instead of latched, because the write is not persistent --
        it lands on the emulator's in-memory ROM copy, never on the .nds,
        so reloading the ROM in BizHawk brings the redirect back and the
        client has to notice and re-apply it.

        Every ROM-domain access is wrapped: the domain is confirmed
        writable under BizHawk's melonDS core (2026-08-24, patches/
        diag_rom_domain_writable.lua) but that is one configuration, not a
        guarantee, and a read-only domain must cost this feature only,
        never the tick that carries check reporting and item delivery."""
        if not bool(ctx.slot_data.get("randomize_start_location", False)):
            return
        if self.flags_array_address is None:
            return

        target = await self._read_start_location_revocation_target(ctx)
        if target is None:
            return
        rom_offset, vanilla_value = target

        try:
            current = (await bizhawk.read(ctx.bizhawk_ctx, [(rom_offset, 4, "ROM")]))[0]
        except bizhawk.RequestFailedError:
            return
        if struct.unpack("<I", bytes(current))[0] == vanilla_value:
            return  # already vanilla -- revoked earlier, or never redirected

        starter_byte_index, starter_bit_index = flag_byte_and_bit(_START_LOCATION_FLAG_GOT_STARTER)
        starter_byte = (
            await bizhawk.read(
                ctx.bizhawk_ctx, [(self.flags_array_address + starter_byte_index, 1, "ARM9 System Bus")]
            )
        )[0]
        if not (starter_byte[0] & (1 << starter_bit_index)):
            return  # hasn't picked a starter yet on this save

        map_id = await self._current_map_id(ctx)
        if map_id is None or map_id in _START_LOCATION_HOME_MAP_IDS:
            return  # still in New Bark / Elm's Lab: the redirect is still needed

        try:
            await bizhawk.write(ctx.bizhawk_ctx, [(rom_offset, struct.pack("<I", vanilla_value), "ROM")])
        except bizhawk.RequestFailedError:
            pass  # read-only ROM domain on this setup -- retried next tick

    async def _apply_start_location_blackout_spawn(self, ctx: BizHawkClientContext) -> None:
        """randomize_start_location: point `LocalFieldData.lastSpawn` at the
        starting town's Pokemon Center, once per save, so a whiteout before
        the first Center visit does not send the player back to New Bark.
        See _LOCAL_FIELD_DATA_LAST_SPAWN_OFFSET for the decomp side.

        Same trigger as _revoke_start_location_redirect (FLAG_GOT_STARTER
        set and the player standing on a third map, i.e. through the
        redirected door already). Then, unless _BLACKOUT_SPAWN_LATCH_FLAG
        is already set: if lastSpawn still reads New Bark's id, write the
        town's id and the latch together; otherwise the game has already
        moved it (a Center was entered), so only the latch is written and
        the value is never touched again. One guarded write each time, so
        a value the game changes in between is never clobbered; any failure
        is simply retried next tick."""
        if not bool(ctx.slot_data.get("randomize_start_location", False)):
            return
        spawn_id = _START_LOCATION_TOWN_SPAWN_IDS.get(ctx.slot_data.get("starting_town"))
        if spawn_id is None or self.flags_array_address is None or self._array_headers_address is None:
            return

        starter_byte_index, starter_bit_index = flag_byte_and_bit(_START_LOCATION_FLAG_GOT_STARTER)
        latch_byte_index, latch_bit_index = flag_byte_and_bit(_BLACKOUT_SPAWN_LATCH_FLAG)
        latch_address = self.flags_array_address + latch_byte_index
        starter_byte, latch_byte = (
            await bizhawk.read(
                ctx.bizhawk_ctx,
                [
                    (self.flags_array_address + starter_byte_index, 1, "ARM9 System Bus"),
                    (latch_address, 1, "ARM9 System Bus"),
                ],
            )
        )
        if latch_byte[0] & (1 << latch_bit_index):
            return  # already handled on this save
        if not (starter_byte[0] & (1 << starter_bit_index)):
            return  # hasn't picked a starter yet on this save

        map_id = await self._current_map_id(ctx)
        if map_id is None or map_id in _START_LOCATION_HOME_MAP_IDS:
            return  # not through the redirected door yet

        dynamic_region_base = self._array_headers_address - _SAVE_COUNTER_SIZE - _DYNAMIC_REGION_SIZE
        chunk_offset = await _chunk_offset(ctx, self._array_headers_address, _LOCAL_FIELD_DATA_CHUNK_ID)
        spawn_address = dynamic_region_base + chunk_offset + _LOCAL_FIELD_DATA_LAST_SPAWN_OFFSET
        current_spawn = (await bizhawk.read(ctx.bizhawk_ctx, [(spawn_address, 2, "ARM9 System Bus")]))[0]

        latched = latch_byte[0] | (1 << latch_bit_index)
        writes = [(latch_address, bytes([latched]), "ARM9 System Bus")]
        guards = [
            (latch_address, bytes(latch_byte), "ARM9 System Bus"),
            (spawn_address, bytes(current_spawn), "ARM9 System Bus"),
        ]
        if struct.unpack("<H", bytes(current_spawn))[0] == _SPAWN_ID_NEW_BARK:
            writes.append((spawn_address, struct.pack("<H", spawn_id), "ARM9 System Bus"))
        await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, guards)

    async def _apply_power_plant_prerestored(self, ctx: BizHawkClientContext) -> None:
        """magnet_train on: make the game believe the Kanto Power Plant is
        already repaired, so the Magnet Train runs as soon as the player
        holds the Pass. See _FLAG_RESTORED_POWER's block for what is written
        and why each piece is needed.

        Waits for FLAG_GOT_STARTER: the save must exist (game_watcher
        already refuses trainer_id 0) and _std_init (scr_seq_0149.s, run
        once by CallFieldTask_NewGame, src/field_warp_tasks.c:417) must
        have run, or its own `SetFlag FLAG_HIDE_*` lines would undo part of
        this write. State-driven, no bookkeeping: FLAG_RESTORED_POWER is
        both the goal and the sentinel (nothing in the game ever clears it),
        so once it reads set, whether from this write or from a real
        repair, the method stops at its first read. The two chain vars are
        each checked for 0 so a save that already progressed is left
        alone. One guarded write, retried next tick on any mismatch.

        Also runs with magnet_train off once the player has typed
        /restore_power (cmd_restore_power): a manual way out for a save
        where the real repair cannot be reached. The request is save-scoped
        (_reset_save_scoped_progress drops it) and needs no bookkeeping of
        its own either, since FLAG_RESTORED_POWER ends it the same way."""
        if not (bool(ctx.slot_data.get("magnet_train", False)) or self._power_restore_requested):
            return
        if self.flags_array_address is None:
            return

        flags_address = self.flags_array_address
        starter_byte_index, starter_bit_index = flag_byte_and_bit(_START_LOCATION_FLAG_GOT_STARTER)
        power_byte_index, power_bit_index = flag_byte_and_bit(_FLAG_RESTORED_POWER)
        starter_byte, power_byte = await bizhawk.read(
            ctx.bizhawk_ctx,
            [
                (flags_address + starter_byte_index, 1, "ARM9 System Bus"),
                (flags_address + power_byte_index, 1, "ARM9 System Bus"),
            ],
        )
        if power_byte[0] & (1 << power_bit_index):
            return  # already restored, by this client or by the real scene
        if not (starter_byte[0] & (1 << starter_bit_index)):
            return  # no game in progress yet

        vars_address = flags_address - FLAGS_ARRAY_OFFSET
        copycat_address = vars_address + (_COPYCAT_CHAIN_VAR - _VAR_BASE) * 2
        cerulean_address = vars_address + (_CERULEAN_CHAIN_VAR - _VAR_BASE) * 2
        flags, copycat_raw, cerulean_raw = await bizhawk.read(
            ctx.bizhawk_ctx,
            [
                (flags_address, FLAGS_ARRAY_SIZE, "ARM9 System Bus"),
                (copycat_address, 2, "ARM9 System Bus"),
                (cerulean_address, 2, "ARM9 System Bus"),
            ],
        )
        flags = bytes(flags)

        to_set = list(_POWER_PLANT_FLAGS_TO_SET)
        to_clear = list(_POWER_PLANT_FLAGS_TO_CLEAR)
        writes: list[tuple[int, bytes, str]] = []
        guards: list[tuple[int, bytes, str]] = []
        if struct.unpack("<H", bytes(copycat_raw))[0] == 0:
            to_set += _COPYCAT_CHAIN_FLAGS_TO_SET
            to_clear += _COPYCAT_CHAIN_FLAGS_TO_CLEAR
            writes.append((copycat_address, struct.pack("<H", 1), "ARM9 System Bus"))
            guards.append((copycat_address, bytes(copycat_raw), "ARM9 System Bus"))
        if struct.unpack("<H", bytes(cerulean_raw))[0] == 0:
            to_clear += _CERULEAN_CHAIN_FLAGS_TO_CLEAR
            writes.append(
                (cerulean_address, struct.pack("<H", _CERULEAN_CHAIN_VAR_VALUE), "ARM9 System Bus")
            )
            guards.append((cerulean_address, bytes(cerulean_raw), "ARM9 System Bus"))

        new_flags = bytearray(flags)
        for flag_id in to_set:
            byte_index, bit_index = flag_byte_and_bit(flag_id)
            new_flags[byte_index] |= 1 << bit_index
        for flag_id in to_clear:
            byte_index, bit_index = flag_byte_and_bit(flag_id)
            new_flags[byte_index] &= ~(1 << bit_index) & 0xFF
        for byte_index, (old, new) in enumerate(zip(flags, new_flags)):
            if old != new:
                writes.append((flags_address + byte_index, bytes([new]), "ARM9 System Bus"))
                guards.append((flags_address + byte_index, bytes([old]), "ARM9 System Bus"))

        await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, guards)

    async def _apply_wing_passes(self, ctx: BizHawkClientContext) -> None:
        """The monks test RAINBOW_WING_PASS_FLAG / SILVER_WING_PASS_FLAG
        (rom/wingmonkdata.py): set each one once its wing item has been
        received. The Pewter-side wing (Silver in HeartGold, Rainbow in
        SoulSilver) also makes the other version's legendary appear in
        vanilla (scr_seq_0750_T03.s:66/:72, `ClearFlag FLAG_HIDE_...`), so
        that hide flag is cleared in the same write, unless it was caught.
        State-driven: the pass flag is the latch, so each wing is handled
        once per save. Waits for FLAG_GOT_STARTER, like
        _apply_power_plant_prerestored, so the new-game init script cannot
        set the hide flag back afterwards."""
        if self.flags_array_address is None:
            return
        received = {item.item for item in ctx.items_received}
        wanted = [
            (key, flag) for key, flag in _WING_PASS_FLAGS.items()
            if HEARTGOLD_ITEM_ID_BASE + ITEMS[key]["id"] in received
        ]
        if not wanted:
            return
        flags_address = self.flags_array_address
        flags = bytes((await bizhawk.read(ctx.bizhawk_ctx, [(flags_address, FLAGS_ARRAY_SIZE, "ARM9 System Bus")]))[0])

        def is_set(flag_id: int) -> bool:
            byte_index, bit_index = flag_byte_and_bit(flag_id)
            return bool(flags[byte_index] & (1 << bit_index))

        if not is_set(_START_LOCATION_FLAG_GOT_STARTER):
            return
        soulsilver = (ctx.slot_data.get("options") or {}).get("game_version") == 1
        pewter_wing, hide_flag, caught_flag = _PEWTER_WING_LEGENDARY["soulsilver" if soulsilver else "heartgold"]
        new_flags = bytearray(flags)
        for key, pass_flag in wanted:
            if is_set(pass_flag):
                continue
            byte_index, bit_index = flag_byte_and_bit(pass_flag)
            new_flags[byte_index] |= 1 << bit_index
            if key == pewter_wing and not is_set(caught_flag):
                byte_index, bit_index = flag_byte_and_bit(hide_flag)
                new_flags[byte_index] &= ~(1 << bit_index) & 0xFF
        writes, guards = [], []
        for byte_index, (old, new) in enumerate(zip(flags, new_flags)):
            if old != new:
                writes.append((flags_address + byte_index, bytes([new]), "ARM9 System Bus"))
                guards.append((flags_address + byte_index, bytes([old]), "ARM9 System Bus"))
        if writes:
            await bizhawk.guarded_write(ctx.bizhawk_ctx, writes, guards)

    async def _restore_reusable_tms(self, ctx: BizHawkClientContext) -> None:
        """Reusable TMs: no ROM patch (see NOTES.md for why the ARM hook
        approach was abandoned). Every tick, compare each TM/HM pocket
        item's total quantity (summed across slots) against the last
        tick's count and write back any decrease via the same
        plan_bag_item_write/guarded_write path _apply_received_items uses
        -- a consumed TM/HM simply reappears next poll. The first tick
        after (re)connecting only records a baseline."""
        if not bool(ctx.slot_data.get("reusable_tms", False)) or self.bag_base_address is None:
            return

        pocket_offset, pocket_capacity = BAG_POCKET_OFFSETS["TMsHMs"]
        pocket_address = self.bag_base_address + pocket_offset
        pocket_bytes = bytearray(
            (await bizhawk.read(ctx.bizhawk_ctx, [(pocket_address, pocket_capacity * 4, "ARM9 System Bus")]))[0]
        )

        current_quantities: dict[int, int] = {}
        for offset in range(0, len(pocket_bytes), 4):
            item_id, quantity = struct.unpack_from("<HH", bytes(pocket_bytes), offset)
            if item_id != 0:
                current_quantities[item_id] = current_quantities.get(item_id, 0) + quantity

        if self._known_tm_quantities is not None:
            stack_cap = stack_cap_for_pocket("TMsHMs")
            for item_id, known_quantity in self._known_tm_quantities.items():
                missing = known_quantity - current_quantities.get(item_id, 0)
                if missing <= 0:
                    continue
                plan = plan_bag_item_write(bytes(pocket_bytes), item_id, missing, stack_cap)
                if plan is None:
                    continue  # pocket full, or stack cap reached -- retry next tick
                slot_offset, slot_bytes = plan
                write_succeeded = await bizhawk.guarded_write(
                    ctx.bizhawk_ctx,
                    [(pocket_address + slot_offset, slot_bytes, "ARM9 System Bus")],
                    [(pocket_address + slot_offset, bytes(pocket_bytes[slot_offset : slot_offset + 4]), "ARM9 System Bus")],
                )
                if write_succeeded:
                    pocket_bytes[slot_offset : slot_offset + 4] = slot_bytes
                    current_quantities[item_id] = current_quantities.get(item_id, 0) + missing

        self._known_tm_quantities = current_quantities

    async def _update_death_link_tag(self, ctx: BizHawkClientContext) -> None:
        """Set/clear the "DeathLink" connection tag once per connection to
        match this player's own `death_link` option -- CommonContext's own
        `update_death_link` helper (also used to send the initial
        ConnectUpdate)."""
        if self._death_link_tag_set:
            return
        await ctx.update_death_link(bool(ctx.slot_data.get("death_link", False)))
        self._death_link_tag_set = True

    async def _send_death_link_on_faint(self, ctx: BizHawkClientContext) -> None:
        """DeathLink send side: poll GAME_STAT_PLAYER_MON_FAINTED and send
        a death the moment it increases. The first tick after
        (re)connecting only records a baseline.

        The counter is stored XOR-encrypted and has to be decrypted before
        it means anything at all -- see the _GAMESTATS_SECURE_REGION_OFFSET
        block for the decomp derivation and for the real "DeathLink fires
        at the start of every other battle" bug that reading it raw caused.
        The checksum/key halfwords are fetched in the same read request as
        the ciphertext so they describe the same moment.

        Two things can only ever *suppress* a send, never cause one:
        a decrypted value above the game's own 9999 cap for this stat (a
        read that cannot come from a real save -- keep the old baseline
        untouched and try again next tick), and an increase too large to be
        a real sequence of faints (re-baseline, but stay quiet). A save
        reload or a New Game makes the counter go backwards, which simply
        re-baselines: _reset_save_scoped_progress also clears the baseline
        outright when the save file itself changes."""
        if not bool(ctx.slot_data.get("death_link", False)) or self.gamestats_address is None:
            return

        stat_address = self.gamestats_address + _GAME_STAT_PLAYER_MON_FAINTED_OFFSET
        crypt_address = self.gamestats_address + _GAMESTATS_CHECKSUM_OFFSET
        raw_stat, raw_crypt = await bizhawk.read(
            ctx.bizhawk_ctx,
            [(stat_address, 2, "ARM9 System Bus"), (crypt_address, 4, "ARM9 System Bus")],
        )
        (ciphertext,) = struct.unpack("<H", bytes(raw_stat))
        checksum, key_high = struct.unpack("<HH", bytes(raw_crypt))
        fainted_count = _decrypt_gamestats_halfword(
            ciphertext, checksum, key_high, _GAME_STAT_PLAYER_MON_FAINTED_OFFSET
        )

        if fainted_count > _MAX_PLAUSIBLE_PLAYER_MON_FAINTED:
            return  # impossible value -- bad read, keep the old baseline

        previous = self._known_player_mon_fainted
        self._known_player_mon_fainted = fainted_count
        if previous is None:
            return  # first tick after (re)connecting: baseline only

        if not 0 < fainted_count - previous <= _MAX_PLAUSIBLE_FAINTS_PER_TICK:
            return

        self._ignore_next_death_link = True
        await ctx.send_death(f"{ctx.player_names[ctx.slot]}'s Pokémon fainted!")

    async def _receive_death_link(self, ctx: BizHawkClientContext) -> None:
        """DeathLink receive side: notice `ctx.last_death_link` changing
        (CommonContext's own DeathLink bookkeeping) and zero every real
        party Pokemon's current HP, matching a vanilla blackout.
        `_ignore_next_death_link` skips the echo of this player's own
        just-sent death (Bounce rebroadcasts to the sender too)."""
        if not bool(ctx.slot_data.get("death_link", False)) or self.party_address is None:
            return

        if self._previous_death_link is None:
            self._previous_death_link = ctx.last_death_link
            return

        if ctx.last_death_link == self._previous_death_link:
            return
        self._previous_death_link = ctx.last_death_link

        if self._ignore_next_death_link:
            self._ignore_next_death_link = False
            return

        cur_count_raw = (
            await bizhawk.read(ctx.bizhawk_ctx, [(self.party_address + _PARTY_CUR_COUNT_OFFSET, 4, "ARM9 System Bus")])
        )[0]
        (cur_count,) = struct.unpack("<i", bytes(cur_count_raw))
        cur_count = max(0, min(cur_count, _PARTY_MAX_SIZE))

        mons_address = self.party_address + _PARTY_MONS_OFFSET
        writes = [
            (
                mons_address + i * _PARTY_POKEMON_STRUCT_SIZE + _PARTY_POKEMON_HP_OFFSET,
                struct.pack("<H", 0),
                "ARM9 System Bus",
            )
            for i in range(cur_count)
        ]
        if writes:
            await bizhawk.write(ctx.bizhawk_ctx, writes)

    async def game_watcher(self, ctx: BizHawkClientContext) -> None:
        if ctx.server is None or ctx.server.socket.closed:
            self._warn_if_offline(ctx)
            return
        self._offline_ticks = 0
        if ctx.slot_data is None:
            return

        try:
            # _ensure_addresses_located belongs INSIDE this try (moved
            # 2026-08-22): only its cheap re-validation step catches
            # RequestFailedError of its own, while the full
            # _locate_save_addresses scan under it does not, and
            # worlds._bizhawk.context's own _game_watcher has no catch
            # around game_watcher(ctx) at all. A transient disconnect
            # during the scan therefore used to kill the GameWatcher task
            # permanently and silently -- the exact same class of bug that
            # moving the trainer_id read in here fixed on 2026-08-18.
            if not await self._ensure_addresses_located(ctx):
                return  # retried automatically next tick

            # Read trainer ID to make the applied_item_count key
            # save-unique (so a new save file gets a naturally new key the
            # server doesn't know about, instead of reusing stale counts
            # from earlier attempts on the same slot). PlayerProfile.id is
            # at offset 16 (player name is 8 u16s = 16 bytes at offset 0).
            # Inside this try block (not before it, see the real bug this
            # fixed 2026-08-18): worlds._bizhawk.context's own
            # _game_watcher has no catch around this call at all, so an
            # unprotected bizhawk.read here that raises RequestFailedError
            # (e.g. mid-reconnect, the exact same transient condition every
            # other bizhawk call in this method already tolerates via the
            # except below) permanently kills the GameWatcher task for the
            # rest of the session -- silently, with no further retries ever
            # happening again.
            trainer_id_bytes = (
                await bizhawk.read(ctx.bizhawk_ctx, [(self.playerdata_profile_address + 16, 4, "ARM9 System Bus")])
            )[0]
            (trainer_id,) = struct.unpack("<I", bytes(trainer_id_bytes))

            if not self._accept_trainer_id(trainer_id):
                return  # nothing this tick, see that method's docstring

            if trainer_id == 0:
                # No save file exists yet. src/save.c's Save_Init calls
                # Save_InitDynamicRegion at boot regardless of whether
                # there is a save file, so every located address already
                # looks valid here -- but "New Game" will MI_CpuClearFast
                # the whole dynamic region out from under it
                # (Save_InitDynamicRegion_Internal), taking any item this
                # client wrote with it. PlayerProfile.id is a full 32-bit
                # MTRandom() draw made while the new file is being created
                # (src/overlay_36.c: `u32 rand = MTRandom(); if
                # (set_trainer_id) PlayerProfile_SetTrainerID(profile,
                # rand);`), long before the player can hold anything, so
                # gating on it costs no real delivery latency and makes
                # writing into a condemned save impossible. It can in
                # principle draw exactly 0 and strand that one save, at
                # odds of 1 in 2**32 -- accepted, and far better than the
                # certainty of losing items on every single new game.
                # Nothing is *reported* from here either, for the same
                # reason: an all-zero flags read reports nothing anyway,
                # but a stale one might.
                return

            applied_key = _APPLIED_ITEM_COUNT_KEY_TEMPLATE.format(team=ctx.team, slot=ctx.slot, trainer_id=trainer_id)
            delivered_ahead_key = _DELIVERED_AHEAD_KEY_TEMPLATE.format(
                team=ctx.team, slot=ctx.slot, trainer_id=trainer_id
            )
            money_applied_key = _STARTING_MONEY_APPLIED_KEY_TEMPLATE.format(
                team=ctx.team, slot=ctx.slot, trainer_id=trainer_id
            )
            ctx.set_notify(money_applied_key)
            self._starting_money_applied = self._starting_money_applied or bool(
                int(ctx.stored_data.get(money_applied_key, 0) or 0)
            )
            self._restore_item_delivery_progress(ctx, applied_key, delivered_ahead_key)

            await self._apply_qol_options(ctx)
            await self._apply_starting_money(ctx, money_applied_key)
            await self._apply_start_location_flags(ctx)
            await self._revoke_start_location_redirect(ctx)
            await self._apply_start_location_blackout_spawn(ctx)
            await self._apply_power_plant_prerestored(ctx)
            await self._apply_wing_passes(ctx)
            await self._restore_reusable_tms(ctx)
            await self._update_death_link_tag(ctx)
            await self._send_death_link_on_faint(ctx)
            await self._receive_death_link(ctx)
            await self._check_locations(ctx)
            await self._apply_received_items(ctx, applied_key, delivered_ahead_key)
            await self._apply_pending_badges(ctx)
        except bizhawk.RequestFailedError:
            pass  # exit handler, return to main loop to reconnect

    def _accept_trainer_id(self, trainer_id: int) -> bool:
        """Track which save file the located addresses currently describe,
        and answer "is it safe to act on this tick's reads?".

        A changed PlayerProfile.id means a different save file: a new game,
        a different file loaded from the title screen, or the boot-time
        all-zero dynamic region before either. Everything scoped to the old
        one is dropped (_reset_save_scoped_progress, which carries the full
        write-up of the item-loss bug this exists for).

        The change itself must be seen on two consecutive ticks before
        anything acts on it, mirroring _MAX_IMMEDIATE_CHECK_BATCH's own
        confirmation rule and for the same asymmetry: a one-tick delay
        costs nothing, whereas resetting the delivery counter on a single
        garbage read would make the very next tick re-write every already-
        delivered item into the Bag a second time. Transient garbage does
        not reproduce bit-for-bit; a real save switch does."""
        if trainer_id == self._known_trainer_id:
            self._pending_trainer_id = trainer_id
            return True

        if trainer_id != self._pending_trainer_id:
            self._pending_trainer_id = trainer_id
            return False  # first sighting -- wait for one confirming read

        self._known_trainer_id = trainer_id
        self._reset_save_scoped_progress()
        return True

    async def _save_block_signature_valid(self, ctx: BizHawkClientContext) -> bool:
        """Layer 1 of the check-report guard (see its section comment):
        Pokedex.magic still reads POKEDEX_MAGIC at the located address, so
        the addresses cached from an earlier tick still describe this
        game's live SaveData. On mismatch, the cached arrayHeaders address
        is dropped as well, so the next tick re-runs the full scan instead
        of trusting the same stale one all over again.

        Returns True when there is nothing to verify: the manual bag/flags
        override env vars skip the scan entirely and leave the Pokedex
        address unlocated (see _ensure_addresses_located), and that
        troubleshooting path stays exactly as unguarded as it was."""
        if self.pokedex_caught_species_address is None:
            return True

        magic_address = (
            self.pokedex_caught_species_address - _POKEDEX_CAUGHT_SPECIES_OFFSET + _POKEDEX_MAGIC_OFFSET
        )
        raw = (await bizhawk.read(ctx.bizhawk_ctx, [(magic_address, 4, "ARM9 System Bus")]))[0]
        (magic,) = struct.unpack("<I", bytes(raw))
        if magic == _POKEDEX_MAGIC:
            return True

        self._array_headers_address = None
        return False

    async def _check_locations(self, ctx: BizHawkClientContext) -> None:
        """Report every location whose savedata flag now reads as set,
        through the three-layer untrustworthy-read guard documented above
        _MAX_IMMEDIATE_CHECK_BATCH. Every rejection path clears
        `_pending_check_batch` on the way out, so a batch is only ever sent
        after two *consecutive* fully-trusted reads agreed on it -- a
        rejected read can never serve as one of the two confirmations.

        Goal detection (_report_goal) rides on the same trusted read, with
        the same rule: `_goal_pending` is consumed here and only re-armed
        by a trusted read, so every rejection path also drops it."""
        goal_seen_last_tick = self._goal_pending
        self._goal_pending = False
        if not await self._save_block_signature_valid(ctx):
            self._pending_check_batch = None
            return

        flags_address = self.flags_array_address
        flags_bytes = bytes(
            (await bizhawk.read(ctx.bizhawk_ctx, [(flags_address, FLAGS_ARRAY_SIZE, "ARM9 System Bus")]))[0]
        )
        if not _flags_read_looks_sane(flags_bytes):
            self._pending_check_batch = None
            return

        newly_checked = {
            ap_location_id
            for flag_id, ap_location_id in _FLAG_ID_TO_AP_LOCATION_ID.items()
            if ap_location_id in ctx.missing_locations and is_flag_set(bytes(flags_bytes), flag_id)
        }

        # Dexsanity (task M3.4): Pokedex.caughtSpecies is its own savedata
        # array, not SaveVarsFlags.flags[] -- a separate read, separate map,
        # unioned into the same newly_checked set so one ctx.check_locations
        # call covers both. Best-effort: pokedex_caught_species_address can
        # be None under the manual bag/flags override env vars (see
        # _ensure_addresses_located), in which case Dexsanity checks are
        # simply skipped this tick rather than failing the whole thing.
        #
        # dexsanity_trigger ("catch"/"encounter"): Pokedex.seenSpecies is
        # the exact same shape as caughtSpecies (same size, same bit
        # formula) and sits immediately after it in the struct
        # (include/pokedex.h), so this is just a fixed +64 byte offset --
        # no separate address needs to be located.
        if self.pokedex_caught_species_address is not None:
            pokedex_address = self.pokedex_caught_species_address
            if ctx.slot_data.get("dexsanity_trigger") == "encounter":
                pokedex_address += _POKEDEX_CAUGHT_SPECIES_SIZE
            pokedex_bytes = bytes(
                (
                    await bizhawk.read(
                        ctx.bizhawk_ctx,
                        [(pokedex_address, _POKEDEX_CAUGHT_SPECIES_SIZE, "ARM9 System Bus")],
                    )
                )[0]
            )
            # An impossible Pokedex read discredits the whole tick, not
            # just its own contribution: both arrays come out of the same
            # located save block, so if one of them is garbage there is no
            # reason to trust the other one either.
            if not _pokedex_read_looks_sane(pokedex_bytes):
                self._pending_check_batch = None
                return
            newly_checked |= {
                ap_location_id
                for bit, ap_location_id in _DEXSANITY_FLAG_ID_TO_AP_LOCATION_ID.items()
                if ap_location_id in ctx.missing_locations and is_flag_set(bytes(pokedex_bytes), bit)
            }

        await self._report_goal(ctx, flags_bytes, goal_seen_last_tick)

        if not newly_checked:
            self._pending_check_batch = None
            return

        # Layer 3: a batch bigger than a normal tick's worth waits for one
        # identical confirming read. Nothing is lost by waiting -- the
        # flags stay set, so a legitimate batch is simply sent one tick
        # later, and a batch that keeps growing (the player carries on
        # playing) is re-confirmed against its own latest shape each tick.
        if len(newly_checked) > _MAX_IMMEDIATE_CHECK_BATCH and newly_checked != self._pending_check_batch:
            self._pending_check_batch = newly_checked
            return

        self._pending_check_batch = newly_checked
        if newly_checked != self.local_checked_locations:
            self.local_checked_locations = newly_checked
            await ctx.check_locations(newly_checked)

    async def _report_goal(self, ctx: BizHawkClientContext, flags_bytes: bytes, goal_seen_last_tick: bool) -> None:
        """Send CLIENT_GOAL once this slot's goal (slot_data "goal") is met.
        See _GOAL_ELITE_FOUR's block for what each goal reads and why.

        A false goal is irreversible (under "release on goal" it hands out
        every remaining item at once), so this is only ever called by
        _check_locations with a flags read that already passed layers 1
        and 2, which itself only runs once game_watcher has accepted a real
        save (_accept_trainer_id, trainer_id != 0). The memory-based goals
        additionally need two consecutive trusted reads (layer 3's rule):
        the first one only arms `_goal_pending`. n_badges reads no memory,
        so it needs no confirmation."""
        if ctx.finished_game:
            return

        goal = int(ctx.slot_data.get("goal", _GOAL_ELITE_FOUR))
        if goal == _GOAL_N_BADGES:
            required = int(ctx.slot_data.get("goal_badge_count", 16))
            if ctx.slot_data.get(SLOT_DATA_OPTIONS_KEY, {}).get("johto_only"):
                required = min(required, _JOHTO_BADGE_COUNT)  # same cap as __init__.py's set_rules
            received = {item.item for item in ctx.items_received if item.item in _AP_ITEM_ID_TO_BADGE_INDEX}
            reached = len(received) >= required
        elif goal == _GOAL_CHAMPION_RED:
            reached = False
            if is_flag_set(flags_bytes, _FLAG_RED_DEFEATED):
                vars_address = self.flags_array_address - FLAGS_ARRAY_OFFSET
                var_address = vars_address + (_VAR_RED_DEFEATED - _VAR_BASE) * 2
                raw = (await bizhawk.read(ctx.bizhawk_ctx, [(var_address, 2, "ARM9 System Bus")]))[0]
                reached = struct.unpack("<H", bytes(raw))[0] == 1
            if reached and not goal_seen_last_tick:
                self._goal_pending = True
                return
        elif goal == _GOAL_ELITE_FOUR:
            reached = is_flag_set(flags_bytes, _FLAG_GAME_CLEAR)
            if reached and not goal_seen_last_tick:
                self._goal_pending = True
                return
        else:
            return  # unknown goal value from a newer apworld: never guess

        if not reached:
            return
        ctx.finished_game = True
        await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])

    def _restore_item_delivery_progress(
        self, ctx: BizHawkClientContext, applied_key: str, delivered_ahead_key: str
    ) -> None:
        """Merge the server-side resume point (both halves of it, see
        _DELIVERED_AHEAD_KEY_TEMPLATE) into this session's own bookkeeping,
        every tick -- ctx.set_notify's answer only arrives asynchronously,
        so the first tick after connecting may still see neither key. Only
        ever merges (max / set union), never overwrites: whichever of the
        two sides is ahead wins, so a stale or late Datastorage value can
        never re-deliver an item that was already written."""
        ctx.set_notify(applied_key, delivered_ahead_key)
        self._applied_item_count = max(self._applied_item_count, int(ctx.stored_data.get(applied_key, 0) or 0))
        self._delivered_ahead |= _indices_from_mask(int(ctx.stored_data.get(delivered_ahead_key, 0) or 0))
        self._compact_delivery_progress()

    def pending_item_indices(self, ctx: BizHawkClientContext) -> list[int]:
        """items_received indices not delivered yet, for /pending. Items
        this client never writes (own-world items the ROM already hands
        out, unknown ids) are counted as delivered by _apply_received_items
        on its next tick, so they only show up here briefly."""
        return [
            index
            for index in range(self._applied_item_count, len(ctx.items_received))
            if index not in self._delivered_ahead
        ]

    def _compact_delivery_progress(self) -> None:
        """Fold every _delivered_ahead index that has become contiguous
        with _applied_item_count back into the counter, and drop the ones
        already covered by it. Keeps the mask empty in the normal case
        (nothing blocked -> nothing delivered out of order) and bounded to
        the items still queued behind a full pocket otherwise."""
        self._delivered_ahead = {index for index in self._delivered_ahead if index >= self._applied_item_count}
        while self._applied_item_count in self._delivered_ahead:
            self._delivered_ahead.remove(self._applied_item_count)
            self._applied_item_count += 1

    async def _apply_received_items(
        self, ctx: BizHawkClientContext, applied_key: str, delivered_ahead_key: str
    ) -> None:
        """Apply as many pending items as possible in this single tick (up
        to _MAX_ITEMS_APPLIED_PER_TICK), instead of just one -- otherwise a
        large backlog trickles in at roughly one item per second.

        An item whose Bag pocket is full is *not* a reason to stop: that
        condition is deterministic, not transient (nothing this client does
        will free a slot -- only the player can), so stopping there froze
        every later item's delivery permanently, whatever pocket it was
        bound for (real bug, 2026-08-19). Such an item simply stays pending
        while the scan carries on, and the ones delivered past it are
        remembered in _delivered_ahead so they are neither delivered twice
        nor lost across a client restart (see
        _DELIVERED_AHEAD_KEY_TEMPLATE). A failed guarded_write is the one
        genuinely transient case, and still stops the tick."""
        locally_substituted = (
            _LOCALLY_SUBSTITUTED_AP_LOCATION_IDS_REMOTE
            if bool(ctx.slot_data.get("remote_items", False))
            else _LOCALLY_SUBSTITUTED_AP_LOCATION_IDS_NORMAL
        )

        applied_this_tick = 0
        index = self._applied_item_count
        # Bag fields already found full this tick: rediscovering that with
        # one more read RPC per queued item is not worth it when the next
        # tick is a second away anyway.
        full_bag_fields: set[str] = set()
        while applied_this_tick < _MAX_ITEMS_APPLIED_PER_TICK and index < len(ctx.items_received):
            if index in self._delivered_ahead:
                # Already written into the Bag by an earlier tick that
                # scanned past a blocked item.
                index += 1
                continue

            next_item = ctx.items_received[index]

            # Archipelago's server sends every item belonging to this
            # player through items_received once its location is checked
            # -- including this player's own locations, which this client
            # already delivered via ROM substitution (unless remote_items
            # is on -- see build_locally_substituted_ap_location_ids's own
            # docstring). Writing it into the Bag again would double it --
            # see NOTES.md.
            already_delivered_locally = (
                next_item.player == ctx.slot and next_item.location in locally_substituted
            )

            # Badges never go through the Bag at all -- receiving one sets
            # the matching bit in PlayerProfile.johtoBadges/kantoBadges
            # instead (see rom/badgedata.py for how the vanilla local
            # grant is neutralized so it can't also set this bit). That
            # write is done by _apply_pending_badges, which re-derives the
            # whole set from ctx.items_received every tick so it stays
            # idempotent across save-state reloads (see its own docstring)
            # -- here we only advance the resume counter.
            badge_index = None if already_delivered_locally else _AP_ITEM_ID_TO_BADGE_INDEX.get(next_item.item)
            if badge_index is not None:
                self._delivered_ahead.add(index)
                index += 1
                applied_this_tick += 1
                continue

            write_info = None if already_delivered_locally else _AP_ITEM_ID_TO_BAG_WRITE_INFO.get(next_item.item)
            if write_info is None:
                # Not one of this world's own bag items, or already
                # delivered locally -- count it as "applied" so the queue
                # doesn't stall, no RPC round trip needed, keep looping.
                self._delivered_ahead.add(index)
                index += 1
                applied_this_tick += 1
                continue

            native_item_id, bag_field = write_info
            if bag_field in full_bag_fields:
                # Another item bound for this same pocket already found it
                # full this tick -- leave this one pending too and keep
                # scanning for items bound elsewhere.
                index += 1
                continue

            pocket_offset, pocket_capacity = BAG_POCKET_OFFSETS[bag_field]
            pocket_address = self.bag_base_address + pocket_offset
            pocket_size = pocket_capacity * 4

            pocket_bytes = (
                await bizhawk.read(ctx.bizhawk_ctx, [(pocket_address, pocket_size, "ARM9 System Bus")])
            )[0]

            if not _pocket_looks_plausible(bytes(pocket_bytes)):
                # Not a Bag at all: the cached address went stale. Force a
                # fresh scan next tick instead of calling the pocket full.
                logger.warning("Bag data looks wrong, searching for your save data again.")
                self._array_headers_address = None
                break

            plan = plan_bag_item_write(bytes(pocket_bytes), native_item_id, 1, stack_cap_for_pocket(bag_field))
            if plan is None:
                if index not in self._reported_stuck_items:
                    self._reported_stuck_items.add(index)
                    name = _item_display_name(ctx, next_item.item)
                    logger.warning(
                        f"Could not add {name} to your Bag: that pocket is full (or already holds the "
                        "maximum). Make room and it will arrive on its own."
                    )
                # Pocket genuinely full (or this item's own stack is at its
                # cap) -- deterministic, so retrying it later in this same
                # tick would only waste read RPCs. It stays pending until
                # the player makes room; every *other* pocket's items keep
                # flowing (see this method's own docstring).
                full_bag_fields.add(bag_field)
                index += 1
                continue

            slot_offset, slot_bytes = plan
            write_succeeded = await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(pocket_address + slot_offset, slot_bytes, "ARM9 System Bus")],
                [(pocket_address + slot_offset, bytes(pocket_bytes[slot_offset : slot_offset + 4]), "ARM9 System Bus")],
            )
            if not write_succeeded:
                # Pocket contents changed between the read and the write
                # (e.g. the player used/moved an item at the same time) --
                # normally transient, unlike the full-pocket case above,
                # so retry the whole tick rather than writing over stale
                # data. Repeated failures mean a stale address instead.
                self._bag_write_failures += 1
                if self._bag_write_failures >= _BAG_WRITE_FAILURES_BEFORE_RELOCATE:
                    logger.warning("Items could not be written to your Bag, searching for your save data again.")
                    self._array_headers_address = None
                    self._bag_write_failures = 0
                break

            self._bag_write_failures = 0
            self._reported_stuck_items.discard(index)
            self._delivered_ahead.add(index)
            index += 1
            applied_this_tick += 1

        self._compact_delivery_progress()
        if applied_this_tick > 0:
            await self._store_applied_item_count(ctx, applied_key, delivered_ahead_key)

    async def _store_applied_item_count(
        self, ctx: BizHawkClientContext, applied_key: str, delivered_ahead_key: str
    ) -> None:
        """Persist both halves of the received-item resume point in one
        message batch. The out-of-order half goes first on purpose: if the
        connection dies between the two, an item delivered ahead of the
        counter is still recorded (the counter simply lags and catches up
        next tick), whereas the reverse order could forget it and hand it
        out twice."""
        delivered_ahead_mask = _mask_from_indices(self._delivered_ahead)
        ctx.stored_data[delivered_ahead_key] = delivered_ahead_mask
        ctx.stored_data[applied_key] = self._applied_item_count
        await ctx.send_msgs(
            [
                {
                    "cmd": "Set",
                    "key": delivered_ahead_key,
                    "default": 0,
                    "want_reply": False,
                    "operations": [{"operation": "or", "value": delivered_ahead_mask}],
                },
                {
                    "cmd": "Set",
                    "key": applied_key,
                    "default": 0,
                    "want_reply": False,
                    "operations": [{"operation": "max", "value": self._applied_item_count}],
                },
            ]
        )

    async def _apply_pending_badges(self, ctx: BizHawkClientContext) -> None:
        """Set PlayerProfile.johtoBadges/kantoBadges's bit for every
        badge_* item this player has ever received, immediately on receipt
        -- the bit is purely the "may I use this HM move in the field"
        permission, nothing else.

        This used to defer the write until that gym Leader's own per-gym
        sentinel flag showed the Leader had genuinely been beaten, because
        every gym script's battle guard was `CheckBadge <badge>` and the
        bit therefore doubled as "already beaten, skip the fight". That
        overloading is gone as of 2026-08-19: rom/badgegatedata.py rewrites
        each of those guards to test the sentinel flag directly, restoring
        the vanilla meaning of the guard while leaving the profile bit free
        to mean only what a randomized badge item should mean.

        Deferring was itself buggy in a multiworld, which is why it had to
        go rather than merely being relaxed. A badge item can be placed
        anywhere, so a player who beat, say, Falkner before badge_zephyr
        arrived never satisfied the "received AND sentinel set" pair in the
        order the old code needed: the bit stayed unwritten, `CheckBadge`
        stayed false, Falkner stayed re-fightable, and his win branch
        (`SetVar VAR_SCENE_ELMS_LAB, 6`, gating the Elm's Lab egg pickup)
        replayed forever. Worse, four Leaders `AddVar VAR_MIDGAME_BADGES, 1`
        in that same replayable branch while the story tests that counter
        for strict equality against 3, so re-winning permanently blocked the
        Rocket takeover of Mahogany Town and the Radio Tower. See
        rom/badgegatedata.py's own docstring for the full decomp citations.

        A ROM patched before 2026-08-19 still has the old `CheckBadge`
        guards, so applying the bit early there would skip the fight --
        regenerate the patch (this client and the .apworld that produced
        the ROM are expected to match, same coupling as every other ROM
        patch).

        Re-derives the set from ctx.items_received fresh every tick rather
        than tracking it in instance state, so a client restart mid-seed
        cannot lose a badge -- nothing here depends on anything but live
        savedata and the server's own items_received list. The per-badge
        read is still done every tick because the write must stay
        idempotent: the player may reload an older save state at any time,
        and the bit has to come back.

        One exception, owned here so the two writes can never fight each
        other tick after tick: the Thunder Badge bit is held CLEAR while
        _thunder_badge_withheld says so (see _BADGE_THUNDER_INDEX's block),
        and written back on the first tick that condition ends. When that
        condition cannot be read this tick, the Thunder bit is left exactly
        as it is, while every other badge is still delivered."""
        if self.playerdata_profile_address is None:
            return

        thunder_withheld = await self._thunder_badge_withheld(ctx)
        if thunder_withheld:
            await self._clear_badge_bit(ctx, _BADGE_THUNDER_INDEX)

        seen_badge_indices = {
            _AP_ITEM_ID_TO_BADGE_INDEX[item.item] for item in ctx.items_received if item.item in _AP_ITEM_ID_TO_BADGE_INDEX
        }
        for badge_index in seen_badge_indices:
            if badge_index == _BADGE_THUNDER_INDEX and thunder_withheld is not False:
                continue  # withheld, or undecidable this tick
            byte_offset = _PROFILE_JOHTO_BADGES_OFFSET if badge_index < 8 else _PROFILE_KANTO_BADGES_OFFSET
            bit = badge_index if badge_index < 8 else badge_index - 8
            badge_byte_address = self.playerdata_profile_address + byte_offset
            current_byte = (await bizhawk.read(ctx.bizhawk_ctx, [(badge_byte_address, 1, "ARM9 System Bus")]))[0]
            if current_byte[0] & (1 << bit):
                continue  # already applied

            new_byte = bytes([current_byte[0] | (1 << bit)])
            await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(badge_byte_address, new_byte, "ARM9 System Bus")],
                [(badge_byte_address, bytes(current_byte), "ARM9 System Bus")],
            )

    async def _thunder_badge_withheld(self, ctx: BizHawkClientContext) -> bool | None:
        """True while the Thunder Badge bit must read clear: Lt. Surge not
        beaten yet (_FLAG_HIDE_VERMILION_GYM_STOPS unset) and the player in
        Vermilion City or its gym. See _BADGE_THUNDER_INDEX's block for the
        decomp side (src/gymmick_init.c:56).

        False when the feature cannot apply at all (flags array or map id
        not locatable, e.g. the manual override env vars), so badge
        delivery keeps its plain behavior there. None when a read failed
        this tick: the caller then touches neither direction, and the next
        tick decides again."""
        if self.flags_array_address is None:
            return False
        try:
            byte_index, bit_index = flag_byte_and_bit(_FLAG_HIDE_VERMILION_GYM_STOPS)
            stops_byte = (
                await bizhawk.read(
                    ctx.bizhawk_ctx, [(self.flags_array_address + byte_index, 1, "ARM9 System Bus")]
                )
            )[0]
            if stops_byte[0] & (1 << bit_index):
                return False  # Surge beaten: the vanilla meaning of the bit holds again
            map_id = await self._current_map_id(ctx)
        except bizhawk.RequestFailedError:
            return None
        if map_id is None:
            return False
        return map_id in _THUNDER_BADGE_WITHHELD_MAP_IDS

    async def _clear_badge_bit(self, ctx: BizHawkClientContext, badge_index: int) -> None:
        """Clear one PlayerProfile badge bit (same byte/bit split as
        PlayerProfile_TestBadgeFlag, src/player_data.c). Idempotent: stops
        at the read when the bit is already clear. Guarded write, and any
        bizhawk failure is swallowed so it costs this tick's clear only."""
        byte_offset = _PROFILE_JOHTO_BADGES_OFFSET if badge_index < 8 else _PROFILE_KANTO_BADGES_OFFSET
        bit = badge_index if badge_index < 8 else badge_index - 8
        badge_byte_address = self.playerdata_profile_address + byte_offset
        try:
            current_byte = (await bizhawk.read(ctx.bizhawk_ctx, [(badge_byte_address, 1, "ARM9 System Bus")]))[0]
            if not (current_byte[0] & (1 << bit)):
                return
            await bizhawk.guarded_write(
                ctx.bizhawk_ctx,
                [(badge_byte_address, bytes([current_byte[0] & ~(1 << bit) & 0xFF]), "ARM9 System Bus")],
                [(badge_byte_address, bytes(current_byte), "ARM9 System Bus")],
            )
        except bizhawk.RequestFailedError:
            pass  # retried next tick

