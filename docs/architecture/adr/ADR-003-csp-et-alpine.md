# ADR-003 — Politique CSP et suppression d'Alpine.js

- **Statut** : Accepté — *révisé après mesure de l'usage réel*
- **Contexte** : `config/settings/base.py` déclarait une CSP stricte tandis que
  `static/js/alpine.min.js` était le build standard d'Alpine.

## Problème constaté

La politique de sécurité de contenu déclare `script-src 'self'`. Le build standard
d'Alpine.js évalue ses expressions (`x-show="open"`, `x-text="…"`) au moyen d'un
constructeur de fonction, ce qui requiert `'unsafe-eval'`. En production, avec la CSP
active, **toute l'interactivité Alpine aurait échoué silencieusement** : menu mobile,
accordéons, onglets des portails. Le défaut ne se voyait pas en développement, où la
CSP est désactivée — le pire profil de bug, invisible jusqu'à la mise en ligne.

Un second défaut est apparu au même endroit : les gabarits utilisaient `x-collapse`,
une directive fournie par le plugin `@alpinejs/collapse`, **qui n'était jamais chargé**.
Les panneaux d'accordéon s'ouvraient donc sans animation, et Alpine émettait un
avertissement en console à chaque rendu.

## Révision de la décision

La première rédaction de cet ADR retenait le build CSP d'Alpine et écartait la
suppression pure et simple comme « non justifiée ». **Cette conclusion reposait sur une
estimation, pas sur une mesure.** Le relevé effectif de l'usage l'a infirmée :

| Élément mesuré | Volume réel |
|---------------|------------|
| Gabarits contenant du Alpine | 8 |
| Directives `x-data` | 10 |
| Gestionnaires de clic | 12 |
| Liaisons `x-show` / `x-bind` / `x-text` | 25 |

Surtout, **la nature de ces usages** : sept des dix composants sont des accordéons et
des panneaux dépliants, c'est-à-dire précisément ce que `<details>` / `<summary>` fait
nativement, mieux — accessible au clavier, annoncé correctement par les lecteurs
d'écran, fonctionnel sans JavaScript, et sans aucun coût de chargement.

Le reste (menu mobile, menu déroulant, notification éphémère, révélation du mot de
passe, onglets) représente une soixantaine de lignes de JavaScript, dans le style du
fichier `static/js/iteag.js` qui existait déjà et concentrait la logique du site.

## Décision

**Supprimer Alpine.js.** Les comportements sont repris ainsi :

| Comportement | Remplacement |
|-------------|-------------|
| Accordéons « Mes cours », FAQ (page et accueil) | `<details class="accordeon">` natif |
| Menu mobile | `initMenuMobile()` — bascule `hidden` et `aria-expanded` |
| Menu déroulant utilisateur | `initMenusDeroulants()` — clic extérieur et Échap |
| Notifications éphémères | `initMessagesFlash()` — transition CSS, `role="status"` |
| Révélation du mot de passe | `initRevelationMotDePasse()` — bascule `type`, `aria-pressed` |
| Onglets du portail enseignant | `initOnglets()` — `role="tablist"`, `aria-selected` |
| Bandeau de verset aléatoire | Balise de gabarit `{% verset_aleatoire %}`, tirage serveur |

La CSP reste `script-src 'self'`, sans `'unsafe-eval'` ni `'unsafe-inline'`.
`media-src` sera ajouté au moment du lecteur vidéo, pour le seul domaine du stockage.

## Conséquences

**Positives**
- La contradiction entre la politique déclarée et le code embarqué disparaît à la
  racine : il n'y a plus de bibliothèque à rendre compatible.
- Une dépendance front de 40 Ko en moins sur chaque page.
- Gain d'accessibilité net : les accordéons deviennent utilisables au clavier et
  correctement annoncés ; les onglets, les notifications et le bouton de révélation
  portent désormais les attributs ARIA qui leur manquaient.
- Le bandeau de verset est rendu côté serveur : il est indexable et s'affiche même
  sans JavaScript.
- Toute la logique d'interface tient dans un fichier versionné et relisible, plutôt
  que dispersée dans des attributs HTML.

**Négatives / limites assumées**
- Un futur besoin de réactivité fine (liaison bidirectionnelle sur un formulaire
  complexe) demanderait de réintroduire une bibliothèque. HTMX couvre déjà les
  échanges serveur ; le cas ne s'est pas présenté à ce jour.
- Les comportements sont à ré-initialiser après un échange HTMX : c'est fait dans
  `htmx:afterSwap`, et cela doit le rester pour tout nouveau composant.

## Suivi

Rouvrir cette décision si un écran exige un état client riche et partagé entre
plusieurs composants — auquel cas le build CSP d'Alpine reste l'option de repli,
ciblée sur cet écran et non chargée globalement.
