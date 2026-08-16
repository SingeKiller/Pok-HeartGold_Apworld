# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.2] - 2026-08-17

### Changed
- **`randomize_menu_unlocks` split into 7 independent toggles** (user
  request): `randomize_bag`, `randomize_trainer_card`, `randomize_pokedex`,
  `randomize_pokegear`, `randomize_save_button`, `randomize_options_button`,
  each pickable on its own instead of from one combined list.
- **Added `randomize_bicycle`**: the Bicycle can now also be turned into a
  real, shufflable AP item instead of always being handed over for free at
  Goldenrod's Bike Shop -- previously a documented gap, never tracked as a
  location at all.
- Rewrote every option added tonight to be shorter and more direct for
  players configuring their own YAML; regenerated the default template
  (`docs/Pokemon HGSS.yaml`) to match.

## [0.6.1] - 2026-08-17

### Fixed
Code review caught these before anything in 0.6.0 shipped -- see
`docs/scope.md`'s "Code review fixes" entry for the full writeup.
- `randomize_menu_unlocks` locations were self-checking: receiving the
  item auto-completed the player's own location for it, with no real
  in-game action, and a genuine vanilla trigger landing at the wrong
  moment could be lost permanently. Detection and gating are now handled
  atomically by the same function.
- `johto_only` combined with `sphere_based_trainer_leveling` crashed
  generation (`KeyError`) after a full multiworld fill.
- `randomize_learnsets`'s ROM write ran unconditionally for every player,
  not just those who enabled it -- now skipped whenever unchanged, and
  degrades gracefully instead of crashing on a future data mismatch.
  Also verified safe on a real SoulSilver ROM (previously unverified).
- A write-guard race in `_apply_start_location_flags` (start-location
  menu-unlock grant) could clobber a flag that changed mid-write.
- A latent crash in `set_rules` if a future exit rule ever targeted an
  edge `extra_route_blockers` removes.

## [0.6.0] - 2026-08-17

### Added
- **`randomize_start_location`'s region graph is now logic-integrated**,
  closing that option's own "known gap": the fill algorithm's own
  reachability now genuinely starts from the chosen `starting_town`
  instead of always assuming New Bark, regardless of this option. All 10
  candidate towns verified completable via real generation + fill.
- **`randomize_menu_unlocks`** option: turn any of Bag/Trainer Card/
  Pokedex/Pokegear/Save button/Options button into a real, shufflable AP
  item instead of always being unlocked for free. Combines cleanly with
  `randomize_start_location`. None selected by default (no effect).
- **`extra_route_blockers`** option: closes the Route 46 -> Route 45
  one-way ledge shortcut for extra difficulty (previously left in as
  vanilla behavior -- it lets a player reach 7 of Johto's 16 badges with
  effectively zero items). Off by default; verified safe in combination
  with every `randomize_start_location` starting town.
- **`randomize_learnsets`** option: randomizes which move each species
  learns at each level-up slot (the level itself stays vanilla). Purely
  cosmetic to this project's own logic -- no region-access rule depends
  on level-up movesets, only on owning HM items.

## [0.5.0] - 2026-08-17

### Added
- **`randomize_start_location`**: skip the New Bark Town origin story and
  spawn directly inside Elm's Lab instead. The real, vanilla 3-way starter
  choice still plays out exactly as normal (Elm's own lab script, not a
  hand-rolled substitute); a new `starting_town` option picks (or
  `random`-rolls) which of 10 towns the lab's exit door leads to instead of
  New Bark. Bag, Trainer Card, Save, Options, Pokédex and Pokégear access
  are all granted automatically once the starter is chosen, and the rival
  is pre-advanced past his first New Bark/Cherrygrove checkpoint so he
  doesn't wait forever for an encounter that will never happen. Off by
  default. Known gap: the region graph still treats New Bark as the fixed
  logical origin regardless of this option -- see `docs/scope.md`.

