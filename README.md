# ITEAG — Plateforme académique et institutionnelle

Refonte du site de l'Institut de Théologie Évangélique des Antilles et de la Guyane :
migration WordPress → Django 5 / Wagtail 7, avec quatre portails (public, étudiant,
enseignant, administratif), un espace E-Learning à accès contrôlé et une
boutique de livres avec commandes, suivi et gestion de stock.

**Maître d'ouvrage** : ITEAG · **Maître d'œuvre** : Trait d'Union Studio

---

## Documentation

| Document | Objet |
|----------|-------|
| [`src/cahier_de_charge_v2.md`](src/cahier_de_charge_v2.md) | Cahier des charges contractuel |
| [`docs/architecture/uml.md`](docs/architecture/uml.md) | Dossier de conception UML |
| [`docs/architecture/adr/`](docs/architecture/adr/) | Décisions d'architecture |
| [`docs/plan/plan-finalisation.md`](docs/plan/plan-finalisation.md) | Plan de finalisation par lots |
| [`docs/plan/plan-correction-audit.md`](docs/plan/plan-correction-audit.md) | Correction des constats de l'audit du 3 août 2026 |
| [`docs/architecture/adr/ADR-005-fournisseurs-video-externes.md`](docs/architecture/adr/ADR-005-fournisseurs-video-externes.md) | Choix du fournisseur de diffusion vidéo |
| [`docs/architecture/adr/ADR-006-paiement-en-ligne-stripe.md`](docs/architecture/adr/ADR-006-paiement-en-ligne-stripe.md) | Paiement en ligne : Stripe, webhook, TVA |
| [`docs/exploitation/runbook.md`](docs/exploitation/runbook.md) | Manuel d'exploitation — sauvegardes, supervision, incidents |
| [`docs/exploitation/cloudflare.md`](docs/exploitation/cloudflare.md) | Activation Turnstile, proxy DNS, TLS et WAF Cloudflare |
| [`docs/exploitation/coolify.md`](docs/exploitation/coolify.md) | Déploiement OVH Cloud via Coolify, variables secrètes, R2 et Stripe live |
| [`docs/exploitation/notifications.md`](docs/exploitation/notifications.md) | Événements notifiés, destinataires et contrôle SMTP |

---

## Démarrage rapide

### Avec Docker (recommandé)

```bash
cd src
cp .env.example .env          # ajuster DJANGO_SECRET_KEY
docker compose up --build
```

Le service `node` compile les feuilles de style en continu. L'application écoute sur
<http://localhost:8000>.

### En local

Prérequis : Python 3.12, Node 22, PostgreSQL 16 (ou SQLite pour aller vite), Redis.

```bash
cd src
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
npm install

npm run build                                        # styles + bibliothèques tierces
export DJANGO_SETTINGS_MODULE=config.settings.dev
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver --noreload
```

Pendant le développement, laisser `npm run css:watch` tourner dans un second terminal.

Pour tester les notifications réelles, renseigner `EMAIL_HOST`,
`EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` et `EMAIL_TEST_RECIPIENT` dans
`src/.env`, puis lancer :

```bash
python manage.py tester_notifications_email
```

La commande envoie sept messages de contrôle sans créer de candidature, de
commande ou de compte. En développement, les notifications déclenchées depuis
le site sont envoyées immédiatement ; en production, le worker Celery s'en
charge.

> **`npm run build` est obligatoire après chaque `git pull`.**
> `static/css/main.css` est un artefact de compilation, ignoré par git :
> récupérer une branche apporte les gabarits mais **pas** les styles. Le site
> s'ouvre alors avec un HTML neuf sur des règles anciennes, et la mise en page
> paraît cassée sans qu'aucune erreur ne soit levée.
>
> `manage.py check` — donc `runserver` — le signale désormais en nommant les
> composants manquants, et la suite de tests échoue dans le même cas.

### Jeux de données

