# PLAN OPÉRATIONNEL — Projet ITEAG-2026-REFONTE

## Projet
- **Nom** : Refonte ITEAG — Migration WordPress → Django/Wagtail
- **Maître d'ouvrage** : ITEAG (Institut de Théologie Évangélique des Antilles et de la Guyane)
- **Maître d'œuvre** : Trait d'Union Studio (TUS)
- **Référence CDC** : `src/cahier_de_charge_v2.md`
- **Conception** : `docs/architecture/uml.md`
- **Plan détaillé** : `docs/plan/plan-finalisation.md`
- **Dépôt** : `github.com/beaudelaire1/iteag`

## Phase active
**Finalisation achevée — lots 0 à 8 livrés**

Les phases 1 à 3 du CDC étaient implémentées à la reprise. Les neuf lots du plan
de finalisation ont été menés à terme : remise à niveau du socle, socle
transverse, domaine e-learning vidéo, portails étudiant, enseignant et
administratif, conversion publique, qualité et exploitation.

## Architecture retenue
- **Pattern** : Modular Monolith (Django)
- **Stack** : Python 3.12 / Django 5.x / Wagtail 7.x / PostgreSQL 16 / Redis / Celery / Tailwind CSS 4 / HTMX
- **Justification** : proportionnée au volume réel (~200 étudiants, ~10 enseignants, ~2 635 notices biblio). Pas de microservices, pas de SPA.

## Décisions structurantes

| # | Décision | Justification |
|---|---------|---------------|
| D1 | Modular Monolith | Proportionné, maintenable, déployable simplement |
| D2 | Wagtail = CMS éditorial, portail Django custom = métier | Séparation claire des responsabilités |
| D3 | PostgreSQL full-text (pas Elasticsearch) | Volume insuffisant pour justifier ES |
| D4 | S3 en prod, MinIO en dev local | Compatibilité API, simplicité |
| D5 | Tailwind CSS 4 + design system propriétaire | Standard TUS, léger, cohérent |
| D6 | HTMX seul, sans framework client | Voir ADR-003 — CSP stricte préservée |
| D7 | SQLite en dev rapide, PostgreSQL en staging/prod | Vélocité dev sans sacrifier la prod |
| D8 | GitHub Actions CI/CD | Intégrée au dépôt existant |
| D9 | Vidéo : S3 privé + URL présignée courte | Voir ADR-001 — protection sans DRM |
| D10 | Accès module = donnée, pas règle codée | Voir ADR-002 — autonomie du secrétariat |

## Applications

| App | Responsabilité | État |
|-----|---------------|------|
| `core` | Socle transverse : modèles abstraits, mixins, balises | Livré |
| `accounts` | Utilisateurs, profils, authentification, rôles | Livré |
| `website` | Pages Wagtail, actualités, événements, FAQ | Livré |
| `formations` | Parcours, disciplines, cours, professeurs, tarifs | Livré |
| `admissions` | Candidatures, workflow d'admission | Livré |
| `academics` | Sessions, promotions, ECTS, stages, VAE, paiements | Livré |
| `lms` | Ressources, évaluations, annonces (présentiel) | Livré |
| `library` | Catalogue bibliothèque, recherche full-text | Livré |
| `documents` | Génération PDF, documents administratifs | Livré |
| `administration` | Portail administratif | Livré — extrait de `core` |
| `elearning` | Modules vidéo, accès, progression, attestations | Livré — LOT 2 |

## Avancement des lots

| Lot | Objet | État |
|-----|-------|------|
| 0 | Remise à niveau du socle | Livré |
| 1 | Socle transverse — notifications, audit, 2FA, newsletter | Livré |
| 2 | Domaine e-learning vidéo et contrôle d'accès | Livré |
| 3 | Portail étudiant vidéo | Livré |
| 4 | Portail enseignant de production | Livré |
| 5 | Pilotage des accès côté administration | Livré |
| 6 | Catalogue public et conversion | Livré |
| 7 | Qualité, sécurité, couverture | Livré |
| 8 | Exploitation | Livré côté technique ; voir le manuel pour ce qui relève de l'infrastructure |

## Suite immédiate

| Point | Détenteur |
|-------|-----------|
| Export du catalogue bibliothèque | ITEAG |
| Contenus textuels validés | ITEAG |
| Table de redirections depuis l'ancien site | ITEAG |
| Exercice de restauration chronométré | Exploitant |
| Sauvegardes déportées et versionnage S3 | Exploitant |

## Risques actifs

| # | Risque | Impact | Atténuation |
|---|--------|--------|-------------|
| R1 | Contenus textuels ITEAG non fournis | Retard des lots 6 et 8 | Contenu de démonstration structuré |
| R2 | Export bibliothèque au format inconnu | Bloque l'import des 2 635 notices | Importeur tolérant, correspondance configurable |
| R3 | Volume vidéo supérieur aux prévisions | Coût de stockage et de trafic | Mesure dès la mise en service ; bascule HLS prévue |
| R4 | Débit insuffisant en Guyane et Martinique | Abandon des étudiants distants | Vidéos plafonnées en 720p, supports téléchargeables |
| R5 | Dette : portails encore dans les apps de domaine | Couplage `academics` ↔ `lms` | Cliquet en place ; extraction planifiée |

## Qualité mesurée

| Domaine | Mesure | Cible |
|---------|--------|-------|
| Tests | 529 verts | ≥ 200 |
| Couverture | 92 % | ≥ 90 % |
| Couverture du contrôle d'accès | 100 % | 100 % |
| Lint et format | 0 erreur | 0 |
| Vulnérabilités des dépendances | 1 résiduelle, sans correctif amont, non exploitable ici | 0 exploitable |
| Build de production | Vérifié à chaque commit | Vérifié |
