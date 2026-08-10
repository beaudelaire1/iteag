# Plan de travail — vers un GO sans réserve

**Origine** : audit technique de `main` au commit `c43bfcc`, 9 août 2026.
**Objet** : lever, une par une, les conditions du verdict *« GO pour le socle et les
portails · NO-GO ciblé sur l'ouverture publique de la boutique et du paiement »*,
puis lever les limites de l'audit lui-même.

---

## Préalable : ce que « sans réserve » exige réellement

L'audit portait deux choses distinctes, et seule la première se corrige par du code.

1. **Les constats** — 5 majeurs, 4 mineurs, 6 observations. Corrigeables dans le dépôt.
2. **Les limites de l'audit** — huit points non évaluables en analyse statique :
   pas d'environnement live, pas d'accès aux résultats CI, suite exécutée hors
   cible, couverture non recalculée, CVE non vérifiées, configuration des
   fournisseurs non vérifiable, contenu non fourni, rapport non contre-vérifié.

Corriger les constats donne un « GO conditionné à vérification ». Le
« sans réserve » demande en plus des **preuves d'exécution** : c'est l'objet des
lots 5 et 6. Un plan qui s'arrêterait au lot 4 promettrait ce qu'il ne peut pas
tenir.

**Convention de travail** — le dépôt verrouille ses décisions par des tests, et la
CI impose un plancher de couverture de 90 %. Chaque correction ci-dessous arrive
donc **avec son test**, sans quoi le cliquet du projet ne joue pas et la
correction régressera silencieusement.

**Estimations** — en jours-homme, à la charge de Trait d'Union Studio sauf
mention contraire. Ce sont des estimations, pas des engagements : elles supposent
un développeur déjà familier du dépôt.

---

## Vue d'ensemble

| Lot | Objet | Effort | Débloque |
|-----|-------|--------|----------|
| 0 | Décisions à prendre avant de coder | 0,5 j | Les lots 1 et 2 |
| 1 | Lever le NO-GO ciblé sur la vente | 2,5 j | **Ouverture boutique + paiement** |
| 2 | Conformité RGPD restante | 1,5 j | Défendabilité en cas de contrôle |
| 3 | Robustesse et exploitation | 1,5 j | Tenue en service courant |
| 4 | Nettoyage | 0,5 j | Lisibilité, dette évitée |
| 5 | Hors code — ITEAG et exploitant | — | **Toutes les limites d'audit** |
| 6 | Vérification finale et prononcé du GO | 1 j | Le verdict lui-même |
| | **Total code** | **≈ 7,5 j** | |

Les lots 1 à 4 sont indépendants entre eux et parallélisables après le lot 0. Le
lot 5 court en parallèle du reste et n'est pas sur le chemin critique du
développement — il l'est en revanche sur celui du GO.

---

## Lot 0 — Décisions à prendre avant d'écrire une ligne

Trois arbitrages bloquent la suite. Ils coûtent une réunion, pas du développement.
Les prendre après avoir codé garantit de refaire le travail deux fois : la valeur
choisie doit atterrir **simultanément** dans le code, dans le registre et sur la
page publiée.

| # | Décision | Qui tranche | Enjeu |
|---|----------|-------------|-------|
| 0.1 | Durée de conservation du **journal d'audit** : 12 ou 24 mois | ITEAG, responsable de traitement | Le code applique 730 jours, les documents publiés annoncent 12 mois. L'un des deux ment. |
| 0.2 | Durée de conservation du **journal d'accès vidéo** | ITEAG | Aucune purge n'existe aujourd'hui. La finalité codée (détection de partage) n'exploite que 24 h : une durée courte est parfaitement défendable. |
| 0.3 | Délai au-delà duquel la **charge utile Stripe** n'est plus utile au rapprochement comptable | ITEAG + comptable | Conditionne la tâche de minimisation. À distinguer de la conservation des pièces comptables (10 ans), qui porte sur le montant et la référence, pas sur le corps de la notification. |

