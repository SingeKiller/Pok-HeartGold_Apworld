# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
