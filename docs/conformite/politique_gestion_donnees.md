# ITEAG — Politique interne de gestion des données

Version : 7 août 2026

## 1. Objet

Cette politique fixe les règles appliquées aux données personnelles et aux données métier traitées par la plateforme ITEAG, depuis leur collecte jusqu'à leur suppression. Elle complète la politique publique de protection des données et le registre des traitements.

Elle s'applique aux données des candidats, étudiants, enseignants, personnels, visiteurs, abonnés à la lettre d'information, emprunteurs de la bibliothèque et clients de la boutique.

## 2. Responsabilités

La direction de l'ITEAG est responsable de la gouvernance des données. Le secrétariat traite les dossiers dans la limite de ses missions. Les enseignants n'accèdent qu'aux données pédagogiques nécessaires aux cours qui leur sont attribués. Les administrateurs techniques interviennent pour l'exploitation et la sécurité, sans utiliser les données à d'autres fins.

Tout nouvel accès, export massif, nouveau prestataire ou nouvelle fonctionnalité collectant des données personnelles doit être justifié par un besoin métier identifié.

## 3. Règles de collecte

Avant d'ajouter un champ à un formulaire, l'équipe doit pouvoir répondre à quatre questions :

1. À quoi cette donnée sert-elle ?
2. Quelle base permet son traitement ?
3. Qui en a réellement besoin ?
4. Quand doit-elle être supprimée ou anonymisée ?

Un champ dont la finalité n'est pas identifiable ne doit pas être collecté.

Les informations facultatives doivent être distinguées des informations obligatoires. Les données particulièrement sensibles, notamment celles susceptibles de révéler des convictions religieuses, font l'objet d'une vigilance renforcée et ne doivent jamais être réutilisées pour du profilage ou de la publicité comportementale.

## 4. Information des personnes

Toute collecte importante doit renvoyer vers la politique publique `/protection-des-donnees/` et comporter, au point de collecte, une information courte sur la finalité lorsque le contexte ne la rend pas suffisamment évidente.

La politique publique indique au minimum : identité du responsable, finalités, principales bases juridiques, catégories de destinataires, durées de conservation, prestataires structurants, transferts éventuels, droits et moyen de saisir la CNIL.

## 5. Accès et habilitations

L'accès suit le principe du moindre privilège :

- candidat : accès à son propre suivi via un jeton non devinable ;
- étudiant : accès à son dossier, ses cours, ses travaux, notes et documents ;
- enseignant : accès aux étudiants et travaux nécessaires à ses cours ;
- secrétariat : accès aux traitements administratifs nécessaires à ses missions ;
- direction/administration : accès élargi lorsque la fonction le justifie ;
- administration technique : accès uniquement pour exploitation, maintenance, sécurité et restauration.

Un accès fonctionnel ne doit jamais reposer uniquement sur le masquage d'un bouton : les permissions sont contrôlées côté serveur.

## 6. Stockage et sécurité

Les données applicatives sont conservées dans PostgreSQL. Les fichiers et médias de production sont placés dans le stockage objet configuré pour l'ITEAG. Les sauvegardes utilisent un espace séparé du stockage courant.

Les mesures minimales sont : HTTPS, cookies d'authentification sécurisés, protection CSRF, séparation des rôles, double authentification des accès administratifs concernés, protection contre les tentatives de connexion abusives, stockage signé des médias privés, journalisation des opérations sensibles et sauvegardes hors serveur.

Les secrets, clés API et mots de passe de production ne doivent jamais être commités dans le dépôt Git.

## 7. Conservation et archivage

La durée de conservation est définie par traitement dans `registre_traitements.md`. Les valeurs structurantes actuellement retenues sont :