**Livrable** : trois valeurs écrites et datées dans
`docs/conformite/registre_traitements.md`.
**Effort** : 0,5 j.

---

## Lot 1 — Lever le NO-GO ciblé sur la vente

C'est le seul lot qui conditionne l'ouverture de la boutique et du paiement.

### 1.1 — Webhook Stripe : rendre le rejeu possible et la panne visible

*Audit §3.2-A · 🟠 Majeur · Effort : 1,5 j*

**Le défaut** — La trace `EvenementStripe` est créée et **commitée** avant
l'exécution de la livraison ([`webhook.py:67`](../../src/apps/paiements/services/webhook.py)).
Si la livraison échoue, la vue répond 500, Stripe redélivre, l'insertion viole la
contrainte d'unicité, `EvenementDejaTraite` est levée et la vue répond **200**.
Stripe se tait. Le champ `traite` existe, est écrit, et n'est **jamais relu**.

Résultat : `statut=PAYE`, `contrepartie_delivree=False`, aucune relance, aucune
alerte. L'étudiant lit « Paiement confirmé » et un bouton qui le mène à un 403.

**Trois modifications, dans cet ordre :**

**a) Donner un lecteur au champ `traite`** — `apps/paiements/services/webhook.py:73`

Sur `IntegrityError`, relire la trace existante plutôt que lever immédiatement.
Ne lever `EvenementDejaTraite` que si `traite=True` ; sinon, **rejouer** l'action.
Le rejeu est sûr : `attribution.delivrer` est idempotent sous verrou via
`contrepartie_delivree` (`attribution.py:23`).

**b) Tâche de réparation planifiée** — nouveau `paiements.reparer_livraisons`,
déclaré dans `CELERY_BEAT_SCHEDULE` (`config/settings/base.py:490`)

Balaie les règlements `statut=PAYE AND contrepartie_delivree=False` depuis plus de
N minutes, rappelle `delivrer()`, et **notifie le secrétariat** au-delà de deux
échecs consécutifs. Sans la notification, on remplace un silence par un autre.

**c) Ne plus afficher une confirmation trompeuse** —
`templates/paiements/succes.html`

Quand `reglement.est_paye` mais que la contrepartie n'est pas délivrée, afficher
un message d'attente explicite et la référence à donner au secrétariat, plutôt
qu'un bouton « Commencer la formation » qui mène à un refus.

**Tests attendus** — dans `apps/paiements/tests/test_webhook.py` :
1. livraison qui échoue puis redélivrance Stripe → la contrepartie **est**
   délivrée et la réponse est 200 ;
2. redélivrance d'un événement réellement traité → aucun effet, réponse 200 ;
3. la tâche de réparation rattrape un règlement payé non délivré ;
4. deux échecs de réparation déclenchent la notification.

**Documentation** — entrée au §5 du runbook : « Un paiement est encaissé mais rien
n'est délivré », avec la requête de diagnostic et la commande de relance.
Entrée au tableau §4 pour la nouvelle tâche planifiée.

---

### 1.2 — Bouton de commande : mention de l'obligation de paiement

*Audit §3.7-C · 🟠 Majeur · Effort : 0,25 j*

**Le défaut** — Le bouton qui conclut la commande porte le libellé **« Suivant »**
(`templates/commerce/commander.html:51`). C'est bien lui qui crée la `Commande`,
réserve le stock et vide le panier (`apps/commerce/views.py:214`), y compris pour
les modes `virement` et `sur_place` où aucune page de paiement ne suit.

L'article L221-14 du code de la consommation impose que cette fonction porte la
mention **« commande avec obligation de paiement »** ou une formule équivalente
dénuée d'ambiguïté. À défaut, le consommateur **n'est pas engagé**.

Le tunnel d'achat de module, lui, fait déjà correctement les choses
(« Acheter cette formation », `templates/elearning/module_detail.html:159`).
L'écart est une incohérence entre deux tunnels, pas une lacune de connaissance.

**Correction** — Remplacer le libellé. Le texte exact relève de la rédaction ;
la mention relève de l'obligation.

