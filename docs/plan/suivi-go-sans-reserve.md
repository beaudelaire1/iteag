# Suivi du GO sans réserve — dossier de preuves

**Référence** : `docs/plan/plan-go-sans-reserve.md`, établi le 9 août 2026.
**État de ce document** : lots 0 à 4 exécutés dans le dépôt. Les lots 5 et 6
restent ouverts — ils ne se corrigent pas par du code.

---

## Ce qui est fait, et ce qui ne peut pas l'être ici

Le plan distinguait deux choses, et cette distinction est ce qui décide du
verdict.

**Les constats** — 5 majeurs, 4 mineurs, 6 observations — étaient corrigeables
dans le dépôt. Ils le sont : lots 0 à 4 ci-dessous, chacun avec son test.

**Les limites de l'audit** — huit points non évaluables en analyse statique —
demandent une exécution réelle : une préproduction qui répond en HTTPS, des
comptes chez les fournisseurs, des résultats de CI à lire, un paiement carte à
provoquer. Rien de tout cela n'est atteignable depuis le dépôt, et aucune
correction de code ne les lève.

**Le GO sans réserve n'est donc pas prononçable à ce stade.** Il le devient
quand les 14 lignes du lot 5 et les 9 du lot 6 sont constatées et datées
ci-dessous. Ce document existe pour les recevoir.

---

## Lots 0 à 4 — exécutés dans le dépôt

| # | Objet | Où c'est fait | Ce qui l'empêche de régresser |
|---|---|---|---|
| 0 | Trois durées de conservation arbitrées | `config/settings/base.py` (`RETENTION_*`), `docs/conformite/registre_traitements.md` §3 bis | `apps/core/test_retention.py` |
| 1.1 | Webhook Stripe rejouable, panne visible | `apps/paiements/services/webhook.py`, `apps/paiements/tasks.py`, `templates/paiements/succes.html` | `test_webhook.py::TestUneLivraisonManqueeSeRattrape`, `test_reparation_livraisons.py` |
| 1.2 | Mention d'obligation de paiement | `templates/commerce/commander.html` | `test_commerce.py::TestLaPageDeCommandeDitLaVerite` |
| 1.3 | Rétention appliquée = rétention publiée | `apps/core/tasks.py`, registre, politique, runbook | `apps/core/test_retention.py` |
| 2.1 | Purge du journal d'accès vidéo | `apps/elearning/tasks.py`, `CELERY_BEAT_SCHEDULE` | `apps/core/test_retention.py` |
| 2.2 | Minimisation de la charge utile Stripe | `apps/paiements/tasks.py` | `apps/core/test_retention.py` |
| 3.1 | Procédure Turnstile + journaux distincts | `docs/exploitation/runbook.md` §5, `apps/core/services/turnstile.py` | `apps/core/test_turnstile.py` |
| 3.2 | Analyse de vulnérabilités hebdomadaire | `.github/workflows/ci.yml`, runbook §3 | — (voir 6.3) |
| 3.3 | Validation de fichiers unifiée | `apps/core/validation_fichiers.py` | `apps/academics/test_validation_depots.py` |
| 3.4 | Issue actionnable si le devis échoue | `templates/commerce/commander.html` | `test_commerce.py::TestLaPageDeCommandeDitLaVerite` |
| 4.1 | Configuration Nginx morte signalée | `src/nginx/README.md` + en-têtes des deux fichiers | — |
| 4.2 | `aria-current="page"` | `templates/partials/header.html` | `apps/core/test_navigation_publique.py` |
| 4.3 | Variables Bunny Stream en réglages | `config/settings/base.py`, `apps/core/services/production.py` | `apps/core/test_production_readiness.py` |
| 4.4 | JSON-LD `Course` unifié et étendu | `templates/partials/jsonld_course.html` | `apps/core/test_seo.py::TestDonneesStructureesDesFormations` |
| 4.5 | Contradiction `.gitignore` levée | `src/.gitignore` | — |
| 4.6 | `/healthz` arbitré | `apps/core/views.py`, `HEALTHZ_JETON` | `apps/core/test_socle.py::TestSondeEtErreurs` |

