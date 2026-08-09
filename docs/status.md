# État du projet & reprise — 2026-08-10 (mise à jour finale)

**Lire d'abord** : M4 est maintenant validé end-to-end en conditions
réelles. Un premier test d'intégration (T2) le 2026-08-10 avait trouvé
que l'adresse des flags "confirmée" la session précédente
(`0x0227D39C`) ne tenait pas dans la durée (voir
`docs/architecture.md`, section "T2 live integration test (2026-08-10)").
Un second essai la même session, avec une méthode de validation croisée
plus rigoureuse (plusieurs ramassages indépendants, positions
byte/bit prédites vérifiées, stabilité confirmée dans le temps), a
trouvé la bonne adresse : **`0x0227D340`** (voir "Second attempt, same
day" dans `docs/architecture.md`). Un test final bout-en-bout (serveur +
client réels, ROM patché, BizHawk réel) a confirmé **4 ramassages réels
sur 4 correctement détectés et remontés au serveur**, sans faux positif
(3 `ground_item` + 1 `npc_gift`). `client.py` a été mis à jour avec
cette adresse et commité.

Le reste de ce fichier (rédigé avant ces découvertes) décrit l'état
*avant* -- gardé pour l'historique de la procédure de recherche RAM, mais
l'adresse citée plus bas (`0x27D820`, candidate d'une session antérieure)
est obsolète : c'est `0x0227D340` qui est la valeur actuellement utilisée
par `client.py`.

## Ce qui reste avant de clore M4 formellement

- Injection d'items distants (`_apply_next_received_item`) : couverte par
  les tests unitaires, mais pas testée en direct cette session (il
  faudrait un deuxième slot joueur pour envoyer un item et vérifier sa
  réception réelle dans le sac).
- `hidden_item` reste hors scope (bloqueur séparé déjà documenté, table
  ARM9 statique).
- Passe Reviewer sur le changement final d'adresse, pas encore faite.

Ce document est fait pour être lu **en premier** par quiconque (humain ou
nouvelle session Claude sans mémoire de la conversation précédente) reprend
ce projet. `docs/architecture.md` contient l'historique technique détaillé
(spikes, décisions, investigations) — ce fichier-ci est un résumé
d'orientation + un plan d'action concret.

## Résumé ultra-rapide