**Test attendu** — dans `apps/commerce/` : le rendu de la page de commande
contient une mention d'obligation de paiement sur le bouton de validation.
Un test de gabarit suffit et empêche la régression au prochain remaniement
graphique.

---

### 1.3 — Aligner la rétention appliquée sur la rétention publiée

*Audit §3.7-A · 🟠 Majeur · Effort : 0,5 j · dépend de 0.1*

**Le défaut** — Trois sources, deux valeurs :

| Source | Valeur |
|--------|--------|
| `apps/core/tasks.py:61` — `purger_journal_audit(jours=730)` | **24 mois** |
| `docs/exploitation/runbook.md:204` | **2 ans** |
| `docs/conformite/politique_gestion_donnees.md:62` | **12 mois** |
| `docs/conformite/registre_traitements.md:33` | **12 mois** |

La politique publiée sur le site affirme une durée que le système n'applique pas.
Ce n'est pas une imprécision interne : c'est une information trompeuse au sens de
l'article 13 du RGPD, opposable lors d'une réclamation ou d'un contrôle. Le
runbook confirme que 730 est intentionnel — ce sont donc deux documents qui n'ont
jamais été confrontés, pas un oubli de paramétrage.

**Correction** — Appliquer la valeur retenue au lot 0.1 dans les quatre sources.
Si le choix est 24 mois, ce sont les documents publics qu'il faut corriger.

**Test attendu** — un test qui lit la valeur appliquée et échoue si elle diverge
de la valeur documentée. C'est le seul moyen d'empêcher les deux de dériver à
nouveau ; le dépôt pratique déjà ce genre de verrou
(`apps/core/test_verrou_dependances.py`).

---

### Porte de sortie du lot 1

La boutique et le paiement peuvent être ouverts au public lorsque :

- [ ] les quatre tests du 1.1 passent en CI sur PostgreSQL ;
- [ ] la mention d'obligation de paiement est en place et testée ;
- [ ] les quatre sources de rétention affichent la même valeur, sous test ;
- [ ] le runbook porte les deux nouvelles entrées (§4 et §5).

---

## Lot 2 — Conformité RGPD restante

Ne bloque pas l'ouverture technique, mais conditionne la défendabilité en cas de
réclamation ou de contrôle CNIL. À traiter dans la même fenêtre que le lot 1 :
les trois points partagent la même cause — un registre qui promet ce que le code
ne fait pas.

### 2.1 — Purge du journal d'accès vidéo

*Audit §3.7-B · 🟠 Majeur · Effort : 0,75 j · dépend de 0.2*

**Le défaut** — `JournalAccesVideo` (`apps/elearning/models.py:733`) conserve
`adresse_ip` et `user_agent_hash` à chaque demande de lecture, autorisée ou
refusée. **Aucune purge n'existe** : le planificateur ne couvre que notifications,
sessions et `JournalAudit`, et `purger_journal_audit` ne touche que
`core.JournalAudit`.

Double impact : conservation sans limite d'adresses IP nominatives — alors que le
registre annonce 12 mois pour exactement ces données — et croissance non bornée de
la table la plus écrite du domaine e-learning.

**Correction** — Tâche `elearning.purger_journal_acces` sur le modèle de
`core.purger_journal_audit`, planifiée mensuellement, avec la durée du lot 0.2.

