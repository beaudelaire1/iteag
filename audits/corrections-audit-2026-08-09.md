# Suites données à l'audit du 2026-08-09

Document compagnon de [`audit-preprod-2026-08-09.md`](audit-preprod-2026-08-09.md).
Il reprend chaque point du rapport, dit ce qui a été fait, et — pour ce qui reste
ouvert — dit exactement qui doit agir.

**Base de départ** : commit `3400bab` (« Aligner le runbook sur les sauvegardes R2 »).
**Nature des changements** : code, gabarits, tests, workflows et documentation. Aucune migration de base de données, aucune dépendance ajoutée.

---

## 1. Tableau de suivi

| # | Constat | Sévérité initiale | État |
|---|---|---|---|
| R1 | Aucune mention légale ni CGV, alors que la boutique encaisse | 🔴 | **Corrigé dans le code** — reste 6 valeurs à saisir par l'ITEAG (§3) |
| R2 | Signature des PDF officiels avalée silencieusement | 🟠 | **Corrigé** |
| R3 | Alignement hôte servi / `SITE_URL` / `Site` Wagtail non contrôlé | 🟠 | **Corrigé** |
| R4 | Les cinq workflows `predeploy-*` ne s'exécutaient plus | 🟠 | **Corrigé** |
| R5 | 18 champs de formulaire sans nom accessible | 🟡 | **Corrigé** |
| R6 | Identifiant de compte R2 publié dans la CSP | 🟡 | **Documenté** — une variable à renseigner (§3) |
| O1 | `src/nginx/` contredit `coolify.md` | ⚪ | **Corrigé** (documentation) |
| O2 | `AXES_LOCKOUT_PARAMETERS` non justifié | ⚪ | **Corrigé** (commentaire) |
| O3 | `meta robots` contredisait `X-Robots-Tag` | ⚪ | **Corrigé** |
| O4 | Aucun `assertNumQueries` | ⚪ | Non traité — voir §4 |
| O5 | `ASSET_VERSION` : `stat()` par requête, redondant | ⚪ | Non traité — voir §4 |
| O6 | Artefacts PDF versionnés | ⚪ | Non traité — voir §4 |

---

## 2. Ce qui a été fait, point par point

### R1 🔴 — Mentions légales et conditions générales de vente

**Deux pages servies par du code**, comme les deux politiques existantes, et non
comme pages éditoriales Wagtail : un document dont la loi impose la présence ne
doit pas pouvoir disparaître d'un clic dans l'arborescence.

- `apps/website/views.py` — `mentions_legales`, `conditions_generales_vente`
- `apps/website/urls.py` — `/mentions-legales/`, `/conditions-generales-de-vente/`
- `templates/website/mentions_legales.html` — éditeur, directeur de la publication, hébergeur, propriété intellectuelle, signalement, accessibilité, droit applicable
- `templates/website/conditions_generales_vente.html` — 15 articles couvrant les trois natures de vente réellement implémentées (livres physiques, modules numériques, frais de scolarité) : prix et TVA article par article, tunnel de commande, livraison Guadeloupe/Martinique/Guyane avec ses trois modes, paiement Stripe/virement/sur place, **droit de rétractation traité séparément pour chaque nature**, modèle de formulaire de rétractation, garanties légales, médiation, force majeure
- `apps/website/sitemaps.py` — les deux pages entrent au plan du site
- `templates/partials/footer.html` — liées depuis toutes les pages

**La case d'acceptation lie désormais le document qu'elle engage.**
`apps/commerce/forms.py` construit le libellé de `accepte_conditions` avec un
lien vers les CGV. Il est construit dans `__init__` et non dans la déclaration du
champ : résoudre une URL à l'import du module s'exécuterait avant le chargement
de la configuration d'URL.

**Renonciation expresse au droit de rétractation sur les modules.**
Un module s'ouvre dès l'encaissement. L'article L221-28 du code de la
consommation ne fait tomber le droit de rétractation que si l'acheteur a
expressément demandé cette exécution immédiate *et* reconnu y renoncer. Sans
cela, l'ITEAG devrait rembourser pendant quatorze jours un contenu déjà
consultable.

- `templates/elearning/module_detail.html` — case à cocher obligatoire, avec lien vers les CGV
- `apps/paiements/views.py` — `AchatModuleView` refuse l'achat sans cette déclaration. Le contrôle est refait côté serveur : une case retirée du DOM ne doit pas suffire à sauter la déclaration.

**Ce que le déploiement refuse désormais.** `apps/core/services/production.py`
ajoute six valeurs obligatoires (forme juridique, immatriculation, directeur de
la publication, hébergeur et son adresse, médiateur de la consommation). Une
mention légale amputée ne vaut pas mieux qu'une mention absente : le manque
bloque l'ouverture au lieu de se découvrir à la lecture.

