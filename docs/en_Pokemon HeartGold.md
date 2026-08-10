# Pokémon HeartGold

## What Gets Randomized

- Wild encounters (grass, surf, fishing, rock smash, headbutt -- with
  HGSS's morning/day/night tables preserved).
- Trainer parties, including the Elite Four and Red.
- Evolutions -- the *method* a species evolves by (level, stone, trade,
  friendship, ...) is preserved; only the *target* species is randomized,
  so a Pokémon that used to evolve by leveling up still evolves by
  leveling up, into something else.
- Base stats -- each species keeps its own total stat budget, only
  redistributed across HP/Attack/Defense/Sp. Attack/Sp. Defense/Speed.
- Move stats -- Power, PP, and Accuracy, with Type always preserved.
- Ground items, NPC gifts, HMs/TMs, and badge-gated key items.
- Apricorns & Berries.
- Victory condition (Elite Four, Red at Mt. Silver, or a configurable
  number of badges -- your choice, see the YAML options).

## Notable Differences from Base Game

- **Starters are not randomized.** Extensive investigation could not
  locate a patchable source for the vanilla starter species in the ROM --
  see the project's `docs/architecture.md` for the full write-up. You'll
  always be offered the vanilla Chikorita/Cyndaquil/Totodile choice.
- **Hidden items are not randomized.** They stay at their vanilla item and
  are not part of the check pool this release. Picking them up has no
  effect on your Archipelago game.
- **Gym badges are not randomized.** HGSS represents badges as a
  save-data flag rather than a bag item, so (unlike some other Pokémon
  worlds) they can't currently be shuffled into the general item pool --
  each badge is still earned from its usual gym, in the usual order, and
  only tracked internally for logic purposes (e.g. gating which HMs you
  can use in the field).
- Trainersanity (a check for every trainer battle won) and Dexsanity (a
  check for registering each species as seen/caught) are available as
  optional, off-by-default toggles.
