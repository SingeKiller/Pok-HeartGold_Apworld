# Pokémon HeartGold — APWorld

Un monde [Archipelago](https://archipelago.gg) pour **Pokémon HeartGold**
(version US) : rencontres sauvages, équipes de dresseurs, évolutions,
stats de base, stats des capacités, objets au sol, cadeaux PNJ, CT/CS et
plus encore, tous randomisables et intégrés dans la logique du
multiworld. Voir [docs/scope.md](docs/scope.md) pour le détail exact de
ce qui est randomisé en v1 (et ce qui est prévu pour plus tard).

## Téléchargement

- **`.apworld` (à installer directement dans Archipelago)** :
  [dernière version](https://github.com/SingeKiller/Pok-HeartGold_Apworld/releases/latest/download/pokemon_heartgold.apworld)
  *(lien actif une fois la première release publiée — voir
  [CHANGELOG.md](CHANGELOG.md) pour l'état actuel)*.
- **Code source complet** (pour builder ou modifier en local) :
  [.zip](https://github.com/SingeKiller/Pok-HeartGold_Apworld/archive/refs/heads/main.zip) ·
  [.tar.gz](https://github.com/SingeKiller/Pok-HeartGold_Apworld/archive/refs/heads/main.tar.gz)
  (GitHub ne propose pas nativement de `.rar`).

## Installation rapide

1. Place `pokemon_heartgold.apworld` dans le dossier `custom_worlds` de
   ton installation Archipelago (pas dans `lib/worlds`).
2. Génère ton fichier d'options (YAML) via `Generate Templates` dans
   l'Archipelago Launcher, puis place-le dans le dossier `Players`.
3. Lance la génération normalement depuis le Launcher.

Guide complet, pas à pas (BizHawk, connexion au serveur, dépannage) :
[docs/setup_en.md](docs/setup_en.md).

## Builder / modifier en local

Ce dépôt ne contient que le nécessaire pour builder, faire tourner ou
modifier l'APWorld — pas les tests ni l'outillage de dev (gardés en local
via `.gitignore`, voir [docs/architecture.md](docs/architecture.md)).

```bash
python data_gen.py   # régénère data/ depuis data_gen/
python build.py      # produit pokemon_heartgold.apworld à la racine
```

Documentation complète de l'architecture et des choix techniques :
[docs/architecture.md](docs/architecture.md).

## Licence

[MIT](LICENSE).
