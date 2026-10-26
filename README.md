# Pokémon HeartGold - APWorld

*[English version](README.en.md)*

Un monde [Archipelago](https://archipelago.gg) pour **Pokémon HeartGold
et SoulSilver** (version US) : rencontres sauvages, équipes de dresseurs,
évolutions, stats de base, stats des capacités, objets au sol (y compris
les objets cachés), cadeaux PNJ, CT/CS et plus encore, tous randomisables
et intégrés dans la logique du multiworld. Le détail de chaque version est
dans le [CHANGELOG](CHANGELOG.md).

## Utilisation d'un LLM et travail manuel

Ce projet est développé avec l'aide d'un LLM (un assistant de
programmation basé sur l'IA), utilisé pour rédiger et analyser une
partie du code, des données de logique et de la documentation. Rien
n'est publié sans mon propre travail dessus :

- **Relecture** de chaque modification avant publication.
- **Lecture des fichiers principaux** :
  - `client.py` : le client BizHawk (checks, livraison des objets,
    DeathLink) ;
  - `patch_gen.py`, `output_patch.py` et `rom/` : le patch de la ROM ;
  - `data_gen/rules.toml`, `data_gen/regions.toml` et `locations.py` :
    la logique ;
  - `__init__.py` et `options.py` : la génération et les options YAML ;
  - les README, le CHANGELOG et `docs/` : les textes publics.
- **Vérifications** de la logique et des retours de joueurs avant chaque
  correction.
- **Tests en jeu** sur émulateur (BizHawk), sur HeartGold et SoulSilver.
- **Retouches et corrections manuelles** : les bugs signalés sont
  reproduits, le code est retouché et corrigé à la main quand il le faut,
  puis revérifié en jeu avant d'être publié.

J'assume la responsabilité de tout ce qui est publié ici. Signale tout
problème dans les [issues GitHub](https://github.com/SingeKiller/Pok-HeartGold_Apworld/issues).

## Téléchargement

- **`.apworld` (à installer directement dans Archipelago)** :
  [dernière version](https://github.com/SingeKiller/Pok-HeartGold_Apworld/releases/latest/download/poke_hgss.apworld).
  Le nom du jeu à mettre dans le YAML est `Pokemon HGSS Singe`.
- **Code source complet** (pour builder ou modifier en local) :
  [.zip](https://github.com/SingeKiller/Pok-HeartGold_Apworld/archive/refs/heads/main.zip) ·
  [.tar.gz](https://github.com/SingeKiller/Pok-HeartGold_Apworld/archive/refs/heads/main.tar.gz)
  (GitHub ne propose pas nativement de `.rar`).
- **Fichier YAML par défaut** (si tu n'arrives pas à en générer un
  toi-même via le Launcher) :
  [`docs/Poke_HGSS.yaml`](docs/Poke_HGSS.yaml) - à
  éditer avec un éditeur de texte puis à déposer dans le dossier
  `Players` de ton installation Archipelago.

## Installation rapide

1. Place `poke_hgss.apworld` dans le dossier `custom_worlds` de
   ton installation Archipelago (pas dans `lib/worlds`). Aucune autre
   installation n'est nécessaire (les dépendances de lecture/écriture de
   ROM sont embarquées directement dans le `.apworld`).
2. Génère ton fichier d'options (YAML) via `Generate Templates` ou via
   `option creator` dans l'Archipelago Launcher, puis place-le dans le
   dossier `Players` - ou récupère directement le
   [fichier YAML par défaut](docs/Poke_HGSS.yaml) ci-dessus si
   tu préfères ne pas en générer un toi-même.
3. Lance la génération normalement depuis le Launcher.

Guide complet, pas à pas (BizHawk, connexion au serveur, dépannage) :
[docs/setup_en.md](docs/setup_en.md).

## Builder / modifier en local

Ce dépôt ne contient que le nécessaire pour builder, faire tourner ou
modifier l'APWorld, pas les tests ni l'outillage de dev (gardés en local
via `.gitignore`).

```bash
python data_gen.py   # régénère data/ depuis data_gen/
python build.py      # produit poke_hgss.apworld à la racine
```

## Remerciements

Ce projet s'appuie sur le travail de plusieurs projets open source :

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
  ARM utilisé pour les hooks ARM du patch de la ROM.
- [ArchipelagoMW/Archipelago](https://github.com/ArchipelagoMW/Archipelago) -
  le randomizer multiworld sur lequel repose ce monde.
- [DarthMDev/hgss_archipelago](https://github.com/DarthMDev/hgss_archipelago)
  et [EyeballSweat/hgss_archipelago](https://github.com/EyeballSweat/hgss_archipelago) -
  mondes HGSS Archipelago consultés à titre de comparaison lors de
  l'investigation d'un bug de double-livraison d'objets.

## Licence

[MIT](LICENSE).
