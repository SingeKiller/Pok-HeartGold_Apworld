# Architecture

## Why a flat layout

Archipelago loads a world as a Python package under `worlds/<game_name>/` in
the Archipelago repository (or as a built `.apworld` zip with the same
internal layout). The package root **is** the world — there is no nested
`/backend` subfolder in the loaded package. This is a hard technical
constraint, not a style choice, so the repository root doubles as the
Archipelago package root.

## Layout

```
/                       Archipelago package root (the "backend" data/world)
  __init__.py           World class, registers the game with Archipelago
  items.py               Item definitions and id map
  locations.py            Location definitions and id map
  regions.py              Region graph construction
  rules.py                 Access/logic rules
  options.py               Player-facing yaml options
  species.py                Pokémon species data + in-generation randomization
  client.py                  BizHawk client (in-game connector)

  data_gen/                Source data (toml/json) hand-authored or extracted
                            from the reference ROM/decomp
  data_gen_templates/       Python templates that turn data_gen/ sources into
                            the generated data/ package
  data_gen.py                Entry point: regenerates data/ from data_gen/ +
                              data_gen_templates/
  data_gen_rules.py           Logic-rule generation helpers
  data/                        Generated at dev time by data_gen.py — NOT
                                committed (gitignored), rebuilt from source

  patch_gen.py               Builds the distributable ROM patch
  patches/                    Committed base patch (e.g. bsdiff4) applied to
                               a user-supplied vanilla ROM
  rom/                         ROM read/write access layer (NitroFS, ARM hook
                                injection via armips — see decision below)

  docs/                        Player-facing docs (setup guide, game page)
  tests/                       Unit tests
  ressources/                  Reference-only, git-ignored: pret/pokeheartgold
                                decomp and ljtpetersen/platinum_archipelago
```

## Correspondence with the original CLAUDE.md structure

The original `CLAUDE.md` described a nested structure (`/backend`,
`/database`, `/patch`, `/Roam`) that predates the discovery that Archipelago
requires a flat package root. That intent maps onto the actual layout as
follows:

| Original CLAUDE.md | Actual location |
|---|---|
| `/backend` (Archipelago World Data) | repository root (`items.py`, `locations.py`, `regions.py`, `rules.py`, `options.py`, `species.py`, `__init__.py`, `client.py`) |
| `/database` (data_gen / data_gen_template) | `data_gen/`, `data_gen_templates/`, `data_gen.py`, `data_gen_rules.py` |
| `/patch` (patches) | `patches/`, `patch_gen.py` |
| `/Roam` (rom) | `rom/` |
| `/docs` | `docs/` (unchanged) |

## ROM code injection strategy (decided)

Three options were evaluated:

1. **Full decomp rebuild** (as `platinum_archipelago` does) — requires the
   proprietary MWCC 2.0/sp2p2 compiler and Nitro SDK 4.2, not available on
   this machine. **Rejected** for now.
2. **ARM hooks via `armips`** — the `pret/pokeheartgold` decomp is used only
   as a map of symbols/addresses; targeted assembly patches are injected
   without rebuilding the whole ROM. No proprietary toolchain required.
   **Chosen.**
3. **Client-only (RAM-only)** — no ROM code changes, client reads/writes game
   RAM directly. Lowest cost but no in-game item-received feedback. Kept as
   a fallback if option 2 proves infeasible for a given feature.

`armips` (Kingcom/armips, MIT) is built from source at
`ressources/armips` (git-ignored, read-only external checkout, never
committed — cloned `--recursive`, built with CMake+Ninja+MinGW g++). The
built binary is `ressources/armips/build/armips.exe` (v0.11.0). Not on
`PATH`; invoke by full path (M4's patch-build tooling should do the same,
or accept an `ARMIPS_PATH` env var following the same convention as
`ARCHIPELAGO_PATH`/`HEARTGOLD_ROM_PATH`).

## Reference projects (read-only, never committed)

- `ressources/Decomposition/pokeheartgold` — `pret/pokeheartgold` decomp.
  Source of ROM memory addresses, symbols and data structures.
- `ressources/platinum_archipelago` — `ljtpetersen/platinum_archipelago`
  (MIT). Architectural reference for how an Archipelago Gen4 Pokémon world is
  structured; not copied directly.

## Spikes

