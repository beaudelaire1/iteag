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
**Finalisation grade commercial — LOT 0 : remise à niveau du socle**

Les phases 1 à 3 du CDC (portail public, admissions et espace étudiant, portail
enseignant) sont implémentées. Le chantier en cours porte sur la livrabilité, puis sur
l'extension « formation vidéo à accès sécurisé ».

## Architecture retenue
- **Pattern** : Modular Monolith (Django)
- **Stack** : Python 3.12 / Django 5.x / Wagtail 6.x / PostgreSQL 16 / Redis / Celery / Tailwind CSS 4 / HTMX
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
| `elearning` | Modules vidéo, accès, progression, attestations | **À créer — LOT 2** |

## Avancement — LOT 0

| Tâche | Statut | Notes |
|-------|--------|-------|
| Lint et format à zéro erreur | FAIT | 232 → 0 ; exclusions documentées par fichier |
| Chaîne d'assets de production | FAIT | Étape Node ; source Tailwind sortie de `static/` |
| Suppression de la dépendance Alpine | FAIT | Composants natifs ; voir ADR-003 |
| Doublon `config/` racine | FAIT | Copie obsolète supprimée |
| Test d'architecture | FAIT | Cliquet sur la dette de dépendances |
| Séparation du portail administratif | FAIT | Cycle `core` ↔ `academics` résorbé |
| README | FAIT | Installation, conventions, architecture |
| Mise à jour de ce plan | FAIT | — |
| Tests de fumée sur les gabarits | FAIT | 14 tests ; pages sans directive interdite |
| Job CI de build des assets | FAIT | `collectstatic` vérifié au commit |

**Sortie de lot** : `ruff check` et `ruff format` sans erreur, 123 tests verts,
`collectstatic` vérifié en conditions de production.

## Suite immédiate

| Lot | Objet | Dépend de |
|-----|-------|-----------|
| LOT 1 | Socle transverse : notifications, audit, 2FA, newsletter | LOT 0 |
| LOT 2 | Domaine e-learning vidéo — **chemin critique** | LOT 0, LOT 1 |
| LOT 3 | Portail étudiant vidéo | LOT 2 |

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
| Tests | 123 verts | ≥ 200 |
| Couverture | 84 % | ≥ 90 % (100 % sur le contrôle d'accès) |
| Lint | 0 erreur | 0 |
| Build de production | Vérifié | Vérifié à chaque commit |