### Fixed
- **Randomized starters whose display label is a raw decomp identifier**
  (Nidoran-M/F, Mr. Mime, Ho-Oh, Mime Jr., Porygon-Z, and the Deoxys/
  Wormadam/Giratina/Shaymin/Rotom alternate forms) crashed the
  starter-selection text patch with a charmap error whenever
  `randomize_starters` happened to land on one of them. A pre-existing
  bug, never triggered before since no earlier seed had picked one of
  these species; fixed with a small display-name override table plus
  regression tests covering every affected species.

## [0.4.0] - 2026-08-17

### Added
- **`randomize_move_categories`**: shuffle each damaging move's Physical/
  Special category (a real, engine-honored per-move split in Generation
  IV). Status moves are never touched either direction.
- **`randomize_tm_moves`**: shuffle which move each TM (TM01-TM92)
  teaches. HM01-HM08 always keep their vanilla move -- this project's
  region-access rules key off owning the HM item, not whatever move it
  currently teaches.
- **`randomize_type_chart`**: shuffle the type-effectiveness chart's
  resistances/weaknesses/immunities across the vanilla exception table.
  Never touches the two engine-internal marker rows the Foresight/Odor
  Sleuth/Scrappy mechanic depends on.
- **`starting_money`**: set (or `random`-roll, 0-5000) how much money the
  player starts with. Applied once, client-side, guarded by a
  server-stored flag so a later reconnect never re-wipes money the
  player has since earned or spent.
- **`johto_only`**: exclude all of Kanto (180 regions) from the region
  graph -- no location is created there, Kanto's 8 badges are never
  added to the item pool, and `goal_badge_count` is silently capped at 8
  for the `n_badges` goal. Johto's own Elite Four and the post-game Red
  fight on Mount Silver are unaffected.

## [0.3.3] - 2026-08-16

### Added
- **`dexsanity_trigger`** option: choose whether Dexsanity checks fire on
  catching a species (`catch`, default, unchanged) or on merely
  encountering it (`encounter`, reads the Pokedex's `seenSpecies`
  bitfield instead of `caughtSpecies`).
- **`dexsanity_encounter_types`** option: restrict which encounter
  methods (land, surf, rock smash, old/good/super rod, headbutt) count
  toward Dexsanity at all. Defaults to every method (no behaviour
  change).

## [0.3.2] - 2026-08-17

### Fixed
- **Receiving a badge from another location before physically reaching
  that gym could permanently skip the fight.** Every gym Leader's own
  field script gates its battle behind "do you already have my badge",
  so setting the badge bit immediately on receipt (instead of on
  actually beating them) made the Leader think the fight had already
  happened. This silently broke more than the fight itself: Elm's Lab's
  egg-pickup phone call and two Trainersanity-eligible trainers near
  Violet City were also gated on that same battle actually happening.
  Fixed client-side -- the badge bit is now only written once the
  player has genuinely beaten that Leader, no ROM patch needed.

## [0.3.1] - 2026-08-16

### Added
- **Legendarysanity** option: turns catching Ho-Oh (Bell Tower) and Lugia
  (Whirl Islands) into real checks, alongside `trainersanity`/`dexsanity`.
  Off by default -- both stay exactly vanilla (same place, same
  post-Elite Four requirement) when off, matching how other Pokemon
  Archipelago worlds treat static legendary encounters.

## [0.3.0] - 2026-08-16

### Added
- **Real badge randomization.** Badges are now tradeable/shufflable AP
  items instead of a fixed logic milestone: each gym's vanilla `GiveBadge`
  call is neutralized so it can no longer double-grant a badge locally,
  and defeating a Leader is detected the same way any other trainer
  battle is.
- **Trainersanity, made real.** 390 real, fillable trainer-battle
  locations (one per person-event trainer across the game), off by
  default via the `trainersanity` option.
- **A 4th wild-encounter randomization mode**, `zone_method_mapping`:
  assigns one consistent replacement species per (zone, encounter
  method) group instead of randomizing every slot independently, so a
  route's grass encounters read as a single species again.
