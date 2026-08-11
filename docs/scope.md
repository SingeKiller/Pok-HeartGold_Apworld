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
- Level scaling.
- SoulSilver support (a legally-dumped US SoulSilver ROM is now available
  locally as of 2026-08-08, so the earlier blocker is gone; still kept in
  v2 by default - see open question below - with the architecture left open
  to a second version via a version identifier, no abstraction built ahead
  of need).

## Why this split

Everything in v1 has a direct, well-understood equivalent already shipped in
`platinum_archipelago` (read-only reference) and known decomp data sources.
Everything in v2 either needs a game system with no existing Archipelago
Gen4 precedent (Pokéwalker, Pokéathlon), depends on a ROM we don't have yet
(SoulSilver), or is a pure quality-of-life addition that doesn't block a
playable v1 (DeathLink, level scaling).