```bash
python manage.py setup_initial_pages   # arborescence Wagtail
python manage.py seed_formations       # parcours, disciplines, cours, tarifs
python manage.py seed_profs_detail     # fiches professeurs détaillées
```

### Jeu de démonstration complet

Une seule commande peuple toute la plateforme — comptes, candidatures,
étudiants, sessions, classes, copies à corriger, bibliothèque, boutique,
accès e-learning :

```bash
python manage.py seed_demo                      # tout, référentiel compris
python manage.py seed_demo --sans-referentiel   # si seed_formations est déjà passé
```

Elle est **idempotente** : la relancer complète le jeu sans le dupliquer.
Chaque sous-commande reste utilisable seule (`seed_boutique`,
`seed_vie_academique`, `seed_lms`, `seed_candidatures`, `seed_bibliotheque`,
`seed_comptes`, `seed_elearning_demo`).

Le jeu est composé pour que **chaque écran montre au moins un cas de chaque
état qu'il sait afficher** : des candidatures dans les cinq statuts du
workflow d'admission, des copies dans les cinq états du cycle de correction,
des stocks au-dessus et au-dessous du seuil d'alerte. Une liste dont toutes
les lignes se ressemblent ne démontre ni ses filtres ni ses actions.

> Les comptes créés partagent un mot de passe de démonstration
> (`DemoIteag!2026`), acceptable sur un poste de travail et **nulle part
> ailleurs**. Sur un environnement accessible depuis l'extérieur, passer
> `python manage.py seed_comptes --mot-de-passe "…"`.

---

## Organisation du dépôt

```
docs/                        Conception, décisions, plan
src/
├── apps/
│   ├── core/                Socle transverse — modèles abstraits, mixins, balises
│   ├── accounts/            Utilisateurs, rôles, authentification
│   ├── formations/          Référentiel : disciplines, parcours, cours, professeurs
│   ├── admissions/          Candidatures et workflow d'admission
│   ├── academics/           Sessions, promotions, ECTS, stages, VAE, paiements
│   ├── lms/                 Ressources, évaluations, annonces (présentiel)
│   ├── library/             Catalogue de la bibliothèque
│   ├── commerce/            Boutique, commandes, stocks et alertes
│   ├── paiements/           Encaissement Stripe — modules, frais, commandes
│   ├── documents/           Documents administratifs PDF
│   ├── website/             Pages éditoriales Wagtail — et plan du site
│   ├── elearning/           E-Learning — modules, accès, progression
│   ├── portail_etudiant/    Espace étudiant
│   ├── portail_enseignant/  Espace enseignant
│   └── administration/      Portail administratif et secrétariat
├── assets/css/input.css     Source Tailwind (jamais servie telle quelle)
├── static/                  Fichiers servis — main.css y est généré
├── templates/               Gabarits Django
└── config/settings/         base · dev · test · prod
```

`assets/` contient les **sources** ; `static/` ce qui est **servi**. Ne pas replacer de
source dans `static/` : elle serait collectée et traitée comme un fichier livrable.

---

## Conventions

### Qualité

```bash
ruff check .                 # doit sortir sans erreur
ruff format --check .        # idem
pytest -q                    # suite complète
pytest --cov=apps            # avec couverture
```

Ces trois commandes sont celles de l'intégration continue. Un commit qui les casse
casse la CI.

### Tester comme la CI, sur PostgreSQL

Par défaut la suite tourne sur SQLite, pour la vélocité (décision D7). L'intégration
continue, elle, tourne sur **PostgreSQL 16** — et les deux moteurs ne se comportent pas
pareil. Une suite verte en local ne prouve donc rien sur ce qui dépend du moteur.

```bash
DATABASE_URL="postgres://user@localhost/postgres" pytest -q
```