- **Ho-Oh and Lugia as real, checkable locations.** Both are only
  reachable after defeating the Elite Four/Champion, matching vanilla,
  and losing/fleeing the encounter never blocks anything -- the Pokemon
  simply reappears.
- **Quality-of-life options**: `fast_text_speed` and
  `skip_battle_animations`, applied once per connection and live-
  verified against a real BizHawk session. Both off by default.
- **Reusable TMs** option: a consumed TM reappears in the Bag on the
  client's next poll, no ROM patch needed.
- **DeathLink support.** One of your own Pokemon fainting sends a death;
  receiving one faints your whole party (zeroes current HP), matching a
  vanilla blackout.
- **Convert trade/friendship evolutions** option: rewrites any trade- or
  friendship-based evolution into a plain level-up evolution at a
  configurable level, a single-player accessibility fix.
- The garbled "???" placeholder name shown when picking up another
  player's item is now a real, readable message.

### Changed
- **Renamed the world from "Pokemon HeartGold" to "Pokemon HGSS"**
  (built file is now `pokemon_hgss.apworld`), reflecting that it has
  supported both HeartGold and SoulSilver ROMs since 0.1.1. The patch
  file extension (`.apheartgold`) and local settings key are
  deliberately unchanged for backward compatibility.
- The starter-choice screen now shows the actually-randomized species'
  name instead of always showing Chikorita/Cyndaquil/Totodile -- the
  species you received was always correct, only the on-screen text
  lagged behind.
- Randomized starters are now restricted to species with at least one
  evolution, matching vanilla (each of the three starters has two) --
  previously a randomized starter could land on an already fully-evolved
  species.

### Fixed
- **Region graph logic bugs** found via real tester spoiler-log feedback:
  two missing vanilla HM/item gates (a Surf gate, a Squirtbottle-gated
  Sudowoodo), and a one-way ledge (Route 46 into Route 45) that wrongly
  let players climb back up, both of which let some seeds reach their
  goal at sphere 0/1 with effectively no items owned.

### Planned for a future release
Not implemented yet -- see `docs/scope.md`'s "v3" section for the full
investigation notes on each:
- Trainer level matching (scale your Pokemon's level to a trainer's
  strongest, with a configurable offset) -- blocked on live battle-state
  detection, needs a real ARM code hook this project has no toolchain for.
- Randomized start location and starter kit -- blocked on live player-
  position manipulation, same class of blocker as above.
- Human-readable location display names in the client/spoiler log --
  deprioritized, and a real risk to item-substitution delivery was found
  that needs a dedicated audit pass first.
- An optional extra-difficulty mode that adds artificial route/passage
  blockers beyond the existing HM/badge/item gates -- not yet
  investigated, no blocker identified so far.

## [0.2.0] - 2026-08-12

### Added
- **Universal Tracker (`tracker.apworld`) support.** UT can now re-generate
  a HeartGold slot locally and track it, with no YAML needed from whoever
  is tracking (`ut_can_gen_without_yaml`): `fill_slot_data` publishes every
  world option under a new nested `options` key, and a UT re-run restores
  them before building the region graph. Seeds from 0.1.4 and earlier still
  track correctly -- their flat `goal`/`goal_badge_count` keys are the only
  slot data that affects logic, and are read as a fallback. A tracker re-run
  also skips the ROM-only species/move/trainer randomization, which has no
  bearing on logic.
- **v2 Phase 1: Nuzlocke aids.** `disable_ohko_moves` neutralizes
  Guillotine/Horn Drill/Fissure/Sheer Cold into ordinary 60 power / 100
  accuracy moves. `disable_trapping_abilities` removes Arena Trap, Shadow
  Tag, and Magnet Pull from every Pokémon that has one, replaced with a
  copy of the species' own other ability (or Run Away for mono-ability
  trappers like Wobbuffet). Both off by default, live-verified on real
  HeartGold and SoulSilver ROMs.

