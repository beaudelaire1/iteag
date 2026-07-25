# ADR-004 — Chaîne de production des assets statiques

- **Statut** : Accepté
- **Contexte** : `Dockerfile.prod`, `.gitignore`, `config/settings/prod.py`

## Problème constaté

La chaîne actuelle est rompue, et le défaut ne se manifeste qu'au déploiement :

1. `static/css/main.css` — la sortie de Tailwind — est exclue par `.gitignore` ;
2. `Dockerfile.prod` ne comporte **aucune étape Node** pour la régénérer ;
3. l'étape `collectstatic` est masquée par `|| true`, donc l'échec est silencieux ;
4. la production utilise `CompressedManifestStaticFilesStorage`, qui lève une exception
   au premier `{% static 'css/main.css' %}` non résolu.

Comme `base.html` référence cette feuille de style, **toutes les pages** échoueraient.
Le `|| true` transforme une erreur de build franche en panne de production.

## Décision

Construire les assets **dans l'image**, au moyen d'une étape dédiée, et faire échouer
le build à la moindre erreur.

```dockerfile
# ── Étape assets ──
FROM node:22-alpine AS assets
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY static/ static/
COPY templates/ templates/
RUN npm run css:build

# ── Étape runtime ──
COPY --from=assets /app/static/css/main.css static/css/main.css
RUN python manage.py collectstatic --noinput   # sans « || true »
```

Principes retenus :

1. **La source de vérité reste `static/src/css/input.css`.** Le CSS compilé n'est jamais
   commité : il est reproductible.
2. **Le build échoue bruyamment.** Aucune commande de build n'est suffixée par `|| true`.
3. **Les templates sont copiés dans l'étape assets** : Tailwind 4 balaie le contenu pour
   déterminer les classes utilisées ; sans les templates, la feuille produite serait
   amputée. C'est l'erreur classique de ce montage.
4. **Le versionnage par manifeste est conservé** (`CompressedManifestStaticFilesStorage`) :
   il permet un cache navigateur d'un an sans risque de version périmée.
5. **Un test de fumée** exécute `collectstatic --noinput` en intégration continue, afin
   que la rupture soit détectée au commit et non au déploiement.

## Conséquences

- L'image de production grossit du temps de build Node (~30 s), sans impact sur sa taille
  finale : l'étape `assets` est écartée du runtime.
- Le développement local reste inchangé (`npm run css:watch` via Docker Compose).
- Un déploiement ne peut plus produire un site sans style : le cas est devenu impossible.
