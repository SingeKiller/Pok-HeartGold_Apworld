# Pokémon HeartGold - APWorld

*[Version française](README.md)*

An [Archipelago](https://archipelago.gg) world for **Pokémon HeartGold
and SoulSilver** (US version): wild encounters, trainer parties,
evolutions, base stats, move stats, ground items (including hidden
items), NPC gifts, HMs/TMs, and more, all randomizable and integrated
into multiworld logic. What each version changed is in the
[CHANGELOG](CHANGELOG.md).

## Use of an LLM and manual work

This project is developed with the help of an LLM (an AI coding
assistant), used to write and analyse part of the code, the logic data
and the documentation. Nothing is published without my own work on it:

- **Review** of every change before it is published.
- **Reading of the main files**:
  - `client.py`: the BizHawk client (checks, item delivery, DeathLink);
  - `patch_gen.py`, `output_patch.py` and `rom/`: the ROM patch;
  - `data_gen/rules.toml`, `data_gen/regions.toml` and `locations.py`:
    the logic;
  - `__init__.py` and `options.py`: generation and the YAML options;
  - the READMEs, the CHANGELOG and `docs/`: the public texts.
- **Checks** of the logic and of player reports before each fix.
- **In-game testing** on an emulator (BizHawk), on both HeartGold and
  SoulSilver.
- **Manual edits and fixes**: reported bugs are reproduced, the code is
  edited and fixed by hand where needed, then checked again in game
  before it is published.

I take responsibility for everything published here. Please report any
problem in the [GitHub issues](https://github.com/SingeKiller/Pok-HeartGold_Apworld/issues).

## Download

- **`.apworld` (install directly into Archipelago)**:
  [latest release](https://github.com/SingeKiller/Pok-HeartGold_Apworld/releases/latest/download/poke_hgss.apworld).
  The game name to use in the YAML is `Pokemon HGSS Singe`.
- **Full source code** (to build or modify locally):
  [.zip](https://github.com/SingeKiller/Pok-HeartGold_Apworld/archive/refs/heads/main.zip) ·
  [.tar.gz](https://github.com/SingeKiller/Pok-HeartGold_Apworld/archive/refs/heads/main.tar.gz)
  (GitHub doesn't natively offer `.rar`).
- **Default YAML file** (if you can't get the Launcher to generate one
  for you): [`docs/Poke_HGSS.yaml`](docs/Poke_HGSS.yaml) -
  edit it with a text editor, then drop it in your Archipelago install's
  `Players` folder.

## Quick install

1. Put `poke_hgss.apworld` in your Archipelago install's
   `custom_worlds` folder (not `lib/worlds`). No separate install step is
   needed -- the ROM read/write dependencies are bundled directly inside
   the `.apworld`.
2. Generate your options file (YAML) via `Generate Templates` in the
   Archipelago Launcher, then place it in the `Players` folder -- or grab
   the [default YAML file](docs/Poke_HGSS.yaml) above directly
   if you'd rather not generate your own.
3. Run generation normally from the Launcher.

Full step-by-step guide (BizHawk, connecting to a server,
troubleshooting): [docs/setup_en.md](docs/setup_en.md).

## Building / modifying locally

This repository only contains what's needed to build, run, or modify the
APWorld, not tests or dev tooling (kept locally via `.gitignore`).

```bash
python data_gen.py   # regenerates data/ from data_gen/
python build.py      # produces poke_hgss.apworld at the repo root
```

## Acknowledgments

This project builds on the work of several open source projects:

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
  assembler used for the ROM patch's ARM hooks.
- [ArchipelagoMW/Archipelago](https://github.com/ArchipelagoMW/Archipelago) -
  the multiworld randomizer this world is built for.
- [DarthMDev/hgss_archipelago](https://github.com/DarthMDev/hgss_archipelago)
  and [EyeballSweat/hgss_archipelago](https://github.com/EyeballSweat/hgss_archipelago) -
  other HGSS Archipelago worlds reviewed for comparison while
  investigating a duplicate-item-delivery bug.

## License

[MIT](LICENSE).