### Changed
- The ARM9 recompression step no longer hard-fails a patch if
  `apnds.lz.compress_code` can't shrink the post-secure-area data (rare):
  it now falls back to writing that region uncompressed and zeroing
  `SDK_COMPRESSED_STATIC_END`, matching the game's own boot-time no-op
  path for a zero value there (verified directly against the decomp's
  `crt0.s`, community-suggested).

### Removed
- **QoL options (`fast_text_speed`, `skip_battle_animations`), shipped
  and reverted the same day.** Live BizHawk testing showed neither option
  actually changed anything in-game. The in-word `Options` bitfield
  packing order the write relied on was never independently confirmed
  against a live session before shipping -- see `docs/scope.md` for the
  post-mortem. May return once someone can verify the real bit layout
  live.

## [0.1.4] - 2026-08-11

### Fixed
- **v0.1.3 broke every real install.** `compatible_version` was removed
  from `archipelago.json` to satisfy a manifest-compliance test, but
  nothing stamped it back into the packaged `.apworld` at build time --
  Archipelago's own manifest loader does a raw dict access on that field
  and fails to load the world at all without it (silently falling back to
  `world_version 0.0.0`). `build.py` now stamps `compatible_version` into
  the packaged manifest, matching what Archipelago's native build tool
  does, while the source `archipelago.json` still omits it correctly.
- The new patch-version check (also from v0.1.3) read its own
  `archipelago.json` with a plain filesystem path, which only works for a
  loose dev checkout -- every real `.apworld` is zip-loaded, so every real
  install hit `FileNotFoundError` on `generate_output`. Now reads it
  through the module's own loader instead, verified against an actual
  zipimport-loaded module this time, not just the dev test harness.

## [0.1.3] - 2026-08-11

### Added
- `start_inventory_from_pool` is now supported: items named there are
  removed from this world's item pool and backfilled with filler, so the
  pool still matches the unfilled-location count. Badges cannot be named
  (they are AP event items, not real bag items) and are rejected at YAML
  validation.
- New `game_version` option: declares whether the seed is intended for a
  HeartGold or SoulSilver ROM. Required now that wild-encounter data
  genuinely differs between the two versions (see below) -- the patcher
  refuses to apply a patch to a ROM that doesn't match the declared
  version, with an actionable error instead of silently writing wrong
  data.
- Patch files now record the APWorld version that generated them, and
  applying one with a different installed version raises an actionable
  error instead of a bare `KeyError` if the patch data format has changed
  in between -- community-suggested (2026-08-11), citing a real incident
  on another APWorld.

### Fixed
- `start_inventory` items are now actually delivered to the game. The
  client requested `items_handling = 0b011`, which leaves out the
  `remote_start_inventory` bit, so the server never sent them: the fill
  algorithm counted them as owned while the player never received them,
  which could produce unwinnable seeds when starting with a progression
  item (HMs, rods, Bicycle, S.S. Ticket, ...). Now `0b111`.
- Wild-encounter data was never actually version-aware despite SoulSilver
  support shipping in v0.1.1: 643 fields in the source encounter data (79
  more for headbutt trees) genuinely differ between HeartGold and
  SoulSilver, but only the HeartGold value was ever kept, and
  `randomize_wild_pokemon: vanilla` (the default) wrote it to the ROM
  unconditionally -- so a SoulSilver player with default options got
  their own SoulSilver encounters silently overwritten with HeartGold's
  data on every generation. A second, compounding bug found while fixing
  this: the ROM write path itself always targeted HeartGold's NitroFS
  encounter table regardless of which ROM was being patched, which would
  have made even correctly-resolved SoulSilver data invisible to a real
  SoulSilver cartridge's own game code. Both fixed and live-verified
  against real HeartGold and SoulSilver ROMs.

## [0.1.2] - 2026-08-11