**Tests** : `apps/website/test_pages_legales.py` (11 tests) — pages publiques,
valeurs réellement rendues, obligations de vente à distance couvertes, médiateur
publié seulement s'il est désigné, liens depuis le pied de page, présence au plan
du site, lien depuis la case de commande, refus du contrat de production.
`apps/paiements/tests/test_vue_webhook.py` — deux tests sur la renonciation.

### R2 🟠 — Signature des documents officiels

`apps/documents/services_generation.py` distingue maintenant deux situations que
le code confondait :

- **aucune signature déposée** → chaîne vide, dégradation acceptée, comportement inchangé ;
- **signature déposée mais illisible** (panne R2, objet supprimé, droits retirés) → journalisation via `logger.exception` puis levée de `SignatureIllisible`.

La conséquence compte autant que la cause : le gabarit
`templates/documents/pdf/document.html` rend inconditionnellement « Fait aux
Abymes, le … », la qualité et le nom du signataire ; seule l'image est
conditionnelle. Un PDF produit sans elle n'a pas l'air incomplet — il a l'air
signé. On préfère donc l'échec, réparable par une relance.

- `apps/documents/tasks.py` bascule la tâche en `ECHEC` avec un message lisible par l'étudiant (mécanisme préexistant, qui ne se déclenchait plus puisque l'exception était avalée en amont) ;
- `apps/elearning/tasks.py` intercepte `SignatureIllisible` et laisse l'attestation sans PDF plutôt que d'en produire un trompeur, suivant le motif déjà retenu pour `MoteurPDFIndisponible`.

**Tests** : `apps/documents/test_signature_illisible.py` (8 tests) et un test dans
`apps/elearning/tests/test_taches.py`. Le chemin d'échec n'était couvert par
aucun test.

### R3 🟠 — Cohérence de l'hôte public

`apps/core/services/production.py` gagne `anomalies_donnees_production()`,
séparée de la fonction existante à dessein : celle-ci ne lit que des réglages et
reste utilisable sans base, ce que ses tests exploitent. La nouvelle compare
l'hôte du `Site` Wagtail par défaut à celui de `SITE_URL` — l'écart que corriger
une variable d'environnement ne répare pas, puisque cet enregistrement vit en
base.

`verifier_production` accepte `--sans-base` pour les contextes sans PostgreSQL
(le job `build` de la CI), et exécute les deux familles de contrôles sinon.

`scripts/verifier_go_live.sh` ajoute deux étapes que seule une requête extérieure
peut établir :

- la balise canonique de l'accueil vaut exactement l'adresse publiée ;
- le plan du site ne contient qu'un seul nom d'hôte ;
- les deux pages légales répondent 200.

Les blocs Python y sont passés par l'entrée standard plutôt qu'en `python -c` :
l'analyse de la page demande des apostrophes, qu'une chaîne shell entre
apostrophes ne peut pas contenir.

**Tests** : `TestLHotePublicEstUnSeulEtMemeHote` (6 tests) et trois tests dans
`apps/core/test_go_live_ops.py`, dont un qui compile les blocs Python embarqués
dans le script shell — un script inséré dans un fichier shell n'est relu par
personne et n'échoue qu'au moment de la bascule.

### R4 🟠 — Workflows de prédéploiement dormants

Les cinq workflows `predeploy-*` étaient conditionnés à
`github.head_ref == 'agent/…'`. Ces branches ayant été fusionnées, la condition
n'était plus jamais vraie : le contrôle existait, passait pour actif, et ne
s'exécutait plus — scan de sécurité dynamique ZAP compris.

Les gardes sont retirées. Les déclencheurs ne dépendent plus d'aucun nom
éphémère : toute PR vers `main`, un rendez-vous hebdomadaire échelonné
(lundi 3 h à 4 h 20, pour ne pas lancer cinq navigateurs à la même minute contre
la préproduction), et le déclenchement manuel.

Le périmètre du gate d'accessibilité passe de 4 à 7 pages : `/bibliotheque/`,
`/boutique/` et `/e-learning/` s'ajoutent. C'est par ce trou qu'est passé R5 —
le seuil était strict, mais il ne regardait pas ces pages.

**Test** : `test_aucun_controle_de_predeploiement_ne_depend_d_un_nom_de_branche`
empêche d'y revenir.

### R5 🟡 — Noms accessibles des champs de formulaire

18 champs, 10 gabarits, tous corrigés par un `id` et un `<label>` — visible
lorsque la place le permet, `sr-only` sinon, motif déjà employé dans le projet
(pied de page, tableaux du back-office). Aucun changement visuel.

Dans les tableaux de présence et d'assiduité, l'étiquette nomme l'étudiant
concerné (« Présence de Jeanne Dupont ») : dans une grille, « statut » répété
trente fois ne distingue rien.

