# AGENTS.md

## Mission
Travailler sur ce dépôt sans casser les flux existants.

## Stack
- Django
- HTMX
- Alpine.js
- PostgreSQL
- WeasyPrint

## Lire d'abord
- README.md
- pyproject.toml
- requirements.txt
- config/settings/
- apps/*/models.py
- apps/*/views.py
- templates/

## Commandes
- Tests : pytest
- Lint : ruff check .
- Format : ruff format .
- Run : python manage.py runserver

## Règles du repo
- Ne jamais introduire React.
- Préserver les conventions Django existantes.
- Toute modification métier doit vérifier permissions, validations et impacts admin.
- Toute vue modifiée doit être vérifiée côté sécurité et performance.
- Limiter le rayon d’impact des refactors.

## Livraison attendue
Toujours répondre avec :
1. compréhension du besoin
2. fichiers touchés
3. changements réalisés
4. validations faites
5. risques restants