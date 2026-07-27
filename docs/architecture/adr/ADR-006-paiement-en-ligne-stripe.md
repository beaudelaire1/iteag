# ADR-006 — Paiement en ligne par Stripe Checkout, dans une couche partagée

- **Statut** : accepté
- **Date** : 2026-07-27
- **Décideur** : maîtrise d'œuvre, sur demande du maître d'ouvrage

## Contexte

Trois choses se paient à l'ITEAG, et jusqu'ici aucune ne se payait en ligne :
un module de formation, des frais d'inscription, un livre de la boutique. Le
règlement se faisait par virement, chèque, espèces ou au secrétariat, et se
constatait à la main.

Le constat qui a déclenché cette décision est plus brutal que l'absence de
paiement : **rien, dans le code, ne reliait un règlement à un accès**.
`academics.Paiement` et `commerce.Commande` ignoraient `elearning`, et
`InscriptionModule` ignorait l'argent. La question « comment quelqu'un qui n'a
pas payé peut-il regarder la formation ? » n'avait donc pas de réponse
technique : il n'y avait rien à contourner.

## Décision 1 — une couche `paiements`, ni dans la boutique ni dans l'e-learning

`apps/commerce` porte des invariants de stock et d'expédition qu'une formation
n'a pas : y faire entrer un article immatériel aurait obligé à neutraliser ces
règles au cas par cas. À l'inverse, dupliquer l'intégration Stripe dans chaque
domaine aurait multiplié par trois la surface où une erreur coûte de l'argent.

Ce que les trois usages partagent n'est pas le métier, c'est l'encaissement.
`apps/paiements` ne porte que cela : un montant, une TVA, une session Stripe,
un état, et la contrepartie à délivrer.

**Le sens de la dépendance est le point important.** `paiements` connaît les
trois domaines vendeurs ; aucun ne le connaît en retour. Un domaine qui
appellerait le paiement deviendrait indissociable de Stripe, et donc
intestable sans lui. L'invariant est vérifié par `test_architecture.py`.

## Décision 2 — Checkout hébergé, jamais de formulaire de carte

Aucune donnée bancaire ne touche nos serveurs. Le périmètre PCI tombe au plus
simple, et l'authentification forte (3-D Secure) reste à la charge de Stripe,
qui la met à jour à notre place.

C'est aussi la seule option compatible avec une règle que nous nous imposons :
ni le code, ni l'exploitant, ni un assistant automatisé ne manipulent de numéro
de carte.

## Décision 3 — la notification fait foi, jamais la redirection

C'est la décision la plus importante du dossier, et l'erreur la plus commune
dans les intégrations de paiement.

Un utilisateur ferme son onglet, son réseau tombe, son téléphone se verrouille :
la redirection de retour n'arrive pas. Si elle portait la décision, il aurait
payé sans rien recevoir. Stripe, lui, renotifie jusqu'à obtenir un 2xx.

Un règlement devient donc « payé » dans `services/webhook.py`, et nulle part
ailleurs. La page de retour est informative : elle affiche « en cours de
confirmation » tant que la notification n'est pas arrivée, plutôt qu'un succès
qui serait faux une fois sur vingt.

Trois propriétés en découlent, et chacune a son test :

| Propriété | Mécanisme | Ce qu'elle empêche |
|---|---|---|
| Authenticité | Signature vérifiée avant toute lecture du contenu | Qu'un tiers déclare un paiement abouti sur une adresse publique |
| Idempotence | `EvenementStripe.identifiant` unique ; l'insertion tranche, pas une lecture préalable | Qu'une redélivrance ouvre deux accès ou double une commande |
| Acquittement honnête | 500 en cas d'échec, jamais 200 par confort | Qu'un encaissement soit perdu parce que Stripe a cru avoir été entendu |

Le montant encaissé est recontrôlé contre le montant attendu. Délivrer une
formation à 300 € sur 3 € encaissés serait irrattrapable.

## Décision 4 — le remboursement referme ce que le paiement a ouvert

`charge.refunded` révoque l'accès ; `charge.dispute.created` aussi, **sans
attendre l'arbitrage bancaire**. Rouvrir un accès coûte un clic ; laisser
consommer une formation contestée coûte la formation.

Un remboursement partiel ne referme rien : rembourser un geste commercial ne
retire pas ce qui a été acheté.

## Décision 5 — la TVA est saisie, pas calculée par un service tiers

Le maître d'ouvrage saisit le taux article par article. L'ITEAG peut relever de
l'exonération de formation professionnelle (CGI art. 261-4-4°) sur ses modules
sans y relever sur ses livres : un service de calcul automatique aurait tranché
à sa place une question qui est juridique, pas technique.

Le prix est saisi TTC — c'est ce que le visiteur lit et ce que Stripe encaisse.
HT et TVA en sont dérivés puis **figés** sur le règlement : un taux modifié plus
tard ne doit pas réécrire l'histoire comptable. La TVA est obtenue par
soustraction, de sorte que HT + TVA redonne toujours exactement le TTC encaissé.

> **Réserve à lever par le maître d'ouvrage** : le statut d'exonération de
> l'ITEAG doit être confirmé auprès de son comptable. Le code sait facturer les
> deux cas ; il ne sait pas lequel s'applique.

## Décision 6 — l'accès acheté est perpétuel

Choix commercial du maître d'ouvrage. Techniquement, `InscriptionModule` sait
porter une échéance (`date_fin_acces`) : elle n'est simplement pas posée à
l'achat. Le jour où cela changerait, cela se ferait à une seule ligne,
`_delivrer_module()`.

## Conséquence sur le contrôle d'accès vidéo

Une politique `ACHAT` est ajoutée, et `PROTECTION_MINIMALE` la mappe sur
`NiveauProtection.SIGNEE`. Ce n'est pas une précaution de forme : un module
vendu est le cas où le lien porteur coûte le plus cher. Une adresse YouTube
partagée une fois rendrait la formation gratuite pour tous ceux qui la
reçoivent, sans qu'aucune révocation ne puisse y remédier.

De même, un module dont **toutes** les leçons sont en aperçu gratuit ne peut
plus être publié sous une politique restreinte. C'est ainsi qu'un module payant
peut se retrouver intégralement offert sans que personne ne le voie.

## Conséquences

- Nouvelle dépendance : `stripe` (Python).
- Le secret de signature du webhook est aussi critique que la clé secrète : un
  contrôle système (`paiements.E001`) refuse une configuration où l'un existe
  sans l'autre, car elle encaisserait sans délivrer.
- Les règlements sont en lecture seule dans l'administration : ce sont des
  écritures comptables, et les corriger à la main désynchroniserait le site de
  Stripe.
- L'exposition d'un point d'entrée public sans CSRF est assumée : la protection
  vient de la signature cryptographique, vérifiée avant toute lecture du corps.
