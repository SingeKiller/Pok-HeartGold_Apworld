# Architecture

## Why a flat layout

Archipelago loads a world as a Python package under `worlds/<game_name>/` in
the Archipelago repository (or as a built `.apworld` zip with the same
internal layout). The package root **is** the world - there is no nested
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
  data/                        Generated at dev time by data_gen.py - NOT
                                committed (gitignored), rebuilt from source

  patch_gen.py               Builds the distributable ROM patch
  patches/                    Committed base patch (e.g. bsdiff4) applied to
                               a user-supplied vanilla ROM
  rom/                         ROM read/write access layer (NitroFS, ARM hook
                                injection via armips - see decision below)

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

## ROM code injection strategy (revised after C14)

Three options were evaluated:

1. **Full decomp rebuild** (as `platinum_archipelago` does) - requires the
   proprietary MWCC 2.0/sp2p2 compiler and Nitro SDK 4.2, not available on
   this machine. **Rejected**.
2. **ARM hooks via `armips`** - the `pret/pokeheartgold` decomp is used only
   as a map of symbols/addresses; targeted assembly patches are injected
   without rebuilding the whole ROM. No proprietary toolchain required.
   **Originally chosen; set aside for v1 after C14** - the `armips`+`patch_gen.py`
   pipeline itself works (proven end-to-end against the real ROM, see task
   C14), but the one real hook point identified (`ScrCmd_GiveItem` via
   `gScriptCmdTable`) has no known ROM address, and neither a decomp build
   nor an automated signature scan could recover it (see C14's "Blocker
   1"; would need a proper disassembler with cross-reference analysis,
   e.g. Ghidra/IDA, not available in this session). Revisit if that
   tooling becomes available.
