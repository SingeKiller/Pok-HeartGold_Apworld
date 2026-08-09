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
committed — cloned `--recursive`, built with CMake+Ninja+MinGW g++,
**statically linked** — `-static -static-libgcc -static-libstdc++` — so
the binary has no external MinGW/CRT DLL dependency and runs the same from
Bash, PowerShell, or Python `subprocess`; see task C14's "Blocker 2" for
why this mattered). The built binary is `ressources/armips/build/armips.exe`
(v0.11.0). Not on `PATH`; invoke by full path (M4's patch-build tooling
does this via the `ARMIPS_PATH` env var, following the same convention as
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

## C14 — Ground item check mechanism (proof of concept)

Task C14 set out to prove the hardest remaining piece of the whole project:
turning a vanilla ground-item pickup ("item ball") into a real Archipelago
check, without corrupting the save. This section documents what was found,
what was built, and — importantly — two blockers that stopped the "real"
in-game hook from being wired up in this session. Per this project's own
risk policy ("prudence over progress" for ROM-patching work), neither
blocker was forced past with a guessed/fragile fix.

### How a vanilla item ball actually works (decomp investigation)

- Every item ball placed on a map is an object event with
  `scriptId: "std_itemball_<name>"` and `eventFlag: "FLAG_HIDE_ITEMBALL_<name>"`
  (see `ressources/Decomposition/pokeheartgold/files/fielddata/eventdata/zone_event/*.json`,
  e.g. `007_R02.json`'s `obj_R02_monstarball`). `std_itemball_*` constants
  are a contiguous block `_std_item_ball = 7000` .. `7254` (plus a
  `std_itemball_variadic = 7255` catch-all), immediately followed by
  `_std_hidden_item = 8000` — i.e. **the full "currently running an item
  ball script" range is `[7000, 8000)`**
  (`include/constants/std_script.h`).
- `src/script_manager.c`'s `sScriptBankMapping` routes every script id in
  that range to the **same** compiled bytecode bank,
  `scr_seq/scr_seq_0141.bin` (`{ _std_item_ball, NARC_scr_seq_scr_seq_0141_bin, NARC_msg_msg_0199_bin }`).
  That NARC's source (`files/fielddata/script/scr_seq/scr_seq_0141.s`) has
  255 tiny per-itemball blocks (`scr_seq_0141_000` .. `_254`) that each just
  do `SetVar VAR_SPECIAL_x8008, <item id>` / `SetVar VAR_SPECIAL_x8009, <quantity>`
  then jump to **one shared tail**, `scr_seq_0141_255`. That tail is the
  real logic: it checks bag space, then calls the `GiveItem` bytecode
  command (`GiveItem VAR_SPECIAL_x8004, VAR_SPECIAL_x8005, VAR_SPECIAL_RESULT`)
  to actually add the item, and only *afterwards* runs `HidePerson` /
  message text.
- `GiveItem` (the bytecode command) is implemented natively by
  `ScrCmd_GiveItem` (`src/scrcmd_items.c`):
  ```c
  BOOL ScrCmd_GiveItem(ScriptContext *ctx) {
      FieldSystem *sav_ptr = ctx->fieldSystem;
      u16 item_id = ScriptGetVar(ctx);
      u16 quantity = ScriptGetVar(ctx);
      u16 *ret_ptr = ScriptGetVarPointer(ctx);
      Bag *bag = Save_Bag_Get(sav_ptr->saveData);
      *ret_ptr = Bag_AddItem(bag, item_id, quantity, HEAP_ID_FIELD1);
      return FALSE;
  }
  ```
  This is dispatched through a flat native-function-pointer table,
  `const ScrCmdFunc gScriptCmdTable[]` (`src/data/fieldmap/script_cmd_table.h`,
  853 entries total). `ScrCmd_GiveItem` is entry **index 125** (opcode
  `0x7D`), counted directly from that header (`ScrCmd_Nop` = index 0).
  **This is the ideal hook point**: intercepting `ScrCmd_GiveItem` (gated
  on the caller's active script id being in `[7000, 8000)`, using the
  `ScriptEnvironment.activeScriptNumber` field set by
  `SetupScriptEngine`) would catch every ground-item pickup uniformly,
  with no per-script-instance patching needed.
- **Check *detection* turns out to need no ROM patch at all.** Every
  itemball object's `eventFlag` (`FLAG_HIDE_ITEMBALL_*`, ordinary savedata
  flags starting at `0x420`, see `include/constants/flags.h`) is what makes
  the item ball disappear forever once picked up — and that flag is set by
  generic, already-vanilla engine code, not anything itemball-specific:
  `MapObject_Delete()` in `src/map_object.c`:
  ```c
  void MapObject_Delete(LocalMapObject *object) {
      u32 eventFlag = MapObject_GetEventFlag(object);
      FieldSystem *fieldSystem = MapObject_GetFieldSystem(object);
      FieldSystem_FlagSet(fieldSystem, eventFlag);
      MapObject_Remove(object);
  }
  ```
  So a client can detect "this ground item was picked up" purely by
  reading the existing flag bit from savedata — the same technique
  `ressources/platinum_archipelago/client.py` already uses for its own
  location checks (`VarsFlags.get_flag`/`FlagCheck`), just with HeartGold's
  own flag ids. Flags live in `SaveVarsFlags` (`include/save_vars_flags.h`):
  `struct SaveVarsFlags { u16 vars[NUM_VARS]; u8 flags[NUM_FLAGS / 8]; }`
  (`NUM_VARS = 0x170`, `NUM_FLAGS = 2912`), i.e. `flags[flagId / 8] & (1 << (flagId & 7))`.
  This project has not yet located `SaveVarsFlags`'s byte offset inside the
  *whole* HGSS save block (that's `client.py` work, out of scope for C14) —
  only its own internal layout, which is enough to design the protocol
  below.

### Chosen protocol (design)

Given the above, the protocol for a future working client is:

- **Check detection**: read the existing `FLAG_HIDE_ITEMBALL_<location>`
  bit directly from savedata (no ROM patch required — this is genuinely
  vanilla behavior, see `MapObject_Delete` above).
- **Item substitution for local items**: patch the item ball's own script
  bytecode operand (`SetVar VAR_SPECIAL_x8008, <item id>` inside
  `scr_seq_0141.bin`, one `SetVar` per itemball index) to the item id
  Archipelago generation decided for that location. This is a plain NARC
  data edit through the existing `rom/` NitroFS layer (C13) — no ARM code
  needed, no unknown addresses, same risk profile as `rom/itemdata.py`
  etc. **Not implemented in C14** (out of scope: C14 is the check
  *mechanism* PoC, not the full data-patching pass — this is recorded here
  so the next task doesn't have to re-derive it).
- **A small RAM protocol struct**, for the day a real ARM hook can be
  wired up (below), so a BizHawk client can read "a ground-item check was
  just triggered" and, for remote items, suppress the vanilla grant:

  ```
  offset  size  field
  0x00    4     magic             ASCII "HGAP" (0x50414748 little-endian)
  0x04    2     version           protocol version, currently 1
  0x06    2     reserved0         always 0
  0x08    4     last_check_sent   AP location id of the most recent
                                   ground-item check triggered (0 = none)
  0x0C    4     check_sent_seq    incremented every write to
                                   last_check_sent, so a client can tell a
                                   new event apart from re-reading the same one
  0x10    2     local_item_id     native HG/SS item id to actually grant
                                   for the pending pickup if local; 0 if not
                                   applicable / remote
  0x12    2     is_remote         1 if the pending pickup belongs to
                                   another player's world, 0 otherwise
  ```
  Total size: `0x14` (20) bytes. Fixed location: `0x023FF800`, chosen by
  the same convention `ressources/platinum_archipelago/client.py` uses for
  its own `AP_STRUCT_PTR_ADDRESS` (near the very top of the DS's 4 MiB
  EWRAM region, `0x02000000`-`0x023FFFFF`) — **this is a conventional
  choice, not something this task exhaustively proved unused for HGSS
  specifically**; confirming there's no visible corruption/crash from
  using it is part of the manual in-game (BizHawk) validation the project
  owner will do separately (see "What remains to be validated manually"
  below).

### Blocker 1: no ROM address for the real hook point

Wiring `ScrCmd_GiveItem`/`gScriptCmdTable` up as a real hook needs to know
where they live in the actual retail ROM. Two avenues were tried:

1. **A decomp-provided symbol/address table.** None exists. This decomp
   only ships *source* (`.c`/`.s`/data headers); real addresses are only
   assigned by actually linking a byte-identical build, which needs the
   proprietary MWCC 2.0/sp2p2 compiler + Nitro SDK 4.2 — both unavailable
   on this machine (see "## ROM code injection strategy" above; this is
   the same constraint that already ruled out the "full decomp rebuild"
   option). `asm/*.s` files *do* embed real addresses in their filenames,
   but only for functions that are still **raw, un-decompiled** assembly —
   `ScrCmd_GiveItem` already has matched C source
   (`src/scrcmd_items.c`), so (if genuinely matched) it has no such file
   left to read an address from. `gScriptCmdTable` itself references many
   still-unnamed placeholder entries (`ScrCmd_048`, `ScrCmd_102`, …),
   meaning the *table as a whole* is very unlikely to be a byte-matched,
   buildable unit yet either — so even a from-scratch attempt at building
   just this one file would not reliably reproduce the retail table's
   layout.
2. **An automated signature scan of the real, retail ROM.** Using `ndspy`
   to load the actual `Pokemon - HeartGold Version (USA).nds` (never
   modified, only read) and its ARM9 binary plus all 129 ARM9 overlays, a
   Python script (see this task's own working notes; not committed —
   one-off investigation, not project tooling) searched for a contiguous
   run of `gScriptCmdTable`'s expected size (853 4-byte pointers, all
   resolving into the same code region) anywhere in ARM9 or any overlay.
   `capstone` (a disassembler) was installed **only for this
   investigation** — it is *not* added to `requirements.txt`/
   `requirements-dev.txt`, since it isn't needed at runtime by anything
   committed. The best candidate found was a run of 301 pointers (in the
   overlay sharing base address `0x021E5900` with the field-system
   overlay), nowhere near the expected 853 — ruling out a cheap, reliable
   recovery of the address this way. Reliably finding it would need a
   proper interactive disassembler with cross-reference analysis (e.g.
   Ghidra/IDA with an NDS/ARM9 loader) to trace callers/callees, which is
   out of scope for this session.

A third option — hooking the ARM9 **entry point** instead, which *is*
always known with certainty (it's a plain ROM header field,
`arm9EntryAddress`, read directly, no decomp guessing involved) — was
considered and rejected: the entry point (`0x02000800`) sits well inside
the Nintendo DS "secure area" (the first `0x4000` bytes of the ARM9
binary), which the retail cartridge/BIOS validates against a CRC stored in
the ROM header (`secureAreaChecksum`). `ndspy` reads that checksum but
**does not recompute it on save** — confirmed by reading its own source
(`ndspy/rom.py`, the field is round-tripped with a literal
`# TODO: Actually recalculate` comment). Patching bytes inside the secure
area with this tooling would therefore leave a stale, incorrect checksum
in the saved ROM: a real risk of the ROM failing to boot on strict
emulators or real hardware. This was declined rather than forced.

### Blocker 2: `armips` itself does not currently run — RESOLVED

Separately from the address question: `ressources/armips/build/armips.exe`
(the local build recorded for M4, see "## ROM code injection strategy")
was initially found to **fail to start** in this project's own dev
environment, with Windows error `0xC0000135` / `STATUS_DLL_NOT_FOUND`, in
a Bash-tool subprocess context specifically (invoking it via a native
PowerShell session worked fine — the two contexts resolve the MinGW
runtime DLL dependency chain differently). **Fixed** by rebuilding
statically (`-DCMAKE_EXE_LINKER_FLAGS="-static -static-libgcc
-static-libstdc++"`): the resulting `armips.exe` has no external MinGW/CRT
DLL dependency (`ldd` shows only core Windows system DLLs), runs
identically from Bash, PowerShell, or Python `subprocess.run`.

A second, independent bug surfaced once `armips` could actually run:
`patches/ground_item_hook.s` was missing the top-level `.nds` architecture
directive (armips needs it before anything else in the file to know which
instruction set/directives to enable), and had `.arm` positioned *before*
`.create` instead of after — confirmed against `ressources/armips/Tests/
ARM/*/*.asm`'s own examples, all of which follow `.nds`/`.gba` →
`.create` → `.arm`/`.thumb`. Fixed; `tests/test_patch_gen.py` now passes
for real (7/7, not skipped) with `ARMIPS_PATH` pointed at the rebuilt
binary.

### What C14 actually delivers, given both blockers

- `patches/ground_item_hook.s` — a real, self-contained armips source
  implementing the protocol struct's `HeartGoldAP_Init` and
  `HeartGoldAP_RecordGroundItemCheck` functions (ARM mode). **Not called
  from anywhere** — there is no known-safe call site to hook yet (Blocker
  1). It exists to prove the rest of the pipeline.
- `rom/__init__.py` gained narrow, **append-only** ARM9 access
  (`HeartGoldRom.arm9`, `.arm9_ram_address`, `.arm9_entry_address`,
  `.append_to_arm9()`). Append-only is a deliberate safety constraint: it
  never touches the first `0x4000` (secure-area) bytes, so it can't
  invalidate `secureAreaChecksum` the way entry-point hooking would have
  (see Blocker 1's rejected third option).
- `patch_gen.py` assembles `patches/ground_item_hook.s` with `armips`
  (`ARMIPS_PATH` env var, same convention as `ARCHIPELAGO_PATH`/
  `HEARTGOLD_ROM_PATH`) and appends the result to a ROM copy's ARM9
  binary via the above.
- `tests/test_patch_gen.py` covers: the patch assembles without error;
  the assembled code contains the expected protocol magic constant
  (cheap, address-independent sanity check); applying it to a real ROM
  copy doesn't raise, leaves the ROM re-openable (`HeartGoldRom`'s own
  header/game-code validation), grows ARM9 by exactly the assembled code's
  size, leaves unrelated NitroFS content byte-identical, and the appended
  bytes at the reported address match what was assembled (the task's own
  suggested fallback: verify the protocol lands "at the expected location"
  by inspecting the patched binary, since real in-game/BizHawk testing
  isn't available to this agent). **All 7 tests now pass for real**
  (Blocker 2 resolved, see above) with `ARMIPS_PATH` pointed at the
  rebuilt static `armips.exe`.

### What remains to be validated manually / next steps

- Determine `gScriptCmdTable`'s real ROM address, either by a genuine
  match-build of enough of the field-script engine (needs the proprietary
  MWCC toolchain) or by proper disassembler-assisted reverse engineering
  (Ghidra/IDA), then wire `ScrCmd_GiveItem`'s table entry (index 125) to
  jump into `HeartGoldAP_RecordGroundItemCheck` (gated on
  `ScriptEnvironment.activeScriptNumber` being in `[7000, 8000)`, per the
  investigation above) before falling through to the original behavior.
- Confirm the `0x023FF800` EWRAM scratch address is genuinely unused by
  the real game at runtime (no visual glitches, no crashes) — this needs
  actual BizHawk play-testing, out of reach for this agent.
- Implement and test the local-item substitution data patch
  (`SetVar VAR_SPECIAL_x8008, <item id>` inside `scr_seq_0141.bin`) as a
  `rom/eventscriptdata.py`-style module, following `rom/itemdata.py`'s
  pattern.