**Test** : `apps/core/test_noms_accessibles.py` balaie les 228 gabarits du projet
et échoue sur tout champ sans étiquette, sans `aria-label` et hors `<label>`
englobant. Six tests éprouvent l'heuristique elle-même — un test de couverture
qui accepte tout ne protège de rien.

### O1, O2, O3 — Observations traitées

- **O1** : `docs/exploitation/coolify.md` disait « le dépôt ne contient ni configuration Nginx, ni service certbot ». La phrase est remplacée par ce qui est vrai et vérifiable — aucun fichier Compose ne démarre ces services, `src/nginx/` est une référence non déployée — avec la commande qui permet de le contrôler.
- **O2** : `AXES_LOCKOUT_PARAMETERS` porte désormais sa justification, dans un fichier où presque tous les autres réglages ont la leur. L'arbitrage est explicité dans les deux sens, ainsi que ce qui borne le risque : Turnstile est validé avant `authenticate()`, donc avant tout comptage d'échec.
- **O3** : la balise `meta robots` suit la même source de vérité que l'en-tête `X-Robots-Tag` (`HOTES_INDEXABLES`). Une préproduction ne peut plus annoncer « index, follow » dans son HTML pendant que son en-tête dit l'inverse. **Test** : `test_la_balise_robots_dit_la_meme_chose_que_l_entete`.

### Corrections incidentes

**Deux commentaires de gabarit écrits en syntaxe courte multiligne.** La syntaxe
`{# … #}` de Django ne franchit pas les sauts de ligne : un commentaire écrit
ainsi sort en clair dans la page. `apps/core/test_gabarits_structure.py` l'a
attrapé sur `base.html` et `elearning/module_detail.html` — les deux sont passés
en `{% comment %}`. Le garde-fou du projet a fonctionné exactement comme prévu.


`test_domaine_public_reste_indexable` interrogeait `iteag.org` sans déclarer ce
domaine : il ne passait que dans l'ordre du fichier, en profitant de l'`override`
du test précédent, et échouait exécuté seul. Il porte maintenant sa propre
déclaration. Ce n'est pas un défaut trouvé par l'audit, mais il a été rencontré
en corrigeant O3 et laissé réparé.

---

## 3. Ce qui reste à faire — et par qui

Ces valeurs ne sont connues que de l'ITEAG. **Tant qu'elles ne sont pas saisies
dans Coolify, `verifier_production` refuse l'instance** : le go-live ne peut donc
pas se faire par inadvertance avec des mentions légales incomplètes.

Quatre des six valeurs ont pu être pré-remplies à partir de sources publiques.
**Elles sont sourcées, pas validées** : la vérification revient à l'ITEAG.

| Variable | État | Valeur et source |
|---|---|---|
| `ITEAG_FORME_JURIDIQUE` | Pré-remplie | « Association régie par la loi du 9 décembre 1905 ». Source : iteag.org, page « L'institut » — « La forme — Une association loi 1905 » ; même mention dans l'archive du 23 juillet 2023. **Ce n'est pas une association loi 1901.** Réserve : le registre INSEE classe l'association en catégorie **9220 « Association déclarée »**, sans mention de la loi de 1905. À trancher d'après les statuts. |
| `ITEAG_IMMATRICULATION` | Pré-remplie | « RNA W9G2004341 — SIRET 829 562 529 00018 ». Source : annuaire des entreprises (INSEE + RNA), recherche « ITEAG » → **une seule** correspondance, « INSTITUT DE THEOLOGIE EVANGELIQUE DES ANTILLES ET DE LA GUYANE — ITEAG », siège « 201 LOTISSEMENT POINTE D'OR 97139 LES ABYMES » — la même adresse que celle du site. Association active, créée le 14 novembre 2016, SIREN 829 562 529. |
| `ITEAG_HEBERGEUR` | Pré-remplie | « OVH SAS ». Source : `docs/exploitation/coolify.md` — à confirmer |
| `ITEAG_HEBERGEUR_ADRESSE` | Pré-remplie | « 2 rue Kellermann, 59100 Roubaix, France » — à confirmer |
| `ITEAG_DIRECTEUR_PUBLICATION` | Pré-remplie | « Jean-Claude Girondin ». Gouvernance indiquée par la maîtrise d'ouvrage : Jean-Claude Girondin président, Alain Nisus directeur pédagogique. C'est le président qui figure ici, la LCEN (art. 6-III-1) désignant le représentant légal de la personne morale ; la direction pédagogique est un rôle interne, sans effet sur cette responsabilité. Si l'association a formellement désigné quelqu'un d'autre à cette fonction, c'est ce nom-là qu'il faut mettre. Aucune source publique ne donnait ces noms. |
| `ITEAG_MEDIATEUR` | **Laissée vide** | Seule valeur que je n'ai pas remplie. Un médiateur n'existe qu'une fois l'adhésion souscrite : y inscrire un nom avant adhésion enverrait les clients vers un organisme sans mandat, dont ils verraient la réclamation refusée — le préjudice porterait sur eux, pas sur l'ITEAG. Choisir un médiateur référencé par la CECMC, souscrire, puis reporter ses coordonnées. |

