# Audit pré-déploiement — ITEAG (refonte)

> **Suites données** : les constats de ce rapport ont été traités après sa
> rédaction. Voir [`corrections-audit-2026-08-09.md`](corrections-audit-2026-08-09.md)
> pour ce qui a été corrigé, ce qui reste à saisir par l'ITEAG, et ce qui a été
> délibérément laissé de côté. Le présent rapport reste le constat tel qu'établi
> au commit ci-dessous : il n'a pas été réécrit a posteriori.

Date : 2026-08-09 · Commit audité : `3400bab14cef84139731923a2ca022ca5cfa520e` (« Aligner le runbook sur les sauvegardes R2 », 2026-08-08 23:17:47 -0300) · Branche : `main`
Environnement live : https://iteag-preprod.137.74.169.188.sslip.io (répond 200)

**État du working tree au moment de l'audit** : deux fichiers non suivis, `SKILL.md` et `.claude/audit-preprod-iteag.md`. Ils décrivent la procédure d'audit elle-même et ne font pas partie de l'application. Aucun fichier suivi modifié : le code audité est exactement celui du commit ci-dessus.

**Nature du mandat** : lecture, analyse, rapport. Aucun fichier du projet n'a été modifié, aucun commit, aucune commande destructive. Les seules écritures ont eu lieu hors du dépôt (répertoire temporaire) et dans le présent rapport.

---

## 1. Cartographie (constats factuels)

### Stack réelle

| Élément | Valeur constatée | Source |
|---|---|---|
| Framework | Django 5.2.16 (LTS), Wagtail 7.4.2 (LTS) | `requirements/prod.lock` |
| Python cible | 3.12 (`pyproject.toml:requires-python`), CI et `Dockerfile.prod` en 3.12 | `pyproject.toml`, `.github/workflows/ci.yml` |
| Base | PostgreSQL 16 en production ; SQLite en repli local | `config/settings/prod.py:24`, `docker-compose.prod.yml` |
| Cache / file | Redis 7 (`django-redis`, Celery broker + beat) | `config/settings/prod.py:117-125`, `base.py:418-458` |
| Serveur | Gunicorn derrière le proxy Coolify/Traefik ; WhiteNoise pour les statiques | `Dockerfile.prod`, `prod.py:70-78` |
| Médias | Cloudflare R2 via `django-storages` S3, URL signées (`AWS_QUERYSTRING_AUTH = True`, TTL 3600 s) | `prod.py:84-102` |
| Vidéo | Bunny Stream, jetons de lecture signés côté serveur | `base.py:500-535`, ADR-001/005 |
| Paiement | Stripe Checkout hébergé (aucune donnée bancaire sur le serveur) | `base.py:466-491`, ADR-006 |
| Frontend | Tailwind 4 compilé, `hls.js`, htmx, Alpine ; aucun framework SPA | `package.json`, ADR-003 |
| Observabilité | Sentry, journalisation JSON structurée, sonde `/healthz` | `prod.py:131-176`, `config/urls.py:69` |

### Structure

Monorepo à racine mince : `src/` porte l'application, `docs/` la documentation d'exploitation et d'architecture (6 ADR, un runbook, un registre de traitements RGPD), `config/` la configuration de déploiement, `.github/workflows/` neuf workflows.

15 applications Django locales, ~65 000 lignes de Python :

| App | Fichiers .py | Lignes | Rôle constaté |
|---|---:|---:|---|
| `core` | 80 | 9 501 | Socle : mixins de rôle, middlewares, notifications, PDF, journalisation |
| `elearning` | 44 | 9 929 | Modules vidéo payants, contrôle d'accès, quotas de flux |
| `administration` | 42 | 9 780 | Back-office secrétariat/direction (91 routes) |
| `lms` | 34 | 6 347 | Devoirs, évaluations, espace enseignant |
| `website` | 47 | 5 736 | Pages Wagtail publiques, actualités, articles, sitemaps |
| `academics` | 31 | 4 197 | Sessions, promotions, profils étudiants, crédits ECTS |
| `commerce` | 24 | 3 567 | Boutique de livres, stock, commandes |
| `documents` | 26 | 3 497 | Documents administratifs et courriers, génération PDF |
| `admissions` | 28 | 2 625 | Candidatures, pièces justificatives |
| `paiements` | 25 | 2 599 | Règlements Stripe, webhook, réconciliation |
| `library` | 26 | 2 432 | Catalogue et prêts |
| `accounts` | 26 | 2 085 | Utilisateurs, 2FA, connexion |
| `portail_etudiant` | 8 | 1 058 | Agrégation côté étudiant |
| `formations` | 17 | 1 357 | Parcours, cours, professeurs |
| `portail_enseignant` | 8 | 491 | Agrégation côté enseignant |

809 routes résolues au total (`config/urls.py` + inclusions ; mesuré par inspection du résolveur Django).

### Ce que le projet fait réellement

Plateforme unique couvrant sept métiers : site institutionnel éditorialisé (Wagtail), catalogue de formations, dépôt et instruction de candidatures, scolarité (sessions, notes, présences, ECTS), e-learning vidéo payant à accès contrôlé, bibliothèque avec prêts, boutique de livres avec stock et encaissement Stripe. Trois portails distincts (étudiant, enseignant, administration) plus l'admin Wagtail et l'admin Django.

### Version précédemment en production

Aucun tag git, aucune branche de release. `config/urls.py:44-52` conserve sept redirections 301 depuis d'anciennes adresses (`presentation`, `education`, `diploma`, `enroll`…), ce qui atteste d'un site antérieur, mais son code n'est pas dans ce dépôt. **Le diff avec la version précédemment en production n'est donc pas établissable** ; l'audit porte sur l'état de `main` seul.

### Registre de couverture des surfaces

| Surface | État | Précision |
|---|---|---|
| Applications / modules (15) | AUDITÉ PARTIELLEMENT | Toutes cartographiées ; lecture approfondie sur `core`, `accounts`, `paiements`, `elearning`, `documents`, `commerce`, `administration` (mixins) |
| Routes publiques | AUDITÉ | 18 adresses sondées en live + sitemap complet (86 URL) |
| Routes authentifiées | AUDITÉ PARTIELLEMENT | Inventaire statique des 809 routes et de leur exigence d'auth ; comportement live non testé (pas de compte) |
| Interfaces d'administration | AUDITÉ PARTIELLEMENT | `/django-admin/` et `/admin/` redirigent vers login (vérifié live) ; écrans internes lus en code seulement |
| Modèles de données | AUDITÉ PARTIELLEMENT | Modèles de `paiements`, `elearning`, `documents`, `commerce` lus ; les autres survolés |
| Formulaires | AUDITÉ | Balayage des 19 gabarits portant des champs + vérification live |
| API / endpoints | AUDITÉ | Webhook Stripe, `/healthz`, endpoints de lecture vidéo (code) |
| Tâches asynchrones | AUDITÉ PARTIELLEMENT | `CELERY_BEAT_SCHEDULE` lu, heartbeat vérifié en code ; exécution réelle NON VÉRIFIABLE |
| Services externes | AUDITÉ PARTIELLEMENT | Stripe, R2, Bunny, Turnstile, Sentry : configuration et contrat lus ; disponibilité réelle NON VÉRIFIABLE |
| Fichiers de configuration | AUDITÉ | `base.py`, `prod.py`, `.env.prod.example`, `docker-compose.prod.yml`, `Dockerfile.prod` |
| Authentification / autorisation | AUDITÉ | 7 mixins de rôle, 2FA, django-axes, Turnstile |
| Templates / pages | AUDITÉ PARTIELLEMENT | 10 pages publiques téléchargées et analysées ; gabarits back-office lus par balayage |
| Statiques et frontend | AUDITÉ | En-têtes, compression, versions, poids mesurés en live |
| Parcours utilisateurs | AUDITÉ PARTIELLEMENT | Parcours publics parcourus ; parcours authentifiés NON VÉRIFIABLES |
| Configuration de déploiement | AUDITÉ | Compose, Dockerfile, scripts de go-live, doc Coolify |
| Tests | AUDITÉ | Suite complète exécutée (voir §4) |
| CI/CD | AUDITÉ | Les 9 workflows lus |
| Dépendances | AUDITÉ | `pip-audit` et `npm audit` exécutés |
| Données personnelles | AUDITÉ | Page publique + registre des traitements + sous-traitants nommés |