**Tests attendus** — la tâche supprime au-delà du seuil et conserve en deçà ;
la valeur appliquée correspond à la valeur documentée (même verrou qu'en 1.3).

**Documentation** — entrée au tableau §4 du runbook ; ligne correspondante
au registre.

---

### 2.2 — Minimisation de la charge utile Stripe

*Audit §3.7-D · 🟠 Majeur · Effort : 0,75 j · dépend de 0.3*

**Le défaut** — `EvenementStripe.charge_utile` reçoit l'événement Stripe complet
(`webhook.py:70`). Un `checkout.session.completed` transporte `customer_details` :
nom, adresse électronique, adresse postale, pays. Le registre énonce pourtant que
cette charge utile est « à minimiser dès qu'elle n'est plus utile »
(`registre_traitements.md:41`). La mesure est déclarée et absente du code.

**Correction** — Tâche périodique vidant `charge_utile` des événements traités
au-delà du délai retenu. Conserver `identifiant`, `type_evenement`, `reglement`,
`traite` : cela suffit à l'idempotence et à la piste d'audit comptable, sans
conserver les données personnelles du payeur.

**Attention** — cette tâche doit s'exécuter **après** la correction 1.1, sinon
elle viderait la charge utile d'événements encore rejouables. Le délai retenu
doit être très supérieur à la fenêtre de rejeu de Stripe.

**Tests attendus** — la charge utile est vidée au-delà du seuil ; les champs
d'identification et d'idempotence survivent ; un événement non traité n'est
jamais vidé.

---

## Lot 3 — Robustesse et exploitation

*Effort total : 1,5 j*

### 3.1 — Procédure d'indisponibilité de Cloudflare Turnstile

*Audit §3.1-A · 🟡 Mineur · Effort : 0,25 j*

`turnstile.py:59` retourne `False` sur toute exception réseau, et le formulaire de
connexion valide Turnstile avant tout (`accounts/forms.py:26`). Une panne de
`siteverify` bloque donc **toutes** les connexions, personnel compris.

Le choix du fail-closed est le bon : ouvrir le formulaire de connexion quand
l'anti-robot est aveugle serait pire. Ce qui manque est la procédure.

**Correction** — Entrée au §5 du runbook : « Turnstile indisponible », indiquant
la manœuvre (`CLOUDFLARE_TURNSTILE_ENABLED=False`), sa durée maximale, le fait que
`verifier_production` signalera alors l'instance comme non conforme — et que c'est
attendu — puis la remise en service.

**Optionnel** (0,25 j) — distinguer dans les journaux un refus de jeton d'une
panne de `siteverify`, pour que l'alerte dise laquelle des deux se produit.

---

### 3.2 — Planifier l'analyse de vulnérabilités

*Audit §3.1-C · 🟡 Mineur · Effort : 0,25 j*

Le job `security` de `.github/workflows/ci.yml` (pip-audit + npm audit) ne se
déclenche que sur `push` et `pull_request`. Après la mise en service, le dépôt
bougera peu : une CVE publiée sur Django, Wagtail ou Pillow après la dernière
fusion ne sera signalée à personne — alors même que le verrou à empreintes
garantit que l'image déployée contient exactement la version vulnérable.

**Correction** — Ajouter un `schedule` hebdomadaire au job `security`, comme en
portent déjà les cinq workflows de pré-déploiement. Alternative ou complément :
activer Dependabot sur `requirements/*.lock` et `package-lock.json`.

**Point d'attention** — un `schedule` qui échoue en silence ne vaut rien.
Vérifier que l'échec du job remonte bien à quelqu'un.

---

### 3.3 — Unifier la validation des fichiers déposés

*Audit §3.1-B · 🟡 Mineur · Effort : 0,5 j*

`apps/academics/forms.py:18` ne contrôle qu'extension et taille. La même classe de
fichier, côté candidature, passe par extension + MIME + signature binaire, y
compris structure ZIP pour DOCX/ODT (`apps/admissions/formulaires.py:108`).

Le risque immédiat est faible — extensions admises sans `.html`/`.svg`, médias
servis depuis l'origine R2, déposant authentifié. Le vrai coût est la double
règle : deux endroits qui répondent différemment à la même question dérivent.

**Correction** — Extraire `valider_fichier_piece` vers `apps/core/` et l'employer
des deux côtés. L'extraction est préférable à la duplication : elle donne un seul
endroit à faire évoluer le jour où un format s'ajoute.

**Test attendu** — un fichier renommé (contenu HTML en `.pdf`) est refusé à la
remise de devoir comme il l'est déjà à la candidature.

---

### 3.4 — Devis de livraison indisponible : proposer une issue

*Audit §3.6-A · 🟡 Mineur · Effort : 0,5 j*

`templates/commerce/commander.html:50` désactive le bouton quand la destination
n'est pas tarifée. Le message d'erreur existe et est correctement lié par
`aria-describedby`, mais l'acheteur devant un bouton grisé n'a **aucune action
alternative** proposée. Il abandonne, et l'ITEAG n'en sait rien.

**Correction** — À côté du message, un lien de contact du secrétariat, ou la
proposition du retrait sur place quand la destination n'est pas couverte.

**Test attendu** — la page rend une issue actionnable lorsque le devis échoue.

---

## Lot 4 — Nettoyage

*Effort total : 0,5 j · aucun impact fonctionnel, uniquement de la dette évitée*

| # | Point | Fichier | Action |
|---|-------|---------|--------|
| 4.1 | Configuration Nginx morte | `src/nginx/` | Supprimer, ou ajouter un en-tête disant que ce répertoire ne décrit pas le déploiement Coolify. Le risque est qu'un durcissement futur y soit écrit sans effet. |
| 4.2 | `aria-current="true"` | `templates/partials/header.html:31,50` | Remplacer par `aria-current="page"`, jeton prévu pour la rubrique courante. |
| 4.3 | Variables Bunny hors réglages | `apps/elearning/bunny_metadata.py:26` | Passer par les réglages Django et les ajouter à `verifier_production`. Leur absence dégrade aujourd'hui en silence (chapitres vides). |
| 4.4 | JSON-LD `Course` partiel | `templates/formations/cours_detail.html` | Étendre aux fiches `parcours_detail` et aux modules e-learning. Gain SEO, aucun impact fonctionnel. |
| 4.5 | Contradiction `.gitignore` | `src/.gitignore` | `package-lock.json` y est ignoré alors que la racine le documente comme versionné. Sans effet aujourd'hui (le fichier est suivi), mais trompeur. |
| 4.6 | `/healthz` public | `apps/core/views.py:183` | Arbitrer : restreindre par en-tête ou par réseau, ou assumer. À décider avec l'exploitant selon le mode de supervision retenu. |

---

## Lot 5 — Hors code : ITEAG et exploitant

**C'est ce lot qui lève les limites de l'audit, et il n'est pas à notre main.**
Il reprend le §7 du runbook, qu'il ne remplace pas.

| # | Point | Qui | Preuve attendue |
|---|-------|-----|-----------------|
| 5.1 | Exercice de restauration R2 chronométré et réussi | Exploitant | Compte rendu daté : durée, périmètre restauré, écarts constatés |
| 5.2 | Verrouillage / lifecycle des buckets R2 vérifié | Exploitant | Capture de la configuration Cloudflare |
| 5.3 | Service de sauvegarde actif, sauvegarde récente constatée | Exploitant | Liste des objets du bucket avec horodatage |
| 5.4 | Tâches planifiées déclarées et vérifiées en service | Exploitant | Journal Beat montrant les exécutions réelles |
| 5.5 | Alertes branchées sur `/healthz` et Sentry | Exploitant | Test d'alerte déclenché et reçu |
| 5.6 | Compte Bunny, zone de diffusion, clé de signature | ITEAG | `manage.py verifier_bunny` passant sur la préproduction |
| 5.7 | Masters vidéo conservés hors du fournisseur | ITEAG | Attestation de l'emplacement de conservation |
| 5.8 | Import du catalogue bibliothèque | ITEAG fournit l'export | `importer_notices` exécuté, volumétrie constatée |
| 5.9 | Migration du contenu éditorial | ITEAG fournit les textes validés | Pages publiées et relues |
| 5.10 | Table de redirections depuis l'ancien site | ITEAG fournit la liste | Redirections chargées et testées |
| 5.11 | Second facteur activé sur chaque compte administratif | Secrétariat + direction | Liste des comptes avec appareil TOTP confirmé |
| 5.12 | **Identité légale renseignée** | ITEAG | `verifier_production` passe : forme juridique, immatriculation, directeur de publication, hébergeur, médiateur |
| 5.13 | **Statut juridique tranché au regard de l'obligation légale d'accessibilité** | ITEAG | Position écrite : l'art. 47 de la loi 2005-102 s'applique ou non |
| 5.14 | DPA signés : OVH, Cloudflare, Stripe, Sentry, Bunny, messagerie | ITEAG | Contrats archivés |

Les points 5.8 à 5.10 dépendent de données que seul l'ITEAG détient : ils ne
peuvent pas être anticipés côté technique. Le point 5.12 est déjà bloquant au
déploiement — `verifier_production` refuse une instance dont l'une de ces valeurs
est vide.

---

## Lot 6 — Vérification finale et prononcé du GO

*Effort : 1 j · à exécuter après les lots 1 à 5, sur la préproduction*

Les corrections ne suffisent pas : il faut produire les preuves que l'audit
initial n'a pas pu produire. Chaque ligne ci-dessous lève une limite nommée du
rapport.

| # | Vérification | Limite levée |
|---|--------------|--------------|
| 6.1 | Suite complète verte **sur PostgreSQL 16, Python 3.12, Django 5.2.16** — donc en CI, pas en local | Limite 3 : suite exécutée hors cible |
| 6.2 | Couverture recalculée et constatée au-dessus du plancher | Limite 4 |
| 6.3 | `pip-audit` et `npm audit` verts sur les verrous déployés, à J-0 | Limite 5 : CVE non vérifiées |
| 6.4 | Rapports Lighthouse, ZAP baseline, interactions clavier/mobile, captures visuelles **lus**, écarts arbitrés | Limite 2 : résultats CI non consultés |
| 6.5 | En-têtes réellement servis relevés sur la préproduction en HTTPS : CSP, HSTS, `X-Robots-Tag`, `Permissions-Policy`, `frame-ancestors` | Limite 1 : pas d'environnement live |
| 6.6 | Parcours de bout en bout en conditions réelles : candidature, achat de module, commande boutique avec paiement carte, lecture d'une vidéo protégée, remboursement Stripe | Limite 1 |
| 6.7 | Test réel du chemin de panne du 1.1 : provoquer un échec de livraison, vérifier que la réparation rattrape et que le secrétariat est notifié | Limite 1 — et c'est la vérification la plus importante du plan |
| 6.8 | `manage.py verifier_production` **sans** `--sans-base`, sur le serveur | Limite 6 : configuration fournisseurs |
| 6.9 | Relecture du présent rapport et du plan par un tiers | Limite 8 : rapport non contre-vérifié |

**Le GO sans réserve est prononçable lorsque les 9 lignes du lot 6 sont
constatées et datées, et non lorsque les lots 1 à 4 sont fusionnés.**

---

## Ce que ce plan ne fait pas

Par honnêteté sur son périmètre :

- **Il ne traite pas la performance en charge.** Aucun test de montée en charge
  n'est prévu ; l'audit n'a relevé aucun N+1 en lecture statique, mais les temps
  de réponse réels restent inconnus. Pour un institut de cette taille, c'est un
  arbitrage raisonnable — à assumer explicitement, pas à ignorer.
- **Il ne traite pas l'accessibilité au-delà du code.** Contrastes réels, ordre de
  tabulation, zoom 200 %, lecteurs d'écran : le lot 6.4 s'appuie sur les outils
  automatiques, qui couvrent au mieux la moitié des critères WCAG. Un audit
  d'accessibilité conduit par une personne, idéalement concernée, reste le seul
  moyen de savoir. À arbitrer selon le point 5.13.
- **Il ne rejuge pas les choix d'architecture.** Ils sont documentés en ADR,
  cohérents et testés. Les remettre en cause à ce stade coûterait plus que ce que
  cela rapporterait.

---

*Plan établi le 9 août 2026, à partir de l'audit du commit `c43bfcc`.
Toute fusion sur `main` postérieure à ce commit invalide les références
fichier:ligne et demande une revérification.*
