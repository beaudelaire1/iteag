# PLAN OPÉRATIONNEL — Projet ITEAG-2026-REFONTE

## Projet
- **Nom** : Refonte ITEAG — Migration WordPress → Django/Wagtail
- **Maître d'ouvrage** : ITEAG (Institut de Théologie Évangélique des Antilles et de la Guyane)
- **Maître d'œuvre** : Trait d'Union Studio (TUS)
- **Référence CDC** : `src/cahier_de_charge_v2.md`
- **Dépôt** : `github.com/beaudelaire1/iteag`

## Phase active
**Phase 1 — Fondations et portail public**

## Architecture retenue
- **Pattern** : Modular Monolith (Django)
- **Stack** : Python 3.12 / Django 5.x / Wagtail 6.x / PostgreSQL 16 / Redis / Celery / Tailwind CSS 4 / HTMX / Alpine.js
- **Justification** : proportionnée au volume réel (~200 étudiants, ~7 enseignants, ~2635 notices biblio). Pas de microservices, pas de SPA.

## Décisions structurantes

| # | Décision | Justification |
|---|---------|---------------|
| D1 | Modular Monolith, 9 apps max V1 | Proportionné, maintenable, déployable simplement |
| D2 | Wagtail = CMS éditorial, Django Admin custom = métier | Séparation claire des responsabilités |
| D3 | PostgreSQL full-text (pas Elasticsearch) | Volume insuffisant pour justifier ES |
| D4 | S3 en prod, MinIO en dev local | Compatibilité API, simplicité |
| D5 | Tailwind CSS 4 + design system propriétaire | Standard TUS, léger, cohérent |
| D6 | HTMX + Alpine.js, zéro React | Standard TUS, interactivité ciblée |
| D7 | SQLite en dev rapide, PostgreSQL en staging/prod | Vélocité dev sans sacrifier la prod |
| D8 | GitHub Actions CI/CD | Intégrée au dépôt existant |

## Apps Django V1

| App | Responsabilité | Phase |
|-----|---------------|-------|
| `core` | Utils, mixins, base templates, email service | 1 |
| `accounts` | Utilisateurs, profils, auth, rôles | 2 |
| `website` | Pages Wagtail, actualités, événements, témoignages, FAQ, newsletter | 1 |
| `formations` | Parcours, disciplines, cours, catalogue | 1 |
| `admissions` | Candidatures, workflow admission | 2 |
| `academics` | Sessions, promotions, inscriptions, ECTS, stages, VAE | 2-3 |
| `lms` | Ressources, devoirs, évaluations, notes | 3 |
| `library` | Catalogue bibliothèque, notices, recherche | 3 |
| `documents` | Génération PDF, stockage docs admin | 2 |

## Avancement Phase 1

| Tâche | Statut | Notes |
|-------|--------|-------|
| Structure projet Django | EN COURS | |
| pyproject.toml + dépendances | À FAIRE | |
| Settings multi-env (base/dev/prod) | À FAIRE | |
| App core + base templates | À FAIRE | |
| App website (Wagtail pages) | À FAIRE | |
| App formations (catalogue) | À FAIRE | |
| Tailwind CSS + design system | À FAIRE | |
| Templates portail public | À FAIRE | |
| SEO (sitemap, robots, meta) | À FAIRE | |
| Docker Compose dev | À FAIRE | |
| CI/CD GitHub Actions | À FAIRE | |
| Tests fondations | À FAIRE | |

## Risques actifs

| # | Risque | Impact | Atténuation |
|---|--------|--------|-------------|
| R1 | Contenus textuels ITEAG non fournis | Retard Phase 1 | Contenu placeholder structuré |
| R2 | Export bibliothèque format inconnu | Bloque BIB-001 | Reporter à Phase 3 |

## Scores qualité (Phase 1)

| Domaine | Score | Cible |
|---------|-------|-------|
| Architecture | - | 95/100 |
| Sécurité | - | 95/100 |
| Performance | - | 95/100 |
| UX/UI | - | 95/100 |
| SEO | - | 95/100 |
| Tests | - | 95/100 |
| Documentation | - | 95/100 |
| DevOps | - | 95/100 |
