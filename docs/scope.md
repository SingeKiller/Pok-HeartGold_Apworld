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
    something.

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

## v2 (planning started 2026-08-11, execution order: Nuzlocke aids + QoL first)

A Planner pass (2026-08-11) re-evaluated this whole list against the real
code/decomp rather than assumption. One correction worth flagging: badges
turned out to be far more tractable than originally believed here (see
below) -- the "savedata flag bit, not a bag item" framing undersold how
close the existing flag-reading mechanism already gets.

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
  6-byte re-entry guard has a safe substitute. Not yet implemented.
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
  feedback (2026-08-11) after the v0.1.1 playtest. **Implemented, then
  reverted the same day (v2 Phase 1, 2026-08-11):** `options.py`'s
  `FastTextSpeed`/`SkipBattleAnimations` applied once per connection by
  `client.py` directly to the `Options` bitfield at the head of the
  `SAVE_PLAYERDATA` chunk. Live BizHawk testing showed neither option
  actually changed anything in-game, so both were pulled -- the in-word
  bitfield packing order the write relied on (assumed standard
  little-endian ARM, first-declared field in the low bits) had never been
  independently confirmed against a live session, and that assumption is
  the leading suspect. Revisit only with a real live-BizHawk verification
  step (dump the actual `Options` word, toggle the setting in-game, diff)
  before re-attempting either option.
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
  "empty item substitution" section) with something clearer, e.g. a
  reserved, renamed item slot showing "Item sent!" instead of a blank
  name -- community feedback (2026-08-11), confirmed feasible via the
  game's message-archive format (`msg_0222`, decoder documented in the
  decomp's own tooling), not yet implemented.
- **Trainersanity, made real** (moved here from its old "v1 stretch goal"
  slot above, 2026-08-11) -- confirmed feasible with zero ROM patch, see
  the note above. Not yet implemented.

## Why this split

Everything in v1 has a direct, well-understood equivalent already shipped in
`platinum_archipelago` (read-only reference) and known decomp data sources.
Everything remaining in v2 needs a game system with no existing Archipelago
Gen4 precedent (Pokéwalker, Pokéathlon) or is a pure quality-of-life
addition that doesn't block a playable v1 (DeathLink, QoL options,
Nuzlocke mode, the "???" placeholder, badges, Trainersanity).