**Ce qui a été cherché, et où.** Trois sources, en ne cherchant que ces six
valeurs :

1. **`iteag.org` en ligne** — application React ; le contenu ne figure pas dans le HTML servi, il a donc été extrait du bundle `main.059026a5.js` (2,3 Mo), ce qui couvre toutes les routes d'un coup.
2. **L'archive du 23 juillet 2023** (`main.1a7ea30b.js`), plus l'inventaire des adresses archivées.
3. **L'annuaire des entreprises** (INSEE + RNA), pour l'immatriculation.

Aucune des deux versions du site n'a jamais comporté de page de mentions
légales, et l'inventaire des URL archivées n'en contient aucune. Trois faux
positifs ont été écartés en cours de route : « Directeur de la publication »
apparaît dans le bundle comme rôle d'auteur d'un ouvrage du catalogue de la
bibliothèque, « RNA » comme fragment interne de React, et « NDA » comme cote de
rayonnage.

Enfin, le registre indique `est_organisme_formation: false` : l'ITEAG n'est pas
déclaré comme organisme de formation. `ITEAG_NUMERO_DECLARATION_ACTIVITE` reste
donc vide, ce qui est cohérent — cette variable est facultative.

Facultatives : `ITEAG_MEDIATEUR_ADRESSE`, `ITEAG_MEDIATEUR_URL`,
`ITEAG_NUMERO_DECLARATION_ACTIVITE`, et les dates de version
`ITEAG_MENTIONS_VERSION` / `ITEAG_CGV_VERSION`.

**Recommandé, non bloquant** : `AWS_S3_CUSTOM_DOMAIN` (R6). Sans domaine
personnalisé R2, l'origine des médias injectée dans la CSP est l'URL brute du
bucket, qui publie l'identifiant du compte Cloudflare dans chaque réponse HTTP.
Le code utilise déjà cette variable en priorité : aucune modification applicative
n'est nécessaire.

**Deux réserves que ce travail ne lève pas :**

1. **Le contenu juridique demande une relecture par un conseil.** Les CGV
   décrivent fidèlement ce que le code fait — modes de livraison, destinations,
   modes de paiement, traitement du remboursement, accès perpétuel aux modules.
   La rédaction reste celle d'un développeur, pas d'un juriste, et certaines
   clauses dépendent de choix que seul l'ITEAG peut arrêter (politique de retour,
   frais de retour, conditions propres à chaque parcours).
2. **Le statut juridique de l'ITEAG n'est toujours pas établi par le dépôt.**
   L'applicabilité du RGAA reste ouverte.

---

## 4. Ce qui a été délibérément laissé de côté

- **O4 — absence d'`assertNumQueries`.** Ajouter des garde-fous de requêtes sur les vues de liste est un travail utile, mais c'est un chantier à part : il demande de choisir les vues, de fixer des seuils défendables et de les tenir. L'insérer ici l'aurait bâclé.
- **O5 — `ASSET_VERSION`.** Le gain est marginal et la modification touche l'invalidation de cache de tous les assets. À faire à froid, pas dans un lot de correctifs de go-live.
- **O6 — artefacts PDF versionnés.** Cosmétique ; les retirer sans savoir qui les régénère risquerait de casser une habitude de travail.

Ces trois points restent des observations : aucun n'a d'impact constaté
aujourd'hui.

---

## 5. Vérifications exécutées

| Contrôle | Commande | Résultat |
|---|---|---|
| Style | `ruff check .` | `All checks passed!` |
| Format | `ruff format --check .` | 484 fichiers déjà formatés |
| Suite complète | `pytest` | **3 275 passés, 3 ignorés, 0 échec** en 4 min 30 (Python 3.14 / SQLite) |
| Syntaxe du gate serveur | `sh -n scripts/verifier_go_live.sh` | valide |
| Blocs Python embarqués | `ast.parse` sur les 3 blocs | valides |
| Balayage des noms accessibles | script d'audit rejoué sur `templates/` | 0 champ sans nom accessible |

**Non vérifié** : le rendu visuel des deux nouvelles pages dans un navigateur, et
le comportement des workflows `predeploy-*` réveillés — ils ne s'exécuteront qu'à
la prochaine PR vers `main`. Les gabarits reprennent la structure et les classes
des deux pages de politique existantes, et la suite confirme qu'ils répondent 200
avec le contenu attendu, mais cela ne remplace pas un coup d'œil.
