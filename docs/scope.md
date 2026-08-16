# Scope - v1 vs v2

Decided after the M1 spikes (see `docs/architecture.md`, "## Spikes" for the
underlying data: 514 items, 142 encounter maps, 738 trainers in the decomp;
`ndspy` for NitroFS access; no globally-reserved ID range strictly required
by current Archipelago, item/location IDs only need to be unique within this
world).

## v1 (this project's initial release target)

- Wild encounters: grass / surf / fishing (old/good/super rod) / rock smash /
  headbutt, with HGSS's morning/day/night time-of-day tables.
- Trainer parties (including the Elite Four and Red).
- Evolutions (logic-aware: evolution methods stay reachable in logic).
- Base stats (added 2026-08-10, task M4.5): HP/Attack/Defense/Sp. Attack/
  Sp. Defense/Speed, growth rate untouched (unrelated to the deferred
  "level scaling" v2 item below).
- Move stats (added 2026-08-10, task M4.5): Power/PP/Accuracy, Type
  always preserved.
- Static/gift Pokémon (Eevee, Lapras, red Gyarados, Dratini/Poliwag catching
  contest prizes, static legendaries).
- Ground items, **hidden items**, NPC gifts, HMs/TMs, badges.
- Apricorns & Berries.
- Trainer level scaling, move type randomization, species type
  randomization (added 2026-08-11, v0.1.1): off-by-default toggles in
  `options.py` (`trainer_level_scaling`, `randomize_move_types`,
  `randomize_species_types`), moved up from the v2 list below once found
  to be simple, self-contained additions.
- SoulSilver support (added 2026-08-11, v0.1.1): a single Archipelago
  world (`game = "Pokemon HGSS"` since the 2026-08-15 rename, was
  `"Pokemon HeartGold"` before) accepts either a US HeartGold or a
  US SoulSilver ROM via dual-MD5 validation -- see
  `docs/architecture.md`'s SoulSilver section.
