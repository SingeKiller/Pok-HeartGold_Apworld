# Pokémon HeartGold - APWorld

*[English version](README.en.md)*

Un monde [Archipelago](https://archipelago.gg) pour **Pokémon HeartGold
et SoulSilver** (version US) : rencontres sauvages, équipes de dresseurs,
évolutions, stats de base, stats des capacités, objets au sol (y compris
les objets cachés), cadeaux PNJ, CT/CS et plus encore, tous randomisables
et intégrés dans la logique du multiworld. Voir [docs/scope.md](docs/scope.md) pour le détail exact de
ce qui est randomisé en v1 (et ce qui est prévu pour plus tard).

## Téléchargement

- **`.apworld` (à installer directement dans Archipelago)** :
  [dernière version](https://github.com/SingeKiller/Pok-HeartGold_Apworld/releases/latest/download/pokemon_heartgold.apworld)
  *(lien actif une fois la première release publiée, voir
  [CHANGELOG.md](CHANGELOG.md) pour l'état actuel)*.
- **Code source complet** (pour builder ou modifier en local) :
  [.zip](https://github.com/SingeKiller/Pok-HeartGold_Apworld/archive/refs/heads/main.zip) ·
  [.tar.gz](https://github.com/SingeKiller/Pok-HeartGold_Apworld/archive/refs/heads/main.tar.gz)
  (GitHub ne propose pas nativement de `.rar`).
- **Fichier YAML par défaut** (si tu n'arrives pas à en générer un
  toi-même via le Launcher) :
  [`docs/Pokemon HGSS.yaml`](docs/Pokemon%20HGSS.yaml) - à
  éditer avec un éditeur de texte puis à déposer dans le dossier
  `Players` de ton installation Archipelago.

## Installation rapide

1. Place `pokemon_hgss.apworld` dans le dossier `custom_worlds` de
   ton installation Archipelago (pas dans `lib/worlds`). Aucune autre
   installation n'est nécessaire (les dépendances de lecture/écriture de
   ROM sont embarquées directement dans le `.apworld`).
2. Génère ton fichier d'options (YAML) via `Generate Templates` ou via
   `option creator` dans l'Archipelago Launcher, puis place-le dans le
   dossier `Players` - ou récupère directement le
   [fichier YAML par défaut](docs/Pokemon%20HGSS.yaml) ci-dessus si
   tu préfères ne pas en générer un toi-même.
3. Lance la génération normalement depuis le Launcher.

Guide complet, pas à pas (BizHawk, connexion au serveur, dépannage) :
[docs/setup_en.md](docs/setup_en.md).

## Builder / modifier en local

Ce dépôt ne contient que le nécessaire pour builder, faire tourner ou
modifier l'APWorld, pas les tests ni l'outillage de dev (gardés en local
via `.gitignore`, voir [docs/architecture.md](docs/architecture.md)).

```bash
python data_gen.py   # régénère data/ depuis data_gen/
python build.py      # produit pokemon_hgss.apworld à la racine
```

Documentation complète de l'architecture et des choix techniques :
[docs/architecture.md](docs/architecture.md).

## Remerciements

Ce projet s'appuie sur le travail de plusieurs projets open source :

- [pret/pokeheartgold](https://github.com/pret/pokeheartgold) - le decomp
  HeartGold/SoulSilver, source des adresses mémoire, symboles et
  structures de données utilisés dans tout ce projet.
- [ljtpetersen/platinum_archipelago](https://github.com/ljtpetersen/platinum_archipelago)
  (MIT) - référence architecturale pour la structuration d'un monde
  Archipelago Gen4 Pokémon.
- [ljtpetersen/apnds](https://github.com/ljtpetersen/apnds) (MIT) -
  bibliothèque de lecture/écriture de ROM NDS, vendorée directement dans
  ce dépôt (`apnds/`) pour que le `.apworld` fonctionne sans aucune
  installation manuelle côté joueur.
- [RoadrunnerWMC/ndspy](https://github.com/RoadrunnerWMC/ndspy) (GPLv3) -
  utilisée durant une bonne partie du développement pour le même rôle,
  avant la migration vers `apnds`.
- [Kingcom/armips](https://github.com/Kingcom/armips) (MIT) - assembleur
  ARM utilisé lors des essais de patch par hooks ARM (voir
  [docs/architecture.md](docs/architecture.md)).
- [ArchipelagoMW/Archipelago](https://github.com/ArchipelagoMW/Archipelago) -
  le randomizer multiworld sur lequel repose ce monde.
- [DarthMDev/hgss_archipelago](https://github.com/DarthMDev/hgss_archipelago)
  et [EyeballSweat/hgss_archipelago](https://github.com/EyeballSweat/hgss_archipelago) -
  mondes HGSS Archipelago consultés à titre de comparaison lors de
  l'investigation d'un bug de double-livraison d'objets.

## Licence

[MIT](LICENSE).