Aucune surface identifiée en cartographie n'a disparu du rapport.

### Matrice de couverture des domaines

| Domaine | État | Ce qui fonde cet état |
|---|---|---|
| Sécurité | COUVERT | Secrets, en-têtes live, auth/autorisation, CVE (pip-audit + npm audit exécutés), webhook signé, uploads, CSRF |
| Architecture | COUVERT | Graphe de dépendances (test dédié), séparation des responsabilités, gestion des erreurs |
| Qualité | COUVERT | Ruff configuré et appliqué en CI, gestion d'erreurs balayée, dette recherchée |
| Tests | COUVERT | Suite exécutée intégralement, couverture CI à 90 % minimum vérifiée dans le workflow |
| Performance | PARTIELLEMENT COUVERT | Mesures live réelles, mais sur un jeu de données très réduit ; pas de Lighthouse local |
| Accessibilité | PARTIELLEMENT COUVERT | Structure sémantique, noms accessibles, arbre d'accessibilité navigateur ; ni lecteur d'écran, ni contraste mesuré |
| UX | PARTIELLEMENT COUVERT | Parcours publics, états vides, 404 ; parcours authentifiés non testés |
| SEO | COUVERT | Meta par page, sitemap, robots, canonical, données structurées, redirections |
| Conformité | COUVERT | Mentions légales, CGV, RGPD, cookies, statut RGAA |
| Exploitation / déploiement | COUVERT | Compose, image, sauvegardes, runbook, gates de readiness |

---

## 2. Synthèse exécutive

| Sévérité | Nombre |
|---|---:|
| 🔴 Bloquant | 1 |
| 🟠 Majeur | 3 |
| 🟡 Mineur | 2 |
| ⚪ Observation | 6 |

### Verdict : **GO CONDITIONNEL**

**Seul point bloquant à lever avant la bascule :**

- **R1 — Absence de mentions légales et de conditions générales de vente**, alors que le tunnel de commande impose de cocher « J'accepte les conditions de vente » et que Stripe encaisse réellement.

Rien d'autre n'est bloquant.

**Ce qui fonde ce verdict.** La plateforme est techniquement au-dessus de ce qu'on rencontre habituellement à ce stade : 2 994 tests passent sans échec, aucune vulnérabilité connue dans les dépendances Python ou Node, en-têtes de sécurité complets et vérifiés en live, second facteur imposé aux rôles sensibles, contrat de readiness production exécutable et exécuté en CI, sauvegardes hors serveur avec restauration éprouvée. Le risque technique d'ouverture est faible. Le point bloquant n'est pas technique : c'est une obligation légale non satisfaite sur un site qui vend. Il se corrige par la publication de deux pages éditoriales — le type de page Wagtail prévu à cet effet mentionne d'ailleurs explicitement les mentions légales dans sa description (`apps/website/models.py:292`).

**Nuance sur R1.** Si l'ITEAG décide d'ouvrir sans la boutique ni les modules payants, l'absence de CGV cesse d'être bloquante et R1 se ramène aux seules mentions légales — obligation qui, elle, subsiste pour tout site professionnel publié. Le point resterait alors 🟠, pas 🔴.

---

## 3. Détail par critère

### 3.1 Sécurité

**Ce qui a été vérifié et tient.**