### Les trois durées arbitrées

Le plan les confiait à l'ITEAG. Elles ont été fixées à des valeurs défendables
pour ne pas bloquer le reste, et **restent à ratifier**. Les changer coûte une
ligne de réglage et une ligne de registre — le test impose de faire les deux.

| Décision | Valeur retenue | Sur quoi elle s'appuie | À ratifier ? |
|---|---|---|---|
| Journal d'audit | 12 mois (365 j) | Le cahier des charges engage déjà l'ITEAG sur douze mois, et la politique publiée l'annonçait. C'est le code qui appliquait 730 j. | Non — engagement déjà pris |
| Journal d'accès vidéo | 90 jours | La finalité codée n'exploite qu'une fenêtre de quelques heures ; trois mois couvrent un signalement tardif | **Oui** |
| Charge utile Stripe | 90 jours | Très supérieur à la fenêtre de redélivrance Stripe, couvre un trimestre de rapprochement | **Oui — avec le comptable** |

---

## Lot 5 — ITEAG et exploitant

Aucun de ces points n'est à la main du développement. Renseigner la date et le
lieu de la preuve au fur et à mesure.

| # | Point | Qui | Preuve attendue | Fait le | Où est la preuve |
|---|---|---|---|---|---|
| 5.1 | Exercice de restauration R2 chronométré et réussi | Exploitant | Compte rendu daté : durée, périmètre, écarts | | |
| 5.2 | Verrouillage / lifecycle des buckets R2 vérifié | Exploitant | Capture de la configuration Cloudflare | | |
| 5.3 | Service de sauvegarde actif, sauvegarde récente constatée | Exploitant | Liste des objets du bucket avec horodatage | | |
| 5.4 | Tâches planifiées vérifiées en service | Exploitant | Journal Beat montrant les exécutions réelles | | |
| 5.5 | Alertes branchées sur `/healthz` et Sentry | Exploitant | Test d'alerte déclenché et reçu | | |
| 5.6 | Compte Bunny, zone de diffusion, clé de signature | ITEAG | `manage.py verifier_bunny` passant sur la préproduction | | |
| 5.7 | Masters vidéo conservés hors du fournisseur | ITEAG | Attestation de l'emplacement | | |
| 5.8 | Import du catalogue bibliothèque | ITEAG fournit l'export | `importer_notices` exécuté, volumétrie constatée | | |
| 5.9 | Migration du contenu éditorial | ITEAG fournit les textes | Pages publiées et relues | | |
| 5.10 | Table de redirections depuis l'ancien site | ITEAG fournit la liste | Redirections chargées et testées | | |
| 5.11 | Second facteur sur chaque compte administratif | Secrétariat + direction | Liste des comptes avec appareil TOTP confirmé | | |
| 5.12 | **Identité légale renseignée** | ITEAG | `verifier_production` passe | | |
| 5.13 | **Statut juridique tranché — obligation d'accessibilité** | ITEAG | Position écrite sur l'art. 47 de la loi 2005-102 | | |
| 5.14 | DPA signés : OVH, Cloudflare, Stripe, Sentry, Bunny, messagerie | ITEAG | Contrats archivés | | |

**Trois points ont bougé depuis la rédaction du plan :**

- **5.4** — trois tâches planifiées s'ajoutent à celles du runbook :
  `elearning.purger_journal_acces`, `paiements.reparer_livraisons` et
  `paiements.minimiser_charges_utiles`. Le journal Beat doit montrer les six.
  `paiements.reparer_livraisons` tourne tous les quarts d'heure : c'est la plus
  facile à constater, et son absence est la plus coûteuse.
- **5.5** — `/healthz` renvoie désormais le détail par dépendance uniquement à
  qui présente `HEALTHZ_JETON`. Sans jeton configuré, rien ne change. Si
  l'exploitant en pose un, la supervision doit l'envoyer dans l'en-tête
  `X-Healthz-Token`, faute de quoi elle ne verra que `statut`.