3. **Client-only (RAM-only)** - no ROM code changes for the check/receive
   mechanism itself; the BizHawk client reads/writes game RAM and savedata
   directly. **Chosen for v1.** Concretely, per C14's own investigation:
   - **Check detection**: read the existing `FLAG_HIDE_ITEMBALL_*` (etc.)
     savedata bits directly - genuinely vanilla behavior
     (`MapObject_Delete`, see C14), no ROM patch needed at all.
   - **Local items** (an AP location whose generation-decided item belongs
     to this same player/world): still patched directly into the ROM's
     data via `rom/` (C13) - rewriting an item ball's script bytecode
     item-id operand is a plain NitroFS data edit, no ARM code involved,
     same risk profile as `rom/itemdata.py` etc. This is *not* the
     "ARM hooks" strategy being set aside; it was always going to be a
     data-only edit (see C14's protocol design section).
   - **Remote items** (destined for another player): the client injects
     them directly into the player's bag via a savedata/RAM write, once
     the check-detection flag fires - no in-game "item received" message
     animation for v1 (the acknowledged cost of this option), but no
     unknown ROM addresses required either.

`armips` (Kingcom/armips, MIT) is built from source at
`ressources/armips` (git-ignored, read-only external checkout, never
committed - cloned `--recursive`, built with CMake+Ninja+MinGW g++,
**statically linked** - `-static -static-libgcc -static-libstdc++` - so
the binary has no external MinGW/CRT DLL dependency and runs the same from
Bash, PowerShell, or Python `subprocess`; see task C14's "Blocker 2" for
why this mattered). The built binary is `ressources/armips/build/armips.exe`
(v0.11.0). Not on `PATH`; invoke by full path (M4's patch-build tooling
does this via the `ARMIPS_PATH` env var, following the same convention as
`ARCHIPELAGO_PATH`/`HEARTGOLD_ROM_PATH`).

## Reference projects (read-only, never committed)

- `ressources/Decomposition/pokeheartgold` - `pret/pokeheartgold` decomp.
  Source of ROM memory addresses, symbols and data structures.
- `ressources/platinum_archipelago` - `ljtpetersen/platinum_archipelago`
  (MIT). Architectural reference for how an Archipelago Gen4 Pokémon world is
  structured; not copied directly.

## Spikes

Three research/PoC spikes run against the real HeartGold (US) ROM and the
decomp, to de-risk the architecture above before committing to it further.

### Spike 1 - Reading/writing NitroFS

**Library chosen: [`ndspy`](https://pypi.org/project/ndspy/) (pip).**
`apnds` was ruled out per the task brief (it's a precompiled binary tool
built for `platinum_archipelago`'s own ARM hack, not a reusable library -
confirmed by inspecting `ressources/platinum_archipelago/rom/__init__.py`,
which imports `..apnds.rom.Rom` from a module that isn't vendored in that
reference repo at all, i.e. it's an external, project-specific dependency).
Writing an equivalent "from scratch" NitroFS reader/writer (FNT/FAT parsing,
ARM9 secure-area handling, alignment rules) would be reinventing a
well-tested wheel for no benefit here.

**CORRECTION (2026-08-11, from community feedback + a dispatched research
agent): both claims above about `apnds` and `ndspy`'s license were wrong.**
`ndspy` is **GPLv3**, not MIT (see the M6 ndspy/GPL section below -- this
was only discovered much later, during a real install test, and drove the
whole "manual `lib/` copy" workaround since GPLv3 code can't be bundled
in this MIT-licensed `.apworld`). `apnds` is real, public, actively
maintained, pure-Python, and **MIT-licensed**:
[GitHub](https://github.com/ljtpetersen/apnds),
[PyPI](https://pypi.org/project/apnds/) (latest 0.2.4, June 2026) -- the
Spike 1-era investigation apparently only looked at the *vendored copy*
inside `ressources/platinum_archipelago/apnds/` (no `pyproject.toml`/
package metadata in a vendored copy) rather than checking whether it also
existed as a real standalone package. Confirmed via research: `apnds`'s
`rom.py`/`narc.py`/`lz.py` modules cover the same ROM/NARC/ARM9-code-
decompression functionality this project actually uses from `ndspy`
(plus AES/modcrypt support `ndspy` doesn't have), and
`DarthMDev/hgss_archipelago` (a competing HGSS Archipelago world) already
vendors `apnds` directly inside its own repo and uses it in production --
proof this migration path is real and works. See the M6 section below
for the full license story as it was actually discovered, and "## ndspy
-> apnds migration" near the end of this document for the actual port
(done 2026-08-11): `rom/__init__.py` now runs entirely on a vendored
`apnds` copy, both the GPL concern and the "copy ndspy into `lib/`
manually" player-facing install step are gone.

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
  `0x80` (icon/banner offset field - expected, since layout changed).
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

`ndspy` is now declared in `requirements.txt` (new file - runtime
dependency of the world itself, distinct from `requirements-dev.txt`).
`tests/test_rom_roundtrip.py` covers this: it reads the ROM path from the
`HEARTGOLD_ROM_PATH` environment variable and skips cleanly if unset/absent,
so CI (which has no ROM) is unaffected.

### Spike 3 - Fiabilité des données du decomp

Cross-checked three axes between `ressources/Decomposition/pokeheartgold`
and public/known facts about HeartGold (US):

1. **Items.** `files/itemtool/itemdata/item_data.csv` has **514 rows**
   (513 real items + the `ITEM_NONE` placeholder row) - not the ~236
   figure floated as an assumption to verify; that assumption was wrong.
   Cross-checked against `include/constants/items.h`: item constants span
   IDs 0 (`ITEM_NONE`) to 536 (`ITEM_ENIGMA_STONE`), i.e. 537 possible ID
   slots, of which 22 (IDs 113–134) are explicit `ITEM_UNUSED_*` reserved
   placeholders (a well-documented Gen III→IV artifact: contest/frontier
   items dropped between Emerald and Diamond/Pearl) and thus correctly
   excluded from the CSV. 537 − 22 = 515 real named constants, but the CSV
   only has 514 rows: **`ITEM_EXPLORER_KIT` has a constant (ID present in
   the header) but no corresponding stats row in `item_data.csv`** - a
   genuine, minor gap in the decomp's data export. Max item ID 536 matches
   what's publicly documented for the Gen IV/HGSS item index range.
2. **Encounter tables.** `files/fielddata/encountdata/gs_enc_data.json`
   (not `encountdata/*` split into per-zone files, as the task brief
   assumed - it's a single JSON with a top-level `"encounters"` array) has
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
truth for `data_gen`,** but not blindly 100% trustworthy - axis 1 already
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

### Spike 4 - Réservation d'ID Archipelago

Looked at `pokemon_platinum`, `pokemon_emerald` and `pokemon_rb` in the
local Archipelago clone (`E:\Users\Olivier\Desktop\projet\archipelago`,
read-only reference) for how they reserve item/location ID ranges:

- `pokemon_emerald`: `BASE_OFFSET = 3860000` (`data.py`), added to small
  internal item/flag values for both items and locations.
- `pokemon_rb`: items use `item_id + 172000000` (`items.py`).
- `pokemon_platinum`: **no offset at all** - `get_raw_id()` returns raw
  in-game values (`item_class << 12 | item_id`, topping out well under
  65536). This looked like an anomaly worth explaining, and the current
  Archipelago `docs/world api.md` (in the same local clone) explains it:
  *"Locations and items can share IDs, and locations can share IDs with
  other games' locations."* / *"Items and locations can share IDs, and
  items can share IDs with other games' items."* (lines 226 and 251).
  IDs only need to be unique **within** a single world's own item/location
  namespace - the historical assumption that every game must reserve a
  disjoint global ID range no longer holds for current Archipelago (items
  and locations are namespaced per-game internally). `pokemon_platinum`
  is written against this current rule; `pokemon_emerald`/`pokemon_rb`
  simply predate it (or keep the defensive convention anyway).

Even though a disjoint range is not strictly required anymore, this project
follows the defensive convention used by the majority of currently
maintained worlds (`pokemon_emerald`, `pokemon_rb`, `tunic`, `dark_souls_3`,
etc.) - it costs nothing, aids debugging/log-reading, and future-proofs
against any tooling that still assumes global uniqueness. Scanning every
`base_id`/`BASE_OFFSET`-style constant across `worlds/` in the local clone,
the reserved values found range from `1000` up to `2000300204` (`ahit`),
with a clear, wide unused gap between `66600000` (`shapez`, rounded down)
and `509342400` (`tunic`). Both stay well within the documented "recommended"
32-bit-safe range (1 to 2³¹−1 = 2147483647).

**Proposed ranges for `pokemon_heartgold`** (in that gap, non-overlapping,
each with 1,000,000 IDs of headroom - the decomp data above suggests we
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

## C14 - Ground item check mechanism (proof of concept)

Task C14 set out to prove the hardest remaining piece of the whole project:
turning a vanilla ground-item pickup ("item ball") into a real Archipelago
check, without corrupting the save. This section documents what was found,
what was built, and - importantly - two blockers that stopped the "real"
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
  `_std_hidden_item = 8000` - i.e. **the full "currently running an item
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
  the item ball disappear forever once picked up - and that flag is set by
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
  reading the existing flag bit from savedata - the same technique
  `ressources/platinum_archipelago/client.py` already uses for its own
  location checks (`VarsFlags.get_flag`/`FlagCheck`), just with HeartGold's
  own flag ids. Flags live in `SaveVarsFlags` (`include/save_vars_flags.h`):
  `struct SaveVarsFlags { u16 vars[NUM_VARS]; u8 flags[NUM_FLAGS / 8]; }`
  (`NUM_VARS = 0x170`, `NUM_FLAGS = 2912`), i.e. `flags[flagId / 8] & (1 << (flagId & 7))`.
  This project has not yet located `SaveVarsFlags`'s byte offset inside the
  *whole* HGSS save block (that's `client.py` work, out of scope for C14) -
  only its own internal layout, which is enough to design the protocol
  below.

### Chosen protocol (design)

Given the above, the protocol for a future working client is:

- **Check detection**: read the existing `FLAG_HIDE_ITEMBALL_<location>`
  bit directly from savedata (no ROM patch required - this is genuinely
  vanilla behavior, see `MapObject_Delete` above).
- **Item substitution for local items**: patch the item ball's own script
  bytecode operand (`SetVar VAR_SPECIAL_x8008, <item id>` inside
  `scr_seq_0141.bin`, one `SetVar` per itemball index) to the item id
  Archipelago generation decided for that location. This is a plain NARC
  data edit through the existing `rom/` NitroFS layer (C13) - no ARM code
  needed, no unknown addresses, same risk profile as `rom/itemdata.py`
  etc. **Not implemented in C14** (out of scope: C14 is the check
  *mechanism* PoC, not the full data-patching pass - this is recorded here
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
  EWRAM region, `0x02000000`-`0x023FFFFF`) - **this is a conventional
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
   proprietary MWCC 2.0/sp2p2 compiler + Nitro SDK 4.2 - both unavailable
   on this machine (see "## ROM code injection strategy" above; this is
   the same constraint that already ruled out the "full decomp rebuild"
   option). `asm/*.s` files *do* embed real addresses in their filenames,
   but only for functions that are still **raw, un-decompiled** assembly -
   `ScrCmd_GiveItem` already has matched C source
   (`src/scrcmd_items.c`), so (if genuinely matched) it has no such file
   left to read an address from. `gScriptCmdTable` itself references many
   still-unnamed placeholder entries (`ScrCmd_048`, `ScrCmd_102`, …),
   meaning the *table as a whole* is very unlikely to be a byte-matched,
   buildable unit yet either - so even a from-scratch attempt at building
   just this one file would not reliably reproduce the retail table's
   layout.
2. **An automated signature scan of the real, retail ROM.** Using `ndspy`
   to load the actual `Pokemon - HeartGold Version (USA).nds` (never
   modified, only read) and its ARM9 binary plus all 129 ARM9 overlays, a
   Python script (see this task's own working notes; not committed -
   one-off investigation, not project tooling) searched for a contiguous
   run of `gScriptCmdTable`'s expected size (853 4-byte pointers, all
   resolving into the same code region) anywhere in ARM9 or any overlay.
   `capstone` (a disassembler) was installed **only for this
   investigation** - it is *not* added to `requirements.txt`/
   `requirements-dev.txt`, since it isn't needed at runtime by anything
   committed. The best candidate found was a run of 301 pointers (in the
   overlay sharing base address `0x021E5900` with the field-system
   overlay), nowhere near the expected 853 - ruling out a cheap, reliable
   recovery of the address this way. Reliably finding it would need a
   proper interactive disassembler with cross-reference analysis (e.g.
   Ghidra/IDA with an NDS/ARM9 loader) to trace callers/callees, which is
   out of scope for this session.

A third option - hooking the ARM9 **entry point** instead, which *is*
always known with certainty (it's a plain ROM header field,
`arm9EntryAddress`, read directly, no decomp guessing involved) - was
considered and rejected: the entry point (`0x02000800`) sits well inside
the Nintendo DS "secure area" (the first `0x4000` bytes of the ARM9
binary), which the retail cartridge/BIOS validates against a CRC stored in
the ROM header (`secureAreaChecksum`). `ndspy` reads that checksum but
**does not recompute it on save** - confirmed by reading its own source
(`ndspy/rom.py`, the field is round-tripped with a literal
`# TODO: Actually recalculate` comment). Patching bytes inside the secure
area with this tooling would therefore leave a stale, incorrect checksum
in the saved ROM: a real risk of the ROM failing to boot on strict
emulators or real hardware. This was declined rather than forced.

### Blocker 2: `armips` itself does not currently run - RESOLVED

Separately from the address question: `ressources/armips/build/armips.exe`
(the local build recorded for M4, see "## ROM code injection strategy")
was initially found to **fail to start** in this project's own dev
environment, with Windows error `0xC0000135` / `STATUS_DLL_NOT_FOUND`, in
a Bash-tool subprocess context specifically (invoking it via a native
PowerShell session worked fine - the two contexts resolve the MinGW
runtime DLL dependency chain differently). **Fixed** by rebuilding
statically (`-DCMAKE_EXE_LINKER_FLAGS="-static -static-libgcc
-static-libstdc++"`): the resulting `armips.exe` has no external MinGW/CRT
DLL dependency (`ldd` shows only core Windows system DLLs), runs
identically from Bash, PowerShell, or Python `subprocess.run`.

A second, independent bug surfaced once `armips` could actually run:
`patches/ground_item_hook.s` was missing the top-level `.nds` architecture
directive (armips needs it before anything else in the file to know which
instruction set/directives to enable), and had `.arm` positioned *before*
`.create` instead of after - confirmed against `ressources/armips/Tests/
ARM/*/*.asm`'s own examples, all of which follow `.nds`/`.gba` →
`.create` → `.arm`/`.thumb`. Fixed; `tests/test_patch_gen.py` now passes
for real (7/7, not skipped) with `ARMIPS_PATH` pointed at the rebuilt
binary.

### What C14 actually delivers, given both blockers

- `patches/ground_item_hook.s` - a real, self-contained armips source
  implementing the protocol struct's `HeartGoldAP_Init` and
  `HeartGoldAP_RecordGroundItemCheck` functions (ARM mode). **Not called
  from anywhere** - there is no known-safe call site to hook yet (Blocker
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
  the real game at runtime (no visual glitches, no crashes) - this needs
  actual BizHawk play-testing, out of reach for this agent.
- Implement and test the local-item substitution data patch
  (`SetVar VAR_SPECIAL_x8008, <item id>` inside `scr_seq_0141.bin`) as a
  `rom/eventscriptdata.py`-style module, following `rom/itemdata.py`'s
  pattern.

## C16 -- client.py (BizHawk connector)

Task C16 built `client.py`, the actual `BizHawkClient` implementing the
protocol C14 designed: read vanilla savedata flags to detect checks, write
remote items directly into the running game's `Bag` savedata. Local items
need no client involvement (already patched into the ROM's own data, see
C14/C15). This section documents what was found, what was built, and the
one genuinely open blocker -- in the same spirit as C14's own "two
blockers" writeup, and following this project's standing risk policy
("prudence over progress" for anything that writes to a real player's save
file, if anything a *stricter* bar than C14's read-only ROM-patch case).

### The problem: `SaveData` is not a fixed-offset struct

The natural first assumption -- "`SaveVarsFlags`/`Bag` each live at some
fixed byte offset inside the save file, findable once and hardcoded" -- is
wrong for this game's save system, confirmed by reading
`ressources/Decomposition/pokeheartgold/include/save.h` and `src/save.c`:

- `SaveData` (the RAM struct a running game keeps: `flashChipDetected`,
  `saveFileExists`, `isNewGame`, `statusFlags`, then a flat
  `dynamic_region[SAVE_PAGE_MAX * SAVE_SECTOR_SIZE]` byte array, then
  bookkeeping tables) has **no named field per substructure at all**. Every
  named piece of save state (`SysInfo`, `PLAYERDATA`, `Party`, `Bag`,
  `SaveVarsFlags`, ... 42 in total, `include/constants/save_arrays.h`'s
  `SAVE_SYSINFO`..`SAVE_PCSTORAGE`) is instead a numbered "chunk":
  `SaveArray_Get(saveData, id)` returns
  `&saveData->dynamic_region[saveData->arrayHeaders[id].offset]`.
- Those per-chunk `offset`s are **not** save-file data either -- they are
  computed once, at `SaveData_New()`/`Save_InitDynamicRegion()` time, by
  `SaveData_InitSubstructs()`: walk `gSaveChunkHeaders` (`src/save_arrays.c`,
  a fixed, compile-time-ordered table: id 0 `SAVE_SYSINFO` ..  id 4
  `SAVE_FLAGS` .. id 40 `SAVE_PCSTORAGE`) in order, accumulating each
  chunk's `GetSaveChunkSizePlusCRC()` (`((sizeof(chunk) + 3) & ~3) + 4`) --
  i.e. **every chunk's offset is a deterministic function of every earlier
  chunk's `sizeof()`**, not something read from the save file. This is
  genuinely good news: it means the offsets *can* in principle be
  recovered by pure C-struct arithmetic from the decomp source, with no
  ROM/RAM access needed at all -- unlike C14's Blocker 1 (a real ROM
  address, unrecoverable without a link or a disassembler).

`save_layout.py` (new, pure Python, no BizHawk/Archipelago imports)
re-implements this exact algorithm (`compute_chunk_offsets`,
mirroring `SaveData_InitSubstructs`/`GetSaveChunkSizePlusCRC` line for
line) for chunk ids 0 (`SysInfo`) through 4 (`SaveVarsFlags`) -- `SAVE_BAG`
is id 3, `SAVE_FLAGS` is id 4, both share save "block" 0 with `SysInfo`/
`PLAYERDATA`/`Party` (ids 0-39; only id 40, `SAVE_PCSTORAGE`, starts a new
block/adds page-boundary padding), so no footer/padding is crossed before
id 4 and the accumulation is a straight-line sum.

### What is fully determined vs. the one open ambiguity

Computing each chunk's `sizeof()` from its C definition
(`include/sav_system_info.h`, `include/player_data.h`,
`include/pokemon_types_def.h`, `include/bag_types_def.h`,
`include/save_vars_flags.h`) field-by-field:

- **`Party` (id 2) and `Bag` (id 3) have no ambiguity.** Neither struct (nor
  anything they contain -- `Pokemon`/`BoxPokemon`, whose `// size: 0xEC`
  is stated directly in the decomp itself; `ItemSlot { u16 id; u16
  quantity; }`) has any 8-byte (`s64`/`u64`) member or a bitfield spanning
  a byte boundary that a plain 4-byte-aligned C ABI would lay out
  ambiguously. `PLAYERDATA` (id 1) likewise has none (`Options` is a single
  `u16` bitfield; `IGT`/`PlayerProfile` are plain 8/16/32-bit fields).
  `save_layout.PLAYER_DATA_SIZE` (44) and `save_layout.PARTY_SIZE` (1456)
  are therefore high-confidence, derived once and fixed.
- **`SysInfo` (id 0, the very first chunk) does have 8-byte members**
  (`rtc_offset`; `SysInfo_RTC.seconds_since_nitro_epoch`/
  `seconds_at_game_clear`) -- and how the retail **MWCC 2.0/sp2p2** ARM9
  compiler aligns those is a toolchain ABI fact, not something derivable
  from C source alone (same category of unknown as C14's Blocker 1: no
  real compiler/linker available in this dev environment to just check).
  Two internally-consistent, standard C layouts are possible: the older
  ARM "APCS" convention (8-byte members align like any 4-byte-or-smaller
  member, no extra padding -- `sizeof(SysInfo) == 72`) or the modern
  AAPCS/EABI convention (8-byte members force 8-byte alignment, including
  of the *enclosing* struct's own size -- `sizeof(SysInfo) == 80`).
  Because `SysInfo` is chunk id 0 (first in line), this is exactly an
  8-byte uncertainty that propagates **unchanged** through every later
  offset (`PLAYERDATA`/`Party`/`Bag`/`SaveVarsFlags` all shift by the same
  8 bytes) -- not an unbounded unknown, a well-bounded choice between
  **two** named candidates (`save_layout.CANDIDATE_OFFSETS`:
  `"apcs_4byte_longlong"` / `"eabi_8byte_longlong"`).

### The other open unknown: `SaveData`'s own RAM address

Independent of the above: everything in `save_layout.py` only gives
offsets *relative to* the start of the RAM `SaveData` struct. Its absolute
address is a `static` C global (`sSaveDataPtr`, `src/save.c`) with no
documented value -- unlike `pokemon_emerald`'s `gSaveBlock1Ptr` (a real,
linked-build address that project's own decomp bakes into `data.py`), this
project has no real linked build to read such an address from (same MWCC/
Nitro-SDK unavailability already recorded above and in C14's Blocker 1).
This project's "client-only, no ROM code" v1 strategy (chosen after C14)
also does not give itself a self-locating magic marker in RAM the way
`ressources/platinum_archipelago`'s own client can (its
`AP_STRUCT_PTR_ADDRESS` trick only works because that project's build
burns a real, linked `ap.bin`/protocol struct into the ROM -- a capability
this project deliberately set aside).

**Decision (same "prudence over progress" call as C14's ARM-hook
address, arguably with a higher bar since this is a write path that could
corrupt a real save file):** `client.py` never guesses this address. Two
settings are **required**, read from environment variables
(`HEARTGOLD_SAVE_DATA_ADDRESS`, `HEARTGOLD_SAVE_LAYOUT_CASE`) -- until both
are set, the client logs one actionable message
(`client._missing_configuration_message()`) and does not read or write any
RAM at all.

**Manual discovery procedure** (for the project owner to run once, in a
real BizHawk session -- this is the "what remains to be validated
manually" for this task, mirroring C14's own such section):

1. In BizHawk's RAM Search, domain **"ARM9 System Bus"**, search for the
   player's current in-game money as a signed/unsigned 4-byte value (it is
   stored in plaintext, `PlayerProfile.money`, no encryption). Narrow it
   down with a couple of "changed value" re-searches after spending/
   earning coins in-game.
2. For each candidate money address, compute
   `candidate_address - save_layout.CANDIDATE_OFFSETS[case].money_offset_in_savedata`
   for both `case`s (`money_offset_in_savedata` is exposed exactly for this
   purpose) -- this is the candidate `SaveData` base address for that case.
3. Disambiguate the two cases by then reading
   `base + save_layout.CANDIDATE_OFFSETS[case].bag_offset_in_savedata`
   bytes and checking which one looks like a real `Bag` (an array of
   `ItemSlot{u16 id; u16 qty}` with item ids under ~537, `id == 0`/`qty ==
   0` for empty slots, matching the player's actual current bag contents)
   -- the wrong case will read 8 bytes off and produce implausible ids.
4. Set `HEARTGOLD_SAVE_DATA_ADDRESS` (the confirmed base, from step 2) and
   `HEARTGOLD_SAVE_LAYOUT_CASE` (`"apcs_4byte_longlong"` or
   `"eabi_8byte_longlong"`, whichever matched in step 3) as environment
   variables before launching the client.
5. Confirm end-to-end: pick up a local, already-substituted item ball and
   watch the corresponding location get checked server-side; have another
   test slot send this slot a filler item and watch it appear in the bag
   next `game_watcher` tick (no in-game "item received" toast for v1, see
   below -- check the bag contents directly).

None of this (steps 1-5) could be run in this agent's own session -- no
BizHawk, no emulator, no live game process available here.

### Check detection and item reception, as actually implemented

- **Check detection** (`location_flags.py`, new): `data/locations.py`'s
  `ground_item`/`npc_gift`/`hm_tm` locations already store a real vanilla
  flag id directly as their own `id` (cross-checked against
  `rom/eventscriptdata.py`'s `BLOCK_INDEX_BY_ITEMBALL_FLAG_ID`, whose keys
  -- e.g. 1081, 1056 -- are real `FLAG_HIDE_ITEMBALL_*` values, not small
  indices); `hidden_item` locations store the small `HIDDENITEM_*` index
  instead, needing `+ HIDDEN_ITEMS_FLAG_BASE` (800,
  `include/constants/flags.h`) to become a real flag id. A handful of
  `npc_gift` locations have no single-purpose `FLAG_GOT_*` constant at all
  and were given a synthetic id in a reserved `9000+` band instead
  (`data_gen/locations.toml`'s own header) -- these have **no vanilla flag
  this client can currently read**, `location_flags.flag_id_for_location`
  returns `None` for them (`location_flags.unsupported_location_keys()`
  lists exactly which). Badge locations are events with no real AP
  location id to begin with (`locations.py`) and never reach this client
  either way. `client.py`'s `game_watcher` reads the whole
  `SaveVarsFlags.flags[]` array once per tick and checks every location
  this way in one pass.
- **Item reception**: `save_layout.plan_bag_item_write` decides where to
  write an incoming item inside its Bag pocket (stack onto a matching slot
  under a per-pocket cap, else the first free slot) purely from the raw
  pocket bytes -- deliberately simpler than `Bag_AddItem`'s real TM/HM/
  Berry pocket re-sort (an accepted v1 simplification: the item still lands
  in a valid, correctly-typed slot, just not necessarily where vanilla
  sorting would place it). Since there is no ROM/save-side counter this
  client controls (no `ap.bin`-equivalent, see above), "how many of
  `ctx.items_received` have already been written into the bag" is tracked
  in Archipelago's own server-side data storage (`Set`/`ctx.set_notify`,
  key `pokemon_heartgold_applied_item_count_{team}_{slot}`) so it survives
  client restarts. **Known, inherent limitation**: this does *not* survive
  the player reloading an in-game save state/file from before some
  already-applied items were written -- those items will not be
  re-granted, since nothing about their delivery lives in the save file
  itself. Fixing this for real needs the ROM/ARM-hook side of C14's own
  protocol design (`patches/ground_item_hook.s`'s scaffolding, still
  unwired per Blocker 1), out of scope for this client-only v1. There is
  also no in-game "item received" message/animation for v1, the
  already-acknowledged cost of the client-only strategy recorded above.

### What C16 delivers, and what remains manual

- `save_layout.py` -- pure struct-layout/chunk-offset model (see above),
  fully unit-tested (`tests/test_client.py`).
- `location_flags.py` -- location -> vanilla flag id mapping, unit-tested
  against every real `ground_item`/`hidden_item`/`badge` location once
  `data/` is generated.
- `client.py` -- `HeartGoldClient(BizHawkClient)`: detects the ROM via its
  `IPKE` header game code (`rom.HEARTGOLD_US_ID_CODE`, no per-seed ROM
  marker exists yet, see `__init__.py`'s docstring on why `patch_gen.py`
  doesn't produce a single distributable patch file yet), polls
  `SaveVarsFlags.flags[]` for checks, and writes remote items into `Bag`
  once both required settings above are present. Registered with
  `worlds._bizhawk`'s `AutoBizHawkClientRegister` via a
  `from client import HeartGoldClient` in `__init__.py` (same convention
  `worlds/pokemon_emerald/__init__.py` documents for itself).
- `tests/test_client.py` -- covers everything statable without a real
  BizHawk/emulator connection: `save_layout.py`'s arithmetic (including
  that the two candidate cases differ by exactly the expected 8 bytes
  everywhere), `location_flags.py`'s mapping against every real location,
  and `client.py`'s async read/write orchestration
  (`_check_locations`/`_apply_next_received_item`/
  `_store_applied_item_count`) driven end-to-end against a fake, in-memory
  `ctx` with `worlds._bizhawk.read`/`guarded_write` monkeypatched (real
  network/RAM I/O never happens in these tests). **Not, and cannot be,
  tested here**: anything requiring an actual running HeartGold instance
  (BizHawk + the real `connector_bizhawk_generic.lua` script + a real save
  file) -- that is the "manual discovery procedure" above, entirely the
  project owner's to run.
- `archipelago.json` needed no change: cross-checked against
  `worlds/pokemon_emerald/archipelago.json` in the local Archipelago
  clone, which also declares a `BizHawkClient` subclass and has no
  client-related manifest field -- client registration is purely a Python
  import-time side effect (`AutoBizHawkClientRegister`), not something
  `archipelago.json` (game/version/authors/minimum_ap_version metadata
  only) participates in.

### Manual discovery session results (2026-08-09, project owner + live BizHawk)

Real addresses found in a live session (melonDS core, domain "Main RAM" --
note this is the *same* memory as "ARM9 System Bus" but with the
`0x02000000` EWRAM base subtracted, i.e. `main_ram_addr + 0x02000000 ==
arm9_system_bus_addr`):

- **`PlayerProfile.money`: Main RAM `0x27C2C0`.** Confirmed via BizHawk RAM
  Search changed-value tracking (2400 -> 2300 after an in-game purchase,
  matched the in-game HUD exactly). High confidence.
- **`Bag` (pocket `items`, first field of the chunk): Main RAM `0x27CDA0`.**
  Confirmed **directly** -- the raw bytes at this address are `11 00 07
  00`, i.e. `ItemSlot{id=0x0011=17 (Potion), quantity=7}`, matching the
  player's real inventory (7 Potions) exactly. Independently
  cross-confirmed a second way: `SaveData.arrayHeaders[3]` (the game's own
  chunk offset table, `include/save.h`'s `SaveArrayHeader`, read live at
  Main RAM `0x29F280`-ish) reports `size=0x7A0 (1952)` for chunk id 3
  (`SAVE_BAG`), exactly matching `save_layout.chunk_size_with_footer(
  save_layout.BAG_SIZE)` -- strong independent confirmation this really is
  the `Bag` chunk. **High confidence, safe to use as-is.**
- **`SaveVarsFlags.flags[]` (the actual bit array, after the leading
  `vars[]` array): Main RAM `0x27D820` -- candidate, NOT independently
  confirmed.** Derived arithmetically from the confirmed `Bag` address
  (`0x27CDA0 + chunk_size_with_footer(BAG_SIZE) + vars[]'s 0x2E0-byte
  size`) and cross-checked against `arrayHeaders[4]` (`offset=0xDE4`,
  `size=0x450`), which agrees with the arithmetic to the byte -- so the
  *math* is internally consistent on three independent paths. But the
  bytes actually observed there don't unambiguously look like flag data:
  a clean run of zeros for the first 16 bytes, then some `FFFF` (which can
  legitimately happen -- flash-erased-pattern padding, or 8 genuinely-set
  early-game flags), then ~100 bytes that look like high-entropy noise
  with what might be a ~240-byte repeat -- consistent with either (a)
  genuine flag data (plausible: many small story/pickup flags could
  already be true) or (b) uninitialized-RAM poison fill from the
  emulator core. Not disambiguated in this session.
- **This resolves the earlier "1300-byte unexplained gap"** (see the
  Debugger investigation above) as **not real** -- it was an artifact of
  comparing the wrong two numbers (money-to-bag delta computed one way vs.
  another), not an actual bug in the chunk-size model. The `arrayHeaders`-
  based cross-checks above show the `Bag`/`SaveVarsFlags` *sizes* the
  model computes are exactly right; whatever residual small discrepancy
  exists between the model's predicted absolute `money`-to-`Bag` delta and
  the confirmed one was not fully re-derived algebraically before this
  session ran out of context budget, and `save_layout.py` itself was
  **not modified** this session (too high-risk to patch under time
  pressure without a fully closed derivation) -- it still reflects the
  pre-this-session model. Anyone picking this up next should treat the
  four addresses above (money/bag confirmed, flags candidate, "no 1300-byte
  gap") as the actual ground truth, not `save_layout.py`'s own current
  arithmetic output.
- **`0x27D820` is now DISCONFIRMED, not just unconfirmed.** Direct test:
  Route 30's Antidote ball (`FLAG_HIDE_ITEMBALL` id 1056,
  `data_gen/locations.toml`'s `route_30_antidote`) was picked up live,
  bracketed by two Hex Editor screenshots of `0x27D8A4` (byte offset
  `1056/8=132=0x84` from `0x27D820`, the bit this specific flag should
  set). The byte (`4E3B945C`, the row containing it) is **byte-identical
  before and after** -- the expected bit never flipped. So despite the
  arithmetic agreeing with `arrayHeaders` on three independent paths
  (chunk sizes), `0x27D820` is not where the game actually keeps this
  flag. Likely explanations, untested: the live RAM working copy of
  `SaveData` is laid out differently from the `dynamic_region`-relative
  model this whole derivation assumes (e.g. `SaveArray_Get`'s pointer
  arithmetic might not correspond 1:1 to a flat byte offset the way
  assumed); or `arrayHeaders` itself was read from a stale/inactive save
  slot copy, not the live one being played.
- **Recommended next step (revised)**: for `Bag`, `0x27CDA0` (Main RAM)
  remains solid (confirmed a completely different way -- direct content
  match, not struct arithmetic) and is safe to hardcode/use as-is for
  remote-item injection. For check-detection, **abandon the
  arithmetic-derivation approach** for `SaveVarsFlags` and instead do a
  live **differential RAM search** next session: open BizHawk RAM Search
  (domain Main RAM, 1 Byte, "Different by" a `New Search` taken
  immediately *before* picking up a known item ball, re-searched
  immediately *after* for "changed" values) -- this finds the real
  changed byte(s) directly, with no struct-size assumptions at all, the
  same way the `money` address was originally confirmed. Much more
  reliable than deriving an address and hoping it's right.

### T2 live integration test (2026-08-10) -- `CONFIRMED_FLAGS_ARRAY_ADDRESS` DISCONFIRMED under extended play

A same-session follow-up to the "Manual discovery session results
(2026-08-10)" addendum above (`0x0227D39C`, found via a clean before/after
Lua dump diff on a single known pickup) ran a real, full T2 integration
test: a generated seed, a ROM copy patched with `patch_gen.py`'s
`apply_local_item_substitutions` (345 locations, 217 of them
cross-verified byte-for-byte against the patched ROM before this test --
see this session's own commit), a local `MultiServer.py`, and a real
`BizHawkClient.py` connected to the player's live BizHawk session.

**Local item substitution: confirmed working end-to-end.** The player
picked up two different item sources and received exactly what the seed
placed there both times (Route 29's ground item -> Sea Incense, matching
`AP_..._Spoiler.txt`'s `route_29_potion: SEA_INCENSE`; a vanilla NPC gift
outside this project's 570-location pool correctly produced no location
check at all, as expected for untracked content).

**Check detection via `CONFIRMED_FLAGS_ARRAY_ADDRESS`: does not hold up.**
Over the course of the test:

- Immediately on connecting (before the player had done anything in a
  fresh, just-started save), **16 locations were reported as already
  checked** -- all `npc_gift`/`hm_tm` type, none `ground_item`. Cross-
  checked each flag id against `include/constants/flags.h`: every single
  one resolved to the *correct*, real `FLAG_GOT_*` constant for its
  location (e.g. flag 109 -> `FLAG_GOT_APRICORN_BOX`, matching
  `route_30_apricorn_house_apricorn_box` exactly) -- so this is not a
  `data_gen`/`location_flags.py` id-mapping bug; the flag ids themselves
  are right.
- Later, after the player genuinely picked up Route 29's ground item
  (confirmed via Sea Incense actually appearing in the Bag), **no check
  fired for `route_29_potion` at all** -- the one location that
  definitely should have fired, didn't.
- In the same window, yet another, unrelated location
  (`lake_of_rage_hidden_power_house_tm10`) spontaneously flipped to
  "checked" with no corresponding player action.
- A one-off diagnostic read of the full 364-byte flags array (via a
  throwaway script using `worlds._bizhawk` directly, run after the live
  client was stopped) found it **entirely zero, including the byte for
  `route_29_potion`'s own flag** -- but this read happened after the
  player's save was lost to an unrelated emulator restart (unsaved
  progress, not a client/script side effect), so it reflects a
  fresh/blank save, not new evidence either way about the address itself.

**Conclusion**: the pattern (real actions not registering; unrelated,
untouched locations spontaneously toggling on; all of it restricted to
`npc_gift`/`hm_tm`, never `ground_item`) is not consistent with a stable
read of the real `SaveVarsFlags.flags[]` array. `0x0227D39C` most likely
pointed at a genuinely volatile RAM region (a reused scratch/text/script
buffer, not save data) that happened to produce one clean, single-bit,
before/after diff during the original 2026-08-10 discovery session by
coincidence, rather than because that address is `SaveVarsFlags`. The
`Bag` address (`0x0227CDA0`) is not implicated by any of the above --
both real pickups this session correctly landed the right item in the
right pocket, consistent with its earlier, independent (content-match)
confirmation.

**Status change**: `CONFIRMED_FLAGS_ARRAY_ADDRESS`/
`HEARTGOLD_FLAGS_ARRAY_ADDRESS` in `client.py` must no longer be treated
as resolved -- the module's own "*** RESOLVED 2026-08-10 ***" docstring
section is now only half true (Bag: yes: flags: no) and needs updating.
Check detection is **effectively disabled/unreliable** until a new
address is found. Recommended next step: repeat the differential-RAM-
search idea from the paragraph above, but validated across a **longer
play session with multiple, spaced-out pickups** (not a single
before/after diff) specifically to rule out a volatile/reused buffer --
require the candidate byte to (a) go from 0 to 1 exactly once, (b) stay 1
afterward across many further ticks/actions, and (c) do this for at least
two or three independent known pickups at predicted-correct byte offsets
relative to each other, before trusting it. A single clean diff, as this
project learned twice now (`0x27D820` in the C16 session, `0x0227D39C`
here), is not sufficient evidence on its own.

### Second attempt, same day: `0x0227D340` -- cross-validated across three real pickups

Immediately following the above, the player restarted a fresh save (the
previous one had never been saved and was lost to an unrelated emulator
restart -- not a consequence of this project's own tooling) and repeated
the RAM-diff approach with a fix for the previous attempt's core flaw
(a single before/after diff over real, unpaused gameplay time is far too
noisy: a raw ~32 KB window diff around a single ground-item pickup showed
**433 changed bytes**, the large majority clearly unrelated to save data
at all -- e.g. a ~700-byte block that looks like dialog/text-box render
state, another ~800-byte block that looks like a field-object/script
buffer, both artifacts of the pickup's on-screen message and animation,
plus ordinary background RNG/audio/timer churn from the game simply
running unpaused between the two snapshots).

Fix: instead of trusting any single diff, filter every diff down to
**single-bit** changes only (`before ^ after` is a power of two -- the
signature of a real flag bit, not multi-bit incidental data), then
**cross-validate candidates against a second, independent pickup** at a
different, precisely-known flag id, checking that (a) the predicted byte
delta between the two flags' ids lands on an actual candidate pair and
(b) the bit positions match too.

Concretely: `route_29_potion` (flag id 1081 -> byte 135, bit 1) and
`route_30_potion` (flag id 1088 -> byte 136, bit 0) are exactly 7 flag
ids -- i.e. exactly 1 byte -- apart. After the first pickup, six
single-bit candidates remained in the plausible region near `Bag`
(`0x0227D144`, `0x0227D15C`, `0x0227D270`, `0x0227D353`, `0x0227D3C7`,
`0x0227D4D4`). After the second pickup, one of the new single-bit
candidates, `0x0227D3C8`, sat **exactly one byte after** `0x0227D3C7`
from the first list -- and the bit positions matched too (bit 1, then
bit 0, exactly as predicted). This is not the kind of match noise
produces: two independent constraints (exact +1 byte delta *and* the
exact predicted bit positions) both satisfied by the same pair.

Base address implied: `0x0227D3C7 - 135 = 0x0227D340`.

A third, independent pickup then confirmed it further:
`route_30_antidote` (flag id 1056 -> byte 132, bit 0) was read directly
at the predicted address (`0x0227D340 + 132 = 0x0227D3C4`) *after* the
fact (not found via diffing) and matched exactly. At the same time, the
first two flags (byte 135 bit 1, byte 136 bit 0) were re-read and were
**still correctly set**, several minutes and multiple further player
actions later -- unlike `0x0227D39C`, which had reverted to all-zero
after less elapsed time in the previous, disconfirmed attempt.

**`CONFIRMED_FLAGS_ARRAY_ADDRESS` updated to `0x0227D340`** in
`client.py`, with three independent, mutually-consistent, stable data
points backing it -- meeting the (a)/(b)/(c) bar this document itself set
above, unlike either of the two previous candidates. Re-ran the full
local test suite + ruff after the change (green).

**Closing live end-to-end re-test: passed.** Rebuilt the `.apworld` with
the corrected address, reinstalled it into the local Archipelago
checkout, reset the server's save state, and ran a fresh
`MultiServer.py` + `BizHawkClient.py` session against the same live
BizHawk instance (no manual RAM reads this time -- the real client
polling loop only). Result: **all four of the player's real, live
pickups were detected and reported correctly** --
`route_30_antidote` -> `FULL_HEAL`, `route_30_potion` -> `PECHA_BERRY`,
`route_29_potion` -> `SEA_INCENSE`, and (confirmed with the player,
initially flagged as a suspected false positive given the previous
session's pattern, but genuine this time) `route_30_apricorn_house_
apricorn_box` -> `MAX_ETHER`. No extra/spurious checks fired. This is
the first clean confirmation of check detection working for **both**
`ground_item` (the first three) and `npc_gift` (the fourth) location
types against a real, live game.

### Remote item injection: real save corruption found live, then a fixed absolute-address model found to be the wrong architecture entirely

Continuing the same session's T2 testing, remote item reception
(`_apply_next_received_item`, previously untested live) was exercised via
the server's `!getitem` self-cheat command. Result: **the player's save
was corrupted** -- the in-game Start menu lost its Bag/Status/Save/
Options entries, requiring a save reload to recover (the player had
saved recently enough that only a few minutes of progress were lost).

Root cause investigation: `save_layout.py`'s `BAG_POCKET_OFFSETS`
(pocket byte offsets, computed from declared per-pocket capacities like
`NUM_BAG_ITEMS = 165`) was only ever independently verified for the
*first* pocket -- the one `CONFIRMED_BAG_BASE_ADDRESS` itself was
content-matched against. If any pocket's declared capacity is wrong,
every *later* pocket's computed offset is wrong too, and a write can
land outside the real `Bag` struct entirely, into adjacent save data.
**Fix applied immediately**: `ctx.items_handling` downgraded from
`0b011` (locations + remote items) to `0b001` (locations only) --
`_apply_next_received_item` now never runs (the server never sends
remote items to a client that didn't ask for them), so no RAM writes
happen at all until every pocket offset is independently re-verified
against the real game, the same rigor `CONFIRMED_BAG_BASE_ADDRESS`
itself went through. This is a `client.py` code change (`validate_rom`),
not merely a runtime toggle -- re-enabling it requires deliberately
restoring `0b011` and doing that verification work first.

**A second, deeper problem surfaced investigating the corruption**: a
live scan for a known Bag item (`route_30_apricorn_house` had left the
player with exactly one distinctively-quantified item, cross-checked by
byte-scanning a wide RAM window for it) found it at a **completely
different absolute address** than `CONFIRMED_BAG_BASE_ADDRESS` -- after
the player reloaded their save (recovering from the corruption above),
`Bag` had moved by roughly 1.3 KB. `include/save.h`'s `SaveSlotSpec
saveSlotSpecs[2]` explains why: the game double-buffers save data across
two physical slots (ordinary write-safety practice -- a failed write
never corrupts the other copy), and either slot's in-RAM working copy
can end up active depending on which was written last. **There is no
reason a fixed absolute address should ever have been expected to
survive a save reload** -- the whole "confirm an address empirically,
hardcode it" approach used throughout this session (`CONFIRMED_BAG_BASE_
ADDRESS`/`CONFIRMED_FLAGS_ARRAY_ADDRESS`) was the wrong shape of fix, not
just imprecisely executed.

**The actual fix: locate `SaveData` dynamically, every session, via
`SaveData.arrayHeaders[]` itself** (`include/save.h`), rather than any
fixed address. `arrayHeaders[0..4]` are five consecutive 16-byte
`SaveArrayHeader{int id; u32 size; u32 offset; u16 crc; u16 slot;}`
records whose `id` fields are exactly `0,1,2,3,4` in order (`SAVE_
SYSINFO`.."SAVE_FLAGS", `include/constants/save_arrays.h`) -- a
distinctive, content-independent signature (unlike scanning for actual
item data, which depends on what the player happens to own) that a
bounded RAM scan can reliably find regardless of which physical save
slot is active. Once found, `arrayHeaders[SAVE_BAG].offset`/
`arrayHeaders[SAVE_FLAGS].offset` give the real chunk offsets directly
from the game's own bookkeeping table -- ground truth, no struct-size
modeling and no pocket-capacity assumptions (the exact category of
assumption that caused the corruption above) required at all.

Implemented in `client.py` (`_find_array_headers_address`, `_locate_
save_addresses`, `_ensure_addresses_located`): the scan runs once at
first connection, and again automatically any time a cheap per-tick
validity check on the cached `arrayHeaders` address fails (i.e. a save
reload happened mid-session) -- `game_watcher` skips its tick entirely
rather than read/write at a stale address while relocating. Verified
twice, independently, the same session: the derived `Bag` address landed
byte-for-byte on the address a blind content-scan for a known-owned item
had separately found; and a fresh end-to-end live test (server + real
BizHawk client, dynamic location only, no manual address anywhere)
correctly detected two further real pickups
(`route_29_potion` -> `SEA_INCENSE`, `route_30_potion` -> `PECHA_BERRY`)
with zero false positives, immediately after a save reload that would
have broken the old fixed-address model. `CONFIRMED_BAG_BASE_ADDRESS`/
`CONFIRMED_FLAGS_ARRAY_ADDRESS` are removed from `client.py` entirely
(no longer meaningful); `HEARTGOLD_BAG_BASE_ADDRESS`/`HEARTGOLD_FLAGS_
ARRAY_ADDRESS` env vars remain as a manual override for troubleshooting,
unset by default.

**Update, same session: remote item injection re-verified and re-enabled.**
On reflection, the corruption above was very likely caused simply by the
*wrong base address* (the old `CONFIRMED_BAG_BASE_ADDRESS` was not
actually the start of `Bag`) rather than by `BAG_POCKET_OFFSETS`'s
pocket-capacity model itself, which is sourced directly from the
decomp's own `bag_types_def.h` (`NUM_BAG_ITEMS` etc. are cited decomp
constants, not guesses). With the base now correctly located dynamically
(above), a read-only, live scan of all 8 Bag pockets (via the same
dynamically-located base) found every non-empty slot correctly matching
the player's actual, known inventory (`items`: Big Pearl x5 + Sea
Incense; `berries`: Pecha Berry; every other pocket empty, consistent
with an early-game save) -- zero anomalies, zero misplaced items. This
independently confirms the pocket-offset model itself was never the
problem.

`ctx.items_handling` was restored to `0b011` (locations + remote items)
and re-tested live via the server's `!getitem` cheat command
(`POKE_BALL`, chosen as a pocket with no existing contents to make a
misplacement obvious): the client correctly wrote `Poke Ball x1` into
the `balls` pocket at its expected address, verified again via the same
read-only all-pocket scan afterward -- every other pocket's contents
unchanged and correctly placed, no menu corruption, no misplaced data.
**Remote item injection is confirmed working, live, on top of the
dynamically-located addresses.**

**M4 status after this**: local item substitution, check detection, and
remote item injection are all robust and confirmed live, including
across a save reload. What remains open: `hidden_item` substitution
(separate, already-documented blocker -- static ARM9 table) and a
Reviewer pass on this session's `client.py` changes as a whole.

## M4.5 -- applying species.py's randomizers to the ROM (implemented)

`docs/scope.md`'s v1 list includes wild encounters, starters, trainer
parties and evolutions, and `species.py` already computed all four
(`randomize_wild_encounters`/`randomize_starters`/
`randomize_trainer_parties`/`randomize_evolutions`, seeded from
`world.random`) -- but `__init__.py`'s `set_rules()` only *ran* them and
stored the result on `self` (see that file's own docstring, "for a later
task (ROM patch generation) to consume"). **Nothing wrote this output
into the ROM** -- discovered while answering the user's direct question
about whether these randomizers actually affect real gameplay (they
didn't, yet). Decided (2026-08-10): stay on the documented v1 scope
(not descoping to an items-only release) and implement all of it the
same session, plus two randomizers the user added to scope at the same
time -- base stats and move power/PP/accuracy (type preserved). Every
randomizer now has its own on/off (or off/shuffle/full_random) option.

### Prerequisite: the species raw-index mapping (508 vs 505)

`rom/speciesdata.py`'s own docstring had flagged this as unresolved:
`personal.narc` (a/0/0/2) has 508 entries, `data/species.py`'s `SPECIES`
has 505. Resolved by finding `ressources/Decomposition/pokeheartgold/
files/poketool/personal/personal.json` -- a decomp-authored, human-edited
JSON export whose `baseStats` array is compiled *back* into the real
NARC by the decomp's own build system, meaning its index order **is**
the real raw sub-file index. Matched every `data/species.py` entry's
`label` against `baseStats[i].species`: **505/505 matched**, and the 3
unmatched raw entries were exactly `NONE` (index 0), `EGG` (494), `BAD_
EGG` (495) -- engine-reserved placeholders, confirming both the count
and which indices are the "extra" 3. Verified independently against the
real ROM: reading `personal.narc[1]` gives Bulbasaur's exact real base
stats.

Generated once into `data/species_index.py`'s `SPECIES_KEY_TO_RAW_INDEX`
via a new `data_gen` step (`data_gen/species_index.toml` -> `data_gen_
templates/species_index.py`), the same toml-source-of-truth pattern
every other `data/*.py` table already follows -- not a hand-rolled
static table, reproducible the same way as everything else.

The same technique resolved a second, analogous gap: `data/encounters.py`
has 137 zones, the raw `g_enc_data.narc` (a/0/3/7) has 142. `gs_enc_data.
json`'s own array order is the real raw index (confirmed against the
real ROM: index 0 == map code T20 == `data/encounters.py`'s `new_bark`
zone, byte-for-byte -- its surf slots decode to Tentacool/Tentacruel
exactly). Matched each zone's own `map_code` against `gs_enc_data.
json[i].map`: **134/137 matched** (`data/encounter_zone_index.py`'s
`ENCOUNTER_ZONE_KEY_TO_RAW_INDEX`, same `data_gen` pattern) -- the other
3 (`route_16`/`pewter`/`azalea`) have a *headbutt* table only (a
different NARC, not touched by this work) and no `gs_enc_data.json`
entry to map at all, exactly matching `data_gen/encounters.toml`'s own
already-documented "headbutt-only" flag for those 3 map codes.

### Byte formats (Decomposition headers, each cross-checked live against the real ROM)

- **Base stats** (`include/pokemon_types_def.h`'s `BaseStats`): `hp`/
  `atk`/`def`/`speed`/`spatk`/`spdef` are the entry's first 6 bytes, one
  `u8` each, in that exact order. `rom/speciesdata.py`'s new `write_base_
  stats`/`read_base_stats` touch only those 6 bytes.
- **Moves** (`include/move.h`'s `MoveTbl`, new `rom/movedata.py`,
  `waza_tbl.narc` -> `a/0/1/1`, 471 raw entries, 16 bytes each): `power`
  @ offset 3, `type` @ offset 4, `accuracy` @ offset 5, `pp` @ offset 6.
  `data/moves.py`'s own `id` field is directly usable as the raw index
  here -- unlike species, no separate mapping needed (spot-checked 4
  moves -- tackle/thunderbolt/flamethrower/pound -- against the real ROM,
  power/accuracy/pp/type all matched exactly at `waza_tbl.narc[id]`).
  `write_combat_stats` only ever touches power/accuracy/pp, never type.
- **Evolutions** (`include/pokemon_types_def.h`'s `struct Evolution
  {u16 method; u16 param; u16 target;}`, new `rom/evodata.py`, `evo.narc`
  -> `a/0/3/4`, 508 entries index-aligned with `personal.narc`, 44 bytes
  each = 7 x 6-byte records + 2 unstudied trailing bytes never touched).
  Evolution `method` strings (`data/species.py`'s own `evolutions[i]
  ["method"]`, e.g. `"level"`/`"stone"`/`"trade_item"`) map 1:1 onto
  Decomposition `include/constants/pokemon.h`'s `EvoMethod` enum
  (`EVO_LEVEL = 4` etc.) -- cross-checked live: Bulbasaur's real
  evolution read directly off the ROM was `(method=4, param=16,
  target=2)`, exactly `EVO_LEVEL`, level 16, Ivysaur's raw index.
  `param`'s *type* depends on `method`: a plain int for level/friendship/
  beauty-style methods, an item key for stone/trade_item/item_day/
  item_night, a move key for has_move, a species key for
  other_party_mon -- `patch_gen.py`'s `_encode_evolution_param` dispatches
  on that.
- **Trainer parties** (`include/trainer_data.h`'s `TRPOKE` union, 4
  variants depending on held-item/custom-moves presence): in every
  variant, `species` sits at the same fixed offset (4 bytes in), only
  each *slot*'s total size differs (8/10/16/18 bytes). **The variant is a
  property of the whole trainer, not of any individual mon** -- read from
  `TrainerData.trainerType` (`trdata`'s own first byte: bit 0 = custom
  moves, bit 1 = held item, `src/trainer_data.c`'s own comment). A first
  version of `rom/trainerdata.py`'s `write_party_species` guessed each
  slot's stride from whether that mon's own `data/trainers.py` dict
  happened to carry a `held_item`/`moves` key -- wrong whenever a trainer
  has the held-item bit set but one particular mon holds `ITEM_NONE`
  (`data_gen` then emits no `held_item` key for that mon): a Reviewer
  pass caught this live against the real ROM (Falkner, `trainerType ==
  3`, both mons using 18-byte slots; the guess computed 16, writing the
  second mon's species over the first mon's `level` field). Fixed to
  always derive one stride for the whole party from `read_stats_entry`'s
  own first byte -- see `rom/trainerdata.py`'s own section comment for
  the full story, and `tests/test_patch_gen.py`'s
  `test_apply_trainer_randomization_writes_every_party_correctly` (all
  738 trainers, not just a sample) plus `tests/test_rom_access.py`'s
  `test_trainerdata_write_party_species_uses_trainer_type_not_per_mon_
  keys` (a Falkner-specific regression test) for the tests that would
  have caught this. `data/trainers.py`'s `id` is already 1:1 with the raw
  `trdata`/`trpoke` NARC index (`rom/trainerdata.py`'s own docstring
  already established this at C13, exactly 738 = 738, no gap).
- **Wild encounters** (`include/wild_encounter.h`'s `EncounterData`,
  0xC4 = 196 bytes, confirmed against the real ROM's entry size): land
  morn/day/nite species arrays at 0x14/0x2C/0x44 (12 x u16 each, shared
  `levels[12]` never touched), surf/rock_smash/old_rod/good_rod/
  super_rod each an `EncounterDataSlot{u8 min; u8 max; u16 species;}`
  array at 0x64/0x78/0x80/0x94/0xA8. `rom/encounterdata.py`'s new
  `write_zone_encounters` only ever touches the species `u16` fields,
  never the shared level/rate bytes.

### Starters -- DISCONFIRMED live (candidate address was wrong)

Unlike the other five, the starter choice is not NitroFS data: `src/
choose_starter.c`'s `const int species[] = {SPECIES_CHIKORITA,
SPECIES_CYNDAQUIL, SPECIES_TOTODILE};` is a compiled literal inside an
ARM9 **overlay** -- the same general category of problem as C14's
ground-item ARM hook, but narrower (an in-place *data* patch, not code
injection/call-site hooking). Found by searching the raw species indices
(152/155/158) as a literal `int[3]` (three consecutive little-endian
`u32`s) across the main ARM9 binary and all 129 ARM9 overlays: zero
matches in the main binary, exactly **one** match total across every
overlay -- overlay 61, offset 0x1A98. A second, unrelated 16-bit-pattern
match in overlays 80/99 was inspected and discarded (a long run of
sequential-looking species ids, consistent with a Pokédex-order table,
not a 3-element list).

Added generic ARM9 overlay read/write to `rom/__init__.py`
(`read_overlay`/`write_overlay`, handling the overlay's own compression
flag and patching `arm9OverlayTable`'s stale `compressedSize` field after
recompressing -- overlay 61 is LZ-compressed, 7104 decompressed / 5968
compressed bytes) and `rom/starterdata.py` on top. Correctly kept out of
`patch_gen.py`'s normal apply path pending live verification (same "a
single clean result is not sufficient evidence" lesson as client.py's
RAM-address saga) -- and that caution paid off, though not in the way
first thought: a live test the same session (full-randomizer seed,
patched ROM including the starter write, booted in BizHawk, new game
started) showed **vanilla Chikorita/Cyndaquil/Totodile**, not the seed's
rolled starters, which was first written up here as "the candidate
address is wrong". **That conclusion was itself wrong.** A Reviewer pass
found the real bug: `write_overlay` called `ndspy.codeCompression.
compress(data, isArm9=True)` -- the `isArm9=True` mode reserves the
first 0x4000 bytes uncompressed (the DS secure-area convention for the
*main* ARM9 binary), meaningless for an overlay. For any overlay smaller
than 0x4000 bytes (true for overlay 61, and for most overlays this
project might ever target), that degenerates into "everything is the
uncompressed prefix", producing a payload with **no valid compression
header at all** -- and `ndspy.codeCompression.decompress()` silently
returns such a payload *unchanged* rather than raising, so the original
"mechanically round-trip verified" claim for `rom/starterdata.py` was
true only in the narrow sense that garbage-in-garbage-out round-trips
correctly; the live game almost certainly failed to decompress the
overlay at all and fell back to something else (vanilla data, most
likely, consistent with what was observed). Fixed to `isArm9=False`
(matching `ndspy.code.Overlay.save()`'s own convention) plus an explicit
`compressed_size <= overlay.ramSize` guard; `tests/test_rom_access.py`'s
starter test now asserts real compression integrity (`overlay.
compressed`, decompressed size unchanged, stored size `<= ramSize`)
instead of only re-reading the 3 species values.

**Status: re-tested with the fixed mechanism, DISCONFIRMED for real this
time.** The first live test (which seemed to disconfirm overlay 61 /
offset 0x1A98) was run through the broken `isArm9=True` compression call
and so proved nothing about the address either way. After fixing
`write_overlay`, a second test ROM was built (compression integrity
checked before handoff: `overlay.compressed == True`, decompressed size
unchanged at 7104 bytes, recompressed to 5964 bytes -- comfortably under
the 7104-byte `ramSize` ceiling and close to the original 5968-byte
compressed size, i.e. a healthy, real compressed payload this time, not
the empty-header garbage the old code produced) and booted fresh in
BizHawk. Result: still **vanilla Chikorita/Cyndaquil/Totodile** at the
selection screen, and picking one confirmed it in-party (Cyndaquil, not
one of the seed's rolled starters Bastiodon/Palkia/Dugtrio). With a
verified-correct write mechanism this time, this is now a real,
trustworthy disconfirmation: **overlay 61, offset 0x1A98 is not the
right location** (or overlay 61 is not the overlay actually loaded for
this scene). `rom/starterdata.py` and the overlay read/write plumbing in
`rom/__init__.py` stay in the codebase (the plumbing itself is sound and
reusable for a future candidate), but `OVERLAY_ID`/
`_SPECIES_ARRAY_OFFSET` must be re-derived from scratch, not reused. See
the "possible next angles" list above (confirm overlay 61 is really
loaded for this scene; check `choose_starter_app.c` for its own,
separately-encoded copy; consider a disassembler-based approach) for
where to pick this up.

Wild-encounter randomization was cross-checked in the same session and
confirmed working (a Swalot on Route 29, nowhere near a vanilla Route 29
encounter) -- that path never touched overlay code, so it was unaffected
by the compression bug either way. A follow-up live check (`rare_candy`
x15 injected directly into the Bag via the same live-RAM technique
`client.py` already uses, no server needed) confirmed evolution-target
randomization working too: a level-up evolution landed on a different,
non-vanilla target. Base stats and move stats were not part of either
test seed (`randomize_base_stats`/`randomize_moves` both `off`) --
confirmed only via the ROM-level round-trip tests above, not yet
cross-checked live in a running game.

### New randomizers: base stats and move stats (user-added scope, same session)

Both added by the user mid-session, both follow the exact same
off/shuffle/full_random `Choice` pattern already established for wild
encounters (`options.RandomizeBaseStats`/`options.RandomizeMoves`,
`species.randomize_base_stats`/`species.randomize_move_stats`):
`shuffle` permutes each stat/field independently across every species/
move; `full_random` draws each stat/field independently within the real
observed min-max range for that column (avoids literal 1/255-style
extremes no vanilla entry ever has). Base stats never touch growth
rate/EXP curve or any other species field (unrelated to the deferred
"level scaling" v2 item, docs/scope.md). Move stats never touch `type`
(hard invariant, tested).

### Integration

`__init__.py`'s `set_rules()` now also calls `randomize_base_stats`
(chained onto `randomize_evolutions`'s output, so both land on the same
`generated_species`) and `randomize_move_stats` (`generated_moves`).
`patch_gen.py` gained `apply_trainer_randomization`/`apply_encounter_
randomization`/`apply_evolution_and_stat_randomization`/`apply_move_
randomization`, each taking a `HeartGoldWorld`'s `generated_*` dict and
applying it to a `HeartGoldRom` via the layers above.

### Verification

Every new `rom/*.py` write function was round-trip tested against the
real ROM (write, `rom.save_bytes()`, reopen, read back) both as one-off
manual checks during development and as permanent additions to
`tests/test_rom_access.py` (8 new tests: species-index/encounter-zone-
index completeness, base-stats round-trip, move-stats round-trip +
type-preservation, evolution round-trip, trainer-party round-trip
verifying untouched slots stay byte-identical, encounter-zone round-trip
verifying untouched fields stay byte-identical, starter mechanical
round-trip). Then a full, real, live integration pass: instantiated a
real `HeartGoldWorld` via `test.general.setup_multiworld` with every
randomizer on `full_random`/`shuffle`/`True`, applied all four `patch_
gen.py` functions to a real ROM copy, saved, reopened, and spot-checked
the result -- e.g. `rival_silver`'s randomized party (`smoochum`/`seel`/
`abra` for that seed) read back correctly from the patched ROM's
`trpoke` table, byte-for-byte matching the world's own computed
`generated_trainer_parties`. Full test suite: 193 passed + 42 skipped
without a local ROM, 235 passed with one (`HEARTGOLD_ROM_PATH` set),
ruff clean throughout.

**What's still open**: starters (mechanically works, not live-verified
in-game -- see above); headbutt encounters (a separate, smaller NARC,
not wired up -- the wild-encounter randomizer's *computation* still
covers headbutt, only the ROM write doesn't yet); a Reviewer pass on
this whole body of work; `hidden_item` substitution (separate,
already-documented, unrelated blocker).

**M4's core client-only strategy (docs/architecture.md's "ROM code
injection strategy (revised after C14)", option 3) is now fully
validated end-to-end**: local item substitution (confirmed earlier this
session, 217/217 `ground_item` locations byte-verified against the
patched ROM, plus live pickups) and check detection (confirmed here,
both location-type families, four independent live pickups, zero false
positives) both work against a real ROM, a real emulator, and a real
Archipelago server. Remaining open items before M4 can be called fully
closed: remote-item injection into the Bag (`_apply_next_received_item`)
has unit-test coverage but was not exercised live this session (would
need a second player slot to send an item to test); `hidden_item`
substitution remains out of scope (separate, already-documented
blocker); a Reviewer pass has not yet been run on the final
`0x0227D340` change.

## M4.5 continued -- `hidden_item` substitution resolved (was a documented blocker, now implemented)

The user asked, mid-M4.5, whether hidden items were randomized and
explicitly required both this and starters be resolved before shipping
v1 rather than staying documented limitations. Starters remains
unresolved (see its own section above); `hidden_item` was fully solved
this pass. Full story, since the investigation itself is instructive for
any future similar work:

**Why this was hard, unlike every other table this project patches**:
`sHiddenItemParam` (`src/data/fieldmap/hidden_items.h`, read by
`GetHiddenItemParams` in `script_manager.c`) is a genuine `static const`
C array compiled directly into the ARM9 main binary (confirmed via
`main.lsf`: `script_manager.o` links into "Static main", not any
overlay) -- not a NitroFS NARC sub-file like every other randomized
table (species/moves/evolutions/encounters/trainers/items). A blind
byte-pattern search across the entire ~745KB `rom.arm9` (every
plausible struct layout, every stride/offset hypothesis, and a loose
statistical scan for long runs of merely *plausible*-range values) found
nothing at all -- not even a partial match. This is the same category of
problem that blocked starters.

**Root cause, found only after live debugging**: `rom.arm9` (both this
project's `HeartGoldRom.arm9` and `ndspy`'s own underlying property)
returns the ARM9 binary exactly as packed in the ROM -- which, for
HeartGold, is itself **LZ-compressed beyond the first 0x4000-byte secure
area** (`ndspy.codeCompression`'s `isArm9=True` convention: secure area
raw, everything after compressed). `len(rom.arm9)` is 762,644 bytes; the
real decompressed image (`ndspy.codeCompression.decompress(rom.arm9)`)
is 1,122,040 bytes. Every static search this session (and, in
retrospect, probably every one of C14's original "blocked" attempts
too) was searching *compressed* bytes for an *uncompressed* pattern --
guaranteed to find nothing, regardless of how correct the struct layout
guess was.

**How the real address was actually found (live BizHawk debugging, not
static analysis)**: with the user's help live-testing in BizHawk --

1. A full before/after Main RAM diff (`"ARM9 System Bus"` domain,
   0x02000000-0x023FFFFF) around a real hidden-item pickup (New Bark
   Town's Potion) found the transient write: RAM `0x22A6C1C` going from
   zero to `11 00 01 00 20 03 00 00` (itemId=17/Potion, quantity=1,
   flag=800) -- this is `ScriptEnvironment.specialVars[]`
   (`VAR_SPECIAL_x8000`/`x8001`/`x8002`), a heap-allocated, per-session
   scratch location, not useful for patching directly but confirming the
   mechanism and the decomp's item-id modeling.
2. A Lua `event.onmemorywrite` breakpoint on that address, armed
   *before* a pickup (needed a BizHawk savestate to retry, since
   hidden-item flags are one-shot), captured `emu.getregisters()` at the
   moment of the write -- but the captured PC did not disassemble to
   anything sensible (`lsl r1,r4,#0x1c`, not a store), a red herring that
   cost real time: **the Lua-reported PC is not the address of the
   instruction that just executed** (a pipeline/fetch-stage artifact),
   consistently off by a fixed 4 bytes in this case.
3. BizHawk's native Trace Logger resolved the ambiguity, but only once
   used correctly: run continuously in real time it logs every single
   instruction on both CPUs and effectively freezes the game (a single
   frame's trace was ~150MB). **Paused + single-frame-advanced** instead
   (so logging only covers the handful of frames around the actual
   button press), it produced a small, readable trace with real
   disassembly and per-instruction register state, confirming the real
   store instructions: `strh r1,[r7,#0x0]` at `0x020405FA` (itemId),
   `strh r0,[r6,#0x0]` at `0x02040602` (quantity), `strh r0,[r4,#0x0]`
   at `0x0204060A` (flag) -- each exactly 4 bytes before what the Lua
   breakpoint had reported, confirming the pipeline-offset theory.
   Immediately before the itemId store: `ldr r3,[pc,#0x38]` at
   `0x020405D4`, loading `r3 = 0x020FA558`, then `ldrh r0,[r3,#0x6]`
   (the struct's `index` field, offset 6) -- exactly the decomp's `for
   (...) table[i].index` loop. Since this was the very first loop
   iteration (idx=0, immediate match), `r3` at that point *is*
   `sHiddenItemParam`'s own base address.
4. `0x020FA558` is outside both the (still-compressed-assumption) main
   arm9 range *and* every overlay's RAM window -- looked like a heap
   address at first. It is not: reading live RAM at that address
   (reconnecting to BizHawk, small targeted read rather than a full 4MB
   dump) returned the exact expected table content byte-for-byte, and
   `ndspy.codeCompression.decompress(rom.arm9)[0xFA558:]` (i.e. the
   *decompressed* main ARM9 image, static, no BizHawk needed) matches
   that live read exactly, entry-for-entry, all 231 entries -- full
   round-trip confidence, both live and offline.

**Fix, `rom/__init__.py`**: new "ARM9 main-image decompressed access"
section: `read_main_code_decompressed()` (thin wrapper over
`ndspy.codeCompression.decompress`) and `write_main_code_region(offset,
data)` (decompress, patch in place, recompress with `isArm9=True`,
replace `self._rom.arm9` -- refuses any offset under `0x4000`, the same
secure-area safety constraint `write_overlay` and `append_to_arm9`
already established for their own regions). A decompress -> recompress
-> decompress round trip was verified byte-identical before trusting
this for real writes.

**New module, `rom/hiddenitemdata.py`**: `ARM9_TABLE_RAM_ADDRESS =
0x020FA558`, `read_all`/`read_entry`/`write_item_id`, and
`write_hidden_item_substitution(rom, location_key, item_key)` matching
the existing `write_ground_item_substitution`/`write_npc_gift_
substitution` shape. One real subtlety: `sHiddenItemParam` is **not**
sorted by its own `index` field (e.g. array position 1 has index 1, but
position 2 has index 225) -- `data/locations.py`'s `id` for a
`hidden_item` location is that `index` value (a `HIDDENITEM_*`
constant), so `_find_position_by_index` linearly scans the live table
for a matching `index` field rather than ever treating `id` as a
position directly (mirrors the C engine's own linear-scan lookup in
`GetHiddenItemParams`).

**Wired into `patch_gen.apply_local_item_substitutions`**: `hidden_item`
is now a fourth routed location type alongside `ground_item`/`npc_gift`/
`hm_tm` (only `badge` remains out of scope, since badges aren't items).

**Tests**: `tests/test_hidden_item_substitution.py`, 7 tests against the
real ROM -- entry-0 exact-byte-match, **all 225 real `hidden_item`
locations** cross-checked against their vanilla `original_item` (zero
mismatches), single-entry-touched-only substitution, error handling,
`apply_local_item_substitutions` routing + save/reload round trip, and
every location substitutable without crashing. All pass. Performance
note for later: the "every location substitutable" test alone takes
~34 minutes, since each `write_hidden_item_substitution` call currently
decompresses + recompresses the full 1.1MB ARM9 image independently --
correct but not batched; fine for test/generation-time use (a real seed
patches a bounded, usually much smaller number of hidden-item locations
once), but worth batching into a single decompress/recompress pass if
this ever needs to scale further.

## M4.5 continued -- starters: further investigation, still unresolved (documented v1 limitation)

After hidden_item's compression discovery, retried starters with the
same live-BizHawk technique (memory-write breakpoint + paused/frame-
stepped Trace Logger), plus a fresh Ghidra project built from the
**properly decompressed** ARM9 image this time (`ndspy.codeCompression.
decompress(rom.arm9)`, 1,122,040 bytes -- the earlier starters/hidden_item
Ghidra attempts had all been analyzing the *compressed* 762,644-byte
`arm9.bin`, which explains why every prior Ghidra disassembly attempt
produced garbage regardless of mode/alignment tried).

**Four live capture sessions this pass** (New Bark Town's lab, picking
Chikorita each time, raw species index 152/0x98):

1. Before/after full Main RAM diff around a pick found two clean,
   isolated write sites: RAM `0x0227D032` and `0x0227D090`, both going
   from their old value to `0x98` cleanly (no surrounding noise) --
   promising candidates for "the party's species field."
2. A Lua `event.onmemorywrite` breakpoint on both, combined with a
   paused/frame-stepped Trace Logger capture (same working recipe as
   hidden_item), found the real store instructions: `strh r0,[r4,#0x0]`
   at `0x0204D1D6` and `strh r4,[r0,#0x0]` at `0x02066AA4` (again ~4
   bytes before what the Lua breakpoint alone reported -- confirms the
   pipeline-offset caveat generalizes, at least in this ROM/core).
   Tracing backward from both sites through the live trace log found
   they are **generic, heavily-reused utility functions** -- one is a
   PRNG-based save-block checksum routine (`0x41C64E6D`, the well-known
   LCG multiplier constant, confirms it), the other a generic `SetVar
   (varId, value)` accessor (Ghidra-decompiled: checks `0x3FFF < varId <
   0x8001`, writes through a computed pointer) -- not starter-specific
   code, and not a data table.
3. Traced backward further and found the species value is *read* (not
   computed) from RAM `0x0227C2EC` via `ldrh r4,[r5,#0x0]` at
   `0x0206E8F0` just before being copied into the party-commit path --
   i.e. `0x0227C2EC` holds the "currently selected starter" ahead of
   this whole commit/checksum sequence, and is itself just being copied
   forward, not originated, by anything traced so far.
4. Ghidra's own cross-reference search for callers of the `SetVar`/
   `GetVar` functions confirmed they are used for dozens of unrelated
   purposes throughout the game (a Union Room status-polling loop was
   one real example decompiled) -- chasing all callers is a dead end,
   too broad. Re-armed the breakpoint on `0x0227C2EC` itself and
   recaptured from before the selection screen even appears (no cursor
   movement, no pick) -- still only caught the same generic checksum
   loop re-reading the value every frame the screen is up (67 hits, all
   at the same PC), never an initializing write. BizHawk crashed during
   this capture (~14GB of Trace Logger output across the session,
   cleaned up afterward) without revealing the true origin.

**Conclusion**: the starter species value is set via some initialization
this session's four capture windows never actually contained (most
likely a one-time write when the selection screen's script/task first
starts, before any of the captures were armed) -- unlike hidden_item,
which had a single clean static table, starters appears to flow through
either a script-level `SetVar` (matching the `0x3FFF`-`0x8001` varId
range the `SetVar`-shaped function checks -- worth searching `scr_seq.
narc` for directly, the same way `npcgiftdata.py`'s `TABLE` was derived,
though a first attempt with a guessed var id found nothing) or a
still-unlocated ARM9 code path that hasn't been captured live yet.
`rom/starterdata.py`/the overlay plumbing in `rom/__init__.py` remain in
the codebase (sound, unused). Overlay 61/offset 0x1A98 (the original
candidate from earlier in this project) is confirmed wrong (disconfirmed
live, see the section above); this pass didn't produce a replacement
candidate.

Two more rounds after this, still with the user, before finally stopping:
(a) an exhaustive search for a tightly-packed `{152,155,158}` u16/u8
table -- both orderings, both widths -- across the **properly
decompressed** main ARM9 image and all 129 overlays (two coincidental
hits, overlay 80 and overlay 99, both ruled out live: overlay 80's RAM
region was entirely zeroed -- not loaded -- during the capture, and
overlay 99 wasn't the overlay actually resident at its declared RAM
address at the time, overlay 1 ["field", the always-loaded overworld
overlay] was) and a loose cluster search for 3 nearby `MOV Rd,#imm`
Thumb instructions loading the three species values in any register,
anywhere in the main image; (b) a broadened `scr_seq.narc` search for a
`SetVar` (opcode 41) command with *any* varId in `0x4000`-`0x8000` and
any of the three species raw indices as the value operand. **Both came
back with zero matches.**

**Decided (2026-08-10): starters is removed from v1's exposed option
surface** (`options.py` no longer declares `RandomizeStarters`,
`__init__.py` no longer calls `randomize_starters`/stores
`generated_starters` -- see `docs/scope.md`'s new "Shelved" section).
`species.py`'s `randomize_starters` function and its own direct unit
tests are left in place (pure computation, zero risk, already tested,
ready to reconnect); `rom/starterdata.py` and the overlay write-plumbing
in `rom/__init__.py` also stay, unused. Next angles if picked up again:
a live capture starting from map load / task creation for the selection
screen (before the screen is even visible) rather than from
"already on the selection screen," to catch a true initializing write
instead of steady-state re-reads.

## M5 -- `generate_output` (the missing M4 piece, done first)

Before starting M5's own build/CI work, a real gap surfaced: `__init__.py`
had no `generate_output` method at all. Every M4/M4.5 randomizer
(`patch_gen.py`'s `apply_*` functions) had been exercised only via tests
and ad-hoc live-test scripts -- there was no code path a real `Generate.py`
run (or the WebHost) could actually call to produce a player's patched
ROM. Implemented now, following the same pattern every other ROM-patching
Archipelago world uses (`worlds/pokemon_emerald`, `ressources/
platinum_archipelago`): never embed/transmit the vanilla ROM's own bytes
anywhere in a generated file -- only a small JSON *description* of the
changes goes in the patch file; `.patch()` re-reads the player's own local
ROM copy (from a `settings.Group`, `host.yaml`'s `pokemon_heartgold_
settings.rom_file`) fresh every time it actually runs, possibly on a
different machine than the one that generated the seed.

- New file `output_patch.py`: `HeartGoldProcedurePatch(APAutoPatchInterface)`
  stores 5 JSON blobs (`trainers.json`/`encounters.json`/`species.json`/
  `moves.json`/`item_substitutions.json`) inside a `.apheartgold` zip;
  `.patch(target)` decodes them and calls `patch_gen.py`'s existing,
  already-tested `apply_trainer_randomization`/`apply_encounter_
  randomization`/`apply_evolution_and_stat_randomization`/`apply_move_
  randomization`/`apply_local_item_substitutions` against the player's own
  vanilla ROM, then `rom.save(target)`. Reuses the existing library
  functions verbatim -- no new ROM-writing logic, just the Archipelago-
  facing glue.
- `build_item_substitutions(world)`: walks `world.multiworld.get_locations
  (world.player)`, keeping only locations whose placed item's `.player ==
  world.player` (a *local* item -- see `client.py`'s own docstring for why
  only local items are baked into the ROM at all; a location holding
  another player's item is left at its vanilla `original_item`, which
  `client.py`'s check-detection/remote-injection logic already expects).
  `hidden_item` briefly needed exclusion from `_SUBSTITUTABLE_LOCATION_
  TYPES` (2026-08-10 to 2026-08-11, after a live playtest hit a boot
  white screen with ~225 hidden_item locations patched) -- root-caused
  and reconnected, see "SDK_COMPRESSED_STATIC_END" below.
- `HeartGoldSettings` (in `__init__.py`, `settings_key = "pokemon_
  heartgold_settings"`): a `settings.Group` with one `RomFile` (`settings.
  UserFilePath`, `md5s=[HEARTGOLD_US_MD5]`) -- the per-machine `host.yaml`
  setting every ROM-patching world needs.
- `HeartGoldWorld.generate_output()`: one line, delegates to `output_
  patch.generate_output(self, output_directory)`.

**Verified end-to-end**, not just unit-tested in isolation: a real
`setup_multiworld` -> `Fill.distribute_items_restrictive` -> `world.
generate_output()` run produced a real `.apheartgold`
(`AP_<seed>_P1_<name>.apheartgold`, ~139KB), which was then read back and
`.patch()`-ed against the real ROM, producing a real, correctly-sized
`.nds` (126,645,960 bytes, matching every other successful build this
session) whose species base stats and move stats matched the computed
`generated_species`/`generated_moves` exactly (spot-checked, then covered
by `tests/test_generate_output.py`'s own `test_patch_applies_and_matches_
computed_randomization`, which does the same thing as a permanent test).
4 new tests total, all passing.

`.apignore` was missing `output_patch.py`/`patch_gen.py` entirely (both
now genuinely required at runtime, not just NitroFS-access-layer
dependencies) -- added. `build.py`'s directory-recursion also picked up
`rom/__pycache__/*.pyc` files it had no business packaging -- excluded
now.

## M5 -- public repo scoped to source + build tooling only

Decided 2026-08-11: this repository only tracks what's needed to build,
run, or modify the APWorld -- `tests/`, `requirements-dev.txt`,
`pyproject.toml`, and `CONTRIBUTING.md` are gitignored, not part of the
public GitHub history. They still exist locally for development (pytest/
ruff continue to work exactly as before), they're just never committed.
This mirrors what `.apignore` already scoped the packaged `.apworld`
itself to -- the git repo now follows the same principle one level up.

Consequently `.github/workflows/build.yml` is **build-only**: checkout ->
`pip install -r requirements.txt` -> `python -m compileall` (syntax
sanity check) -> `python data_gen.py` -> `python build.py` -> upload the
resulting `.apworld` as a workflow artifact. No test job -- there is
nothing to run in CI since tests aren't part of this repo. The full test
suite still runs locally the normal way; it's just a dev-time practice,
not a CI gate, going forward.

## M6 -- real install testing found real bugs, plus "empty" item substitution for remote locations

A real Archipelago install test (`D:\Archipelago`, the actual portable/
frozen Windows release, not the local dev checkout) found and fixed two
release-blocking bugs no from-source test could ever have caught:
`archipelago.json`'s `minimum_ap_version` was `"0.6.8"` (just copied from
the dev checkout's own version, not a real dependency -- lowered to
`"0.6.7"`, the actually-verified floor), and `client.py`'s `patch_suffix`
was still `None` (a leftover from before `output_patch.py` existed) --
`AutoBizHawkClientRegister` only registers a class's patch suffix onto
the generic "BizHawk Client" launcher component when it's not `None`, so
the Launcher's "Open Patch" dialog never recognized `.apheartgold` at all
until this was fixed. Also documented (`docs/setup_en.md`,
`README.md`/`README.en.md`): `ndspy` (an external, GPLv3-licensed
dependency, never bundled in the `.apworld`) cannot be installed the
normal way on a frozen/portable Archipelago release (no pip-accessible
environment) -- confirmed live that copying `ndspy`'s pure-Python source
into the install's `lib/` folder (next to the loose `kivymd` package
cx_Freeze already keeps there) makes it importable.

### Remote-item locations no longer leave a real vanilla item behind

A live playtest surfaced a real design question: a `ground_item`/
`npc_gift`/`hm_tm` location whose placed item belongs to *another*
multiworld player was left at its vanilla `original_item` in the ROM (see
`output_patch.py`'s original docstring) -- meaning the player physically
received a real, unearned vanilla item (e.g. a Potion) every time they
checked a location that wasn't "theirs". Not a logic bug (this vanilla
item is never tracked by Archipelago), but a real, user-flagged UX
problem.

The "obvious" fix -- make the pickup grant literally nothing -- was
originally assumed to need reopening the still-unresolved `ScrCmd_
GiveItem` ROM-hook investigation from task C14 (`patches/
ground_item_hook.s`, never wired to a real call site, same risk category
as the starters investigation). It didn't: this project already has full,
tested write access to the item-id operand for both `ground_item`
(`rom/eventscriptdata.py`) and `npc_gift` (`rom/npcgiftdata.py`)
locations -- the open question was only "what does the vanilla pickup
script do with an *invalid* item id", not "how do we intercept the pickup
at all".

Tested live (2026-08-11), on the real ROM, via BizHawk:

- **`ground_item`** (Route 29 Potion, itemball, item id 0): shows a
  garbled "Found ???!" message (item 0 has no real name string), but nothing
  is actually added to the Bag -- confirmed via manual Bag inspection.
  Crucially, the location's real vanilla savedata flag **is still set**
  (independently verified via a live RAM read of `SaveVarsFlags.flags[]`,
  the same flag this project's check-detection already reads) -- so
  `location_flags.py`'s existing flag-read check-detection keeps working
  completely unchanged.
- **`npc_gift`** (New Bark Town Elm's Lab, NPC-delivered, item id 0):
  shows "Obtained ???!" and briefly appears to add an item to the Items
  pocket, but a manual Bag check afterward confirmed it doesn't actually
  persist -- same end result as the itemball case, via a different
  script/NARC path.

Implemented as a proper "empty" substitution, not a special case bolted
onto the existing one: `rom/eventscriptdata.write_ground_item_empty` /
`rom/npcgiftdata.write_npc_gift_empty` (both share their validation logic
with the existing `write_*_substitution` functions via a new private
`_resolve_*` helper each) write item id 0 to a location's script site(s).
`patch_gen.apply_local_item_substitutions`'s `substitutions` dict now
allows `None` (JSON `null`) as an item value -- the sentinel routed to
these new `_empty` functions instead of a real item lookup.
`output_patch.build_item_substitutions` now includes *every*
ground_item/npc_gift/hm_tm location, not just this player's own: a
remote-item location gets `None` instead of being skipped entirely.
`hidden_item` gained the same `_empty` treatment once reconnected (see
"SDK_COMPRESSED_STATIC_END" below): `rom/hiddenitemdata.write_hidden_
item_substitutions` accepts `None` as a per-location value the same way.

Not yet explored: replacing the garbled "???" name with something
cleaner (e.g. a reserved, renamed item slot showing "Item sent!" instead
of a blank name) -- a real refinement, not attempted this session.

## Community feedback round: real duplicate-item bug found (2026-08-11)

Published the `.apworld` and asked for outside testers. One tester ran a
real 2-player game for ~30 minutes and reported (among other things) that
many ground_item locations were being granted *twice* -- e.g. two Jade
Orbs from a single key-item location -- and one npc_gift location (an
Apricorn box randomized to an X Special) delivered both the randomized
item and the original vanilla item.

Root cause: Archipelago's server sends every item belonging to a player
through `items_received` once its location is checked -- **including
locations in that player's own world**, with no protocol-level concept of
"this player's client already delivered this item some other way."
`client.py`'s `_apply_next_received_item` processed every entry in
`items_received` unconditionally and wrote it into the Bag -- so a local
ground_item/npc_gift/hm_tm item was granted twice: once for real via the
ROM edit (picking it up in-game), and once more via network injection the
moment the server saw the check. This project's own "local items are
ROM-substituted, only remote items need network delivery" convention
(`output_patch.build_item_substitutions`) was only ever implemented on
the *output* side -- nothing on the client's *receiving* side ever
skipped an already-locally-delivered item.

Fixed: `location_flags.build_locally_substituted_ap_location_ids()` (new)
returns the AP location ids of every ground_item/npc_gift/hm_tm location
(the same set that can be ROM-substituted). `client.py` computes this
once at import time (`_LOCALLY_SUBSTITUTED_AP_LOCATION_IDS`, same
convention as the existing `_FLAG_ID_TO_AP_LOCATION_ID`) and
`_apply_next_received_item` now skips (marks "applied" without touching
the Bag) any received item whose `NetworkItem.player == ctx.slot` (this
player's own location, per `NetUtils.NetworkItem`'s "sending player"
semantics) **and** `.location` is in that set -- a real remote item
(different sending player) is completely unaffected and still gets
written normally. 2 new tests (one confirming the skip, one confirming a
same-location-id-but-different-player item still gets delivered, to
guard against the filter matching on location id alone).

**Trainersanity/Dexsanity confirmed to be completely inert** (investigated
via a dispatched Explore agent, 2026-08-11): exhaustive search across
every root-level module found zero references to either option outside
`options.py`'s own declaration. `create_locations` (`locations.py`) never
receives `self.options` at all and only ever iterates `data/locations.py`
-- a statically generated dataset with exactly 5 location types (`badge`,
`ground_item`, `hidden_item`, `hm_tm`, `npc_gift`), none of which
represent a trainer battle or a Pokédex entry. So no real Location is
ever created for either feature, regardless of the option's value -- the
spoiler log showing "YES" only reflects Archipelago's generic per-world
option serialization, not any HeartGold-specific implementation.
`docs/scope.md`'s own "stretch goal within v1 if the budget allows" note
is now updated to record that the budget didn't allow it. Decision
(2026-08-11, "continue tels quels"): leave both options in place, inert,
for now -- not removed from the option surface, not implemented either.

**npc_gift/hm_tm check-detection gap: root-caused, not a new bug**
(dispatched Explore agent, 2026-08-11). The tester's report ("many...not
seen by client") is fully explained by the already-known synthetic-id
band (`location_flags._SYNTHETIC_ID_BASE = 9000`) -- both examples the
tester actually named (`route_29_poke_ball`, `new_bark_elms_lab_1f_
potion`) are in that band. No new bug found: exhaustively checked for
duplicate flag ids among the 98 "should be detectable" (id < 9000)
locations (zero found) and for gaps in `rom/npcgiftdata.py`'s `TABLE`
coverage (none -- all 55 npc_gift and all 36 NPC-delivered hm_tm
locations are present). What the agent did find: the scale is bigger
than the code's own "a handful of gifts" comment suggests -- **30 of 128
npc_gift/hm_tm locations (23.4%)** are in the undetectable band,
including recognizable ones like the starter-kit Potion and Route 29's 5
Poké Balls. Worth deciding later whether to leave this as a documented
limitation (current state) or exclude these 30 locations from the AP
pool entirely, same treatment as `hidden_item`/starters -- not decided
yet, since (unlike hidden_item) the *local* delivery still works
correctly here (ROM substitution + the fixed double-delivery bug above);
only cross-player check completion for a *remote* item at one of these
30 locations would silently never reach the other player, which is the
real, still-unresolved failure mode worth weighing.

**Competing HGSS Archipelago worlds reviewed** (dispatched general-
purpose research agent, 2026-08-11): `DarthMDev/hgss_archipelago` uses
the same overall approach as this project (vendored NDS library, vanilla
savedata flag reads for check-detection via `connector_bizhawk_generic.
lua`) -- and, notably, its `items_received` handling does **not**
distinguish local from remote items either (a commented-out, unfinished
`remote_items` option is visible in its source) -- independent
confirmation that the double-delivery bug fixed above is a real, easy-to-
miss trap in this whole class of world, not something this project
uniquely got wrong. `EyeballSweat/hgss_archipelago` turned out to be an
unmodified fork of the main Archipelago framework repo with zero
HeartGold-specific code -- a dead end, nothing to learn from it.

## SDK_COMPRESSED_STATIC_END: hidden_item's real white-screen root cause (2026-08-11)

The white-screen boot failure that forced `hidden_item` back out of
`_SUBSTITUTABLE_LOCATION_TYPES` (see above) was root-caused offline,
before any further live testing, by reading `crt0.s`'s own boot sequence.

**The field**: `_start_ModuleParams + 0x14` (ARM9 RAM address
`0x02000BB4`) is read early in boot (`ldr r0,[r1,#0x14]; bl MIi_
UncompressBackward`) to tell the decompressor where the LZ-compressed
static region *ends* in RAM. Vanilla value = `arm9_ram_address +
len(packed_arm9_bytes)`. This field itself lives inside the DS secure
area (`rom.arm9`'s first `0x4000` bytes), which is never LZ-compressed --
only the bytes *after* `0x4000` are.

**Why every edit broke it**: `ndspy.codeCompression.compress(data,
isArm9=True)` copies `data[:0x4000]` through completely unchanged -- it
never updates this field to match the new compressed size it just
produced. Any real edit that changes the compressed region's size (which
a genuine content change to that region essentially always does) leaves
this field stale. At boot, `MIi_UncompressBackward` then starts
decompressing from the *wrong* address -- corrupting memory before the
game can even show a title screen. Live-verified: 225 hidden_item
substitutions shifted the compressed size from 762,644 to 763,008 bytes
(delta 364) -- exactly the kind of size change this field never
tracked. `write_main_code_region`'s single-edit round trip from the
M4.5 section above never happened to hit this because it was only ever
tested with edits that didn't change the compressed size enough to be
caught before this pass.

**Fix, `rom/__init__.py`**: `write_main_code_regions(edits: list[tuple[
int, bytes]])` -- a two-pass compression. Pass 1 decompresses, applies
every edit, recompresses once to learn the *real* new compressed size,
then patches that size into the never-compressed secure-area prefix at
`_MODULE_PARAMS_ARM9_RAM_ADDRESS + _COMPRESSED_STATIC_END_FIELD_OFFSET`
(`0x02000BA0 + 0x14`). Pass 2 recompresses the now-correctly-prefixed
image for real. Since the field being patched sits in the region that is
never itself compressed, this is mathematically guaranteed to converge
in exactly two passes -- no iteration needed. `write_main_code_region`
(the pre-existing single-edit function) is now a thin wrapper calling
this with a one-element list. This also batches every hidden_item write
into a single decompress/recompress pass instead of one pass per
location -- the "every location substitutable" test dropped from ~34
minutes to seconds.

**`rom/hiddenitemdata.py`**: new `write_hidden_item_substitutions(rom,
substitutions: dict[str, str | None])`, batched via `write_main_code_
regions`, supporting the same `None` "empty" sentinel as ground_item/
npc_gift/hm_tm.

**Reconnected**: `hidden_item` is back in `output_patch._SUBSTITUTABLE_
LOCATION_TYPES` and `location_flags.build_locally_substituted_ap_
location_ids()` (the double-delivery-bug fix above now covers it too --
forgetting to add a newly-reconnected type there would silently
reintroduce that exact bug). `locations.py`'s `SHELVED_LOCATION_TYPES`
mechanism (kept as reusable infrastructure, currently `set()`) is what
`hidden_item` used while excluded, generalized from the earlier
starters-specific removal so any future type needing the same treatment
doesn't need bespoke plumbing.

**New regression test**: `tests/test_hidden_item_substitution.py`'s
`test_bulk_substitution_keeps_compressed_static_end_in_sync` reads the
field directly after a real bulk substitution and asserts it matches the
actual recompressed size -- the specific failure mode this section
documents.

**Status**: fixed and verified via rigorous offline forensics (byte-
delta math, round-trip decompress/recompress checks) -- not yet
confirmed via an actual live BizHawk boot of a real patched ROM with
hidden_item substitutions active. That live confirmation is the explicit
condition the user set before starting the `apnds` migration (see
`docs/scope.md` and this project's own task tracking).

## v0.1.1 batch: constrained undetectable locations, trainer levels/types, client.py cleanup, SoulSilver (2026-08-11)

Follow-up work after the community feedback round and the SDK_
COMPRESSED_STATIC_END fix above, all still uncommitted locally pending
the v0.1.1 release (per the user's own explicit "batch until release"
instruction).

**B1 -- 30 undetectable npc_gift/hm_tm locations constrained, not
excluded**: rather than dropping the 30 locations identified in the
"Community feedback round" section from the AP pool entirely (the
`hidden_item`/starters treatment), `__init__.py`'s new `_constrain_
undetectable_locations(player, multiworld)` sets `item_rule` on exactly
those 30 so they can only ever hold *this* player's own non-progression
items. This keeps all 30 as real, playable checks (local delivery
already worked correctly for them) while eliminating the actual risk: a
remote player's item, or a progression item, landing on a location whose
completion this project's client-side check-detection can never confirm
back to the server.

**B4 -- duplicate `write_party_entry` call**: `rom/trainerdata.py` had
one trainer-party-writing code path invoking `write_party_entry` twice
for the same slot (a leftover from an earlier edit) -- harmless when both
calls agreed, but pure waste and a landmine for any future edit that
touched one call site and not the other. Removed the duplicate.

**C1/C2/C3 -- three v2 features pulled forward into v1** (all off-by-
default `options.py` toggles, approved by the user as "simple, additive"
work suitable for this release rather than the full v2 backlog):
- **Trainer level scaling** (`trainer_level_scaling`, `Range` 50-200,
  default 100): `species.scale_trainer_levels(scale_percent, trainers)`
  is a deterministic percentage scale (not RNG-driven), clamped to
  1-100 in-game. `rom/trainerdata.write_party_levels` writes the result
  -- level lives at offset 2 within each `TRPOKE` slot (`u8 difficulty;
  u8 genderAbilityOverride; u16 level; u16 species;`), a fact already
  established for species substitution in the M4.5 section above, reused
  here for the level field specifically.
- **Move type randomization** (`randomize_move_types`, `Toggle`):
  `species.randomize_move_types(rng, enabled, moves)` draws a new type
  per move, uniformly from the 17 real types -- **never** "mystery"
  (type id 9, "???", not a real move type any hand-designed move should
  land on). `rom/movedata.TYPE_NAME_TO_ID` (18 entries, matched against
  decomp's `include/constants/pokemon.h`) and `write_type` write it --
  offset 4 within each 16-byte move struct, live-verified against all
  467 real moves in the ROM with zero mismatches.
- **Species type randomization** (`randomize_species_types`, `Toggle`):
  `species.randomize_species_types(rng, enabled, species)` preserves
  each species' mono/dual-type structure (a mono-type species stays
  mono-type, just with a different single type; a dual-type species
  draws 2 *distinct* types via `rng.sample`) -- also never draws
  "mystery". `rom/speciesdata.write_types`/`read_types` write/read
  offsets 6/7 of the `BaseStats` struct (`personal.narc`), live-verified
  against all 505 real species' type bytes with zero mismatches
  (confirming mono-type species really do have `type1 == type2` in the
  vanilla data, as the randomizer's own preservation logic assumes).

All three are wired into `__init__.py`'s `set_rules()` immediately after
their respective base randomizers, and covered by both `tests/test_
randomization.py` (pure-computation tests) and `tests/test_patch_gen.py`
(real-ROM write-and-read-back integration tests).

**client.py review, prompted directly by community feedback**: a
tester's independent code review ("projects that rely heavily on LLMs...
tend to heavily overengineer and overcomment things... the solution for
finding the save data isn't great, and it looks like it's going to be
flaky") was taken at face value and acted on, not dismissed:
- Removed genuinely dead code: `HEARTGOLD_SAVE_DATA_ADDRESS_ENV`,
  `HEARTGOLD_SAVE_LAYOUT_CASE_ENV`, `_resolve_save_data_address`,
  `_resolve_save_layout_case_name`, `_missing_configuration_message`,
  and the unused `CANDIDATE_OFFSETS` import -- all leftover from an
  earlier, since-abandoned address-resolution approach.
- Merged `_resolve_bag_base_address_override`/`_resolve_flags_array_
  address_override` (near-identical bodies) into one `_resolve_address_
  override(env_var)`.
- Trimmed the module docstring from ~86 to ~28 lines -- it had
  accumulated restated detail already covered by individual function
  docstrings, exactly the "overcomment" pattern named in the feedback.
- **The real bug** the "flaky" comment pointed at: `_locate_save_
  addresses`'s `arrayHeaders` scan (looking for 5 sequential ints 0-4)
  is a real signature but not a *unique* one across a 64KB scan window --
  the old code trusted the first match unconditionally. New `_find_
  array_headers_candidates(data)` returns every match instead of just
  the first; new `_bag_looks_plausible(ctx, bag_address)` reads
  `_PLAUSIBILITY_CHECK_SLOT_COUNT` (8) `ItemSlot` entries at a
  candidate's derived Bag address and checks each looks like real data
  (`item_id == 0`, or `1 <= item_id <= _MAX_PLAUSIBLE_ITEM_ID` (536)
  with `quantity <= _MAX_PLAUSIBLE_ITEM_QUANTITY` (999)); `_locate_save_
  addresses` now tries every candidate in signature order until one
  passes plausibility, instead of trusting the first blindly. New
  regression test `test_locate_save_addresses_skips_an_implausible_
  candidate_for_a_later_one` hand-builds a two-candidate scan window
  (one garbage, one real-looking) to confirm the skip actually happens.

**build.py / archipelago.json corrections**, prompted by a second piece
of direct feedback ("ton fichier `build.py` ne devrait pas être
nécessaire... mentionne également `make` et `curl`, qui ne sont pas
utilisés par AP"): confirmed Archipelago's own native "Build APWorlds"
tool (`worlds/LauncherComponents.py`'s `_build_apworlds`) uses standard
`GitIgnoreSpec`, compatible with this project's existing `.apignore`,
and that `worlds/__init__.py`'s `load()` does `manifest.pop("compatible_
version", None)` when loading a world -- confirming that field has zero
functional effect, so this project's stale `compatible_version: 5` (now
corrected to `7`, matching the native tool's own hardcoded value) was
cosmetically wrong but never actually broken anything. The native tool
itself needs the world already installed inside a real Archipelago
`worlds/` folder, so it isn't usable standalone in CI or for a quick
local rebuild -- `build.py` stays for that purpose, but its docstring no
longer claims `make`/`curl` are used (they never were) and now
recommends the native tool for real releases.

## SoulSilver support (2026-08-11)

Requested directly by the user, who supplied a legally-dumped US
SoulSilver ROM locally. Chosen architecture (`AskUserQuestion`, "Un seul
monde, deux ROMs acceptées"): **one** Archipelago world (`game =
"Pokemon HeartGold"` stays unchanged -- renaming it would be a breaking
change to every existing YAML/spoiler log referencing it) that accepts
*either* ROM via dual-MD5 validation, rather than a second, parallel
world.

**Why this was tractable without a parallel implementation**:
reconnaissance found HeartGold and SoulSilver share near-identical
internal structure -- identical decompressed ARM9 length (1,122,040
bytes both), identical NitroFS numbered-path sub-file counts across
every table this project reads (items 514, species 508, trdata/trpoke
738 each, moves 471, hidden_item_script 965), the hidden_item ARM9 table
at the exact same RAM address with plausible content in both, and
`SDK_COMPRESSED_STATIC_END` self-consistent for SoulSilver too. Every
existing offset/struct assumption this project already relies on for
HeartGold holds for SoulSilver without modification.

**`rom/__init__.py`**: `SOULSILVER_US_MD5`, `SOULSILVER_US_ID_CODE =
b"IPGE"` alongside the existing HeartGold constants; `_VERSION_BY_MD5`/
`_ID_CODE_BY_VERSION` lookup tables; `HeartGoldRom.version: str | None`
set during `open()`. `_validate_size_and_hash` now returns the detected
version string (or `None` when `expect_vanilla=False`, i.e. opening an
already-patched ROM where no vanilla hash can match). `_validate_game_
code()` checks the version-appropriate expected id code when the version
is known, or that the id code is one of the known values when it isn't.

**Every other MD5/id-code check point extended to a list/tuple of both
values**, not a version-branching rewrite: `client.py`'s `validate_rom`
(`bytes(id_code) not in (HEARTGOLD_US_ID_CODE, SOULSILVER_US_ID_CODE)`),
`output_patch.HeartGoldProcedurePatch.hashes` (`[HEARTGOLD_US_MD5,
SOULSILVER_US_MD5]`), `__init__.py`'s `HeartGoldSettings.RomFile.md5s`
(same list) -- `settings.UserFilePath.md5s` already accepted a list of
valid hashes, so no new settings mechanism was needed at all.

**Verified against the real SoulSilver ROM file**, not just structural
reconnaissance: `tests/test_rom_access.py` gained a `soulsilver_rom_
bytes` fixture (same skip-cleanly-if-env-var-unset convention as the
existing `HEARTGOLD_ROM_PATH` one, new `SOULSILVER_ROM_PATH`) and 4
dedicated tests (open, decompressed ARM9 length match, NARC sub-file
count match, hidden_item table address match) -- all pass against the
real file. The full fast suite (283 tests, excluding the ~9-minute
hidden_item bulk-substitution test) also passes unchanged with both ROM
env vars set, confirming no HeartGold-only regression. Beyond the ROM-
access layer, the full `generate_output()` -> `.patch()` pipeline was
run end-to-end against the real SoulSilver ROM specifically (not just
HeartGold): a real seed's trainer/species/move randomization was
generated, written to a `.apheartgold`, and patched onto the SoulSilver
ROM, producing a correctly-sized `.nds` whose species base stats, types,
and move stats/types all matched the computed randomization exactly --
mirroring `tests/test_generate_output.py`'s existing HeartGold
integration test, just targeted at the other ROM.

## Wild-encounter version bug: found and fixed (2026-08-11, local)

Found immediately after "SoulSilver support" above shipped as v0.1.1: that
work fixed ROM *validation and patching plumbing* only (dual-MD5 accept,
version-agnostic NitroFS offsets everywhere they genuinely are
version-agnostic) -- it never touched wild-encounter *data*, which turned
out to still be silently HeartGold-only end to end. Not a hypothetical: a
SoulSilver player generating with the default options (`randomize_wild_
pokemon: vanilla`, i.e. the common case of a player who wants everything
*except* wild encounters randomized) got a patched ROM whose wild
encounters were, for a real subset of slots, silently HeartGold's data
instead of SoulSilver's own vanilla data.

**Root cause, two independent layers, both needed fixing:**

1. **Data layer.** `data_gen/encounters.toml`'s own header claimed "this
   project targets HeartGold only... the SoulSilver-only value is always
   dropped -- this file has no version-conditional data left". True when
   written (HeartGold-only project), false once SoulSilver shipped as a
   supported ROM. Re-parsing the decomp source directly
   (`ressources/Decomposition/pokeheartgold/files/fielddata/encountdata/
   gs_enc_data.json`, `files/arc/headbutt.json`) found 643 + 79 = 722 raw
   `{"HEARTGOLD": ..., "SOULSILVER": ...}` (`gs_enc_data.json`) /
   `{"gold": ..., "silver": ...}` (`headbutt.json`) leaf divergences across
   both files' full contents; restricted to the 137 zones this project
   actually models (and to the fields this project's toml schema actually
   tracks -- `landSwarm`/`hoenn`/`sinnoh` arrays are decomp fields with no
   equivalent in this project's schema and were left untouched), 622 + 77 =
   699 fields genuinely diverge. Verified example: Route 29 (`R29`), land
   slot 7 is `{level: 2, morn: SENTRET}` in HeartGold vs `{level: 4, morn:
   RATTATA}` in SoulSilver (`day`/`nite` unaffected at that slot).
   `species.py`'s `randomize_wild_encounters(..., encounters=ENCOUNTERS)`
   (the `WILD_VANILLA` default just returns `encounters` unchanged) always
   read this HeartGold-only table regardless of the actual target ROM.

2. **ROM-write layer, found while writing this fix's own integration
   test -- more severe than the data layer alone.** Even with correct
   per-version data available, `rom/encounterdata.py` hardcoded
   `HEARTGOLD_NITROFS_PATH` (`a/0/3/7`, i.e. `g_enc_data.narc`) for every
   read/write, regardless of which ROM was open. The decomp's own
   `include/encounter_tables_narc.h` resolves which of `g_enc_data.narc`
   (`a/0/3/7`) / `s_enc_data.narc` (`a/1/3/6`) the *compiled game code*
   opens via a plain `#ifdef HEARTGOLD` -- a **compile-time**, not
   runtime, choice. Live-verified against both real US ROMs: `a/0/3/7`
   decodes to HeartGold's Route 29 values (morning Sentret) and `a/1/3/6`
   to SoulSilver's (morning Rattata) *identically in both ROM files* --
   confirming both NARCs ship in every HGSS ROM regardless of cartridge
   version (dead weight for whichever table that cartridge's own code
   doesn't read), each with build-time-baked, version-correct content.
   Practical consequence: even a hypothetical fix that only addressed
   layer 1 above would have kept writing correct SoulSilver *data* into
   the wrong NitroFS file on a SoulSilver ROM -- a file that ROM's own
   compiled game code never reads at runtime, making the "fix" a no-op in
   actual play.

**The fix, four parts:**

- `data_gen/encounters.toml`: re-extracted via a one-shot migration
  script (scratchpad-only, not part of the permanent `data_gen_templates/`
  pipeline -- this was a one-time data migration, not a recurring
  generation step). Guard-railed: for every one of the 137 zones, the
  script's own HEARTGOLD-branch extraction from the raw JSON was asserted
  byte-for-byte identical to the toml's pre-existing (curated) value
  before writing anything -- confirmed clean for all 137 zones, 0
  mismatches, before the file was regenerated. Wherever a field
  genuinely diverges, its plain scalar became a `{ heartgold = ...,
  soulsilver = ... }` inline sub-table; non-divergent fields (the large
  majority) stayed untouched plain scalars, keeping the diff/file
  readable. 3 zones (`route_16`/`R16`, `pewter`/`T03`, `azalea`/`T23`)
  have no `gs_enc_data.json` entry at all (headbutt-only, per this
  file's own header) -- their all-zero land/surf/rock_smash/fishing
  tables were verified all-zero/empty first, then carried through
  unchanged; only their headbutt tables went through the same
  dual-version extraction as every other zone.
- `data_gen_templates/encounters.py`: `_build_land_slots`/
  `_build_flat_slots`/`_build_zone` take a `version: Literal["heartgold",
  "soulsilver"]` parameter and resolve each field via a `_resolve` helper
  (dict with exactly `{heartgold, soulsilver}` keys -> pick the branch;
  anything else -> use as-is for both versions). `generate_encounters()`
  now emits `ENCOUNTERS_HEARTGOLD` and `ENCOUNTERS_SOULSILVER` (each
  fully resolved, no trace of the dual-value schema left in the output)
  plus `ENCOUNTERS = ENCOUNTERS_HEARTGOLD` as a compatibility alias for
  every existing caller (notably `species.py`'s `randomize_wild_
  encounters` default parameter).
- `options.py`: new `GameVersion` Choice option (`option_heartgold`
  default, `option_soulsilver`), its own `OptionGroup`. `__init__.py`'s
  `set_rules()` picks `ENCOUNTERS_HEARTGOLD`/`ENCOUNTERS_SOULSILVER`
  based on it before calling `randomize_wild_encounters`.
- `rom/encounterdata.py`: every function that reads/writes the wild-
  encounter NARC (`read_all`/`write_all`/`read_entry`/`write_entry`, and
  therefore `write_zone_encounters`, which delegates to them) now picks
  its NitroFS path via a new `_nitrofs_path_for(rom)` helper keyed on
  `rom.version` (`"soulsilver"` -> `s_enc_data.narc`, anything else,
  including `None` for an already-patched ROM re-opened with `expect_
  vanilla=False` -> `g_enc_data.narc`, the pre-existing default,
  preserved for backward compatibility). `output_patch.py`'s `.patch()`
  writes a small `game_version.json` blob into the `.apheartgold` at
  generation time (the player's *declared* version) and, after opening
  the real target ROM, compares it against `rom.version` (the ROM's
  *actual* version, from its own MD5): a mismatch raises `rom.RomError`
  (the existing base exception type, no new type introduced) with an
  actionable message naming both the declared and actual version and
  telling the player which option to change or which ROM to configure --
  closing the loop so a wrong `game_version` fails loudly at patch time
  instead of silently writing the wrong version's data (or, pre-2026-08-
  11, the wrong NitroFS file entirely) into a real ROM.

**Tests** (`tests/test_encounters.py`, `tests/test_options.py`,
`tests/test_generate_output.py`): `ENCOUNTERS_HEARTGOLD`/`ENCOUNTERS_
SOULSILVER` both exist and differ (Route 29 slot 7 exact values), `
ENCOUNTERS is ENCOUNTERS_HEARTGOLD` alias, dual-field count sanity-checked
(650-750, actual 699) via a structural diff of the two generated dicts
independent of the toml's own bookkeeping; `game_version` option
defaults/values; two real-ROM integration tests --
`test_game_version_mismatch_raises_actionable_error` (generate for
`heartgold` default, patch against the real SoulSilver ROM, confirm
`RomError` is raised, not a silent miswrite or a bare crash) and
`test_soulsilver_wild_encounters_match_soulsilver_values` (generate for
`game_version=soulsilver`, patch against the real SoulSilver ROM, read
back `s_enc_data.narc` directly by path -- `rom.version` comes back
`None` after the required `expect_vanilla=False` re-open, so the test
reads the known path directly rather than relying on `_nitrofs_path_for`'s
version-based default -- and confirm Route 29 slot 7 decodes to Rattata,
not Sentret). All pass against the real US ROMs on this machine.

**Left alone, confirmed not needed**: no rule in `rules.py`/`data_gen/
rules.toml` conditions on a specific wild species (zero "encounter"/
"wild"/"headbutt" references found) -- this was purely a fidelity bug
(the wrong game's data ends up in a real ROM), never a logic/completion-
blocking one. `randomize_wild_pokemon` set to anything other than
`vanilla` was already unaffected in practice for the *content* of what
gets shuffled/randomized (a full permutation or full-random draw doesn't
care which vanilla baseline it started from) -- the fidelity gap was
real regardless, but strictly worse the closer to `vanilla` a player's
own settings were, worst exactly at the default.

## ndspy -> apnds migration (2026-08-11)

The last pillar of the v0.1.1 release, sequenced explicitly after the
SoulSilver work and both live BizHawk confirmations above (the user's own
condition -- "on preconisera le passage a apnds si le hidden_item
fonctionne est stable"): removing `ndspy` (GPLv3, could not legally be
bundled inside this MIT-licensed `.apworld` -- see "## Spikes", Spike 1's
correction paragraph, and the M6 ndspy/GPL section) in favor of `apnds`
0.2.4 (MIT, James Petersen), vendored directly into this repository so
the built `.apworld` needs zero separate install step -- the "copy ndspy
into `lib/` manually" workaround this project has documented since M6 is
gone entirely.

**Empirical validation before touching any code (a Planner-dispatched
plan's "A0" gate)**: rather than porting blind, every load-bearing
assumption was checked against both real ROMs first. Confirmed: `apnds.
rom.Rom.from_bytes` is silent (no stray `print()` output); `apnds.rom.
Rom.files` uses slash-prefixed keys unlike `ndspy`'s bare-path `getFile
ByName`/`setFileByName`; `apnds.rom.Rom.arm9` includes a 12-byte
"nitrocode" trailer (signature `2106C0DE` + an offset word + a reserved
word) that `ndspy`'s own `.arm9` never exposed; `apnds.lz.decompress_
code`/`compress_code` (the "backward code" algorithm) reproduce `ndspy.
codeCompression.decompress`/`compress(isArm9=True)` byte-for-byte on both
ROMs' full ~1.1 MB ARM9 image; the plain-LZ10 `apnds.lz.decompress`/
`compress` pair is the *wrong* algorithm for ARM9 overlays (raises
outright on real overlay data -- `decompress_code` is correct there too,
confirmed against the starter-selection overlay, id 61); and `apnds.
code.CodeStartParams.compressed_end`, found via signature search, is
*exactly* the `SDK_COMPRESSED_STATIC_END` field this project hand-
diagnosed and fixed earlier the same day -- same address (`0x02000BA0`),
same value, on both ROMs. This last point meant apnds' own high-level
`code` module could have replaced this project's whole manual two-pass-
compression fix outright (`get_sections`/`pack_code_from_sections`/
`write_start_info` round-tripped cleanly with zero edits in the spike),
but the migration deliberately did **not** take that path -- see below.

**Design decision: keep the existing `write_main_code_regions` algorithm,
only swap the compressor.** `apnds.code.CodeStartParams`'s higher-level
API also rewrites the autoload-section table on every repack, which is
strictly more surface area than this project's already-live-verified
fix needs to touch. `rom/__init__.py`'s `write_main_code_regions` keeps
its exact double-compression-pass structure (pass 1 learns the new
compressed length, patches `SDK_COMPRESSED_STATIC_END` into the never-
compressed secure-area prefix, pass 2 recompresses with the corrected
field) -- only `ndspy.codeCompression.decompress`/`compress(isArm9=True)`
were replaced by the equivalent apnds primitives. This was a deliberate
minimal-diff choice on top of a fix that had been live-confirmed working
on real hardware-adjacent emulation (BizHawk) just hours earlier, not an
oversight -- `CodeStartParams` remains available for later adoption if
ever needed (its own round-trip already checked out clean in the A0
spike), but was never load-bearing for this migration to succeed.

**The one genuinely new piece of engineering**: `apnds.rom.Rom.arm9`
folds the 12-byte nitrocode trailer *into* `arm9`, unlike `ndspy`. Every
existing caller of this class's own `arm9` property (`patch_gen.py`'s
ground-item-hook load-address arithmetic in particular) is written
against the trailer-*excluded* convention, so `HeartGoldRom.arm9` still
returns the trailer-excluded body (`_split_arm9_footer`), and the
trailer itself is regenerated -- not blindly copied through -- after
every `write_main_code_regions` call, via `apnds.code.get_start_info_
offset` (the same signature search apnds' own high-level API uses
internally). This was verified empirically before being trusted for real
writes: the `DSStartParams` structure the trailer's offset word points
at sits inside the never-edited, never-recompressed 0x4000-byte secure
area on both real ROMs, so a no-op edit (decompress -> recompress with
zero changes -> compare) reproduces the *exact* original trailer bytes,
confirmed on both HeartGold and SoulSilver before shipping.

**Verification, in layers**: 291 tests independently re-run (not just
the implementing agent's own report) against both real ROMs with `ndspy`
actually `pip uninstall`ed from the environment first -- including the
full `tests/test_hidden_item_substitution.py` (the 225-location bulk
substitution that originally surfaced the `SDK_COMPRESSED_STATIC_END`
bug), `tests/test_patch_gen.py`, and `tests/test_generate_output.py` --
all green, zero skips. `python build.py` rebuilt and independently
unzipped to confirm `apnds/*.py` genuinely sits inside the packaged
`.apworld`, not just present in the source tree.

**Real Archipelago install test found a second, unrelated bug**: after
installing the rebuilt `.apworld` into a real portable Archipelago
instance (`D:\Archipelago\custom_worlds`), the world still failed to
load -- but `D:\Archipelago\logs\Launcher_*.txt` showed `ModuleNotFound
Error: No module named 'data.locations'`, not anything apnds-related.
Root cause: `build.py` had been run at a moment when the gitignored,
dev-time-generated `data/` package didn't exist on disk (deleted by
`tests/test_generate_output.py`'s own `world_modules` fixture teardown,
which runs `shutil.rmtree(DATA_DIR)` after the test module finishes --
the full test suite had just been run, including that file, right after
the earlier build). `build.py`'s `whitelisted_paths()` silently
contributed zero files for a `.apignore`-whitelisted directory that
didn't exist at all, with no warning printed -- a real, if narrow, gap:
missing an *individual* whitelisted file already warned to stderr, but a
missing whitelisted *directory* did not. Fixed: `whitelisted_paths()`
now raises `RuntimeError` immediately if a whitelisted directory entry
doesn't exist, naming the directory and pointing at `data_gen.py` if it
looks like the `data/` case specifically -- turns this exact failure mode
into a loud build-time error instead of a silently-broken `.apworld`
that only fails once a real player tries to load it. Confirmed apnds
itself loaded without any import error in this same real-install test --
the only bug found was this unrelated packaging gap.

**Separately**: the Launcher's "Install APWorld" flow refuses to
overwrite an already-installed file of the same name (`Exception:
APWorld is already installed at ...`) -- documented as a new "Common
Issues" entry in `docs/setup_en.md`, since this could otherwise look like
a fix didn't take effect when it's really just a stale file never having
been replaced.
