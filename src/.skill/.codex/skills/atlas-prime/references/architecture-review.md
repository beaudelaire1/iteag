# Architecture Review

Utiliser cette référence quand la mission implique :
- architecture,
- refactor,
- dette technique,
- lecture d’un repo inconnu,
- changements multi-fichiers,
- conception de nouvelle fonctionnalité.

## Lecture du dépôt
Identifier en priorité :
- structure générale,
- points d’entrée,
- couches ou modules,
- conventions réelles,
- frontières métier,
- dépendances critiques,
- dette visible,
- tests existants.

## Questions à se poser
### Responsabilités
- Chaque module a-t-il une responsabilité claire ?
- Observe-t-on du couplage excessif ?
- La logique métier est-elle au bon endroit ?
- Y a-t-il de la duplication évitable ?

### Flux
- Quels sont les flux d’entrée et de sortie ?
- Où se font validations, permissions, transformations, persistance ?
- Le parcours métier est-il lisible ?

### Données
- Les structures de données sont-elles cohérentes ?
- Les dépendances implicites sont-elles dangereuses ?
- Y a-t-il des champs, états ou transitions ambigus ?

### Frontières
- Les interfaces entre modules sont-elles claires ?
- Les effets de bord sont-ils localisables ?
- Les changements peuvent-ils être limités à un petit périmètre ?

## Signaux de fragilité
- fonctions trop longues,
- classes fourre-tout,
- mélange UI / métier / accès données,
- logique dupliquée,
- conventions incohérentes,
- dépendances superflues,
- absence de garde-fous.

## Sortie attendue
Produire :
- cartographie minimale,
- points forts réels,
- faiblesses majeures,
- ordre de correction rationnel,
- arbitrage recommandé.