- candidatures refusées : 2 ans après la décision définitive ;
- dossier étudiant et données académiques : durée du cursus + 5 ans ;
- journal de sécurité et d'audit : 12 mois ;
- messages de contact : 12 mois après le dernier échange utile ;
- pièces comptables : 10 ans lorsque l'obligation correspondante s'applique ;
- sauvegardes : rotation technique d'environ 35 jours pour les quotidiennes et 400 jours pour les archives mensuelles.

Une durée plus longue n'est admise que lorsqu'une obligation, un contentieux, un incident de sécurité ou une preuve nécessaire la justifie. Dans ce cas, les données concernées passent en archivage intermédiaire avec accès réduit.

## 8. Suppression et anonymisation

La suppression doit couvrir l'ensemble des copies actives : base de données, fichiers associés dans le stockage objet et éventuels exports de travail encore présents dans les espaces internes.

Les sauvegardes ne sont pas réécrites pour retirer une donnée individuellement : elles expirent selon leur rotation normale. Lors d'une restauration, une suppression déjà arrivée à échéance doit être rejouée avant de remettre la base restaurée en exploitation lorsque cela est nécessaire.

Les statistiques historiques qui n'ont plus besoin d'identifier une personne doivent être anonymisées plutôt que conserver inutilement les données nominatives.

## 9. Exports et fichiers de travail

Un export CSV, tableur ou PDF contenant des données personnelles devient lui-même un support de données personnelles. Il doit donc :

- être limité aux colonnes nécessaires ;
- être transmis uniquement aux personnes habilitées ;
- ne pas être déposé dans un espace public ou personnel non prévu à cet effet ;
- être supprimé lorsque son usage ponctuel est terminé.

Les exports sensibles doivent être journalisés lorsque la fonctionnalité le permet.

## 10. Sous-traitants et services externes

Avant activation d'un prestataire manipulant des données personnelles, l'ITEAG vérifie :

- le rôle du prestataire et les données auxquelles il accède ;
- les conditions de sous-traitance et le DPA disponible ;
- la localisation du traitement et des sauvegardes ;
- les mécanismes applicables en cas de transfert hors EEE ;
- les réglages permettant de minimiser les données transmises ;
- la procédure de restitution ou suppression en fin de contrat.

Le registre interne recense les services actuellement prévus : OVHcloud, Cloudflare, Stripe, Sentry, Bunny.net, messagerie et, selon les contenus publics, YouTube/Vimeo.

## 11. Demandes d'exercice des droits

Les demandes reçues à `secretariat@iteag.org` sont enregistrées avec leur date de réception, leur objet et leur date de réponse. L'identité n'est vérifiée que lorsque cela est nécessaire et de manière proportionnée.

Le secrétariat coordonne la recherche des données dans les applications concernées. Une demande d'effacement ne conduit pas à supprimer une donnée qu'une obligation légale impose encore de conserver ; elle peut conduire à restreindre son accès ou la placer en archivage intermédiaire.

Les demandes et réponses sont conservées le temps nécessaire à la preuve du traitement de la demande, puis supprimées selon la durée interne retenue.

## 12. Incident ou violation de données

Tout accès non autorisé, perte, destruction, modification ou divulgation accidentelle de données doit être signalé immédiatement à la direction.

L'incident est documenté : date, périmètre, catégories de données et personnes concernées, cause, mesures de confinement et conséquences probables. La direction détermine ensuite, selon le risque, si une notification à la CNIL et/ou aux personnes concernées est requise dans les délais applicables.

Une restauration de sauvegarde ou une correction technique ne clôt pas à elle seule un incident : la cause et les mesures préventives doivent être documentées.

## 13. Revue périodique

Cette politique, le registre et la page publique sont revus au minimum une fois par an et à chaque changement significatif : nouvelle catégorie de données, nouveau prestataire, nouveau mode de paiement, nouveau service d'analyse/mesure d'audience, nouvelle fonctionnalité de publication ou changement important des durées de conservation.

La politique cookies et traceurs est maintenue séparément, car le besoin de consentement dépend des services réellement chargés dans le navigateur et de leur finalité.
