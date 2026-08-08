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

## Reference projects (read-only, never committed)

- `ressources/Decomposition/pokeheartgold` — `pret/pokeheartgold` decomp.
  Source of ROM memory addresses, symbols and data structures.
- `ressources/platinum_archipelago` — `ljtpetersen/platinum_archipelago`
  (MIT). Architectural reference for how an Archipelago Gen4 Pokémon world is
  structured; not copied directly.
