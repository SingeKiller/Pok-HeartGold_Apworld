# Pokémon HeartGold - APWorld

*[Version française](README.md)*

An [Archipelago](https://archipelago.gg) world for **Pokémon HeartGold
and SoulSilver** (US version): wild encounters, trainer parties,
evolutions, base stats, move stats, ground items (including hidden
items), NPC gifts, HMs/TMs, and more, all randomizable and integrated
into multiworld logic. See [docs/scope.md](docs/scope.md)
for the exact v1 scope (and what's planned for later).

## Download

- **`.apworld` (install directly into Archipelago)**:
  [latest release](https://github.com/SingeKiller/Pok-HeartGold_Apworld/releases/latest/download/pokemon_heartgold.apworld)
  *(link goes live once the first release is published, see
  [CHANGELOG.md](CHANGELOG.md) for the current state)*.
- **Full source code** (to build or modify locally):
  [.zip](https://github.com/SingeKiller/Pok-HeartGold_Apworld/archive/refs/heads/main.zip) ·
  [.tar.gz](https://github.com/SingeKiller/Pok-HeartGold_Apworld/archive/refs/heads/main.tar.gz)
  (GitHub doesn't natively offer `.rar`).
- **Default YAML file** (if you can't get the Launcher to generate one
  for you): [`docs/Pokemon HGSS.yaml`](docs/Pokemon%20HGSS.yaml) -
  edit it with a text editor, then drop it in your Archipelago install's
  `Players` folder.

## Quick install

1. Put `pokemon_hgss.apworld` in your Archipelago install's
   `custom_worlds` folder (not `lib/worlds`). No separate install step is
   needed -- the ROM read/write dependencies are bundled directly inside
   the `.apworld`.
2. Generate your options file (YAML) via `Generate Templates` in the
   Archipelago Launcher, then place it in the `Players` folder -- or grab
   the [default YAML file](docs/Pokemon%20HGSS.yaml) above directly
   if you'd rather not generate your own.
3. Run generation normally from the Launcher.

Full step-by-step guide (BizHawk, connecting to a server,
troubleshooting): [docs/setup_en.md](docs/setup_en.md).

## Building / modifying locally

This repository only contains what's needed to build, run, or modify the
APWorld, not tests or dev tooling (kept locally via `.gitignore`, see
[docs/architecture.md](docs/architecture.md)).

```bash
python data_gen.py   # regenerates data/ from data_gen/
python build.py      # produces pokemon_hgss.apworld at the repo root
```

Full architecture and design-decision documentation:
[docs/architecture.md](docs/architecture.md).

## Acknowledgments

This project builds on the work of several open source projects:

- [pret/pokeheartgold](https://github.com/pret/pokeheartgold) - the
  HeartGold/SoulSilver decomp, source of the memory addresses, symbols,
  and data structures used throughout this project.
- [ljtpetersen/platinum_archipelago](https://github.com/ljtpetersen/platinum_archipelago)
  (MIT) - architectural reference for how a Gen4 Pokémon Archipelago
  world is structured.
- [ljtpetersen/apnds](https://github.com/ljtpetersen/apnds) (MIT) - NDS
  ROM read/write library, vendored directly into this repo (`apnds/`) so
  the `.apworld` works with no manual install step for players.
- [RoadrunnerWMC/ndspy](https://github.com/RoadrunnerWMC/ndspy) (GPLv3) -
  used for the same role through most of development, before the
  migration to `apnds`.
- [Kingcom/armips](https://github.com/Kingcom/armips) (MIT) - ARM
  assembler used while prototyping an ARM-hook patching approach (see
  [docs/architecture.md](docs/architecture.md)).
- [ArchipelagoMW/Archipelago](https://github.com/ArchipelagoMW/Archipelago) -
  the multiworld randomizer this world is built for.
- [DarthMDev/hgss_archipelago](https://github.com/DarthMDev/hgss_archipelago)
  and [EyeballSweat/hgss_archipelago](https://github.com/EyeballSweat/hgss_archipelago) -
  other HGSS Archipelago worlds reviewed for comparison while
  investigating a duplicate-item-delivery bug.

## License

[MIT](LICENSE).
