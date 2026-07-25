# ITEAG — Plateforme académique et institutionnelle

Refonte du site de l'Institut de Théologie Évangélique des Antilles et de la Guyane :
migration WordPress → Django 5 / Wagtail 6, avec quatre portails (public, étudiant,
enseignant, administratif) et un module de formation vidéo à accès contrôlé.

**Maître d'ouvrage** : ITEAG · **Maître d'œuvre** : Trait d'Union Studio

---

## Documentation

| Document | Objet |
|----------|-------|
| [`src/cahier_de_charge_v2.md`](src/cahier_de_charge_v2.md) | Cahier des charges contractuel |
| [`docs/architecture/uml.md`](docs/architecture/uml.md) | Dossier de conception UML |
| [`docs/architecture/adr/`](docs/architecture/adr/) | Décisions d'architecture |
| [`docs/plan/plan-finalisation.md`](docs/plan/plan-finalisation.md) | Plan de finalisation par lots |

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

npm run css:build                                    # feuilles de style
export DJANGO_SETTINGS_MODULE=config.settings.dev
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Pendant le développement, laisser `npm run css:watch` tourner dans un second terminal.

### Jeux de données

```bash
python manage.py setup_initial_pages   # arborescence Wagtail
python manage.py seed_formations       # parcours, disciplines, cours, tarifs
python manage.py seed_profs_detail     # fiches professeurs détaillées
```

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
│   ├── documents/           Documents administratifs PDF
│   ├── website/             Pages éditoriales Wagtail
│   └── administration/      Portail administratif
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

---

## Déploiement

L'image de production se construit avec `src/Dockerfile.prod` : une étape Node compile
les feuilles de style, une étape Python installe les dépendances, et la collecte des
statiques échoue bruyamment en cas de rupture — voir
[ADR-004](docs/architecture/adr/ADR-004-pipeline-assets-production.md).

Variables d'environnement attendues : voir `src/.env.example`.

---

*Code propriétaire — Trait d'Union Studio.*