Three research/PoC spikes run against the real HeartGold (US) ROM and the
decomp, to de-risk the architecture above before committing to it further.

### Spike 1 — Reading/writing NitroFS

**Library chosen: [`ndspy`](https://pypi.org/project/ndspy/) (pip, MIT).**
`apnds` was ruled out per the task brief (it's a precompiled binary tool
built for `platinum_archipelago`'s own ARM hack, not a reusable library —
confirmed by inspecting `ressources/platinum_archipelago/rom/__init__.py`,
which imports `..apnds.rom.Rom` from a module that isn't vendored in that
reference repo at all, i.e. it's an external, project-specific dependency).
Writing an equivalent "from scratch" NitroFS reader/writer (FNT/FAT parsing,
ARM9 secure-area handling, alignment rules) would be reinventing a
well-tested wheel for no benefit here.

PoC findings (against the real 128 MiB HeartGold (US) ROM, MD5
`258cea3a62ac0d6eb04b5a0fd764d788`):

- `ndspy.rom.NintendoDSRom(bytes)` loads the ROM and exposes files both by
  numeric ID and by path (`rom.getFileByName("pbr/item_data.narc")`,
  `rom.setFileByName(...)`). Load time ~0.1s.
- **`rom.save()` does *not* produce a byte-identical ROM, even with zero
  file content changes.** It fully repacks the container: file table,
  offsets and padding are all regenerated from scratch. In the PoC,
  re-saving with no changes produced a **126,645,960-byte** output from a
  **134,217,728-byte** input (the original retail ROM is padded out to a
  power-of-two cartridge size; `ndspy` doesn't reproduce that trailing pad),
  and the two byte streams already diverge inside the header, at offset
  `0x80` (icon/banner offset field — expected, since layout changed).
  **This is expected `ndspy` behavior, not corruption**: individually
  re-extracting the same file (`pbr/item_data.narc`) from the rebuilt ROM
  and comparing it to the original bytes gives an exact match (see
  `tests/test_rom_roundtrip.py`, which asserts this file-level property
  rather than a literal whole-ROM MD5 match, since the latter is not an
  achievable/meaningful property with a repacking tool).
- Practical consequence for the ARM-hooks patching strategy above: our
  distributable patch will always produce a *new* `.nds` that is a
  different size than the vanilla ROM, even for otherwise-unmodified files.
  This needs to be tolerated by BizHawk/flashcart tooling downstream (out of
  scope for this spike; flagged as a follow-up risk).

`ndspy` is now declared in `requirements.txt` (new file — runtime
dependency of the world itself, distinct from `requirements-dev.txt`).
`tests/test_rom_roundtrip.py` covers this: it reads the ROM path from the
`HEARTGOLD_ROM_PATH` environment variable and skips cleanly if unset/absent,
so CI (which has no ROM) is unaffected.

### Spike 3 — Fiabilité des données du decomp

Cross-checked three axes between `ressources/Decomposition/pokeheartgold`
and public/known facts about HeartGold (US):

1. **Items.** `files/itemtool/itemdata/item_data.csv` has **514 rows**
   (513 real items + the `ITEM_NONE` placeholder row) — not the ~236
   figure floated as an assumption to verify; that assumption was wrong.
   Cross-checked against `include/constants/items.h`: item constants span
   IDs 0 (`ITEM_NONE`) to 536 (`ITEM_ENIGMA_STONE`), i.e. 537 possible ID
   slots, of which 22 (IDs 113–134) are explicit `ITEM_UNUSED_*` reserved
   placeholders (a well-documented Gen III→IV artifact: contest/frontier
   items dropped between Emerald and Diamond/Pearl) and thus correctly
   excluded from the CSV. 537 − 22 = 515 real named constants, but the CSV
   only has 514 rows: **`ITEM_EXPLORER_KIT` has a constant (ID present in
   the header) but no corresponding stats row in `item_data.csv`** — a
   genuine, minor gap in the decomp's data export. Max item ID 536 matches
   what's publicly documented for the Gen IV/HGSS item index range.
2. **Encounter tables.** `files/fielddata/encountdata/gs_enc_data.json`
   (not `encountdata/*` split into per-zone files, as the task brief
   assumed — it's a single JSON with a top-level `"encounters"` array) has
   **142 map entries**, each with `land`/`surf`/`rock_smash`/`fishing`
   (old/good/super rod) tables plus Hoenn/Sinnoh sound and swarm/fishing
   special-encounter fields. 142 is plausible for HGSS: it counts every
   distinct map with a wild encounter table (routes, cave floors, city
   outskirts, etc.), not just named routes, and HGSS has well over 100 such
   maps once caves/interiors are counted separately from their entrances.
3. **Trainers.** `files/poketool/trainer/trainers.json` has a top-level
   `"trainers"` array of **738 entries**, each with class, type, AI flags,
   items, party and battle messages (spot-checked entries include Silver's
   rival battles with real, level-appropriate parties/movesets). 738 is in
   the range independently reported for HGSS's total trainer roster
   (routinely cited as ~738–750 depending on whether rematch-only or
   facility-only entries are counted).

**Conclusion: the decomp is reliable enough to be the primary source of
truth for `data_gen`,** but not blindly 100% trustworthy — axis 1 already
surfaced one real gap (`ITEM_EXPLORER_KIT` missing its stats row) after
spending very little time cross-checking. `data_gen.py` extraction code
should defensively handle constants with no matching data row (skip with a
warning, or fall back to a default) rather than assuming every declared
constant has full data, and any generated `data/items.py`-equivalent table
should be diffed against `include/constants/*.h` counts as a sanity check
(see `pokemon_platinum`'s own `sanity_check.py`-style pattern for
precedent). Direct binary ROM extraction was not attempted as an
alternative in this spike; given the decomp's data matches known public
figures on 3 independent axes with only one small discrepancy, it is not
currently worth the extra effort compared to using the decomp directly.

### Spike 4 — Réservation d'ID Archipelago

Looked at `pokemon_platinum`, `pokemon_emerald` and `pokemon_rb` in the
local Archipelago clone (`E:\Users\Olivier\Desktop\projet\archipelago`,
read-only reference) for how they reserve item/location ID ranges:

- `pokemon_emerald`: `BASE_OFFSET = 3860000` (`data.py`), added to small
  internal item/flag values for both items and locations.
- `pokemon_rb`: items use `item_id + 172000000` (`items.py`).
- `pokemon_platinum`: **no offset at all** — `get_raw_id()` returns raw
  in-game values (`item_class << 12 | item_id`, topping out well under
  65536). This looked like an anomaly worth explaining, and the current
  Archipelago `docs/world api.md` (in the same local clone) explains it:
  *"Locations and items can share IDs, and locations can share IDs with
  other games' locations."* / *"Items and locations can share IDs, and
  items can share IDs with other games' items."* (lines 226 and 251).
  IDs only need to be unique **within** a single world's own item/location
  namespace — the historical assumption that every game must reserve a
  disjoint global ID range no longer holds for current Archipelago (items
  and locations are namespaced per-game internally). `pokemon_platinum`
  is written against this current rule; `pokemon_emerald`/`pokemon_rb`
  simply predate it (or keep the defensive convention anyway).

Even though a disjoint range is not strictly required anymore, this project
follows the defensive convention used by the majority of currently
maintained worlds (`pokemon_emerald`, `pokemon_rb`, `tunic`, `dark_souls_3`,
etc.) — it costs nothing, aids debugging/log-reading, and future-proofs
against any tooling that still assumes global uniqueness. Scanning every
`base_id`/`BASE_OFFSET`-style constant across `worlds/` in the local clone,
the reserved values found range from `1000` up to `2000300204` (`ahit`),
with a clear, wide unused gap between `66600000` (`shapez`, rounded down)
and `509342400` (`tunic`). Both stay well within the documented "recommended"
32-bit-safe range (1 to 2³¹−1 = 2147483647).

**Proposed ranges for `pokemon_heartgold`** (in that gap, non-overlapping,
each with 1,000,000 IDs of headroom — the decomp data above suggests we
need on the order of ~500 items and a few hundred to low thousands of
locations, so this is generous):

```python
HEARTGOLD_ITEM_ID_BASE = 200_000_000       # items.py: item_name_to_id
HEARTGOLD_LOCATION_ID_BASE = 201_000_000   # locations.py: location_name_to_id
```

These do not collide with any `base_id`/offset found in the local
Archipelago clone's `worlds/` directory. Before this world is submitted
upstream, this range should still be double-checked against the live,
canonical Archipelago world registry (Discord/GitHub), since only the local
clone's current snapshot was checked here.
