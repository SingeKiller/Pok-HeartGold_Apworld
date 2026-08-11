# Rapport Optimizer - Chantier M4 (patch ROM + client BizHawk)

Date : 2026-08-10
Portée : bilan de coût (tokens) et diagnostic d'efficacité des agents sur
le chantier M4, de C13 (couche ROM) jusqu'à la réécriture finale de
`client.py` avec adresses RAM confirmées empiriquement.

**Sources.** Ce rapport n'a pas eu accès à des logs de tokens bruts (aucun
fichier de logs n'est committé dans le dépôt) ni aux 2 rapports précédents
de cette session (non committés non plus, uniquement des réponses de
chat). Les chiffres ci-dessous proviennent donc soit (a) du rappel fourni
par l'orchestrateur pour ce tour, soit (b) de l'inspection directe du
code/docs committés (`docs/status.md`, `docs/architecture.md`,
`client.py`). Chaque chiffre est marqué **[mesuré]** (rapporté par un
agent via son bloc RESULT, relayé par l'orchestrateur) ou **[estimé/non
mesuré]** (travail direct de l'orchestrateur, jamais instrumenté).

## 1. Sommaire exécutif

- Coût cumulé connu du chantier, du Planner jusqu'à la réécriture finale
  de `client.py` : **≈ 3,84 M tokens d'agents**, plus un Tester (résultat
  maintenant connu, voir §7) et **au moins deux postes de coût
  orchestrateur non mesurés** (fix armips, session RAM manuelle) qui ont
  mobilisé le contexte de la conversation principale pendant plusieurs
  heures.
- La politique "Tester/Reviewer obligatoire sur M4, self-check ailleurs"
  continue de bien fonctionner : aucun agent Coder de ce lot n'a livré de
  régression silencieuse, les paires Coder→Tester restent le poste de
  coût le plus prévisible (ratio Tester/Coder stable, ~25-35 %).
- Le pire ratio coût/valeur de ce lot est l'agent **Debugger** (160k
  tokens, `status: blocked`) sur l'écart de 1300 octets de
  `save_layout.py` : son diagnostic n'a pas été la cause du déblocage
  final (une méthode complètement différente, empirique, a résolu le
  problème), même si un de ses sous-résultats (le recoupement via
  `SaveData.arrayHeaders`) a été réutilisé en aval.
- L'enseignement principal : la **session manuelle interactive** (pas un
  agent - l'orchestrateur directement, captures d'écran BizHawk puis
  script Lua) a probablement coûté plus cher en tokens de **contexte de
  conversation principale** que n'importe quel agent de ce chantier, sans
  qu'aucun rapport ne puisse le chiffrer - c'est un angle mort structurel
  du système de reporting actuel.
- M5/M6 (build/CI, doc/release) n'impliquent ni ROM ni émulateur : ce sont
  des chantiers beaucoup plus faciles à cadrer efficacement avec la
  politique déjà en place (self-check orchestrateur, pas de Tester/
  Reviewer obligatoire sauf validation finale).

## 2. Bilan chiffré complet

### 2.1 Rappel - avant ce lot (jusqu'à C13)

| Poste | Tokens | Statut |
|---|---|---|
| Planner + C0-C16 (planification initiale) + Testers associés | **≈ 2,78 M** [rapporté, non re-vérifié ici] | Base des 2 rapports précédents de cette session |

### 2.2 Détail depuis C13 (ce lot)

