# Scope — v1 vs v2

Decided after the M1 spikes (see `docs/architecture.md`, "## Spikes" for the
underlying data: 514 items, 142 encounter maps, 738 trainers in the decomp;
`ndspy` for NitroFS access; no globally-reserved ID range strictly required
by current Archipelago, item/location IDs only need to be unique within this
world).

## v1 (this project's initial release target)

- Wild encounters: grass / surf / fishing (old/good/super rod) / rock smash /
  headbutt, with HGSS's morning/day/night time-of-day tables.
- Starters.
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
- Victory condition (Elite Four / Red at Mt. Silver / N badges — exact
  condition TBD at implementation time, kept configurable via `options.py`).
- Trainersanity / Dexsanity as stretch goals *within* v1 if the budget
  allows once the core above is stable — not a hard requirement to ship v1.

## v2 (explicitly deferred, not started until v1 ships)

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
  v2 by default — see open question below — with the architecture left open
  to a second version via a version identifier, no abstraction built ahead
  of need).

## Why this split

Everything in v1 has a direct, well-understood equivalent already shipped in
`platinum_archipelago` (read-only reference) and known decomp data sources.
Everything in v2 either needs a game system with no existing Archipelago
Gen4 precedent (Pokéwalker, Pokéathlon), depends on a ROM we don't have yet
(SoulSilver), or is a pure quality-of-life addition that doesn't block a
playable v1 (DeathLink, level scaling).