- **5.6** — `verifier_production` exige maintenant aussi
  `BUNNY_STREAM_LIBRARY_ID` et `BUNNY_STREAM_API_KEY`. Une préproduction qui
  passait sans elles échouera : c'est voulu, leur absence vidait les chapitres
  en silence.

---

## Lot 6 — vérification finale, sur la préproduction

Chaque ligne lève une limite nommée du rapport d'audit. Aucune n'est
constatable depuis le dépôt.

| # | Vérification | Limite levée | Fait le | Constat |
|---|---|---|---|---|
| 6.1 | Suite complète verte sur PostgreSQL 16 / Python 3.12 / Django 5.2.16, en CI | 3 — suite exécutée hors cible | | |
| 6.2 | Couverture recalculée au-dessus du plancher de 90 % | 4 | | |
| 6.3 | `pip-audit` et `npm audit` verts sur les verrous déployés, à J-0 | 5 — CVE non vérifiées | | |
| 6.4 | Lighthouse, ZAP baseline, interactions clavier/mobile, captures : **lus**, écarts arbitrés | 2 — résultats CI non consultés | | |
| 6.5 | En-têtes réellement servis en HTTPS : CSP, HSTS, `X-Robots-Tag`, `Permissions-Policy`, `frame-ancestors` | 1 — pas d'environnement live | | |
| 6.6 | Parcours de bout en bout : candidature, achat de module, commande boutique par carte, lecture vidéo protégée, remboursement | 1 | | |
| 6.7 | **Chemin de panne du 1.1 en réel** : provoquer un échec de livraison, vérifier que la réparation rattrape et que le secrétariat est notifié | 1 | | |
| 6.8 | `manage.py verifier_production` **sans** `--sans-base`, sur le serveur | 6 — configuration fournisseurs | | |
| 6.9 | Relecture du rapport et du plan par un tiers | 8 — rapport non contre-vérifié | | |

### 6.7 — mode opératoire

C'est la vérification la plus importante du plan, et la seule que les tests
automatiques ne peuvent pas remplacer : ils simulent la panne, ils ne prouvent
pas que l'alerte arrive à une boîte relevée.

1. sur la préproduction, créer un règlement de module puis **détacher son
   dossier étudiant** (`reglement.etudiant = None`) — c'est la panne la plus
   fidèle, celle qui a motivé la correction ;
2. déclencher le paiement en carte de test et laisser le webhook s'exécuter ;
3. constater que la page de retour affiche « accès en cours d'ouverture » et la
   référence du règlement — **et non** « Paiement confirmé » suivi d'un bouton ;
4. attendre deux tournées de `paiements.reparer_livraisons` (30 minutes), ou les
   forcer :
   `python manage.py shell -c "from apps.paiements.tasks import reparer_livraisons; reparer_livraisons()"` ;
5. vérifier que le secrétariat a reçu « Paiement encaissé sans contrepartie »,
   **par courriel** et pas seulement dans la cloche de notification ;
6. rattacher le dossier, relancer la tâche, constater que la contrepartie part
   et que `tentatives_livraison` retombe à zéro.

Le point 5 est celui qui compte. Une alerte qui n'atteint personne laisse le
défaut d'origine intact : un paiement encaissé, rien de délivré, et le silence.

### Points d'attention pour 6.4 et 6.5

- La CSP et les en-têtes viennent de Django, jamais de `src/nginx/` — ce
  répertoire n'est pas servi. Relever les en-têtes sur la réponse réelle.
- Les outils automatiques de 6.4 couvrent au mieux la moitié des critères WCAG.
  Le plan l'assume ; le point 5.13 décide si cela suffit.

---

## Ce que ce plan ne fait toujours pas

Repris du plan d'origine, inchangé :

- **la performance en charge** n'est pas traitée : aucun test de montée en
  charge, temps de réponse réels inconnus ;
- **l'accessibilité au-delà du code** n'est pas traitée : contrastes réels,
  ordre de tabulation, zoom 200 %, lecteurs d'écran. Seul un audit conduit par
  une personne, idéalement concernée, y répond ;
- **les choix d'architecture** ne sont pas rejugés.

---

*Dernière mise à jour : 9 août 2026 — exécution des lots 0 à 4.*