- **Wild-encounter HeartGold/SoulSilver version bug, fixed 2026-08-11
  (local, not yet released).** SoulSilver support (above) only fixed ROM
  validation/patching plumbing -- `data_gen/encounters.toml` (and every
  data-flow downstream of it) still carried HeartGold-only wild-encounter
  data unconditionally, and `rom/encounterdata.py` always wrote to
  `g_enc_data.narc`. Found and fixed together (see
  `docs/architecture.md`'s "Wild-encounter version bug" section): 699
  fields across the 137 modeled zones (622 from `gs_enc_data.json`, 77
  from `headbutt.json`) actually diverge between versions (e.g. Route
  29's morning Sentret/Rattata swap); a SoulSilver ROM's own compiled
  game code reads `s_enc_data.narc`, never `g_enc_data.narc`, so even
  correct per-version *data* would have been silently inert without also
  fixing which NitroFS file gets patched. New `game_version` option
  (`options.py`) plus a patch-time version-mismatch check
  (`output_patch.py`) close the loop: generating for the wrong declared
  version now fails loudly and actionably at patch time instead of
  silently miswriting the ROM.
- Victory condition (Elite Four / Red at Mt. Silver / N badges - exact
  condition TBD at implementation time, kept configurable via `options.py`).
- Trainersanity / Dexsanity as stretch goals *within* v1 if the budget
  allows once the core above is stable - not a hard requirement to ship v1.
  **Status (2026-08-11): budget didn't allow it for v0.1.1.** Both were
  exposed as YAML options (`options.py`) with no implementation behind
  them -- `create_locations` never created a trainer-battle or Pokédex-
  entry Location, so enabling either option had no effect on generation
  or gameplay (found via community feedback, confirmed by exhaustive code
  search -- see docs/architecture.md's "Community feedback round"
  section). A Planner pass on 2026-08-11 (start of v2 planning) evaluated
  both for real:
  - **Trainersanity: feasible, no ROM patch needed at all.** The vanilla
    game already sets a per-trainer savedata flag on victory
    (`TRAINER_FLAG_BASE`), in the exact same flags array `client.py`
    already scans every tick -- 390 real trainer-battle locations,
    zero new RAM reads, zero ROM writes. Scoped as v2 work ("Phase 7A"),
    not yet implemented. One caveat to design around: ~52 trainers get
    their flag set for free as a side effect of beating their gym
    leader's script, not from an actual battle -- needs documenting so
    it doesn't read as a bug.
  - **Dexsanity: infeasible at full scope, option removed 2026-08-11.**
    "Seen" fires on every wild/trainer battle encounter (hundreds of
    free checks, degenerate by design). "Caught" across the full 493-
    species dex leaves roughly half unreachable from any single seed
    (HGSS's own wild/static/gift pool doesn't cover it), which is a real
    multiworld-integrity risk (another player's item could land on a
    location this seed can never complete) on top of colliding with
    SoulSilver's own version-exclusive species. A scope-reduced version
    (a bounded, seed-aware species subset) might be viable later but
    needs a non-trivial refactor (moving encounter randomization earlier
    in generation) -- not budgeted. Removed from `options.py` rather
    than left inert, since it was already having zero effect either way
    and an inert-but-present option risks players believing it does
    something. **Implemented for real (task M3.4, 2026-08-15), the
    "scope-reduced, seed-aware" version this note anticipated:**
    `randomize_wild_encounters` now runs in `generate_early()` (before
    `create_regions`/`create_items`, and for Universal Tracker re-runs too
    -- see `universal_tracker.TRACKED_OPTION_NAMES`, which now also tracks
    `exclude_legendaries`/`dexsanity`, closing a latent UT-desync gap this
    change would otherwise have introduced), so `species.
    species_encounter_methods(world.generated_encounters)` can determine,
    per seed, exactly which species are genuinely obtainable -- only those
    get a `type = "dexsanity"` location (up to 493 reserved ids, one per
    `species.real_species_pool` entry, mirroring how `type = "trainer"`
    reserves all 390 regardless of whether `trainersanity` is on). Static/
    gift Pokemon (starters, legendaries, in-game gifts) stay out of scope,
    same as C4/C5's own item-location extraction. The multiworld-integrity
    risk is closed differently than "bounding the species subset" alone
    would: every Dexsanity location's `access_rule` only requires owning
    the cheapest catching tool for that species in this seed (Surf+badge,
    a fishing rod, or nothing at all for grass/headbutt species) rather
    than the exact region it spawns in, and the location never holds a
    progression item (filler only, like `type = "trainer"`) -- so the
    rule's intentional looseness can only ever delay a filler pickup, never
    strand a required item behind an actually-unreachable check. Check
    detection needed a new savedata array separate from `SaveVarsFlags.
    flags[]`: `Pokedex.caughtSpecies` (`include/pokedex.h`), read via
    `client.py`'s existing dynamic `_chunk_offset` mechanism pointed at
    `SAVE_POKEDEX` (chunk id 6) instead of `SAVE_FLAGS` -- confirmed live
    that `Pokedex_SetMonCaughtFlag` (`battle_system.c`) fires on every
    catch unconditionally, with no dependency on owning the physical
    Pokédex item first (an assumption this task initially got wrong from
    other Pokémon games' conventions, corrected against the actual decomp
    and a live catch-before-Pokédex test).

## Shelved (task M4.5, 2026-08-10)

- **Starters.** Was in v1 scope; removed after extensive investigation
  (live BizHawk memory-write breakpoints + Trace Logger captures across
  5 sessions, plus exhaustive static search -- no packed species table
  anywhere in the ROM, main ARM9 or any of the 129 overlays, no matching
  `SetVar` script operand) failed to locate a patchable vanilla-species
  source. `species.py`'s `randomize_starters` (pure computation) and
  `rom/starterdata.py` (ROM-write plumbing for the since-disconfirmed
  overlay 61 candidate) both stay in the codebase, tested, ready to
  reconnect if a real patch target is found later. Full investigation
  write-up: `docs/architecture.md`'s "M4.5 continued" sections.
  **Reconnected (task "Randomize Starters", 2026-08-15):** the real target
  turned out to be much simpler than the overlay 61 candidate -- `src/
  choose_starter.c`'s `CreateStarter` has a plain, function-local `const
  int species[]` array, which the compiler places in the decompressed main
  ARM9 image (not an overlay). Located by searching `rom.
  read_main_code_decompressed()` for the literal `int[3]` byte pattern
  (152, 155, 158 -- Chikorita/Cyndaquil/Totodile's raw species indices),
  which matches exactly once, at RAM address `0x02108514`; cross-checked
  against a Thumb `LDR` literal-pool load and the two `BL` calls
  immediately after with `CreateMon`'s own level/personality constants (5,
  32). **Live-verified** with a real BizHawk boot test (trio swapped to
  Bulbasaur/Charmander/Squirtle, confirmed received in-game). One known
  cosmetic gap, not yet fixed: the on-screen name shown during the
  selection scene still displays the vanilla species name -- the species
  actually received is correct, only the displayed text lags behind
  (`choose_starter_app.c` reads the name through a separate `msg_0190_...`
  message-bank lookup, independent of the species array patched here; same
  underlying message-archive-decoding work as the "???" placeholder task
  below, planned to be fixed together).

## v2 (planning started 2026-08-11, execution order: Nuzlocke aids + QoL first)

A Planner pass (2026-08-11) re-evaluated this whole list against the real
code/decomp rather than assumption. One correction worth flagging: badges
turned out to be far more tractable than originally believed here (see
below) -- the "savedata flag bit, not a bag item" framing undersold how
close the existing flag-reading mechanism already gets.

- **Region graph logic fixes (task M0, 2026-08-15).** Tester feedback (real
  spoiler logs) showed seeds reaching their goal at sphere 0 or 1 with zero
  items owned. Root-caused and fixed in `data_gen/regions.toml` and
  `data_gen/rules.toml`: two missing vanilla HM/item gates (Surf on
  `new_bark`/`route_27`, the Squirtbottle Sudowoodo on `route_36`/
  `route_37`), a new `events` requirement concept for pure story flags
  (used to gate the S.S. Aqua Kanto shortcut, the post-Elite-Four Mt Silver
  shortcut, and the Elite Four's own 8-Johto-badge entry gate), and a
  one-way ledge (Route 46 into Route 45) that the raw graph wrongly let
  players climb back up. Verified with a new `tests/test_rules.py` sphere-0
  regression test plus the project's own full test suite (249 tests).
  **One remaining, decomp-confirmed limitation, kept as-is by design
  (2026-08-15 decision, "rester fidele au vanilla, ne rien ajouter"):**
  Blackthorn Gym (and every other Johto gym) never checks the player's
  prior badge count before battling, so the Route 46 ledge is a genuine
  vanilla shortcut, not a bug, that leaves 7 of the 16 badges (Violet,
  Azalea, Goldenrod, Ecruteak, Cianwood, Olivine, Blackthorn) reachable with
  zero items. This means a `goal: n_badges` seed with a low
  `goal_badge_count` (e.g. 4, as in one real tester's own options) stays
  trivially completable at sphere 0/1 even after this fix, since any 4 of
  those 7 satisfy the goal. Not treated as a bug to patch (that would mean
  inventing a non-vanilla gate); documented here instead, and worth
  recommending a `goal_badge_count` above 7 in the player yaml template/docs
  for anyone who wants a `n_badges` goal that actually requires
  progression.
  **Closed out 2026-08-16**: re-verified with a real `ArchipelagoGenerate.exe`
  run (every randomizer on, Trainersanity/Dexsanity/Legendarysanity all on,
  `goal: champion_red`, the deepest goal) -- the playthrough now takes 4 real
  spheres (badges/HMs/S.S. Ticket) before `elite_four_defeated`, no more
  trivial sphere-0/1 completions, no unreachable-location warnings. Also
  confirmed `route_28`/Mt Silver has exactly one incoming edge
  (`route_22_pokemon_league_reception_gate -> route_28`), gated on
  `elite_four_defeated` with no bypass. The playthrough correctly shows
  nothing after `elite_four_defeated_event` for `champion_red` -- reaching
  Mt Silver Summit needs no item beyond what E4 already required, so that's
  not a truncated path, just nothing left to require.
- **Real badge randomization** (as a tradeable/shufflable item, not just a
  fixed logic milestone). Corrected understanding (2026-08-11): a badge is
  a bit in `PlayerProfile.johtoBadges`/`kantoBadges` (the `SAVE_PLAYERDATA`
  chunk), and gym-leader-defeat detection already lives in the *same*
  flags array (`TRAINER_FLAG_BASE`) `client.py` already scans every tick
  -- so both detection and remote delivery reuse mechanisms this project
  already has, not a new one. The one real open question is removing the
  *local* badge grant so it doesn't double up with the AP item: **decided
  2026-08-11 -- patch the 16 gym scripts' `GiveBadge` calls directly**
  (not a client-side workaround), pending verifying `CheckBadge`'s own
  6-byte re-entry guard has a safe substitute. **Implemented (task "Badges
  comme vrais items AP", 2026-08-15):** `type = 'badge'` locations are now
  real, fillable locations like ground_item/npc_gift (`original_item` = a
  new synthetic `badge_*` entry in `data/items.py`, id 9000+badge index,
  always progression) instead of locked events -- check detection reuses
  `TRAINER_FLAG_BASE + <gym Leader's trainer id>`, the same mechanism
  `type = 'trainer'` locations already use, since defeating a Leader is
  itself a `std_trainer`-class battle even though it was never one of the
  390 Trainersanity locations (a raw `TrainerBattle` scrcmd inside a
  scripted sequence, not a simple person-event `scriptId`). `rom/
  badgedata.py` neutralizes each gym's own vanilla `GiveBadge` call (a
  flat 4-byte instruction, opcode 295 + badge index -- overwritten with
  two `Nop` instructions, preserving the script's byte length exactly) so
  it can no longer also set the (possibly wrong, vanilla) badge locally;
  `CheckBadge`'s own re-entry guard is deliberately left untouched, since
  once the local grant stops firing it naturally reflects whether the
  player has genuinely received that badge_* item yet (re-battle the
  Leader on revisit until they have, regardless of where the real item
  ended up). One decomp-confirmed special case, not a bug: the Rising
  Badge (Clair) is granted at a different script site (Dragon's Den
  Shrine's own puzzle-completion cutscene) than her real battle
  (Blackthorn Gym) -- both sites are tracked independently (patch site in
  `rom/badgedata.py`, detection site via `data_gen/locations.toml`'s own
  `trainer` field). `goal: n_badges` and the `[hm_badges]`-gated exit
  rules (Surf/Rock Smash/etc. needing a badge to use the HM in the field)
  both now check ownership of the real `badge_*` item instead of the old
  locked-event name.
  **Real bug, reported by a player and fixed 2026-08-17**: receiving a
  `badge_*` item from anywhere in the multiworld *before* physically
  reaching that gym set the `PlayerProfile` bit immediately -- but every
  gym Leader's own field script gates its `TrainerBattle` call behind
  `CheckBadge`, so the Leader then thought the fight had already
  happened and skipped it entirely (decomp-confirmed in Violet Gym's own
  script: `CheckBadge BADGE_ZEPHYR -> GoToIfEq <skip battle>`). This
  silently broke more than just that one fight: `SetVar
  VAR_SCENE_ELMS_LAB, 6` (which gates Elm's Lab's egg-pickup phone call)
  and `SetTrainerFlag TRAINER_BIRD_KEEPER_GS_ROD`/`_ABE` (unlocking two
  more, Trainersanity-eligible trainers) only happen inside that same
  battle-won branch -- skipping the fight silently stalled all three.
  **Fixed client-side, no ROM/script patch needed**: `client.py`'s
  `_apply_pending_badges` (replacing the old immediate-write logic in
  `_apply_received_items`) now defers setting the `PlayerProfile` badge
  bit until `TRAINER_FLAG_BASE + <that Leader's trainer id>` is already
  set (i.e. the player has genuinely beaten them for real) -- the exact
  same flag the badge location's own check detection already reads.
  Re-derived fresh from `ctx.items_received` every tick rather than
  tracked in instance state, so a client restart mid-seed can't lose
  track of a badge still waiting on its real fight. Verified this is the
  *only* location type with this class of risk (checked every other item
  this project writes directly to savedata -- Bag items, DeathLink's HP
  zeroing, Dexsanity/legendarysanity filler -- none of them double as a
  vanilla script's own "skip this content" condition the way a badge's
  `PlayerProfile` bit does).
- Pokéwalker.
- Pokéathlon.
- Bug Catching Contest / Safari Zone.
- Day care / egg hatching.
- Kurt's Apricorn balls.
- Radio Card / PokéGear features (becomes low-effort once badge
  randomization's generic "remote savedata-bit delivery" mechanism
  exists -- both are just flag bits, same shape as a badge).
- DeathLink (standalone -- not coupled to Nuzlocke mode below in any way,
  that idea was considered and explicitly dropped 2026-08-11).
- **QoL options** (fast text speed, skip battle animations) -- community
  feedback (2026-08-11) after the v0.1.1 playtest. First attempt
  implemented then reverted the same day (v2 Phase 1, 2026-08-11): live
  BizHawk testing showed neither option changed anything in-game, and the
  bit order the write relied on was never independently confirmed.
  **Implemented for real, live-verified 2026-08-15:** did the deferred
  verification step directly -- read `PLAYERDATA`'s Options u16
  (`playerdata_profile_address - PLAYERDATA_PROFILE_OFFSET`), toggled
  Text Speed Fast->Slow in-game and saw `0x0002 -> 0x0000` (confirming
  `textSpeed` occupies bits 0-3 exactly as the naive decomp-order
  assumption predicted -- 2 = Fast, the fastest tier `Options_
  GetTextFrameDelay` itself defines, 1 frame/character; going faster
  would need an ARM code patch, not a savedata write, so out of scope),
  then Battle Scene On->Off and saw `0x0000 -> 0x0080` (confirming
  `battleScene` is bit 7, matching textSpeed(4)+soundMethod(2)+
  battleStyle(1)=7 bits before it exactly). The 2026-08-11 revert's real
  cause was most likely a stale/unverified address, not bit order --
  the original assumption was correct all along. `options.py`'s
  `FastTextSpeed`/`SkipBattleAnimations` (both off by default) are
  applied once per connection by `client.py`'s `_apply_qol_options`, a
  plain masked read-modify-write that leaves every other Options field
  (sound method, battle style, button mode, frame) untouched -- see
  `save_layout.py`'s own header for the full live-verification writeup.
- **Reusable TMs** (2026-08-15, user request while discussing the QoL
  options above). HMs are already never consumed in vanilla
  (`party_menu_items.c`'s `PartyMenu_LearnMoveToSlot` only calls
  `Bag_TakeItem` `if (!MoveIsHM(moveId))`) -- this option covers TMs.
  Investigated a direct ROM patch first (NOP the `Bag_TakeItem` call
  site, the same technique already used for badge neutralization): live
  BizHawk breakpoint tracing found the real call site much harder to
  pin down reliably than the badge/starter cases (two rounds of
  execution/write breakpoints produced an inconsistent address --
  register state pointed at a return address with no valid `BL`
  instruction immediately before it, most likely due to a tail-call
  through an intermediate wrapper). Cross-checked `platinum_archipelago`'s
  own "Reusable TMs" implementation for comparison: it repurposes
  `ItemData.prevent_toss` (`include/item.h`, loaded from
  `item_data.narc`) as a signal bit for their own custom-injected ARM
  hook -- confirming this really does need real code injection to do
  properly, the same risk class as the never-shipped
  `ground_item_hook.s`. **Implemented client-side instead** (2026-08-15,
  user's own suggestion): `client.py`'s `_restore_reusable_tms` compares
  each TM/HM pocket item's total quantity tick-to-tick and writes back
  any decrease via the same `plan_bag_item_write`/`guarded_write` path
  already used to deliver received items -- no ROM patch, no ARM
  address needed at all. Live-verified: taught TM10 to a live save with
  the option enabled, confirmed it reappeared in the Bag on the next
  poll (read back directly: slot 0, id 337, qty 1, matching the
  pre-teach baseline exactly).
- **DeathLink** (2026-08-15). Send side: `GAME_STAT_PLAYER_MON_FAINTED`
  (`include/constants/game_stats.h`, id 97) is a real vanilla `GameStats`
  savedata counter incremented every time one of the player's own
  Pokemon faints -- polled the same "read and diff" way as reusable
  TMs above, no ROM patch. Cross-checked `platinum_archipelago`'s own
  DeathLink client: it uses the exact same technique (their own
  equivalent "num_blacked_out" counter) for the send side, confirming
  this doesn't need their custom ARM-hook infrastructure. Receive side:
  `client.py`'s `_receive_death_link` notices `ctx.last_death_link`
  changing (CommonContext's own `on_deathlink` hook updates it) and
  zeroes every real party Pokemon's current HP -- `include/
  pokemon_types_def.h`'s own `PartyPokemon.hp` field (Pokemon struct
  offset 0x96) is a plain unencrypted u16 mirror kept outside
  `BoxPokemon`'s encrypted/checksummed data blocks ("stored here...
  rather than recalculating stats after each battle" per that struct's
  own doc comment), so this is a safe plain write, no ARM hook needed
  either. `_ignore_next_death_link` skips the echo of this player's own
  just-sent death (AP's "Bounce" mechanism rebroadcasts to the sender
  too).
- **Convert trade/friendship evolutions** (2026-08-15, user request).
  Trade (`trade`/`trade_item`) and friendship-based evolutions are a
  real single-player accessibility problem -- `species.
  convert_trade_and_friendship_evolutions` rewrites any evolution edge
  using one of those methods into a plain `level` evolution at a
  configurable level (`trade_evolution_level` option, default 30) once
  `convert_trade_evolutions` is on. Runs *after* `randomize_evolutions`
  in the pipeline, so it also catches a trade/friendship method that
  evolution randomization itself newly assigned to some species, not
  just the vanilla cases. A pure `data/species.py` transform, reuses the
  exact same `rom/evodata.py` write path `randomize_evolutions` already
  uses (that path already supported `method="level"`) -- no new ROM
  code needed.
- **Nuzlocke mode** -- community feedback (2026-08-11). Two balance
  problems identified, both about un-counterable forced deaths under a
  permadeath ruleset -- scoped as *optional aids* (data-table edits), not
  game-enforced rules. **Decision (2026-08-11): real rule enforcement
  (permadeath blocking a fainted Pokémon from being healed/used again,
  one-catch-per-route limits) stays honor-system, tracked externally by
  the player's future PopTracker pack (see the user's own stated plan),
  not enforced in-game.** True in-game enforcement would need to
  intercept fainting/capture in real time -- ARM-level hooks this project
  has never actually shipped (the one attempt, C14's `ground_item_hook.s`,
  stayed a proof of concept, never wired into production), the same class
  of blocker that stopped starter randomization after 5 investigation
  sessions. Not revisited unless the user explicitly asks for that
  investigation later.
  - OHKO moves (Horn Drill, Fissure, Guillotine, Sheer Cold) disabled --
    an RNG-based instant KO is a bad interaction with permadeath.
    **Implemented (v2 Phase 1, 2026-08-11):** `options.py`'s
    `DisableOhkoMoves`, `species.py`'s `disable_ohko_moves`, ROM write via
    `rom/movedata.py`'s `write_ohko_neutralization` (`waza_tbl.narc`'s
    `effect` field cleared, power/accuracy set to 60/100).
  - Trapping abilities disabled or swapped for the same species' other
    ability: **Arena Trap/"Piège", Shadow Tag/"Marque Ombre", and Magnet
    Pull/"Aimant" (2026-08-11 decision: included alongside the other
    two, same rationale -- traps Steel-types the same way)**.
    **Implemented (v2 Phase 1, 2026-08-11):** `options.py`'s
    `DisableTrappingAbilities`, `species.py`'s
    `neutralize_trapping_abilities`, ROM write via
    `rom/speciesdata.py`'s `write_abilities` (`personal.narc`'s ability
    slots, offset 0x16/0x17 -- confirmed both against the decomp's
    `struct BaseStats` and a live read of the real ROM).
- **Replace the "???" placeholder name** shown when picking up a
  location holding another player's item (see `docs/architecture.md`'s
  "empty item substitution" section) -- community feedback (2026-08-11).
  **Implemented (2026-08-15):** reverse-engineered HGSS's message-archive
  ("MAT") binary format from the decomp's `src/msgdata.c`/`src/item.c`
  (per-bank XOR "encryption" of both the entry table and the text itself,
  both fully reversible, see `rom/msgdata.py`'s own docstring for the
  full derivation), located the real NitroFS path of the item-name bank
  (`msg_0222`, 537 entries, one per item id, path `a/0/2/7` sub-file 222
  -- the decomp's own `files/msgdata/msg.narc` source path has no
  matching symbolic ROM path, this was found via an exhaustive scan of
  every generic bucket path for a sub-file whose entry 0/1 decode to
  "None"/"Master Ball"). `rom/msgdata.py`'s `read_message_text`/
  `write_message_text` decode/encode via a new `data/charmap.py`
  (generated from `data_gen/charmap.toml`, a 75-character ASCII-
  equivalent subset of the decomp's own `charmap.txt`). Considered and
  rejected a fully dynamic per-item name (would need either a proprietary
  matching-decomp build toolchain to add a new ARM hook, the way
  `platinum_archipelago`'s `REMOTE0` item class does it, or a risky
  static byte-pattern scan for a live hook address) in favor of a fixed,
  generic replacement text ("Item sent to another player!", written to
  msg_0222 entry 0 via `patch_gen.apply_placeholder_text_fix`) --
  simpler and more stable, confirmed live via BizHawk. The real item
  name sent is still visible in the Archipelago client console, so
  nothing is actually hidden from the player.
- **Trainersanity, made real** (moved here from its old "v1 stretch goal"
  slot above, 2026-08-11). **Implemented (task M3.3, 2026-08-15):** 390
  real, fillable `type = "trainer"` locations, one per `std_trainer(...)`
  person-event object found across every in-scope `zone_event/*.json`
  (cross-checked against this section's own "390" figure, zero mismatch).
  Check detection reuses `TRAINER_FLAG_BASE + trainer id`
  (`include/constants/flags.h`), the exact same savedata flags array
  `client.py` already polls every tick, no ROM patch. Only created when
  the `trainersanity` option is on; each location contributes a random
  filler item to the pool (no vanilla item to displace). One documented,
  not-a-bug nuance: 52 of the 390 trainers also get their flag set
  automatically the moment their gym's Leader is defeated (each gym
  script has its own explicit `SetTrainerFlag` calls for a handful of its
  own regular trainers, decomp-confirmed count) -- a real vanilla
  convenience for trainers the player dodged en route to the Leader, not
  something this project introduces.
- **`zone_method_mapping` wild encounter mode** (task M3.4 follow-up,
  2026-08-15) -- a 4th `randomize_wild_pokemon` option value, added
  alongside `vanilla`/`shuffle`/`full_random` (none of the three changed).
  Neither existing randomized mode gave a species a *consistent* in-game
  identity: `shuffle` permutes individual slot values (the dozen vanilla
  Sentret slots on one route can each become a different species after
  shuffling, decomp/data-verified live during this task), and
  `full_random` draws every slot independently. `zone_method_mapping`
  instead assigns one replacement species per (zone, encounter method)
  group -- e.g. "route 29's grass table" is one group, "route 29's surf
  table" a separate one -- applied to every slot in that group, so a given
  route's grass encounters are a single consistent species (while its surf
  table can differ). Replacement species are drawn via a new `species.
  _fill_maximizing_distinctness` helper (`rng.sample` when the pool covers
  every group, falling back to "every pool member once, then `rng.choices`
  for the remainder" when it doesn't -- a real edge case here: 458 real
  species with `exclude_legendaries` on vs. up to ~460 (zone, method)
  groups in HeartGold), so a seed uses as much of the national dex as
  mathematically possible rather than repeating a handful of species
  across dozens of routes the way `full_random` can.
- **Starter-choice screen name/description text still shows the vanilla
  name** (2026-08-12, found via the live BizHawk test that confirmed
  `rom/starterdata.py`'s new species-array address): the actually-
  received Pokémon is correct, but `choose_starter_app.c` reads the
  displayed name/description as a hardcoded `msg_0190_0000{1,4} +
  curSelection` message-bank lookup, entirely independent of the species
  array this project patches. **Implemented (2026-08-15):** `msg_0190`
  turned out to live at sub-file index 190 of the exact same message
  narc as `msg_0222` (`rom/msgdata.py`'s `NITROFS_PATH`) -- every
  decomp "msg_NNNN" bank is sub-file NNNN of that one narc, confirmed by
  reading sub-file 190 directly and finding CHIKORITA/CYNDAQUIL/TOTODILE
  in the decoded text, no second exhaustive scan needed.
  `patch_gen.apply_starter_selection_text_fix` rewrites the 3 question
  entries (msg_0190_0001-3) and 3 confirmation entries (msg_0190_0004-6)
  to name the actually-randomized species and its real primary type per
  slot, in the same slot order as `rom/starterdata.py`'s own species[]
  array; a no-op when starters are still vanilla. Same "simpler and more
  stable" call as the "???" fix: vanilla wraps the species name in its
  own text-color control codes, not reproduced here -- a plain-color
  sentence naming the right Pokémon beats an exact color match on the
  wrong one. Added two characters to `data_gen/charmap.toml` for this
  (the game's own small "e" used in "Pokémon", and its own curly
  apostrophe), both taken from real decoded vanilla text, not guessed.
  **Follow-up (2026-08-16, user request):** `randomize_starters` now
  restricts its pool to species with at least one evolution, matching
  vanilla (Chikorita/Cyndaquil/Totodile each have two) -- previously a
  randomized starter could land on an already fully-evolved species.
- **Ho-Oh/Lugia as real, checkable static Pokemon** (task "Ho-Oh/Lugia
  comme Pokemon statiques", 2026-08-15). **Implemented:** two new
  `type = 'static_pokemon'` locations, `catch_ho_oh` (region
  `bell_tower_roof`, map D17R0110) and `catch_lugia` (region
  `whirl_islands_b3f_lugia_cave`, map T10R0701) -- real, fillable
  locations like `trainer`/`badge`, no vanilla item to displace so each
  contributes a random filler item the same way a trainer battle does.
  Check detection reuses
  `include/constants/flags.h`'s own dedicated `FLAG_CAUGHT_HO_OH`
  (0x116) / `FLAG_CAUGHT_LUGIA` (0x117) constants -- the exact same
  `SaveVarsFlags.flags[]` savedata array every other flag-based location
  type already reads, no ROM patch needed. Decomp-confirmed (scr_seq_
  0021_D17R0110.s / scr_seq_0825_T10R0701.s) that the flag is set only
  on an actual successful *catch*: losing or fleeing clears the
  matching `FLAG_HIDE_*` instead and the Pokemon simply reappears,
  never blocking anything -- matches the task's own "pas de combat
  obligatoire" constraint exactly. Both regions only become reachable
  after defeating the Elite Four/Champion in vanilla (scr_seq_0825_
  T10R0701.s is the Hall of Fame victory script itself, and it's what
  first clears both `FLAG_HIDE_BELL_TOWER_HO_OH`/`FLAG_HIDE_WHIRL_
  ISLAND_LUGIA`) -- modeled as an `events = ["elite_four_defeated"]`
  `data_gen/rules.toml` exit_rule gate (the same event already used for
  the Kanto gate) rather than a location-specific rule, since neither
  region holds any other location.
  **Follow-up (2026-08-16, user request): gated behind a new
  `legendarysanity` option, off by default.** Investigated live-game
  knowledge first: the user recalled catching their version's own "box"
  legendary before the Elite Four, but a full decomp search (every
  `ClearFlag`/`SetFlag` reference to both Hide flags across the whole
  project) found no earlier catchable path for either species -- the
  Hall of Fame script above is the only real unlock, both versions,
  unconditionally. What the user likely remembered is a non-catchable
  scripted flyby during the Team Rocket/Radio Tower arc (pre-E4), which
  never touches either Hide/Caught flag. Cross-checked
  `platinum_archipelago`: it doesn't track any static legendary capture
  as an AP location at all (Dialga/Palkia/Giratina, the lake trio, Regis,
  Heatran, Cresselia, etc. all stay fully vanilla; only a species-level
  blacklist option exists, to exclude legendaries from the wild-encounter
  randomization pool). `legendarysanity` follows that precedent: off by
  default, both stay exactly vanilla (same place, same post-Elite Four
  requirement) and simply aren't tracked as a check; on, both become real
  checks the same way `trainersanity`/`dexsanity` do. Independent of
  `exclude_legendaries`: Ho-Oh/Lugia can already appear as an ordinary
  wild-encounter species (and therefore get their own Dexsanity check)
  when `randomize_wild_pokemon` is `full_random`/`zone_method_mapping` and
  `exclude_legendaries` is off -- `legendarysanity` only concerns their
  separate, guaranteed static encounter.

## v3 (deferred -- each blocked on something outside a normal implementation
pass: an external prerequisite, or a real ARM code hook this project has no
working toolchain for -- 2026-08-15)

- **Non-US localization support** (French specifically requested,
  community request 2026-08-12, generalized here to "any Latin-script
  European localization" after discussion -- was v2.1, moved out since
  it cannot even start without a real dump). Feasibility discussion
  findings (general Gen4/NDS ROM-hacking knowledge, NOT verified against
  a real French/German/Italian/Spanish dump -- none available locally):
  - **Likely OK as-is**: ARM9 code RAM addresses (this project's
    already-derived offsets -- the starter species[] array, PlayerProfile
    layout, badge GiveBadge sites, FLAG_CAUGHT_HO_OH/LUGIA, etc.) are
    probably identical across language versions of the same game/revision
    -- Game Freak compiles every localization from the same source, only
    swapping translated string *data*, not game logic. `rom/msgdata.py`'s
    MAT format is also offset-agnostic by design (append-only writes), so
    it would work unmodified regardless of how translation changes
    internal narc byte offsets.
  - **Confirmed encouraging sign**: the decomp's own `charmap.txt` already
    maps 'é' (0x0188) even though this project only ever read it off a US
    ROM -- suggests the charmap is shared/pan-European, not US-only, so
    `data_gen/charmap.toml` would likely just need a handful of added
    entries (è, ê, à, â, ù, û, ç, œ, ...) rather than a rebuild.
  - **Confirmed needs new data, low risk**: header ID code and MD5 (`rom/
    __init__.py`'s `HEARTGOLD_US_MD5`/`_ID_CODE_BY_VERSION`) -- additive,
    not a redesign.
  - **Genuinely unverified, the real risk**: whether ARM9 addresses
    actually hold across localizations for real (not just "likely" per
    general community knowledge), and how many cartridge revisions a
    French release has (the US version has Rev0/Rev1, both already
    special-cased -- see `rom/__init__.py`).
  - **Out of scope entirely, much bigger undertaking**: Japanese --
    different character encoding/font system than the Latin-script
    European versions, not just more charmap entries.
  - **Blocked on**: a legally-owned non-US HGSS dump to actually compare
    (MD5, NitroFS sub-file layout, ARM9 length, and a few already-known
    RAM addresses) before any real implementation work starts. Revisit
    once one is available.
- **Human-readable location display names** (2026-08-15, deprioritized
  after discussion). Investigated: `data_gen/locations.toml`'s `label`
  field is currently write-only -- never read anywhere at runtime (the
  actual Archipelago location name shown in the client/spoiler log is
  always the raw snake_case key, e.g. `route_30_apricorn_house_
  apricorn_box`). 479 of ~1470 locations (every `ground_item`/
  `hidden_item`, 37 of 73 `hm_tm`) have no `label` at all. Purely
  cosmetic -- no effect on generation, gameplay, or rule correctness.
  Wiring `label` up as the real player-facing name would be a breaking
  change in the same family as the "Pokemon HGSS" rename (old seeds'
  spoiler logs/`exclude_locations`/`priority_locations` entries would no
  longer match), on top of needing all 479 missing labels actually
  written. Deprioritized: bad effort/impact ratio versus DeathLink/QoL.
  **Revisited and re-deferred 2026-08-15**: found a second, sharper risk
  beyond the cosmetic one above -- `output_patch.py`'s own
  `build_item_substitutions` (and other generation-time code) does
  `LOCATIONS.get(location.name)`, assuming `location.name` is always
  the raw snake_case key. Wiring `label` up as the real `Location.name`
  would silently break that lookup everywhere it's used unless every
  such call site is found and fixed to go through a key<->label mapping
  instead -- a real risk to check delivery, not just a cosmetic one.
  Needs its own dedicated session with room to audit every call site
  and test thoroughly, not a same-session addition.
- **Trainer level matching** ("mon Pokemon niveau 5 devient niveau 26
  face a un dresseur niveau 24 avec +2", user request 2026-08-15,
  modeled after `pokemon_emerald`'s own `MatchTrainerLevels` option).
  Investigated live: detecting "a trainer battle has started" isn't
  reachable through this project's established SaveData-scanning
  technique at all -- battle state (which trainer, live in-battle
  context) lives in a dynamically-allocated runtime struct, not the
  persistent SaveData block every other feature this project has ever
  read/written lives in. Cross-checked `pokemon_emerald`'s own
  `MatchTrainerLevels`: confirmed it needs a real ARM/GBA code patch
  (their own `options_address`-driven in-battle stat recalculation,
  built with Gen3's mature, free, matching-decomp GCC toolchain) --
  the same category of blocker as every other ARM-hook attempt this
  project has made (`ground_item_hook.s`, the reusable-TMs
  investigation above), and Gen4/HGSS still has no equivalent working
  toolchain. Blocked, not just hard -- needs its own investigation
  session (a live battle-state RAM signature scan, similar in spirit to
  the arrayHeaders scan but for dynamic memory) before this is even
  worth scoping further.
- **Randomized start location + starter kit** (user request 2026-08-15,
  re-investigated in depth 2026-08-16 with live BizHawk verification --
  most of the original "blocked" assessment below turned out to be
  wrong). Original finding: the player's on-screen, *live* position lives
  in the same dynamically-allocated runtime `FieldSystem`/`PlayerAvatar`
  memory as battle state -- not the persistent SaveData block.
  `LocalFieldData_GetCurrentPosition` (`include/save_local_field_data.h`)
  *is* a real, plain SaveData field for map/x/y/direction, but only read
  back at save-file *load* time -- writing it live would not move the
  player until a full reload, so a live-teleport-on-connect design
  (the original plan) genuinely doesn't work.

  **What actually does work, decomp-verified and live-tested 2026-08-16:**
  - `src/location_backup.c`'s `sLocation_PlayerRoom` (a plain, static,
    5-word `Location` ROM constant -- mapId/warpId/x/y/direction) is
    copied into `LocalFieldData.position` by `Save_SetPositionToPlayerRoom`,
    called once from `overlay_36.c`'s `NewGame_InitSaveData` at New Game
    creation (*before* the player even names their character) -- found by
    byte-pattern search in the decompressed ARM9, single unique match at
    RAM address `020FA17C` (file offset `0xFA17C`). **Live-verified
    twice**: overwriting these 20 bytes at runtime (before the game reads
    them) changes where the player actually spawns -- confirmed moving
    within the same room (x/y shift) and confirmed warping to a
    *different real town* (Cherrygrove Pokemon Center, mapId 69, x=8,
    y=13) after character creation. Since this is a static ROM constant,
    not a live teleport, it can simply be baked into the generated patch
    at build time like every other data table this project already
    edits -- no ASM, no reload-timing problem at all.
  - **A complete, ready-made table of every safe warp destination
    already exists in the ROM**: `sSpawnMaps` (`asm/unk_0203BA5C.s`,
    not yet source-matched in the decomp but fully readable as ASM),
    30 entries covering every major Johto/Kanto town and a few routes,
    each with death-warp/fly-point/special-warp coordinates -- these are
    the exact coordinates the game itself already uses for whiteout
    recovery and Fly, so they're guaranteed-valid floor tiles, not
    guessed values. Located and extracted directly from the ROM (byte
    search for the first entry's known values, base offset `0xF9E80`,
    18 bytes/entry): new_bark, cherrygrove, violet, azalea, cianwood,
    goldenrod, olivine, ecruteak, mahogany, lake_of_rage, blackthorn,
    mount_silver, pallet, viridian, pewter, cerulean, lavender,
    vermilion, celadon, fuchsia, cinnabar, indigo_plateau, saffron,
    safari_zone_gate, battle_frontier, pokeathlon_dome,
    route_22_reception_gate, route_32, route_3, route_10 (some of these,
    e.g. Indigo Plateau/postgame spots, would need excluding as
    candidates the same way Crystal/FRLG blocklist theirs).
  - **Skipping the New Bark intro entirely turned out to be simpler than
    expected, but reveals more missing state than expected too.**
    Investigated whether "OakSpeech" (`src/oaks_speech.c`, 2237 lines) is
    the Mom/Elm/rival cutscene -- it isn't; despite the name (carried
    over from Gen 1's Professor Oak), it's purely the character-creation
    UI (name/gender/appearance), self-contained, running independently
    of location. **Live-verified**: redirecting the spawn point to
    Cherrygrove (via the `sLocation_PlayerRoom` patch above) skips the
    New Bark intro entirely -- confirming the whole Mom/Elm's
    Lab/rival/Mystery Egg sequence is gated on physically being in New
    Bark's own maps, not on any global "intro in progress" state. But
    the resulting save is missing more than just the starter: **no Bag,
    no Trainer Card, no Save button, no Options button** were available
    in the pause menu. Root-caused: `src/sys_flags.c`'s
    `CheckGotMenuIconI(state, FLAG_GOT_BAG + icon_idx)` gates each pause
    menu icon behind its own independent flag --
    `include/constants/flags.h`: `FLAG_GOT_BAG` (0x11B),
    `FLAG_GOT_TRAINER_CARD` (0x11C), `FLAG_GOT_SAVE_BUTTON` (0x11D),
    `FLAG_GOT_OPTIONS_BUTTON` (0x11E), plus `FLAG_GOT_STARTER` (0x6A),
    `FLAG_GOT_POKEDEX` (0x6B), `FLAG_GOT_POKEGEAR` (0x9C) found the same
    way -- all in the same `SaveVarsFlags.flags[]` array this project
    already reads/writes constantly (same mechanism as badges). No ASM
    needed to unlock any of these, just the right flag writes.

  **Community feedback (2026-08-16) on candidate town selection, worth
  weighing in on step 1 below**: Cinnabar Island has so few checks in its
  immediate area that the fill algorithm would be forced to place a
  progression item almost immediately -- poor pacing/feel, not a logic
  bug. Mt Silver risks the same issue *and* a real logic conflict on top
  of it: it's already gated behind `elite_four_defeated` in this
  project's own graph (see the Ho-Oh/Lugia entry above), so starting
  there directly would clash with that gate. Likely also applies to
  other side-content spawn points (Safari Zone Gate, Battle Frontier,
  Pokeathlon Dome) -- the curated candidate list (step 1) needs to
  actively exclude sparse-check and already-gated destinations, not just
  postgame-only ones like Indigo Plateau.

  **Remaining work to actually ship this (real, but no more unknown
  blockers)**:
  1. Extract the full `sSpawnMaps` table properly (script, not manual)
     and pick a curated "safe" candidate subset -- excluding sparse-check
     towns (e.g. Cinnabar Island) and anything already gated elsewhere in
     this project's own graph (Mt Silver, Indigo Plateau), per the
     community feedback above.
  2. Bake the chosen town's `sLocation_PlayerRoom` replacement into the
     generated patch (build-time ROM edit, already proven).
  3. Client-side, on first connection to a fresh save: set
     `FLAG_GOT_STARTER`/`FLAG_GOT_POKEDEX`/`FLAG_GOT_POKEGEAR`/
     `FLAG_GOT_BAG`/`FLAG_GOT_TRAINER_CARD`/`FLAG_GOT_SAVE_BUTTON`/
     `FLAG_GOT_OPTIONS_BUTTON`, and write an actual starter Pokemon into
     the (currently empty) Party struct (species from the existing
     `randomize_starters` pipeline) -- same class of write already used
     for DeathLink's HP-zeroing and badge grants.
  4. Rework the region graph to accept a variable starting region
     instead of the hardcoded New Bark root, so Archipelago's own fill
     algorithm naturally guarantees whatever items are needed to
     progress from the chosen town.
  5. Live-verify the whole chain end-to-end (position + flags + starter
     together) before shipping -- tonight's tests only verified position
     and confirmed the missing-menu-icons gap, not a full working seed.
  6. **National Dex is a separate, harder problem**, deliberately not
     solved above: no single flag grants it the way the others do --
     vanilla ties it to completing the regional dex count plus an Oak
     interaction, likely a mode bit inside the Pokedex struct itself
     rather than a `SaveVarsFlags` flag. Not investigated further; would
     need its own pass if a "start with National Dex" option is wanted.

  **Related, much smaller idea surfaced by this investigation (2026-08-16
  user request)**: since Bag/Pokedex/Pokegear are just flags like badges
  already are, they could each become their own real, independently
  toggleable AP item (`randomize_bag`/`randomize_pokedex`/
  `randomize_pokegear`/etc. options, on/off per item in the pool) --
  fully independent of the start-location project above, far simpler
  (no position patch, no region-graph rework, just a flag write per
  item, the same mechanism already proven for badges), and worth doing
  as its own smaller task regardless of whether start-location
  randomization ever ships. The Bicycle (`bicycle`, `data/items.py`
  id 450, already classified `progression`) is a related but different
  case -- not flag-gated at all, it's a plain key item, just currently
  granted by no location anywhere in this project's data (a real gap,
  simple `npc_gift`-shaped fix, confirmed non-logic-blocking since no
  `data_gen/rules.toml` exit rule depends on owning it).
- **Extra difficulty option: artificial route/passage blockers** (user
  request 2026-08-16). Idea: lock some routes/passages behind additional,
  non-vanilla requirements purely to raise randomizer difficulty (beyond
  the existing HM/badge/item gates already modeled in `data_gen/
  rules.toml`). Not investigated yet -- open questions before this can be
  scoped: which routes/passages, what the "key" requirement looks like
  (a new synthetic item? an existing item repurposed? a badge count
  threshold?), and whether it's expressed as a new exit_rule concept or a
  seed-time toggle over the existing rule set. No blocker identified yet
  (unlike the two entries above, this doesn't obviously need live/dynamic
  memory access) -- likely tractable as a pure `data_gen/rules.toml` +
  `rules.py` change, but needs its own design pass before implementation.

## Why this split

Everything in v1 has a direct, well-understood equivalent already shipped in
`platinum_archipelago` (read-only reference) and known decomp data sources.
Everything remaining in v2 needs a game system with no existing Archipelago
Gen4 precedent (Pokéwalker, Pokéathlon) or is a pure quality-of-life
addition that doesn't block a playable v1 (DeathLink, QoL options,
Nuzlocke mode, the "???" placeholder, badges) -- Trainersanity has since
been implemented (task M3.3, 2026-08-15), listed above. v3 is a single
item (non-US localization support) split out separately because it is
blocked on an external prerequisite (a real non-US ROM dump) rather than
on implementation effort or design decisions.
