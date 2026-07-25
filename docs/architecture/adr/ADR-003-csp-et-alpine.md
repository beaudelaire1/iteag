# ADR-003 — Politique CSP et build Alpine.js

- **Statut** : Accepté
- **Contexte** : `config/settings/base.py` déclare une CSP stricte ; `static/js/alpine.min.js`
  est le build standard d'Alpine.

## Problème constaté

La politique de sécurité de contenu déclare `script-src 'self'`. Le build standard
d'Alpine.js évalue ses expressions (`x-show="open"`, `x-text="…"`) au moyen d'un
constructeur de fonction, ce qui requiert `'unsafe-eval'`. En production, avec la CSP
active, **toute l'interactivité Alpine échouerait silencieusement** : menu mobile,
accordéons FAQ, onglets des portails. Le défaut ne se voit pas en développement, où la
CSP est désactivée — c'est le pire profil de bug : invisible jusqu'à la mise en ligne.

Le futur lecteur vidéo aggrave l'enjeu : il manipulera des URL signées et des appels
authentifiés, exactement le type de code qu'on ne veut pas exécuter sous une CSP relâchée.

## Options

| Option | Sécurité | Effort | Verdict |
|--------|---------|--------|---------|
| A — Ajouter `'unsafe-eval'` à `script-src` | Dégradée sur tout le site | Nul | ❌ |
| B — **Utiliser le build CSP d'Alpine** (`@alpinejs/csp`) | Conservée | Réécriture des expressions inline | ✅ **Retenue** |
| C — Supprimer Alpine, tout en HTMX + JS natif | Conservée | Élevé | ⏭ Non justifié |

## Décision

Adopter le **build CSP d'Alpine.js**. Ce build n'évalue pas de chaînes : les
comportements sont déclarés dans des objets JavaScript enregistrés via `Alpine.data()`,
et le template ne référence que des noms de propriétés et de méthodes.

Conséquence concrète sur les templates :

```html
<!-- Avant — nécessite 'unsafe-eval' -->
<div x-data="{ open: false }">
  <button @click="open = !open">Menu</button>
  <nav x-show="open">…</nav>
</div>

<!-- Après — compatible CSP stricte -->
<div x-data="menuMobile">
  <button x-on:click="basculer">Menu</button>
  <nav x-show="ouvert">…</nav>
</div>
```

```js
// static/js/iteag.js
Alpine.data('menuMobile', () => ({
  ouvert: false,
  basculer() { this.ouvert = !this.ouvert; },
}));
```

En complément :

- `script-src` reste `'self'` ; aucune balise `<script>` inline sans nonce.
- Les gabarits qui ont besoin d'un script inline utilisent un **nonce par requête**
  fourni par `django-csp`.
- `media-src` est ajouté à la politique pour autoriser le domaine du bucket S3
  (nécessaire au lecteur vidéo), et lui seul.
- La CSP est d'abord déployée en **mode report-only** sur l'environnement de recette,
  le temps de collecter les violations réelles, puis passée en mode bloquant.

## Conséquences

- Un test d'intégration vérifie qu'aucun template ne contient d'expression Alpine
  inline complexe (heuristique sur `x-data="{`), pour éviter la régression.
- Le fichier `static/js/iteag.js` devient le registre unique des composants Alpine :
  il est versionné, lisible et testable, ce qui vaut mieux que de la logique éparpillée
  dans les attributs HTML.