APWorld Archipelago pour Pokémon HeartGold (US), repo
[github.com/SingeKiller/Pok-HeartGold_Apworld](https://github.com/SingeKiller/Pok-HeartGold_Apworld).
**M0 à M3 sont terminés et validés.** M4 (patch ROM + client BizHawk) est
**très avancé mais pas terminé** : un seul point bloque la boucle complète
check→serveur→réception.

Pour reprendre : lire ce fichier, puis `docs/architecture.md` sections
"## C14", "## C15" (si présente), "## C16" et son addendum "Manual
discovery session results" pour le détail technique complet.

## Ce qui marche, testé, committé (ne pas retoucher sans raison)

- **M0-M3** : socle projet, tooling, spikes, `data_gen` complet (505
  espèces, 467 attaques, 513 items, 450 régions, 586 locations, règles de
  logique), le monde Archipelago complet (`__init__.py`, items/locations/
  regions/rules/options/species), validé par zipimport réel d'un
  `.apworld` construit. 221+ tests, `ruff` clean.
- **M4 en cours** :
  - `rom/` (C13) — couche d'accès ROM (NitroFS via `ndspy`), validée sans
    corruption sur le ROM réel.
  - `armips` compilé et fonctionnel : `ressources/armips/build/armips.exe`
    (rebuild **statique** nécessaire — voir docs/architecture.md "## C14"
    Blocker 2 pour pourquoi).
  - Substitution locale des items (données ROM, sans ARM) : **308
    locations** couvertes (217 `ground_item` + 91 `npc_gift`/`hm_tm`),
    vérifiées bit-à-bit sur le ROM réel. `rom/eventscriptdata.py`,
    `rom/npcgiftdata.py`, `patch_gen.py`.
  - `client.py` (C16) — détection de check + injection d'items distants,
    structure de code prête, mais **une adresse RAM réelle manque encore**
    (voir ci-dessous).

## Le blocage actuel (la seule chose qui empêche M4 d'être fini)

`client.py` a besoin de connaître, en RAM réelle du jeu :
1. **`Bag`** (pour injecter les items reçus des autres joueurs) — **RÉSOLU
   ET CONFIRMÉ** : `0x27CDA0` en domaine BizHawk "Main RAM" (= `0x0227CDA0`
   côté "ARM9 System Bus"). Confirmé deux façons indépendantes (contenu
   direct : Potion x7 lue exactement à cette adresse ; recoupement avec la
   table `SaveData.arrayHeaders` du jeu lui-même). **Fiable, utilisable
   tel quel.**
2. **`SaveVarsFlags`** (pour détecter qu'un check vient d'être déclenché,
   via les flags de sauvegarde `FLAG_HIDE_ITEMBALL_*` etc.) — **NON
   RÉSOLU**. Une adresse candidate (`0x27D820`) était mathématiquement
   cohérente sur 3 recoupements différents, mais un test réel en jeu
   (ramassage de la Ball Antidote Route 30, flag id 1056, octet attendu à
   `0x27D8A4`) a montré que le bit **ne change pas** à cet endroit. Donc
   cette adresse est **fausse**, malgré des calculs qui semblaient se
   confirmer entre eux.

Plusieurs heures de recherche RAM manuelle (RAM Search de BizHawk, captures
d'écran, recherches différentielles avant/après) n'ont pas permis de
trouver la bonne adresse — trop de bruit (minuteurs, RNG, animations) pour
converger à l'œil.

## Plan de reprise concret (dans l'ordre)

### Étape 1 — Trouver `SaveVarsFlags` proprement, via un script Lua (pas la RAM Search GUI)

La RAM Search manuelle s'est avérée trop peu fiable (des dizaines de
milliers d'adresses "changées" à cause du bruit ambiant, impossible à
trier à l'œil). La bonne méthode : un **script Lua BizHawk** qui dump un
fichier binaire exact d'une plage mémoire ciblée, exécuté une fois avant
une action connue et une fois après, puis diffé **en Python, précisément**
plutôt qu'en lisant des captures d'écran.

Squelette de script à écrire (`Tools → Lua Console → New Script` dans
BizHawk) :

```lua
-- dump_savedata.lua
-- Usage: éditer OUTPUT_PATH avant chaque exécution (avant.bin / apres.bin)
local START = 0x27D540  -- adresse Main RAM du début du chunk SaveVarsFlags
local LENGTH = 0x450    -- 1104 octets (taille confirmée via arrayHeaders)
local OUTPUT_PATH = "E:/Users/Olivier/Desktop/dump_avant.bin"  -- changer en dump_apres.bin la 2e fois

local f = io.open(OUTPUT_PATH, "wb")
for i = 0, LENGTH - 1 do
    f:write(string.char(mainmemory.read_u8(START + i)))
end
f:close()
console.log("Dump written to " .. OUTPUT_PATH)
```

Procédure :
1. Charger ce script (l'écrire d'abord avec `OUTPUT_PATH` = `dump_avant.bin`).
2. L'exécuter juste **avant** de ramasser un objet connu (ex: une Ball pas
   encore prise — vérifier dans `data_gen/locations.toml` lesquelles ne
   sont pas encore ramassées dans la partie de test).
3. Ramasser l'objet.
4. Modifier `OUTPUT_PATH` en `dump_apres.bin`, ré-exécuter le script.
5. Donner les deux fichiers (ou leur contenu) à Claude — diff Python
   direct, fiable à 100%, pas d'erreur de lecture visuelle possible.

Si **rien** ne change dans cette plage précise (`0x27D540`-`0x27D994`),
c'est que le chunk entier est à la mauvaise adresse — élargir la plage du
script (ex: tout `0x27C000`-`0x28C000`, la zone probable du `SaveData`
complet) et reproduire le même avant/après pour localiser le vrai chunk
par diff pur, sans hypothèse de structure du tout.

### Étape 2 — Une fois `SaveVarsFlags` confirmé

1. Mettre à jour `save_layout.py`/`location_flags.py`/`client.py` avec
   l'adresse réelle (remplacer ou corriger le calcul qui a échoué).
2. Lancer un agent **Tester** pour valider (M4 = pas d'économie sur les
   tests, cf. politique établie dans la session précédente).
3. Committer.

### Étape 3 — `hidden_item` (bloqué séparément, moins urgent)

Table statique dans l'ARM9 (pas du bytecode NitroFS comme les autres
types), adresse ROM inconnue, même famille de blocage que C14. Peut
attendre après le reste de M4 — v1 peut sortir sans (231 hidden items
resteront vanilla, documenté comme limitation connue).