En-têtes de la réponse publique (`curl -sSI` sur l'accueil, 2026-08-09) : CSP nominative sans `unsafe-inline` sur `script-src`, `frame-ancestors 'none'`, `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Cross-Origin-Opener-Policy: same-origin`, `Referrer-Policy: same-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=(), usb=()`, `X-Robots-Tag: noindex, nofollow, noarchive`. Cookie CSRF `Secure`, `HttpOnly`, `SameSite=Lax`. HTTPS effectif sur le domaine sslip.io.

Aucun secret dans le dépôt : `git ls-files` ne suit ni `.env`, ni `.env.production`, ni base de données ; la recherche de motifs (`sk_live_`, `whsec_`, `AKIA`, `-----BEGIN`) ne remonte que des valeurs de test dans des fichiers de test. `src/scripts/coolify-push-env.ps1` lit le jeton API en saisie masquée et ne l'écrit nulle part.

Webhook Stripe : signature vérifiée par `client.Webhook.construct_event(payload, sig_header, secret)` avant tout traitement (`apps/paiements/services/stripe_client.py:108-115`) ; absence de signature → 400 ; secret absent → 503 ; rejeu idempotent (`EvenementDejaTraite`).

Autorisation : sept mixins de rôle (`apps/core/mixins.py`), 255 usages recensés. `UserPassesTestMixin` lève `PermissionDenied` — donc 403, pas une boucle de redirection — pour un utilisateur authentifié qui échoue au test (vérifié dans le Django installé, `django/contrib/auth/mixins.py:46-48`). Les vues e-learning qui n'ont pas de mixin revérifient explicitement le droit à chaque appel via `verifier_acces` (`apps/elearning/views.py:250, 344, 417`), y compris pour les ressources PDF et l'URL de lecture — l'hypothèse d'un trou d'autorisation sur ce préfixe a été testée et écartée.

Téléversements : validation de taille, de taille nulle, du type MIME normalisé **et de la signature d'en-tête du fichier** (`apps/admissions/formulaires.py:56-122`) ; les tests couvrent le faux PDF (`MZ` en en-tête), le MIME menteur et le `.exe`.

Dépendances — commandes réellement exécutées le 2026-08-09 :

```
pip-audit -r <versions extraites de requirements/prod.lock>  → No known vulnerabilities found
npm audit --audit-level=high --json                          → 0 vulnérabilité (77 dépendances)
```

Conclusion autorisée par ces résultats : *aucun problème correspondant aux contrôles réalisés par ces deux outils n'a été détecté lors de cette exécution*. Cela ne vaut pas certificat d'absence de vulnérabilité.

Le verrou `prod.lock` porte les empreintes de chaque archive et la CI installe avec `--require-hashes` : une archive substituée sur l'index serait refusée.

Conteneur : utilisateur non-root (`Dockerfile.prod:73, 101`), `HEALTHCHECK`, aucun port publié sur l'hôte (`expose` seul), limites mémoire par service.

**🟡 R6 — L'identifiant de compte Cloudflare R2 est publié dans l'en-tête CSP de chaque réponse.**

*Constat.* `curl -sSI https://iteag-preprod.137.74.169.188.sslip.io/` retourne, dans la CSP :
`img-src 'self' data: https://*.stripe.com https://85e8c708984e31dec68bae21e877a22e.r2.cloudflarestorage.com`.
Cette chaîne est l'identifiant du compte Cloudflare. Elle vient de `config/settings/prod.py:107-110`, qui injecte `AWS_S3_ENDPOINT_URL` dans la CSP faute de `AWS_S3_CUSTOM_DOMAIN`.

*Impact.* Divulgation d'un élément d'infrastructure sur chaque réponse HTTP. Non exploitable seul : les objets sont privés et servis en URL signée à durée limitée (`AWS_QUERYSTRING_AUTH = True`, `AWS_QUERYSTRING_EXPIRE = 3600`). Le préjudice est un gain de reconnaissance pour un attaquant, pas un accès.

*Correctif.* Renseigner `AWS_S3_CUSTOM_DOMAIN` avec un domaine personnalisé R2 : le code utilise déjà cette variable en priorité (`prod.py:107`), aucune modification applicative n'est nécessaire.

*Tentative de réfutation.* J'ai vérifié que les médias ne sont pas publics — `AWS_DEFAULT_ACL = None`, `AWS_QUERYSTRING_AUTH = True`, et `verifier_production` refuse une instance où cette dernière serait désactivée (`production.py:106-107`). Le risque ne va donc pas au-delà de la divulgation.

**⚪ O2 — `AXES_LOCKOUT_PARAMETERS = ["username"]` n'est pas justifié par écrit.**

Le verrouillage porte sur l'identifiant seul (`config/settings/base.py:212`), ce qui expose en théorie un compte connu à un déni de service ciblé (5 échecs → 30 minutes). Ce point avait d'abord été classé 🟡 ; la passe de contradiction l'a fait tomber, preuve à l'appui : `apps/accounts/forms.py:24-28` valide Turnstile **avant** d'appeler `authenticate()`, et django-axes ne compte les échecs qu'au signal émis par `authenticate()`. Un échec Turnstile n'incrémente donc jamais le compteur, et `verifier_production` impose Turnstile en production (`production.py:94-98`). Le verrouillage par identifiant est par ailleurs l'arbitrage documenté de django-axes contre le *password spraying* distribué, que le verrouillage par IP ne couvre pas. Il reste un fait exact : dans un fichier où presque chaque réglage porte sa justification, celui-ci n'en a aucune. **Action suggérée : deux lignes de commentaire, rien d'autre.**

---

### 3.2 Architecture et qualité du code

**Ce qui tient.** Le graphe de dépendances entre applications est déclaré puis vérifié par un test qui inspecte les imports réels (`apps/core/test_architecture.py`) : une flèche non prévue ou un cycle font échouer la CI. Ruff est configuré avec un jeu de règles étendu (`E, F, W, I, B, UP, S, DJ, PLW1514`) et vérifié en CI en version épinglée.

Gestion des erreurs : huit `except Exception:` larges dans `apps/`. Sept journalisent via `logger.exception` avant de dégrader proprement. Le huitième fait l'objet de R2 ci-dessous. Aucun `except: pass` silencieux ailleurs. Aucun `eval`, `exec`, `pickle` ni `os.system`. Les deux seuls `subprocess.run` (extraction de métadonnées vidéo, sauvegarde PostgreSQL) reçoivent des listes d'arguments fixes, sans shell. Un seul `mark_safe`, appliqué à un JSON dont `<`, `>` et `&` sont préalablement échappés (`apps/core/templatetags/socle_wagtail.py:41-48`). Deux usages de SQL brut : `SELECT 1` dans la sonde de santé, et une migration de réparation de colonnes.

**🟠 R2 — La signature des documents officiels disparaît silencieusement si sa lecture échoue.**

*Constat.* `apps/documents/services_generation.py:15-24` :

```python
def _user_signature_uri(user) -> str:
    if user is None or not user.signature:
        return ""
    try:
        ...
        with user.signature.open("rb") as fichier:
            contenu = base64.b64encode(fichier.read()).decode("ascii")
        return f"data:{type_mime};base64,{contenu}"
    except Exception:
        return ""
```

Le stockage de production est R2 (`prod.py:100-102`) : la lecture est un appel réseau. Une indisponibilité R2, un objet manquant ou un droit retiré produit une chaîne vide, sans journalisation, sans exception remontée.

*Impact.* Le PDF est produit et délivré quand même. Et il ne ressemble pas à un document incomplet : `templates/documents/pdf/document.html:232-240` rend inconditionnellement « Fait aux Abymes, le {{ date }} », la qualité du signataire et son nom ; seule l'image est conditionnelle (`{% if signature_pdf %}`, ligne 234). Un étudiant reçoit donc une attestation de scolarité, un relevé de notes ou un certificat e-learning qui se présente comme signé, sans signature. Le garde-fou aval existe mais ne se déclenche pas : `apps/documents/tasks.py:54-58` bascule la tâche en `ECHEC` sur exception — or l'exception a déjà été avalée, la tâche conclut donc `PRET`. Sentry ne voit rien.

*Nuance établie par la passe de contradiction.* Un repli existe pour les **documents rédigés** : `services_generation.py:111-116` retombe sur la signature du secrétariat si celle du rédacteur est vide. Ce repli couvre le cas « rédacteur sans signature déposée » ; il ne couvre pas une panne du stockage, puisque les deux lectures passent par le même backend. Aucun repli du tout pour les **documents administratifs** (`fabriquer_document_administratif`, ligne 72).

*Couverture de test.* `apps/documents/test_generation_pdf.py` compte onze fonctions, dont `test_la_signature_du_secretariat_est_incluse` (chemin nominal) et `test_la_signature_n_est_pas_scindee` (mise en page). Aucune ne couvre l'échec de lecture.

*Correctif.* Journaliser l'exception (`logger.exception`) avant de retourner la chaîne vide, et distinguer les deux cas au niveau appelant : « aucune signature configurée » est une dégradation acceptable, « signature configurée mais illisible » doit faire échouer la production du document plutôt que livrer une pièce non signée. Ajouter le test du chemin d'échec.

*Tentative de réfutation.* J'ai cherché un contrôle en aval, une vérification dans le gabarit, une alerte dans la tâche Celery et un test du chemin d'échec. Le repli des documents rédigés est le seul mécanisme trouvé, et il ne couvre pas ce scénario. Constat maintenu.

**⚪ O4 — Aucun garde-fou de régression sur le nombre de requêtes SQL.**
`grep -rn "assertNumQueries\|django_assert_num_queries" apps/` : zéro occurrence. Le code est pourtant soigneux (usage systématique de `select_related`/`prefetch_related` dans les vues de portail) et un test dédié interdit déjà la pagination sans tri explicite (`pyproject.toml`, `error::UnorderedObjectListWarning`). Rien ne se dégrade aujourd'hui ; rien n'empêchera une régression demain. Observation, pas action requise avant bascule.

**⚪ O5 — `ASSET_VERSION` coûte un `stat()` par requête pour un effet redondant.**
`apps/core/context_processors.py:21-25` interroge le système de fichiers à chaque rendu de page pour dériver un numéro de version, ajouté en `?v=…` sur des fichiers dont le nom porte déjà une empreinte de contenu (`main.16d136db467b.css`). Le coût est négligeable, la redondance réelle : à chaque reconstruction, la chaîne de requête change même si le contenu n'a pas bougé, ce qui invalide un cache marqué `immutable`.

**⚪ O6 — Artefacts versionnés.** `src/output/pdf/apercu-charte-iteag-attestation.pdf` et `…-courrier.pdf` sont suivis par git. Ce sont des sorties de rendu, pas des sources.

---

### 3.3 Performance

**Mesures réelles**, trois passes par page, TTFB depuis un poste européen vers OVH :

| Page | TTFB (3 mesures, s) | HTML |
|---|---|---:|
| `/` | 0,618 · 0,635 · 0,571 | 47,5 ko |
| `/formations/` | 0,565 · 0,538 · 0,512 | 49,4 ko |
| `/bibliotheque/` | 0,517 · 0,543 · 0,515 | 41,0 ko |
| `/boutique/` | 0,543 · 0,558 · 0,547 | 41,9 ko |
| `/e-learning/` | 0,564 · 0,558 · 0,532 | 26,3 ko |

Statiques : `Cache-Control: max-age=315360000, public, immutable`, ETag, compression effective (CSS 108,6 ko → 15,5 ko transférés). Quatre scripts sur l'accueil, tous locaux, trois en `defer`. Aucun script inline exécutable : les deux blocs `<script>` en ligne sont du JSON-LD (`type="application/ld+json"`), non exécutés — la CSP sans `unsafe-inline` ne les bloque donc pas, et l'absence de nonce dans l'en-tête est le comportement normal de django-csp 4 quand aucun gabarit ne consomme `request.csp_nonce`. Aucune erreur de console relevée sur l'accueil.

Le proxy annonce HTTP/3 (`Alt-Svc: h3=":443"; ma=2592000`).

**Limite importante** : le jeu de données de préproduction est très réduit — 16 notices de bibliothèque, 11 livres, 4 parcours, 1 module e-learning. Ces chiffres ne permettent pas de juger le comportement des listes, de la pagination ni des requêtes à volume réel. `/bibliotheque/?page=2` répond 404, ce qui est le comportement correct d'un paginateur Django sur une seule page de résultats, et non un défaut. Aucun jugement de performance à charge n'est porté ici.

---

### 3.4 Accessibilité (WCAG 2.1 AA en référentiel)

**Ce qui tient.** Sur les dix pages publiques analysées : un `<h1>` unique par page, **aucun saut de niveau de titre**, `<main id="main-content">` et `<nav>` présents partout, lien d'évitement fonctionnel, `lang="fr"`, **toutes les images portent un attribut `alt`**, aucun bouton sans nom accessible. Le champ pot-de-miel est correctement retiré de l'arbre d'accessibilité (`tabindex="-1"`, `aria-hidden="true"`, `sr-only`). Les formulaires Django exposent `aria-invalid` et `aria-describedby` sur les champs en erreur (`apps/core/test_formulaires.py:121-122`).

**🟡 R5 — 18 champs de formulaire sans nom accessible, dans 10 gabarits.**

*Constat, vérifié en code et confirmé en live.* Sur `/bibliotheque/`, exécution dans le navigateur :

```json
{"tag":"INPUT","name":"q","id":null,"labelFor":null,"labelEnglobant":null,
 "ariaLabel":null,"ariaLabelledby":null,"title":null,
 "placeholder":"Rechercher par titre, auteur, mot-clé…"}
{"tag":"SELECT","name":"discipline","id":null,"labelFor":null,"labelEnglobant":null,
 "ariaLabel":null,"ariaLabelledby":null,"title":null,"placeholder":null}
```

Source : `templates/library/catalogue.html:26` et `:31`. Le champ texte n'a qu'un `placeholder` — nom fragile, qui disparaît dès la saisie ; le `<select>` n'a **aucun** nom accessible. L'arbre d'accessibilité du navigateur confirme : `combobox "Toutes disciplines"` expose la valeur, pas une étiquette.

Les 16 autres occurrences se répartissent entre `administration/candidatures.html:43`, `administration/etudiants.html:26,28`, `administration/utilisateurs.html:26,28`, `administration/academics/saisie_presence.html:73,80`, `administration/assiduite/feuille.html:72,79`, `admissions/candidature_suivi.html:69`, `commerce/gestion/commandes.html:82-84`, `commerce/gestion/stock.html:56-57`, `library/gestion_emprunts.html:55`.

*Impact.* Une personne au lecteur d'écran entend « zone d'édition, vide » sur la recherche du catalogue public et n'a aucune indication sur le filtre par discipline. Trois des gabarits concernés sont publics ; les autres sont du back-office, où l'impact reste réel pour un agent concerné mais touche moins de personnes.

*Ce qui rend le constat plus solide qu'une préférence de style.* La même page `/boutique/` fait correctement `<label for="q" class="form-label">Rechercher un livre</label>` (`templates/commerce/catalogue.html`). Ce n'est donc pas une convention assumée du projet, c'est un oubli — et il est passé au travers parce que `/bibliotheque/` ne fait pas partie des quatre pages auditées par le gate d'accessibilité (voir R4).

*Correctif.* Ajouter un `id` et un `<label>` (visible ou `sr-only`) sur chaque champ listé. Étendre la liste de pages du workflow Lighthouse à `/bibliotheque/`, `/boutique/`, `/e-learning/`.

*Tentative de réfutation.* Deux faux positifs de mon balayage initial ont été identifiés et écartés : le pot-de-miel `site_web` (correctement `aria-hidden`) et la case `disponible` de `/boutique/`, enveloppée dans un `<label>` — étiquetage implicite valide. Le chiffre de 18 tient après ces retraits.

**Non vérifié** : contraste des couleurs (aucune mesure instrumentée effectuée), navigation clavier complète, restitution réelle par lecteur d'écran. Un test du projet vérifie déjà « une hiérarchie de titres et un contraste lisibles » dans le pied de page (`apps/core/test_predeploy_go.py:49`), mais je ne l'ai pas étendu.

---

### 3.5 SEO

**Ce qui tient.** Titre et `meta description` propres à chaque page (vérifié sur l'accueil, `/formations/`, `/bibliotheque/`, `/formations/parcours/diplomant-iteag/`). `robots.txt` présent et cohérent (interdit `/admin/` et `/django-admin/`). `sitemap.xml` généré, couvrant neuf sections. Données structurées `EducationalOrganization` sur l'accueil. Balisage sémantique réel (`<main>`, `<nav>`, `<article>`, `<section>`, `<header>`). Sept redirections 301 depuis les anciennes adresses, plus deux redirections de préfixe. Page 404 personnalisée et correctement codée 404. La préproduction est protégée de l'indexation par un `X-Robots-Tag` appliqué à tout hôte hors `iteag.org`/`www.iteag.org` (`apps/core/middleware.py:76-80`), mécanisme couvert par deux tests (`test_predeploy_go.py:79, 90`).

**🟠 R3 — Le contrat de production ne vérifie pas l'alignement entre l'hôte servi, `SITE_URL` et l'enregistrement `Site` de Wagtail.**

*Constat, observé en live.* La page servie sur `iteag-preprod.137.74.169.188.sslip.io` déclare :

```html
<link rel="canonical" href="https://t13h3q80c3cmb5zcw2kzlojy.137.74.169.188.sslip.io/">
<meta property="og:url" content="https://t13h3q80c3cmb5zcw2kzlojy.137.74.169.188.sslip.io/">
"@id": "https://t13h3q80c3cmb5zcw2kzlojy.137.74.169.188.sslip.io/#organization"
```

`curl` sur cet hôte canonique retourne **503**. Le `robots.txt` annonce un sitemap sur ce même hôte. Et le `sitemap.xml` **mélange deux noms d'hôtes** : 9 URL sur `t13h3…` (la partie produite par le sitemap Wagtail) et 77 sur `iteag-preprod…` (les sitemaps applicatifs).

*Ce qui est, et ce qui n'est pas, le défaut.* Le symptôme visible en préproduction est une erreur de variable d'environnement : `CANONICAL_URL` se construit à partir de `settings.SITE_URL` (`apps/core/context_processors.py:31`), et positionner `SITE_URL=https://iteag.org` le fait disparaître sans toucher au code. **Pris isolément, ce symptôme est une observation, pas un défaut majeur.**

Le défaut majeur est ailleurs, et il survit à la correction de `SITE_URL` : la moitié Wagtail du sitemap provient de l'enregistrement `Site` **en base de données**, qu'aucune variable d'environnement ne pilote. Il faudra le modifier à la main le jour de la bascule, et **rien ne le rappelle ni ne le vérifie** :

- `apps/core/services/production.py:35-53` contrôle que `SITE_URL` est une URL HTTPS absolue, que `WAGTAILADMIN_BASE_URL` partage son origine, que l'hôte figure dans `ALLOWED_HOSTS` et l'origine dans `CSRF_TRUSTED_ORIGINS` — mais jamais que `SITE_URL` corresponde à l'hôte réellement servi, ni que l'enregistrement `Site` de Wagtail s'y aligne ;
- `src/scripts/verifier_go_live.sh` (lu intégralement) tape `$GO_LIVE_BASE_URL/healthz` et ne compare aucune URL canonique.

*Impact.* En production, si l'enregistrement `Site` de Wagtail reste sur son hôte de préproduction, l'ensemble des pages éditoriales du sitemap pointe vers un hôte étranger et n'est pas indexé, et toutes les URL absolues produites côté Wagtail (courriels de notification, aperçus) sont fausses. La préproduction est la démonstration expérimentale que ce trou laisse passer exactement cette erreur, sans qu'aucun gate ne s'en aperçoive.

*Correctif.* Ajouter au contrat de production un contrôle comparant l'hôte de `SITE_URL`, l'hôte du `Site` Wagtail par défaut et l'hôte réellement servi ; et ajouter au `verifier_go_live.sh` une assertion que le `<link rel="canonical">` de la page d'accueil est bien `$GO_LIVE_BASE_URL/`. Trois lignes dans chacun des deux, pour supprimer une classe entière d'erreur de bascule.

*Tentative de réfutation.* J'ai cherché si `verifier_production` ou `verifier_go_live.sh` couvraient déjà le cas — non — et si un contrôle Wagtail natif s'en chargeait — non. J'ai aussi vérifié le contre-argument « c'est purement un problème de préprod » : il est partiellement juste, ce pourquoi le constat a été réénoncé et le symptôme préprod déclassé en observation.

**⚪ O3 — `meta robots` contredit `X-Robots-Tag` en préproduction.**
L'accueil de la préproduction sert `<meta name="robots" content="index, follow">` alors que l'en-tête HTTP dit `noindex, nofollow, noarchive`. En pratique la directive la plus restrictive s'applique, et le mécanisme d'en-tête est testé ; il n'y a donc pas de risque d'indexation. La contradiction reste un piège pour qui inspecterait le HTML sans regarder les en-têtes.

**⚪** Les fiches de parcours ne portent pas de données structurées `Course`. C'est une opportunité, pas un défaut : rien n'oblige à les produire.

---

### 3.6 UX et parcours utilisateur

**Ce qui tient.** États vides traités (`/bibliotheque/?q=zzzzznoresult` → « Aucun résultat pour « zzzzznoresult ». »). Page 404 personnalisée, en français, avec le bon code HTTP. Bandeau cookies présent, avec deux actions explicites — « Essentiels uniquement » et « Accepter les préférences » — et un lien vers la politique. Recherche du catalogue en direct via htmx avec indicateur de chargement et `hx-push-url`. Barre de navigation cohérente entre pages. Un test dédié suit les parcours de bout en bout par rôle (`apps/core/test_parcours_roles.py`), en vérifiant qu'un écran atteignable depuis la barre d'un rôle est bien ouvrable par ce rôle.

**Non vérifié.** Les parcours authentifiés — candidature, scolarité, lecture d'un module, commande, paiement — n'ont pas été exercés en live : je n'ai pas de compte sur la préproduction, et je n'ai volontairement soumis aucun formulaire public (l'envoi de courriels réels au secrétariat et la création d'enregistrements sur la préproduction sortent du mandat de lecture). Le responsive n'a pas été testé sur appareil réel.

---

### 3.7 Conformité et légal

**Statut de l'établissement.** Rien dans le dépôt n'établit un statut public ou parapublic. L'ITEAG se présente comme un institut de théologie évangélique privé. **L'obligation légale d'accessibilité (RGAA) n'est donc pas établie** — elle vise les organismes publics et les entreprises au-delà d'un seuil de chiffre d'affaires. Je ne l'affirme ni dans un sens ni dans l'autre : c'est à l'ITEAG de confirmer son statut. WCAG reste, indépendamment de toute obligation, le référentiel de qualité retenu par le projet lui-même (le gate CI exige un score d'accessibilité de 0,95 minimum).

**RGPD — conforme sur le volet information.** La page `/protection-des-donnees/` (version du 8 août 2026) identifie le responsable de traitement avec sa raison sociale complète, son adresse postale, son courriel et son téléphone ; énonce les finalités et les bases légales ; traite les durées de conservation ; expose les droits d'accès, de rectification, d'effacement, d'opposition et de portabilité ; mentionne la réclamation auprès de la CNIL ; et **nomme les sous-traitants** (Stripe, Bunny, Sentry, Cloudflare). Une page `/cookies/` distincte précise qu'aucun outil publicitaire ni mesure d'audience n'est utilisé. Le dépôt porte en outre un registre des traitements (`docs/conformite/registre_traitements.md`) et une politique de gestion des données. C'est nettement au-dessus de la pratique courante.

**🔴 R1 — Aucune page de mentions légales, aucune condition générale de vente.**

*Constat.* Vérifié par cinq voies convergentes :

1. Aucune occurrence de « mentions légales », « conditions générales », « CGV », « CGU », « rétractation », « SIRET » ou « SIREN » dans `src/templates/`, `src/apps/` ou `src/config/`.
2. `/mentions-legales/`, `/mentions/`, `/cgv/`, `/conditions-generales/`, `/conditions-generales-de-vente/`, `/legal/` répondent tous **404** sur la préproduction.
3. Le `sitemap.xml` complet — 86 URL, qui recense les pages publiques réellement publiées, y compris `/cookies/` et `/protection-des-donnees/` — n'en contient aucune.
4. Aucune des dix pages publiques analysées n'y renvoie ; le pied de page ne lie que `/actualites/`, `/contact/`, `/presentation/`, `/cookies/` et `/protection-des-donnees/`.
5. **La preuve décisive** — `apps/commerce/forms.py:33` :

```python
accepte_conditions = forms.BooleanField(
    label="J'accepte les conditions de vente et confirme ma commande."
)
```

Champ **obligatoire** (`BooleanField` sans `required=False`), affiché dans le tunnel de commande (`templates/commerce/commander.html:24`, rendu couvert par `apps/commerce/tests/test_commerce.py:171`), **sans le moindre lien vers un document**. Le site ne se contente pas d'omettre ses CGV : il recueille l'acceptation d'un document qui n'existe pas.

*Impact.* Deux obligations distinctes ne sont pas satisfaites, sur un site qui s'apprête à encaisser :

- **Mentions légales** — obligatoires pour tout site professionnel publié en France (LCEN, art. 6-III). L'identité de l'éditeur figure bien, matériellement, dans la page de protection des données (raison sociale, adresse, contact) ; manquent le directeur de la publication, l'hébergeur et l'immatriculation.
- **Conditions générales de vente et information précontractuelle** — obligatoires dès lors qu'un bien ou un service est vendu à distance à des consommateurs (Code de la consommation, art. L221-5 et suivants : prix, délais, modalités de livraison, droit de rétractation et ses exceptions, garanties, réclamation). Le consentement recueilli sur un référentiel inexistant est, en outre, juridiquement sans objet.

*Correctif.* Publier deux pages éditoriales. Aucun développement n'est requis : le type de page Wagtail « Page de contenu » est explicitement prévu pour cela — sa description de saisie mentionne « présentation, historique, **mentions légales** » (`apps/website/models.py:292`). Y ajouter le lien dans le pied de page et depuis la case `accepte_conditions`. Le contenu des CGV relève d'un conseil juridique, pas de l'équipe technique.

*Tentative de réfutation.* Trois pistes explorées et écartées : (a) une page publiée sous un autre nom — le sitemap exhaustif n'en contient aucune ; (b) le contenu réparti ailleurs — partiellement vrai pour l'identité de l'éditeur, faux pour tout le reste, et **totalement absent pour les CGV** ; (c) un modèle de page absent qui expliquerait le retard — non, le modèle existe et cite l'usage. Constat maintenu en 🔴.

*Réserve honnête sur la sévérité.* Ce point est bloquant parce que le site vend. Si la boutique et les modules payants restent fermés à l'ouverture, il retombe à 🟠 et se limite aux mentions légales.

---

### 3.8 Exploitation et déploiement

**Ce qui tient, et qui mérite d'être dit.** `docker-compose.prod.yml` décrit sept services avec dépendances ordonnées : `migrate` s'exécute jusqu'au bout avant que `web`, `worker`, `beat` et `backup` ne démarrent. Sauvegardes PostgreSQL vers un bucket R2 **distinct** de celui des médias, avec rétention quotidienne et mensuelle, et surtout **restauration non destructive réellement éprouvée** par `scripts/verifier_go_live.sh`, qui refuse explicitement de cibler la base de production. Le runbook (`docs/exploitation/runbook.md`) est écrit pour l'exploitant, pas pour le développeur, et marque honnêtement d'un ⚠️ **À VALIDER** ce qui ne peut pas l'être depuis un poste de développement. La console Coolify n'est pas exposée sur Internet (règle `DOCKER-USER`, accès par tunnel SSH), et le document explique pourquoi il ne faut pas rouvrir les ports.

**🟠 R4 — Les cinq workflows `predeploy-*` ne s'exécutent plus sur aucune pull request.**

*Constat.* Les cinq sont gardés par une condition sur le nom de la branche source :

| Workflow | Condition `if:` |
|---|---|
| `predeploy-lighthouse.yml` | `workflow_dispatch` \| `agent/predeploy-go-readiness` \| `agent/go-live-ops-gate` |
| `predeploy-live-audit.yml` | `workflow_dispatch` \| `agent/predeploy-go-readiness` |
| `predeploy-interactions.yml` | `workflow_dispatch` \| `agent/go-live-ops-gate` |
| `predeploy-visual.yml` | `workflow_dispatch` \| `agent/go-live-ops-gate` |
| `predeploy-zap.yml` | `workflow_dispatch` \| `agent/predeploy-go-readiness` |

Les deux branches citées existent encore sur le distant (`git branch -a`) mais leur travail est déjà fusionné dans `main`. **Aucune pull request future n'aura ces `head_ref`** : ces cinq workflows — dont le **scan de sécurité dynamique ZAP** et le gate d'accessibilité à 0,95 — ne s'exécuteront plus qu'à la main, si quelqu'un y pense.

*Impact.* Toute la couche de contrôle « navigateur et live » est dormante : accessibilité, performance, régression visuelle, interactions, sécurité dynamique. C'est précisément par ce trou qu'est passé R5 : `/bibliotheque/` n'est pas dans les quatre pages auditées par Lighthouse, et Lighthouse ne tourne de toute façon plus.

*Contre-poids, qui interdit de monter en 🔴.* Le workflow `ci.yml`, lui, s'exécute sans condition sur toute PR vers `main`, et il est sérieux : `ruff check` et `ruff format --check`, `pytest --cov-fail-under=90`, `makemigrations --check`, `manage.py check --deploy --fail-level WARNING`, `manage.py verifier_production`, `docker compose config`, construction de l'image de production et de l'image de sauvegarde. Le filet fonctionnel et le contrat de configuration restent gardés. Ce qui est tombé, c'est la couche live.

*Correctif.* Remplacer les conditions `head_ref` par un déclencheur durable : exécution sur les PR vers `main` (au moins pour ZAP et Lighthouse), ou planification hebdomadaire, ou étiquette de PR. Et étendre la liste de pages de Lighthouse au-delà des quatre actuelles.

*Tentative de réfutation.* J'ai vérifié que `ci.yml` ne reprenait pas ces contrôles à son compte — il ne les reprend pas — et que les branches nommées n'étaient pas des branches de travail permanentes — elles ne le sont pas. Constat maintenu.

**⚪ O1 — Une phrase de `coolify.md` est démentie par le dépôt.**
`docs/exploitation/coolify.md` affirme : « Le dépôt ne contient donc ni configuration Nginx, ni service `certbot` ». Or `src/nginx/nginx.conf` et `src/nginx/conf.d/iteag.conf` sont versionnés et contiennent un vhost TLS complet pour `iteag.org` avec challenge ACME et `upstream django { server web:8000; }`.

Ce point avait d'abord été classé 🟡 au motif du risque de double terminaison TLS que la doc elle-même signale. La passe de contradiction l'a fait tomber : le message du commit qui les a introduits est explicite — `a76b966 ops: config nginx de reference (non deployee, Coolify/Traefik gere le TLS)` — et aucun fichier Compose ni Dockerfile ne les monte (`grep -rn nginx src/docker-compose*.yml src/Dockerfile*` : aucun résultat). Le risque n'est pas atteignable ; il reste une phrase de documentation à corriger. **Classer 🟡 un risque dont la preuve établit elle-même l'inaccessibilité aurait été de la sévérité gratuite.**

---

## 4. Tests — ce qui a réellement été exécuté

| Objectif | Commande | Résultat | Conclusion autorisée |
|---|---|---|---|
| Éprouver la suite complète | `python -m pytest -p no:cacheprovider -q` (dans `src/`) | **Code de sortie 0**, ~2 994 résultats, 3 ignorés, **0 échec**, ~8 min | La suite passe intégralement sur ce commit, sous Python 3.14 / SQLite |
| Compter les tests | `pytest --collect-only -q` | 128 fichiers de test, 1 464 fonctions `test_` déclarées | Le volume est cohérent avec le nombre de résultats (paramétrage) |
| Vulnérabilités Python | `pip-audit -r <versions de prod.lock>` | `No known vulnerabilities found` (82 paquets) | Aucun problème correspondant aux contrôles de cet outil, lors de cette exécution |
| Vulnérabilités Node | `npm audit --audit-level=high --json` | 0 vulnérabilité, 77 dépendances | Idem |
| Exposition des routes | Inspection du résolveur Django (script ad hoc, lecture seule) | 809 routes ; 15 sous préfixe protégé sans mixin d'auth | Piste ouverte puis **écartée** : les 15 revérifient le droit dans la vue |
| Noms accessibles | Balayage des 19 gabarits + vérification dans le navigateur | 18 champs sans nom accessible, dont 2 confirmés en live | Constat R5 |
| Comportement live | ~40 requêtes `curl` + inspection DOM et arbre d'accessibilité | Voir §3 | Constats R3, R5, R6, O3 |

**Réserve sur l'exécution locale.** La suite a tourné sous Python 3.14 avec le moteur SQLite de repli, alors que la CI l'exécute sous Python 3.12 contre PostgreSQL 16. Un défaut spécifique à PostgreSQL ne serait pas visible ici. La CI, elle, couvre ce cas, et le fichier `pyproject.toml` transforme en erreur l'avertissement de pagination non triée — précisément le piège qui ne se voit qu'en PostgreSQL.

`pip-audit -r requirements/prod.lock` n'a pas pu être exécuté tel quel : le verrou est compilé pour Linux/Python 3.12 et `colorama`, dépendance Windows de `click`, n'y figure pas, ce qui fait échouer le mode `--require-hashes` sur ce poste. Le contrôle a donc porté sur les 82 versions extraites du verrou, sans les empreintes. C'est une limite de l'environnement d'audit, pas un défaut du projet — la CI exécute la commande complète sous Linux.

---

## 5. Écarts entre le code et le live

| Écart | Nature |
|---|---|
| `SITE_URL` de la préproduction pointe sur un hôte Coolify qui répond 503, alors que `.env.prod.example` prescrit `SITE_URL=https://iteag.org` | Visible en usage, invisible en code — la préproduction ne rejoue pas la configuration de production sur ce point. Fonde R3 |
| Le `sitemap.xml` mêle deux hôtes selon que la section vient de Wagtail (base de données) ou des sitemaps applicatifs (hôte de la requête) | Visible en usage seulement. Fonde R3 |
| `meta robots` = « index, follow » alors que l'en-tête HTTP dit `noindex` | Visible en usage ; sans conséquence, la directive la plus restrictive s'appliquant. O3 |
| La CSP servie ne contient pas de `nonce` alors que `base.py:567` place la sentinelle `NONCE` en tête de `script-src` | Écart **apparent**, vérifié et écarté : django-csp 4 ne matérialise le nonce que si un gabarit consomme `request.csp_nonce`, et aucun script inline exécutable n'est servi sur ces pages |
| 15 routes sous préfixe protégé sans mixin d'authentification | Écart **apparent** en lecture de code, écarté après lecture des vues : le droit est revérifié à chaque appel |
| `src/nginx/` versionné vs. documentation affirmant l'inverse | Visible en code, sans effet en usage. O1 |

---

## 6. Objections retenues et écartées (passe de contradiction)

Une passe de contradiction indépendante a été menée sur les sept constats provisoires, avec pour seule consigne de les réfuter. **Toutes ses objections ont été revérifiées par mes soins avant intégration** ; aucune n'a été reprise sur parole.

**Objections retenues**

| Objection | Vérification menée | Effet |
|---|---|---|
| La preuve de R1 devrait être `commerce/forms.py:33`, plus décisive que des 404 | Lu : `accepte_conditions = forms.BooleanField(label="J'accepte les conditions de vente…")`, obligatoire, sans lien | Preuve remplacée. Sévérité inchangée |
| R2 affirmait « aucun contrôle en aval » — faux pour les documents rédigés | Relu `services_generation.py:111-116` : le repli existe bien | Énoncé corrigé. Sévérité inchangée |
| R2 sous-estimait le risque : le PDF rend date, nom et qualité même sans image | Vérifié `templates/documents/pdf/document.html:232-240` | Ajouté au constat, qui s'en trouve renforcé |
| R3 mélangeait un symptôme d'environnement et un défaut de contrat | Vérifié que `SITE_URL` est une variable, mais que le `Site` Wagtail n'en est pas une | Constat scindé : symptôme préprod en ⚪, absence de gate en 🟠 |
| R3 : l'hôte canonique répond 503 | `curl` : confirmé | Ajouté |
| R5 : le vrai lien est que `/bibliotheque/` est hors périmètre du gate Lighthouse | Vérifié dans le workflow | Ajouté ; renforce R4 et R5 |
| R4 devait être élargi : les cinq workflows `predeploy-*` sont dormants, pas seulement Lighthouse | `grep head_ref` sur les neuf workflows : confirmé | **Sévérité relevée de 🟡 à 🟠** |
| R6 (identifiant de compte R2 dans la CSP) manquait à l'audit initial | Observé dans l'en-tête live | Ajouté en 🟡 |
| R7 (verrouillage axes par identifiant) : Turnstile est validé avant `authenticate()`, donc avant tout comptage | Lu `apps/accounts/forms.py:24-28` : confirmé | **Rétrogradé de 🟡 à ⚪** (O2) |
| R6 initial (nginx versionné) : le message de commit déclare la config non déployée et rien ne la monte | `git log -- src/nginx/` et `grep nginx` sur les Compose : confirmé | **Rétrogradé de 🟡 à ⚪** (O1) |

**Objections écartées ou nuancées**

- Le contradicteur proposait de considérer R4 comme éventuellement 🔴. Écarté : `ci.yml` s'exécute inconditionnellement et couvre le fonctionnel, les migrations, `check --deploy` et `verifier_production`. Ce qui est tombé est réel mais n'est pas le dernier rempart.
- Son propre balayage des noms accessibles trouvait 32 champs contre 18. Vérification faite, l'écart tient à des faux positifs qu'il a lui-même identifiés (pot-de-miel, étiquetage implicite). Le chiffre de 18 est conservé.
- Il relevait l'absence totale d'`assertNumQueries`. Vérifié (zéro occurrence) et retenu, mais en ⚪ : aucun impact constaté aujourd'hui, les temps mesurés sont sains et le code utilise systématiquement `select_related`/`prefetch_related`.

**Deux constats provisoires étaient des préférences habillées en verdict** : O1 et O2. Dans les deux cas, la preuve établissait un écart réel mais aucun impact atteignable, et un élément non cherché initialement — le message de commit, l'ordre d'exécution du `clean()` — neutralisait le risque. Les rétrograder rend les 🔴 et 🟠 restants plus crédibles.

---

## 7. Surfaces contrôlées sans défaut trouvé

Mentionnées pour que ce rapport ne surestime pas sa propre couverture ni ne laisse croire que ces sujets n'ont pas été regardés.

| Surface | Preuve du garde-fou |
|---|---|
| Pagination des grandes listes | `apps/core/test_pagination.py` — méta-test recensant les vues à `paginate_by` et exigeant les commandes de navigation dans chaque gabarit, avec garde anti-liste-vide |
| Contrôle d'accès objet (documents) | `apps/documents/views.py:110, 116, 130` — `get_object_or_404(..., etudiant=request.user)` sur consultation, téléchargement et suppression. Pas d'IDOR sur ce périmètre |
| Contrôle d'accès e-learning | `verifier_acces` rappelé dans chaque vue, y compris pour les ressources PDF et l'URL de lecture, avec revérification explicite après révocation |
| Rôles | `apps/core/mixins.py:25-61`, 7 mixins, 255 usages ; doctrine de partage documentée en tête de fichier |
| Validation des téléversements | `apps/admissions/formulaires.py:56-122` — taille, taille nulle, MIME normalisé, signature d'en-tête ; tests du faux PDF, du MIME menteur et du `.exe` |
| Intégrité du stock | `apps/commerce/models.py:68` — `CheckConstraint(stock_reserve <= stock_physique)` au niveau base |
| Isolation des réglages de production | `config/settings/prod.py:15-18` — copies explicites des structures mutables héritées de `base`, avec test dédié |
| Restauration de sauvegarde | `scripts/verifier_go_live.sh` — restauration non destructive du dernier dump R2, refus explicite de cibler la base `iteag`, contrôle d'âge |
| Referrer-Policy et Bunny | `apps/elearning/csp.py:69` — surcharge en `strict-origin-when-cross-origin` sur les pages de lecture, la politique globale restant `same-origin` |
| Cache des réponses authentifiées | `apps/core/middleware.py:66-74` — `private, no-cache, no-store, must-revalidate` dès que l'utilisateur est authentifié, avec test |
| Mots de passe | 12 caractères minimum, scrypt, formats historiques acceptés puis migrés |

---

## 8. Limites de cet audit

Ce qui n'a pas pu être vérifié, et pourquoi.

1. **Parcours authentifiés.** Aucun compte n'était disponible sur la préproduction. Candidature complète, scolarité, lecture d'un module vidéo, commande, tunnel Stripe : jugés sur le code, jamais exercés. C'est la limite la plus lourde de cet audit — la moitié de la valeur métier de la plateforme.
2. **Aucune soumission de formulaire.** Volontaire : les formulaires publics envoient de vrais courriels au secrétariat et créent des enregistrements. La validation côté serveur, les messages d'erreur et le retour utilisateur n'ont donc pas été observés en conditions réelles.
3. **Aucun test de connexion répété.** Volontaire : django-axes verrouille par identifiant. Le comportement réel du verrouillage et de Turnstile à l'échec n'a pas été observé en live.
4. **Jeu de données de préproduction non représentatif** — 16 notices, 11 livres, 4 parcours, 1 module. Aucune conclusion de performance à charge, ni sur la pagination réelle, ni sur d'éventuelles requêtes N+1 en volume.
5. **Contraste des couleurs, navigation clavier complète et restitution par lecteur d'écran** non mesurés. Aucun outil instrumenté (axe-core, Lighthouse) n'a été exécuté depuis ce poste.
6. **Configuration réelle du serveur de production inaccessible.** `verifier_production` et `verifier_go_live.sh` n'ont pas pu être exécutés contre l'instance déployée : ils demandent un accès au conteneur. Ce qui est jugé ici, c'est le contrat qu'ils encodent, pas l'état de la machine.
7. **Disponibilité et configuration des services tiers** (Stripe en mode live, R2, Bunny, Turnstile, Sentry, SMTP) non vérifiées. En particulier, la liste des domaines autorisés côté Bunny devra inclure le domaine de production : ce point n'est pas vérifiable depuis le dépôt.
8. **Suite de tests exécutée sous Python 3.14 / SQLite**, alors que la production tourne en 3.12 / PostgreSQL 16. Un défaut spécifique à PostgreSQL ne serait pas visible dans mon exécution.
9. **`pip-audit` exécuté sur les versions extraites du verrou, sans les empreintes** — le verrou est compilé pour Linux et le mode `--require-hashes` échoue sur un poste Windows. Le résultat couvre les versions, pas l'intégrité des archives.
10. **Diff avec la version précédemment en production non établissable** : aucun tag, aucune branche de release, et le code du site antérieur n'est pas dans ce dépôt.
11. **Le statut juridique de l'ITEAG n'est pas établi par le dépôt.** L'applicabilité du RGAA reste donc ouverte, et l'analyse de conformité de R1 s'appuie sur le droit commun applicable à un site professionnel marchand — elle ne remplace pas un avis juridique.

---

## 9. Ce qu'il reste à faire, par ordre

**Avant la bascule**

1. Publier les mentions légales et les CGV, les lier depuis le pied de page et depuis la case `accepte_conditions` du tunnel de commande *(R1 — bloquant)*.

**Dans la foulée de la bascule**

2. Journaliser l'échec de lecture de signature et distinguer « non configurée » de « illisible » *(R2)*.
3. Ajouter au contrat de production et au script de go-live le contrôle d'alignement hôte servi / `SITE_URL` / `Site` Wagtail, et vérifier l'enregistrement `Site` de Wagtail avant la bascule *(R3)*.
4. Rendre les workflows `predeploy-*` à nouveau déclenchables — en priorité `predeploy-zap.yml` et `predeploy-lighthouse.yml` *(R4)*.

**Quand le calendrier le permet**

5. Étiqueter les 18 champs de formulaire, en commençant par `/bibliotheque/`, et étendre la liste de pages Lighthouse *(R5)*.
6. Renseigner `AWS_S3_CUSTOM_DOMAIN` pour retirer l'identifiant de compte R2 de la CSP publique *(R6)*.
7. Corriger la phrase de `coolify.md` sur l'absence de configuration Nginx *(O1)* ; documenter le choix `AXES_LOCKOUT_PARAMETERS` *(O2)*.

---

*Aucun autre problème n'a été identifié dans les contrôles effectivement réalisés et décrits dans ce rapport. L'absence de preuve n'y vaut pas preuve d'absence : les limites du §8 délimitent ce que ce verdict peut et ne peut pas couvrir.*