| # | Étape | Agent(s) | Tokens Coder | Tokens Tester/autre | Total étape | Statut |
|---|---|---|---:|---:|---:|---|
| 1 | C14 - PoC hook ARM | Coder | 265 000 | - | **265 000** [mesuré] | `blocked` (2 blockers réels : DLL `armips` manquante, adresse ROM du point de hook introuvable) |
| 2 | Fix `armips` (rebuild statique) | Orchestrateur (pas d'agent) | - | - | **non mesuré** | Fait directement, résout Blocker 2 de C14 |
| 3 | Substitution locale étendue (`npc_gift`/`hm_tm`) | Coder + Tester | 150 000 | 52 000 | **202 000** [mesuré] | OK - 308 locations couvertes au total |
| 4 | C16 - `client.py` v1 (modèle théorique `save_layout.py`) | Coder + Tester | 288 000 | 72 000 | **360 000** [mesuré] | OK techniquement, mais bloqué sur adresse RAM manquante (documenté comme limite connue, pas un bug de l'agent) |
| 5 | Debugger - écart 1300 octets `save_layout.py` | Debugger | 160 000 | - | **160 000** [mesuré] | `blocked` - cause non trouvée complètement ; recommandation partiellement utile (piste `arrayHeaders`) |
| 6 | Session manuelle interactive BizHawk (captures d'écran + script Lua) | Orchestrateur (conversation principale, pas d'agent) | - | - | **non mesuré** | A fini par trouver les adresses réelles (Bag confirmé, flags confirmés) après plusieurs heures d'aller-retours |
| 7 | Réécriture `client.py` avec adresses confirmées | Coder | 35 000 | - | **35 000** [mesuré, plage 30-40k] | OK - contourne le modèle théorique cassé |
| 8 | Correction des tests en conséquence | Coder | 40 000 | - | **40 000** [mesuré] | OK |
| 9 | Validation finale | Tester | - | 26 306 | **26 306** [mesuré] | `status: ok` - 187 tests passés / 34 skipped, ruff clean, aucun résidu de l'ancien calcul base+offset (voir §7) |

**Sous-total agents mesurés depuis C13 : 265 000 + 202 000 + 360 000 +
160 000 + 35 000 + 40 000 + 26 306 = `1 088 306` tokens.**

### 2.3 Travail hors-agent (orchestrateur direct) - non mesuré, signalé explicitement

- **Fix `armips` (rebuild statique)** : intervention technique courte mais
  non instrumentée. Impact probable faible en tokens (action ciblée), mais
  strictement invisible aux rapports précédents.
- **Session manuelle BizHawk** (recherche RAM, captures d'écran itératives,
  puis script Lua de dump mémoire) : plusieurs heures d'aller-retours dans
  la conversation principale. Coût réel inconnu mais structurellement plus
  cher par tour que le texte pur (captures d'écran = tokens image + relecture
  répétée du même contexte à chaque itération), et cumulatif sur toute la
  durée de la session (contrairement à un agent, dont le contexte est
  jeté à la fin de sa tâche). **C'est le plus gros angle mort de ce
  rapport.**

### 2.4 Total cumulé (vue d'ensemble)

| Composant | Tokens | Nature |
|---|---:|---|
| Base jusqu'à C13 | ≈ 2 780 000 | [mesuré, rapporté] |
| Agents depuis C13 (étapes 1,3,4,5,7,8,9) | 1 088 306 | [mesuré] |
| Fix armips + session manuelle RAM | **non quantifié** | [non mesuré - angle mort] |
| **Total agents connu** | **≈ 3,87 M tokens** | plancher, hors postes non mesurés |

## 3. Ce qui a marché vs ce qui n'a pas marché

### 3.1 Ce qui a le mieux marché : politique Tester/Reviewer ciblée sur M4

- Confirmé par ce lot : les 4 paires Coder→Tester (étapes 1 partiel*, 3,
  4, 7+8→9) gardent un ratio Tester/Coder stable et raisonnable
  (52k/150k ≈ 35 %, 72k/288k ≈ 25 %, 26k/75k ≈ 35 %), sans boucle de
  retry coûteuse détectée dans les chiffres fournis.
  (*C14 n'a pas eu de Tester car il s'est arrêté `blocked` avant livraison
  testable - comportement correct : pas de gaspillage de Tester sur du
  code qui ne tourne pas encore.)
- Le fait de réserver Tester/Reviewer à M4 (patch ROM + client, où une
  régression silencieuse peut corrompre une vraie sauvegarde joueur) et de
  s'appuyer sur le self-check orchestrateur ailleurs continue d'être la
  bonne coupure risque/coût - rien dans ce lot ne contredit la conclusion
  des rapports précédents.
- Étapes 7, 8 et 9 (réécriture ciblée + tests + validation finale, 35k +
  40k + 26k = 101k au total) illustrent le meilleur ratio coût/valeur de
  tout le chantier : tâches petites, bien cadrées (adresses déjà connues,
  changement mécanique), pas de retry, validation propre du premier coup
  (le Tester a confirmé `status: ok` sans aucun aller-retour). C'est le
  patron à reproduire pour M5/M6.

### 3.2 Ce qui a le moins bien marché : le Debugger bloqué sur `save_layout.py`

| | Debugger (agent) | Session manuelle (orchestrateur) |
|---|---|---|
| Coût | 160 000 tokens [mesuré] | non mesuré, mais "plusieurs heures" |
| Résultat direct | `blocked`, cause incomplètement trouvée | Adresses réelles confirmées (Bag + flags) |
| A résolu le problème ? | Non | Oui |
| Valeur résiduelle | Partielle - a suggéré de lire `SaveData.arrayHeaders` en RAM, piste effectivement réutilisée ensuite pour confirmer `Bag` (mais la piste principale du Debugger, l'adresse `0x27D820` dérivée par arithmétique, s'est révélée **fausse** à l'usage réel) | - |

Le vrai coût d'opportunité n'est pas seulement les 160k tokens : c'est
qu'un agent Debugger, par construction, ne peut **pas** exécuter
d'actions dans un émulateur réel (pas de BizHawk accessible depuis son
sandbox). Il a donc été lancé sur un problème dont la nature exacte
(vérification empirique en RAM live) était **hors de son périmètre
d'action possible** dès le départ - ce n'est pas un échec de compétence
de l'agent, c'est un **mauvais choix de découpage de tâche par
l'orchestrateur/Planner** : un problème qui nécessite une vérification
matérielle/émulateur ne devrait pas être confié à un agent texte-seul
sans lui donner, en amont, un script tout prêt à exécuter par un humain
(exactement ce qui a fini par marcher, cf. §4).

## 4. Enseignement principal - le coût caché du travail interactif en conversation principale

La session manuelle (RAM Search GUI + captures d'écran, puis script Lua
de dump mémoire diffé en Python) a **fini par trouver la bonne réponse**,
mais :

1. Son coût réel en tokens n'apparaît dans **aucun** rapport, parce
   qu'elle n'est pas passée par un agent avec un bloc RESULT mesurable -
   c'est un trou structurel de l'instrumentation actuelle.
2. Le contexte de la conversation principale **s'accumule** sur toute la
   session (contrairement au contexte d'un agent, jeté après sa tâche) :
   chaque aller-retour "capture d'écran → lecture → nouvelle capture"
   payait donc un coût croissant, pas plat.
3. Ironie a posteriori : la méthode qui a **effectivement** fonctionné à
   la fin - un script Lua de dump mémoire binaire, exécuté une fois
   avant/une fois après une action connue, diffé **en Python** plutôt
   qu'à l'œil sur des captures d'écran - est *exactement* la méthode déjà
   documentée en clair dans `docs/status.md` ("Étape 1 - via un script Lua,
   pas la RAM Search GUI") **avant** que la longue session interactive ne
   commence. Autrement dit : la solution la moins chère était déjà écrite
   noir sur blanc, mais le chemin réellement emprunté est passé par de
   l'itération GUI coûteuse avant de converger vers elle.

**Recommandation explicite pour l'avenir** : pour toute tâche du type
"itération fine avec un outil externe non scriptable directement par un
agent" (émulateur, GUI, matériel) :

- Ne pas faire l'itération dans la conversation principale à coups
  d'allers-retours capture d'écran / lecture / nouvelle capture.
- Préparer **un** script/outil complet en une fois (ex. le script Lua de
  dump binaire + diff Python déjà écrit dans `docs/status.md`), le donner
  à l'utilisateur avec une procédure numérotée claire, et ne reprendre la
  conversation qu'**une fois les fichiers produits** disponibles à
  analyser en un seul passage.
- Si plusieurs itérations sont malgré tout nécessaires, envisager de les
  déléguer à un agent dédié et jetable par itération (contexte propre à
  chaque tentative) plutôt que de laisser le fil principal accumuler tout
  l'historique des tentatives.
- Envisager d'ajouter un champ optionnel (non-`[INVARIANT]`) au format de
  sortie standard permettant à l'orchestrateur de logguer, même
  approximativement, le travail qu'il fait lui-même hors agent (ex.
  nombre de tours, durée), pour que les futurs rapports Optimizer ne
  soient plus aveugles sur ce poste.

## 5. Recommandations concrètes pour M5/M6

M5 (build/CI) et M6 (doc utilisateur/release) ne touchent ni au ROM ni à
BizHawk - le risque "corruption de sauvegarde joueur" qui justifie
Tester/Reviewer obligatoire sur M4 ne s'applique pas de la même façon.

| Recommandation | Justification |
|---|---|
| Self-check orchestrateur suffisant par défaut (pas de Tester/Reviewer obligatoire), sauf sur la validation finale de release | Aligné avec la politique déjà établie ("pas d'économie sur M4, self-check ailleurs") ; M5/M6 sont hors de la catégorie à risque |
| Découper en petites tâches bien cadrées, à l'image des étapes 7/8/9 de ce lot (35k-40k tokens Coder, ~26k Tester) plutôt que des tâches géantes façon C14/C16 (265k-360k) | Ce lot montre que les tâches petites et bien spécifiées ont le meilleur ratio coût/valeur, sans aucun blocage |
| Viser un budget indicatif &lt; 100k tokens/tâche pour les items M5/M6 (packaging `.apworld`, pipeline CI lint+tests+zipimport, pages de doc utilisateur) | Basé sur l'écart observé entre tâches "bien cadrées" (35-75k) et tâches "avec inconnue externe" (160k-360k) - M5/M6 n'ont pas d'inconnue externe de ce type |
| Réserver un seul agent Reviewer de clôture en fin de M5 et en fin de M6 (pas par sous-tâche) | Suffisant pour attraper les problèmes de cohérence globale sans payer un Reviewer par petit commit |
| Ne pas relancer de Debugger "texte-seul" sur un problème qui nécessite in fine une vérification matérielle/émulateur - ni pour M5/M6 ni ailleurs | Leçon du §3.2 : ce type de tâche doit être requalifié avant d'être confié à un agent |
| Tenir un ledger simple (tableau Markdown mis à jour à chaque étape, dans `docs/status.md` ou un fichier dédié) avec les tokens réels rapportés par chaque agent | Ce rapport a dû reconstruire les chiffres de mémoire faute de logs committés ; un ledger vivant éviterait ça pour les prochains rapports Optimizer |

## 6. Limites de ce rapport

- Aucun log de tokens brut n'était accessible (aucun fichier de ce type
  committé dans le dépôt) : tous les chiffres "mesurés" ci-dessus
  proviennent du rappel fourni pour ce tour ou des blocs RESULT relayés
  par l'orchestrateur, pas d'une relecture directe de traces d'exécution
  brutes.
- Les 2 rapports Optimizer précédents de cette session ne sont pas
  committés non plus (recherchés, absents du dépôt) - impossible de les
  relire pour vérifier le chiffre de 2,78 M tokens jusqu'à C13 ; il est
  repris tel quel, marqué comme non re-vérifié.
- Le coût du fix `armips` et de la session manuelle BizHawk reste
  fondamentalement inconnu (angle mort assumé, voir §4) : ce rapport ne
  invente pas de chiffre pour ces deux postes.

## 7. Mise à jour post-rédaction - résultat du Tester (client.py)

Le Tester de l'étape 9 (dispatché avant la rédaction de ce rapport) a
rendu son verdict pendant la rédaction :

- `status: ok`
- 187 tests passés, 34 skipped, `ruff` clean.
- `client.py` cohérent : aucun résidu de l'ancien calcul base+offset,
  `bag_base_address`/`flags_array_address` utilisés partout (init,
  `validate_rom`, `_check_locations`, `_apply_next_received_item`),
  fallback par variable d'environnement robuste.
- Les anciennes fonctions `_resolve_save_data_address`/
  `_resolve_save_layout_case_name` et les env vars
  `HEARTGOLD_SAVE_DATA_ADDRESS`/`HEARTGOLD_SAVE_LAYOUT_CASE` restent
  définies mais non appelées - confirmé intentionnel (documenté dans le
  docstring du module) et testé isolément, sans résidu cassé.
- `git status` propre côté `ressources/` (seuls `client.py` et
  `tests/test_client.py` modifiés).

Conclusion : la réécriture de `client.py` avec les adresses RAM
confirmées empiriquement est validée et peut être committée.