### Étape 4 — Finir M4

1. Brancher la détection de check confirmée dans `client.py::game_watcher`.
2. **T2 — test d'intégration réel** : générer une seed (`Generate.py` du
   framework Archipelago local), patcher une copie du ROM, lancer BizHawk
   avec `connector_bizhawk_generic.lua` + le client, vérifier qu'un check
   part vers le serveur et qu'un item halted arrive dans le sac.
3. Revue Reviewer de clôture M4.
4. Commit final, passer à M5 (build/CI) puis M6 (doc utilisateur/release).

## Détails d'environnement (pour ne pas les re-découvrir)

- ROM HeartGold US : `E:\Users\Olivier\Desktop\projet\Pokemon - HeartGold Version (USA).nds`
  (var d'env `HEARTGOLD_ROM_PATH`).
- `armips` : `E:\Users\Olivier\Desktop\projet\HeartGold\ressources\armips\build\armips.exe`
  (var d'env `ARMIPS_PATH`) — **build statique obligatoire**, sinon
  `STATUS_DLL_NOT_FOUND` selon le contexte d'invocation.
- Archipelago framework local : `E:\Users\Olivier\Desktop\projet\archipelago`
  (var d'env `ARCHIPELAGO_PATH`).
- BizHawk : `E:\Users\Olivier\Desktop\Bizhack\EmuHawk.exe` (core NDS =
  melonDS, "NDS": 2 dans `config.ini`).
- `.venv\Scripts\pip.exe` du dépôt a un shebang cassé (pointe vers un
  autre projet) — toujours utiliser `.venv\Scripts\python.exe -m pip`/
  `-m pytest`/`-m ruff` explicitement.
- Self-check standard avant tout commit :
  ```
  rm -rf data && .venv/Scripts/python.exe data_gen.py
  .venv/Scripts/python.exe -m pytest -q   # avec HEARTGOLD_ROM_PATH pour la suite complète
  .venv/Scripts/python.exe -m ruff check .
  ```

## Politique d'agents établie cette session (à respecter)

- **Tester/Reviewer obligatoires sur M4** (patch ROM/client — pas
  d'économie ici, contrairement au reste du projet où le self-check
  orchestrateur suffit pour les étapes mineures).
- Découper les grosses étapes en sous-lots plutôt qu'un seul agent géant.
- Sorties d'agents compactes (3-4 lignes) sauf fin de milestone ou bug
  récurrent.
- Ne jamais committer sans self-check vert (`pytest` + `ruff`).
- `ressources/` est en lecture seule, jamais committé, jamais modifié.
- Ne jamais toucher au ROM original — copies uniquement.

## Fichiers clés de cette investigation (déjà committés)

- `docs/architecture.md` — historique technique complet (spikes, C13-C16,
  section "Manual discovery session results" avec toutes les adresses
  trouvées/confirmées/infirmées).
- `save_layout.py` — modèle de la structure `SaveData` (contient encore
  l'ancien calcul théorique, **pas corrigé** cette session — à corriger
  une fois l'étape 1 ci-dessus faite).
- `location_flags.py` — mapping location → flag id.
- `client.py` — le client BizHawk, structure complète, attend juste les
  bonnes adresses via `HEARTGOLD_SAVE_DATA_ADDRESS`/
  `HEARTGOLD_SAVE_LAYOUT_CASE` (ou un patch direct une fois l'adresse
  réelle connue).
