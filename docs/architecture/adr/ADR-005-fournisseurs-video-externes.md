# ADR-005 — Diffusion vidéo déléguée à un fournisseur externe

- **Statut** : accepté — remplace la décision de diffusion de l'ADR-001
- **Date** : 2026-07-26
- **Décideur** : maîtrise d'œuvre, sur demande du maître d'ouvrage

## Contexte

L'ADR-001 retenait un bucket S3 privé avec URL présignée. La maîtrise d'ouvrage
demande de ne pas héberger les fichiers : l'espace de stockage du site ne doit
pas être saturé, et la lecture doit se faire depuis un lien externe sécurisé.

La demande est fondée, et pour une raison qui dépassait le stockage. Le risque
R4 du plan — débit insuffisant en Guyane et en Martinique — n'était pas traité
par l'ADR-001 : un fichier MP4 servi depuis S3 se lit à débit constant, sans
adaptation à la bande passante réelle. Un étudiant en connexion faible attend
ou abandonne. Un fournisseur de diffusion apporte le débit adaptatif et un
réseau de distribution, deux choses que nous n'allions pas construire.

## Le critère de décision

Le choix ne se joue pas sur « fichier ou lien ». Il se joue sur **ce qui peut
être retiré**.

Tout le contrôle d'accès de la plateforme repose sur un point de passage
unique, `services/acces.verifier_acces()`, revérifié à **chaque** demande de
lecture. Cette architecture n'a de valeur que si l'adresse délivrée expire et
ne vaut que pour la personne à qui elle a été remise. Un fournisseur dont le
lien est un porteur permanent réduit ce dispositif à une décoration.

Second critère, moins évident : **qui observe la lecture**. La progression est
mesurée côté serveur avec un incrément plafonné à 30 s par battement,
précisément pour qu'un étudiant ne puisse pas fabriquer du temps de visionnage.
Cette mesure suppose que les événements de lecture viennent de notre lecteur.
Un iframe tiers nous en dessaisit.

## Options examinées

| Option | Révocable | Débit adaptatif | Nos événements de lecture | Coût | CSP |
|---|---|---|---|---|---|
| A. S3 présigné (ADR-001) | oui | **non** | oui | stockage + sortie | `media-src 'self'` |
| B. YouTube non répertorié | **non** | oui | **non** (iframe) | gratuit | `frame-src`, `script-src` tiers |
| C. Vimeo, domaine verrouillé | **partiellement** | oui | **non** (iframe) | forfait | `frame-src` |
| D. Cloudflare Stream | oui | oui | oui (HLS direct) | élevé à l'usage | `media-src`, `connect-src` |
| **E. Bunny Stream** | **oui** | **oui** | **oui** (HLS direct) | **faible** | `media-src`, `connect-src` |

**B est éliminée pour les modules protégés.** Un lien non répertorié est un
porteur permanent : il ne s'annule pas, ne se limite à personne, et un seul
partage suffit à ouvrir l'accès à toute une promotion. S'y ajoutent la marque
et les vidéos suggérées d'un service grand public sur une formation payante.

**C protège de la republication, pas du partage.** Le verrouillage de domaine
est vérifié sur le référent — contournable — et l'adresse sous-jacente, une
fois extraite, n'est révocable pour personne en particulier. Le forfait fixe
reste son argument réel : une facture prévisible.

**D et E offrent la même propriété de sécurité** : jeton signé, expiration
courte, restriction d'adresse IP possible. C'est exactement la propriété de
l'URL présignée, avec le débit adaptatif en plus. Elles se départagent sur le
coût : la diffusion de Cloudflare Stream se facture à la minute vue, ce qui
devient lourd dès que la promotion consomme sérieusement ; Bunny facture au
gigaoctet transféré, cinq à dix fois moins cher à volume comparable.

## Décision

**Bunny Stream pour les modules à accès restreint. YouTube pour les
bandes-annonces du catalogue public.**

Deux besoins distincts, deux outils. Le catalogue public n'a rien à protéger et
gagne au référencement ; un module payant doit pouvoir être coupé.

La lecture se fait sur le manifeste HLS signé, avec un `hls.js` **auto-hébergé**.
Conséquence importante : la politique de sécurité reste `script-src 'self'`,
aucun script tiers n'est chargé, et nous gardons notre lecteur — donc la mesure
de progression plafonnée continue de fonctionner sans changement.

## Invariant imposé par le code

Un fournisseur non révocable ne peut pas servir un module à accès restreint.
Cette règle n'est pas une consigne de documentation : elle est vérifiée à la
validation du modèle et couverte par des tests. Sans elle, il suffirait d'une
inattention — coller un lien YouTube sur une leçon d'un module payant — pour
percer silencieusement tout le dispositif d'accès.

## Conséquences

**Favorables.** Aucun fichier vidéo chez nous, donc pas de saturation ni de
sauvegarde à dimensionner pour la vidéo. Débit adaptatif, ce qui traite R4.
Coût proportionnel à l'usage réel. Le contrôle d'accès et la mesure de
progression sont inchangés : seul le backend de diffusion change, conformément
à l'abstraction posée en ADR-001 — c'est précisément le report qu'elle
préparait.

**Défavorables.** Dépendance à un tiers pour la disponibilité du service. Bunny
est un acteur plus petit que Cloudflare ou Vimeo ; le risque est atténué par
l'abstraction, changer de fournisseur reste l'écriture d'une classe. Le dépôt
d'une vidéo passe désormais par le fournisseur : l'enseignant renseigne un
identifiant au lieu de téléverser un fichier, ce qui est un changement de
geste à accompagner.

**Ce que cette décision ne prétend pas.** Aucun de ces dispositifs n'empêche un
étudiant déterminé d'enregistrer son écran. Le but est de rendre le partage
coûteux et l'accès révocable, pas de le rendre impossible — ce que seul un DRM
prétendrait, au prix d'une complexité sans rapport avec l'enjeu.

## Réversibilité

Le backend S3 de l'ADR-001 est conservé et testé. Si le fournisseur externe
devait être abandonné, le retour se fait par un réglage. C'est la raison pour
laquelle l'abstraction est maintenue plutôt que remplacée.