### Fixed
- Generation no longer fails with `FillError: No more spots to place N
  items` when two or more slots share an item link with
  `link_replacement` enabled. The 30 undetectable npc_gift/hm_tm
  locations rejected item link group items, which are delivered to every
  group member and were never the stalled-remote case that restriction
  guards against. Reported and fixed by community contributor
  gerbiljames.

## [0.1.1] - 2026-08-11

### Added
- SoulSilver support: a US SoulSilver ROM is now accepted alongside
  HeartGold (dual-MD5 validation), same world, same options.
- Hidden items are randomized again, reconnected after root-causing and
  fixing the boot issue that previously disabled them (a stale ARM9
  decompression end-marker left over from any size-changing ROM edit --
  see `docs/architecture.md`). Live-confirmed on real HeartGold and
  SoulSilver ROMs via BizHawk (225 hidden_item substitutions each).
- New optional toggles: trainer level scaling (`trainer_level_scaling`),
  move type randomization (`randomize_move_types`), species type
  randomization (`randomize_species_types`).
- A ready-to-edit default YAML options file, `docs/Pokemon HeartGold.yaml`,
  for players who'd rather not generate their own via the Launcher.

### Changed
- Migrated the ROM read/write layer from `ndspy` (GPLv3) to `apnds`
  (MIT), vendored directly in this repository (`apnds/`). The
  `.apworld` now needs **no separate install step at all** -- the
  previous "manually copy ndspy into Archipelago's `lib/` folder"
  workaround is gone.

### Fixed
- Local ground_item/npc_gift/hm_tm/hidden_item locations whose item
  belongs to another player no longer hand over an unearned vanilla item
  when checked (write item id 0 instead, still fires check-detection).
- The 30 npc_gift/hm_tm locations with no detectable vanilla savedata
  flag are now constrained to only ever hold this player's own
  non-progression items, removing a multiworld-integrity risk.
- Fixed a duplicate ROM write in trainer party patching
  (`rom/trainerdata.py`).
- The BizHawk client no longer blindly trusts the first byte-signature
  match when locating Bag/save addresses in memory; it now verifies
  candidates look like real Bag data before trusting them, addressing a
  flakiness report from community testing.
- `client.py`'s `patch_suffix` is now set, so Archipelago's Launcher
  correctly recognizes `.apheartgold` files for "Open Patch".
- `minimum_ap_version` corrected to `0.6.7` (was accidentally set to the
  dev checkout's own version).
- `build.py`'s docstring no longer references unused `make`/`curl`
  tooling; documents Archipelago's native "Build APWorlds" tool as the
  recommended path for real releases.
- `build.py` now fails loudly if a `.apignore`-whitelisted directory
  (e.g. `data/`) is missing entirely at build time, instead of silently
  packaging an incomplete `.apworld`.

## [0.1.0] - 2026-08-11

### Added
- Archipelago world: items, locations, regions, and logic rules for
  Pokémon HeartGold (US).
- Randomization: wild encounters, trainer parties, evolutions
  (method-preserving), base stats (total-preserving), move stats
  (power/PP/accuracy, type-preserving), ground items, NPC gifts, HMs/TMs.
- Real ROM patch pipeline (`generate_output` / `.apheartgold`) producing
  a playable, patched `.nds` from a generated seed.
- BizHawk client (check detection, remote item delivery) via
  Archipelago's generic BizHawk connector.
- Configurable victory condition (Elite Four / Red / N badges).
- Build tooling (`data_gen.py`, `build.py`/`Makefile`) and a build-only
  GitHub Actions workflow.
- Setup guide and game info page for the Archipelago WebHost.

### Known limitations (see `docs/scope.md`)
- Starters are not randomized (no patchable source found in the ROM).
- Hidden items are not randomized (ROM substitution disabled pending an
  unresolved boot issue -- see `docs/architecture.md`).
- Gym badges are not randomized (HGSS represents them as a save-data
  flag, not a bag item).
- Trainersanity/Dexsanity are exposed as YAML options but currently do
  nothing -- no real Locations are created for them yet, so enabling
  them has no effect on generation or gameplay.
