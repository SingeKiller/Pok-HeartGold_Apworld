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
  world (`game = "Pokemon HeartGold"`) accepts either a US HeartGold or a
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
  **Status (2026-08-11): budget didn't allow it.** Both are exposed as
  YAML options (`options.py`) but have no implementation behind them --
  `create_locations` never creates a trainer-battle or Pokédex-entry
  Location, so enabling either option currently has no effect on
  generation or gameplay (found via community feedback, confirmed by
  exhaustive code search -- see docs/architecture.md's "Community
  feedback round" section). Left in place as inert options for now
  (2026-08-11 decision: "continue tels quels") rather than removed from
  the option surface -- revisit either by actually implementing them or
  by hiding them if this proves confusing to players.

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

## v2 (explicitly deferred, not started until v1 ships)

- **Real badge randomization** (as a tradeable/shufflable item, not just a
  fixed logic milestone). HGSS models badges as a savedata flag bit, not a
  bag item (unlike `platinum_archipelago`'s reference world, where badges
  *can* be real pool items when its own `badges` option is enabled --
  `ressources/platinum_archipelago/locations.py`'s `create_locations`).
  Doing the same here needs a new client-side mechanism to remotely set an
  arbitrary savedata flag bit on receiving a badge item (`client.py`'s
  current remote-item injection only writes Bag items) -- real but
  non-trivial client work, not attempted for v1. For now (v1), each badge
  is still obtained from its normal vanilla gym in the normal order, only
  used as an internal logic milestone (see `locations.py`'s own module
  docstring) -- not randomized, not a real tradeable AP check.
- Pokéwalker.
- Pokéathlon.
- Bug Catching Contest / Safari Zone.
- Day care / egg hatching.
- Kurt's Apricorn balls.
- Radio Card / PokéGear features.
- DeathLink.

## Why this split

Everything in v1 has a direct, well-understood equivalent already shipped in
`platinum_archipelago` (read-only reference) and known decomp data sources.
Everything remaining in v2 needs a game system with no existing Archipelago
Gen4 precedent (Pokéwalker, Pokéathlon) or is a pure quality-of-life
addition that doesn't block a playable v1 (DeathLink).