À faire systématiquement avant de pousser dès qu'on touche à un verrou, une contrainte,
une transaction ou une requête complexe. Le piège déjà rencontré : `select_for_update()`
combiné à un `select_related()` sur une relation **facultative** produit une jointure
externe, que PostgreSQL refuse de verrouiller et que SQLite accepte en silence. Se
limiter à `select_for_update(of=("self",))` quand seule la ligne principale doit être
protégée.

### Architecture

Les dépendances entre applications sont **déclarées** dans
`apps/core/test_architecture.py` et vérifiées à chaque exécution de la suite :

- le graphe de dépendances reste acyclique ;
- `core` ne dépend d'aucune autre application ;
- toute nouvelle application doit être déclarée explicitement.

Les entorses connues sont listées dans `DETTE_ARCHITECTURE` et protégées par un
cliquet : elles ne peuvent que diminuer. Ajouter une dépendance non déclarée fait
échouer la suite — c'est voulu, cela force la discussion.

### Interface

Pas de framework JavaScript côté client : HTMX pour les échanges serveur, composants
natifs pour le reste (voir [ADR-003](docs/architecture/adr/ADR-003-csp-et-alpine.md)).
La politique de sécurité de contenu est stricte — `script-src 'self'`, sans
`unsafe-eval` ni `unsafe-inline`. Toute bibliothèque qui évalue des chaînes est
incompatible avec le projet.

Le système de design vit dans `assets/css/input.css` : utiliser ses composants
(`.btn-primary`, `.form-input`, `.card`, `.accordeon`…) plutôt que des classes
Tailwind ad hoc, afin que l'interface reste conforme à la charte ITEAG.

### Navigation publique

Les rubriques de la barre du site sont **déclarées** dans
`apps/core/navigation.py`, pas écrites dans le gabarit. La barre de bureau et
le menu mobile parcourent la même déclaration : ajouter une entrée à un seul
des deux rendus n'est plus possible. C'est aussi cette déclaration qui indique
la rubrique courante — chacune connaît les chemins qu'elle revendique.

Les panneaux s'ouvrent en CSS, au survol et à la prise de focus, et chaque
intitulé de rubrique reste un lien vers sa page principale : sans JavaScript,
aucune destination n'est hors d'atteinte. Le script n'ajoute qu'un cas,
l'ouverture au doigt là où `:hover` ne se déclenche pas.

> **Une page dont le gabarit rend la barre ne peut pas passer par `cache_page`.**
> La barre porte le prénom, les initiales, le rôle et les liens d'espace de qui
> est connecté ; le cache de page mémorise le HTML complet sous une clé qui
> ignore la session. `apps/formations/test_cache_pages.py` verrouille le cas.

---

## Déploiement

L'image de production se construit avec `src/Dockerfile.prod` : une étape Node compile
les feuilles de style, une étape Python installe les dépendances, et la collecte des
statiques échoue bruyamment en cas de rupture — voir
[ADR-004](docs/architecture/adr/ADR-004-pipeline-assets-production.md).

Variables d'environnement attendues : `src/.env.example` en développement,
`src/.env.prod.example` en production.

La production tourne sur **OVH Cloud, administrée par Coolify**. Le déploiement
est décrit par `src/docker-compose.prod.yml` — PostgreSQL, Redis, une tâche de
migration, l'application, le worker Celery et le planificateur. Coolify y ajoute
ce que le dépôt ne contient volontairement pas : le proxy, le certificat TLS et
les variables secrètes (Stripe, Cloudflare R2, Turnstile, Sentry, Bunny, SMTP).

> Le fichier Compose doit rester lisible par Docker Compose seul :
> ```bash
> docker compose -f src/docker-compose.prod.yml config
> ```
> Une clé propre à l'interface Coolify passe sa lecture mais fait échouer
> Compose — donc le déploiement — avant le premier téléchargement d'image.

Voir [`docs/exploitation/coolify.md`](docs/exploitation/coolify.md) pour le
premier déploiement et la bascule du domaine. Ces opérations nécessitent
l'accord explicite du client.

---

*Code propriétaire — Trait d'Union Studio.*
