# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

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
