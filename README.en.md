# Pokémon HeartGold — APWorld

*[Version française](README.md)*

An [Archipelago](https://archipelago.gg) world for **Pokémon HeartGold**
(US version): wild encounters, trainer parties, evolutions, base stats,
move stats, ground items, NPC gifts, HMs/TMs, and more — all randomizable
and integrated into multiworld logic. See [docs/scope.md](docs/scope.md)
for the exact v1 scope (and what's planned for later).

## Download

- **`.apworld` (install directly into Archipelago)**:
  [latest release](https://github.com/SingeKiller/Pok-HeartGold_Apworld/releases/latest/download/pokemon_heartgold.apworld)
  *(link goes live once the first release is published — see
  [CHANGELOG.md](CHANGELOG.md) for the current state)*.
- **Full source code** (to build or modify locally):
  [.zip](https://github.com/SingeKiller/Pok-HeartGold_Apworld/archive/refs/heads/main.zip) ·
  [.tar.gz](https://github.com/SingeKiller/Pok-HeartGold_Apworld/archive/refs/heads/main.tar.gz)
  (GitHub doesn't natively offer `.rar`).

## Quick install

0. **Important prerequisite: the `ndspy` Python library.** This world
   needs it to read/patch the ROM. If you're using the official Windows
   Archipelago release (the common case), it's a portable build with no
   accessible `pip` — you'll need to manually copy the `ndspy` folder
   (pure Python, get it via `pip download ndspy --no-deps -d .` then
   extract, or from [its repo](https://github.com/RoadrunnerWMC/ndspy))
   into `<your Archipelago install>\lib\`, next to the `worlds\` folder.
   Without this step, HeartGold won't show up in any option list at all.
   Full details in [docs/setup_en.md](docs/setup_en.md).
1. Put `pokemon_heartgold.apworld` in your Archipelago install's
   `custom_worlds` folder (not `lib/worlds`).
2. Generate your options file (YAML) via `Generate Templates` in the
   Archipelago Launcher, then place it in the `Players` folder.
3. Run generation normally from the Launcher.

Full step-by-step guide (BizHawk, connecting to a server,
troubleshooting): [docs/setup_en.md](docs/setup_en.md).

## Building / modifying locally

This repository only contains what's needed to build, run, or modify the
APWorld — not tests or dev tooling (kept locally via `.gitignore`, see
[docs/architecture.md](docs/architecture.md)).

```bash
python data_gen.py   # regenerates data/ from data_gen/
python build.py      # produces pokemon_heartgold.apworld at the repo root
```

Full architecture and design-decision documentation:
[docs/architecture.md](docs/architecture.md).

## License

[MIT](LICENSE).
