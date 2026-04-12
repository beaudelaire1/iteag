📋 CAHIER DES CHARGES FONCTIONNEL ET TECHNIQUE — V2
Refonte digitale de l'ITEAG (iteag.org)
Migration WordPress → Django / Wagtail

Projet : ITEAG-2026-REFONTE
Maître d'ouvrage : Institut de Théologie Évangélique des Antilles et de la Guyane (ITEAG)
Maître d'œuvre : Trait d'Union Studio (www.traitdunion.it)
Date : Avril 2026
Version : 2.0
Statut : Document exécutable — intègre les corrections issues de l'audit v1.1

======================================================================
TABLE DES MATIÈRES
======================================================================

 1. Contexte et enjeux
 2. Modèle pédagogique ITEAG (réalité terrain)
 3. Personas et parcours utilisateurs
 4. Vision cible
 5. Périmètre fonctionnel détaillé
 6. Hors périmètre V1 (exclusions explicites)
 7. Workflows métier formalisés
 8. Architecture fonctionnelle
 9. Modèle de données métier
10. Spécifications techniques
11. CI/CD, environnements et déploiement
12. Exigences de performance
13. Exigences de sécurité
14. Expérience utilisateur et design
15. SEO et visibilité
16. Stratégie de migration de contenu
17. KPIs métier et techniques
18. Livrables attendus
19. Planification et phasage
20. Contraintes et prérequis
21. Points de vigilance résiduels
22. Glossaire métier et technique
23. Signatures

======================================================================
1. CONTEXTE ET ENJEUX
======================================================================

1.1 Situation actuelle

L'ITEAG est une association loi 1905 de formation en théologie évangélique, basée en Guadeloupe (201 lot Pointe d'Or, 97139 Les Abymes), avec un rayonnement sur la Guadeloupe, la Martinique et la Guyane (via distanciel).

Le site actuel (iteag.org) est un site vitrine WordPress comprenant :
- ~12 pages institutionnelles (accueil, présentation, professeurs, formations, diplôme, ITEAG Pro, inscription, contact, actualités, bibliothèque) ;
- 2 635+ notices bibliothécaires cataloguées (titre, auteur, publication, mots-clés, cote) ;
- des images hébergées sur S3 (s3.amazonaws.com/news.iteag.org/) ;
- des actualités sous forme d'images/affiches ;
- des vidéos de cours distribuées sur demande au secrétariat ;
- une présence Facebook et YouTube.

Le site remplit une fonction de vitrine et d'information, mais reste limité pour répondre aux besoins de pilotage académique, d'admission, d'interaction pédagogique et de gestion centralisée.

1.2 Enjeux

- Sortir d'une logique de simple site vitrine sous WordPress.
- Construire une architecture propriétaire robuste, pérenne et conforme au standard TUS.
- Offrir une expérience fluide et adaptée aux visiteurs, étudiants, enseignants et administrateurs.
- Centraliser progressivement les processus pédagogiques et administratifs.
- Renforcer l'autonomie de gestion de l'ITEAG (administration par des profils non techniques).
- Préparer une montée en puissance future sans dépendance excessive aux plugins tiers.
- Adapter la plateforme au modèle pédagogique spécifique de l'ITEAG (sessions intensives, ECTS, double filière).

1.3 Objectifs stratégiques

| # | Objectif | Description | Indicateur |
|---|----------|-------------|------------|
| O1 | Digitalisation | Faire évoluer le site vers un écosystème académique complet | Mise en ligne progressive des processus académiques et administratifs |
| O2 | Pédagogie | Plateforme adaptée à l'enseignement hybride et au modèle session-based ITEAG | Accès unifié aux cours, ressources, suivi ECTS et progression |
| O3 | Performance | Haut niveau de qualité technique et d'expérience utilisateur | Lighthouse > 90, LCP < 2.5s, CLS < 0.1 |
| O4 | Souveraineté | Maîtrise du code, des données et de l'architecture | Code source documenté, auditable, transmissible, sans dépendance critique |
| O5 | Évolutivité | Ajout futur de modules sans refonte complète | Architecture modulaire, apps découplées |
| O6 | Conversion | Augmenter les candidatures et inscriptions via le digital | Taux de conversion visiteur → candidature mesurable |

======================================================================
2. MODÈLE PÉDAGOGIQUE ITEAG (RÉALITÉ TERRAIN)
======================================================================

Ce modèle est la contrainte structurante de toute l'architecture LMS et du modèle de données. Il doit être respecté dans chaque décision de conception.

2.1 Organisation des sessions

- 4 sessions intensives d'une semaine par an, sur 6 ans.
- Périodes fixes : Carnaval (mi-février/mars), Pâques (avril), Grandes vacances (début juillet), Toussaint (novembre).
- Chaque session correspond à un ou plusieurs cours magistraux délivrés en présentiel sur une semaine.
- Distanciel proposé pour les étudiants de Guyane, Martinique et autres.

2.2 Système de crédits ECTS

- 1 crédit ECTS = 25 à 30 heures de travail.
- Chaque cours validé = 2,5 ECTS.
- Diplôme ITEAG : 180 ECTS au total.
- Bachelor FLTE : 180 ECTS (150 ITEAG + 30 FLTE via Vaux-sur-Seine).
- Stages obligatoires : 30 ECTS.
- En cas d'impossibilité de stage : dissertation de fin d'études = 15 ECTS (les 30 ECTS manquants sont couverts par cours in absentia ou e-learning FLTE).

2.3 Filières et parcours

| Parcours | Conditions d'entrée | Visée | ECTS requis |
|----------|---------------------|-------|-------------|
| Parcours diplômant ITEAG | Aucun diplôme requis | Diplôme ITEAG | 180 |
| Parcours Bachelor FLTE | Baccalauréat ou équivalent requis ; lecture anglais conseillée | Bachelor FLTE (Vaux-sur-Seine) | 180 (150 ITEAG + 30 FLTE) |
| Parcours libre | Aucune condition | Pas de diplôme, ni validation | Aucun |
| ITEAG Pro | Cadres d'église | Formation continue | Variable |

Tous les étudiants (diplômant, bachelor, libre) suivent les mêmes cours magistraux. La différence se fait au niveau des exigences de validation.

2.4 Disciplines

5 disciplines principales :
1. Ancien Testament
2. Nouveau Testament
3. Théologie systématique (doctrine)
4. Histoire de l'Église
5. Théologie pratique

2.5 Stages et VAE

- Différents types de stages proposés.
- Encadrement des stages par un tuteur.
- Validation des Acquis de l'Expérience (VAE) possible.

2.6 Tarification

| Formule | Églises fondatrices | Autres |
|---------|---------------------|--------|
| Toutes les sessions (abonnement annuel) | 200 €/session | 250 €/session |
| Session au choix (à la carte) | 250 €/session | 300 €/session |

Soit 4 sessions/an → coût annuel entre 800 € et 1 200 € selon statut et formule.

2.7 Partenariat FLTE

- La Faculté Libre de Théologie Évangélique de Vaux-sur-Seine (flte.fr) est partenaire pour la délivrance du bachelor.
- Les étudiants ITEAG obtiennent 150 ECTS via l'ITEAG.
- Les 30 ECTS complémentaires sont obtenus via cours in absentia ou e-learning de la FLTE.
- La plateforme doit pouvoir enregistrer des crédits obtenus dans une institution externe (FLTE) et les intégrer au suivi de progression de l'étudiant.

2.8 Équipe professorale

7 professeurs identifiés :
- Ruth Labeth
- Alain Nisus (Directeur)
- Daniel Reivax
- Cédric Eugène
- Stéphane Guillet
- Jean-Claude Girondin
- Patrice Kaulanjan

Professeurs chevronnés, souvent Antillo-Guyanais, intervenant depuis l'Hexagone et la Caraïbe.

2.9 Bibliothèque

- > 2 635 ouvrages catalogués (titre, auteur, date de publication, mots-clés, cote).
- > 3 000 ouvrages annoncés sur le site.
- Accessible aux étudiants.
- Consultation physique en priorité ; un accès numérique au catalogue est souhaité sur la plateforme.

======================================================================
3. PERSONAS ET PARCOURS UTILISATEURS
======================================================================

3.1 Persona 1 : Visiteur / Prospect

| Attribut | Description |
|----------|-------------|
| Profil | Membre d'église antillais/guyanais intéressé par la théologie |
| Âge | 25–65 ans |
| Compétence numérique | Basique à intermédiaire |
| Appareil prioritaire | Smartphone (mobile-first) |
| Objectif | Comprendre l'offre ITEAG, découvrir les formations, vérifier les conditions d'admission |
| Parcours critique | Accueil → Formations → Fiche parcours → Conditions → Pré-inscription |
| Frustration type | Informations dispersées, absence de formulaire en ligne, obligation de contacter le secrétariat |
| Critère de succès | Peut déposer une demande de candidature en moins de 5 minutes |

3.2 Persona 2 : Candidat

| Attribut | Description |
|----------|-------------|
| Profil | Visiteur ayant décidé de postuler |
| Compétence numérique | Basique |
| Appareil prioritaire | Smartphone ou ordinateur |
| Objectif | Soumettre un dossier complet, suivre l'avancement de sa candidature |
| Parcours critique | Formulaire de candidature → Soumission → Suivi → Réponse |
| Frustration type | Pas de visibilité sur l'état de son dossier, relances téléphoniques nécessaires |
| Critère de succès | Peut suivre l'état de sa candidature en ligne sans contacter le secrétariat |

3.3 Persona 3 : Étudiant actif

| Attribut | Description |
|----------|-------------|
| Profil | Étudiant inscrit à l'ITEAG, en activité professionnelle parallèle |
| Âge | 30–60 ans |
| Compétence numérique | Basique à intermédiaire |
| Appareil prioritaire | Smartphone (90% du temps), ordinateur en semaine de session |
| Objectif | Consulter planning, accéder aux ressources de cours, remettre devoirs, suivre progression ECTS |
| Parcours critique | Connexion → Tableau de bord → Session en cours → Ressources → Remise devoir |
| Frustration type | Pas d'accès centralisé, documents éparpillés, absence de suivi de progression |
| Critère de succès | Accède à tout depuis son tableau de bord en 2 clics maximum |

3.4 Persona 4 : Enseignant

| Attribut | Description |
|----------|-------------|
| Profil | Professeur intervenant 1 à 4 fois/an en session intensive |
| Compétence numérique | Intermédiaire |
| Appareil prioritaire | Ordinateur portable |
| Objectif | Déposer supports avant session, accéder à la liste des étudiants, noter, communiquer consignes |
| Parcours critique | Connexion → Mon cours → Dépôt supports → Liste étudiants → Saisie notes |
| Frustration type | Processus papier, envoi par email, pas de visibilité sur les remises étudiantes |
| Critère de succès | Peut préparer et gérer son cours entièrement en ligne |

3.5 Persona 5 : Secrétariat / Administration ITEAG

| Attribut | Description |
|----------|-------------|
| Profil | Personnel administratif (1-2 personnes), gestion quotidienne |
| Compétence numérique | Basique — ne doit pas avoir besoin de compétences techniques |
| Appareil prioritaire | Ordinateur de bureau |
| Objectif | Gérer admissions, inscriptions, publication de contenus, communication, suivi paiements |
| Parcours critique | Connexion admin → Dossiers en attente → Validation → Publication actualité |
| Frustration type | Travail manuel, tableurs, communications par téléphone, pas d'outil centralisé |
| Critère de succès | Peut gérer 90% des opérations courantes depuis un seul back-office intuitif |

======================================================================
4. VISION CIBLE
======================================================================

Le futur dispositif est conçu comme un écosystème numérique organisé autour de portails complémentaires :

```
┌─────────────────────────────────────────────────────────────┐
│                    ÉCOSYSTÈME ITEAG                          │
├──────────────┬──────────────┬──────────────┬────────────────┤
│  PORTAIL     │  PORTAIL     │  PORTAIL     │  PORTAIL       │
│  PUBLIC      │  ÉTUDIANT    │  ENSEIGNANT  │  ADMINISTRATIF │
│  (vitrine)   │  (connecté)  │  (connecté)  │  (pilotage)    │
└──────────────┴──────────────┴──────────────┴────────────────┘
```

La stratégie d'interface d'administration est la suivante :
- Wagtail : gestion éditoriale des contenus publics (pages, actualités, événements, témoignages). Interface unique pour le secrétariat non technique.
- Django Admin custom : réservé aux opérations de pilotage métier (admissions, inscriptions, gestion académique, paiements, reporting). Interface séparée, accès restreint.
- L'équipe ITEAG travaille principalement dans Wagtail pour la publication. Elle accède à l'admin Django custom pour les processus métier via un dashboard simplifié.

======================================================================
5. PÉRIMÈTRE FONCTIONNEL DÉTAILLÉ
======================================================================

Chaque fonctionnalité est classée selon la méthode MoSCoW :
- **Must** : indispensable pour la V1, bloque la mise en production si absent.
- **Should** : fortement souhaité en V1, peut être reporté en V1.1 si nécessaire.
- **Could** : enrichissement souhaitable, reportable en V2.
- **Won't V1** : exclu de la V1, prévu en phases ultérieures.

----------------------------------------------------------------------
5.1 Portail public institutionnel
----------------------------------------------------------------------

| ID | Fonctionnalité | Priorité | Critères d'acceptation |
|----|---------------|----------|----------------------|
| PUB-001 | Page d'accueil premium | Must | La page présente : accroche claire, formations mises en avant, témoignages, CTA inscription, actualités récentes. Score Lighthouse > 90. Chargement < 2s. |
| PUB-002 | Présentation institutionnelle | Must | Pages « Qui sommes-nous », historique, mission, valeurs éditables via Wagtail. Administrateur peut modifier le contenu sans développeur. |
| PUB-003 | Catalogue dynamique des formations | Must | Liste des parcours (diplômant ITEAG, bachelor FLTE, libre, ITEAG Pro) avec filtres. Chaque parcours affiche : description, conditions, ECTS, durée, tarifs. Données administrables. |
| PUB-004 | Fiches formation détaillées | Must | Chaque fiche affiche : description du parcours, programme des cours par discipline, conditions d'admission, ECTS par cours (2.5), total ECTS, conditions de validation, tarification, CTA candidature. |
| PUB-005 | Équipe professorale | Must | Page listant les 7+ professeurs avec photo, nom, discipline, biographie courte. Administrable via Wagtail. |
| PUB-006 | Système d'actualités | Must | Liste paginée, page de détail, images, catégorisation. Publication via Wagtail. Flux RSS. |
| PUB-007 | Calendrier des événements | Should | Événements datés, filtrables, avec lieu et description. Affichage calendrier ou liste. |
| PUB-008 | Témoignages | Should | Affichage de témoignages étudiants/diplômés (texte + photo). Administrable. Carousel ou grille. |
| PUB-009 | FAQ | Should | Questions/réponses organisées par thème, administrables via Wagtail. Accordéon accessible. |
| PUB-010 | Formulaires de contact ciblés | Must | Formulaire général + formulaire secrétariat. Destinataire configurable. Confirmation email envoyée à l'expéditeur. Protection anti-spam (honeypot + rate limiting). |
| PUB-011 | Formulaire de pré-inscription / candidature | Must | Formulaire multi-étapes : identité, parcours choisi, motivations, pièces justificatives. Confirmation email. Création automatique d'un dossier de candidature côté admin. |
| PUB-012 | Inscription newsletter | Should | Formulaire email, double opt-in, désinscription, conformité RGPD. Intégration Celery pour envoi. |
| PUB-013 | SEO avancé | Must | Balises meta administrables par page, URLs propres, sitemap XML, données structurées (Organization, Course, Event), optimisation images (WebP, lazy loading), maillage interne. |
| PUB-014 | Bibliothèque publique (catalogue) | Should | Recherche dans le catalogue (2 635+ notices), filtres par auteur/titre/mot-clé/cote. Pas de téléchargement d'ouvrages en V1, consultation des fiches uniquement. |
| PUB-015 | Redirections 301 | Must | Toutes les URLs de l'ancien site redirigées vers les nouvelles. Mapping validé avant mise en production. |

----------------------------------------------------------------------
5.2 Portail étudiant
----------------------------------------------------------------------

| ID | Fonctionnalité | Priorité | Critères d'acceptation |
|----|---------------|----------|----------------------|
| ETU-001 | Authentification sécurisée | Must | Login email/mot de passe. Politique de mot de passe forte (12 car. min, complexité). Verrouillage après 5 tentatives (django-axes). Session expirée après 30 min d'inactivité. |
| ETU-002 | Tableau de bord personnel | Must | Affiche : session en cours/prochaine, ECTS accumulés / 180 total, devoirs en attente, notifications récentes, accès rapides. |
| ETU-003 | Accès aux cours et ressources de session | Must | L'étudiant voit les cours de sa session en cours avec les supports déposés par l'enseignant (PDF, documents). Téléchargement possible. |
| ETU-004 | Suivi de progression ECTS | Must | Vue « Mon parcours » : liste de tous les cours suivis, ECTS obtenus par cours (2.5), total cumulé, ECTS restants. Distinction crédits ITEAG / crédits FLTE (pour le parcours bachelor). |
| ETU-005 | Remise de devoirs | Should | Upload de fichier (PDF, DOCX, max 20 Mo) rattaché à un cours et une évaluation. Confirmation d'envoi. Horodatage. Statut visible (soumis, en correction, noté). |
| ETU-006 | Consultation des notes | Should | Affichage des notes par cours lorsque l'enseignant les publie. Note, appréciation, ECTS validés ou non. |
| ETU-007 | Planning personnel | Should | Calendrier des sessions à venir avec dates et cours prévus. Synchronisation iCal optionnelle (Could). |
| ETU-008 | Documents administratifs | Should | Téléchargement d'attestations (inscription, relevé de notes, certificat de scolarité) générées en PDF via WeasyPrint. |
| ETU-009 | Notifications internes | Should | Notifications in-app : nouveau cours publié, note disponible, message enseignant, rappel session. Badge de compteur non lu. |
| ETU-010 | Suivi des paiements | Could | Vue des paiements effectués, montants, reçus téléchargeables. |

----------------------------------------------------------------------
5.3 Portail enseignant
----------------------------------------------------------------------

| ID | Fonctionnalité | Priorité | Critères d'acceptation |
|----|---------------|----------|----------------------|
| ENS-001 | Gestion des cours | Must | L'enseignant voit ses cours assignés. Il peut modifier la description, ajouter des sections, organiser le contenu de chaque cours. |
| ENS-002 | Upload de contenus pédagogiques | Must | Dépôt de fichiers (PDF, DOCX, PPT, images) rattachés à un cours. Taille max par fichier : 50 Mo. Gestion basique (ajouter, remplacer, supprimer). |
| ENS-003 | Liste des étudiants inscrits | Must | Vue de la liste des étudiants inscrits à un cours donné, avec email et parcours (diplômant/bachelor/libre). |
| ENS-004 | Saisie et publication des notes | Should | Saisie de notes par étudiant et par cours. Publication contrôlée (brouillon → publié). Distinction par exigence de validation (diplôme ITEAG vs bachelor FLTE). |
| ENS-005 | Correction et retour pédagogique | Should | Accès aux devoirs remis. Possibilité de télécharger, annoter (commentaire texte), noter, et retourner le feedback. |
| ENS-006 | Communication de consignes | Should | Publication d'annonces visibles par les étudiants du cours (consignes de session, rappels, informations pratiques). |
| ENS-007 | Tableau de bord enseignant | Could | Vue synthétique : nombre d'étudiants, devoirs en attente de correction, prochaines sessions. |

----------------------------------------------------------------------
5.4 Portail administratif
----------------------------------------------------------------------

| ID | Fonctionnalité | Priorité | Critères d'acceptation |
|----|---------------|----------|----------------------|
| ADM-001 | Gestion des admissions (workflow complet) | Must | Le secrétariat voit tous les dossiers de candidature dans une vue filtrée par statut. Il peut changer le statut (cf. section 7.1). Email automatique à chaque changement de statut. Export CSV de la liste. |
| ADM-002 | Gestion des inscriptions | Must | Après acceptation d'un dossier, l'admin inscrit l'étudiant à un parcours et une promotion. L'inscription crée le compte étudiant et l'associe aux sessions/cours. |
| ADM-003 | Suivi des paiements | Should | Enregistrement des paiements par étudiant (montant, date, mode, session concernée). Vue des impayés. Export. Pas de paiement en ligne en V1 (cf. section 6). |
| ADM-004 | Gestion académique | Must | Organisation des sessions (dates, cours rattachés, enseignants assignés). Affectation des étudiants aux sessions. Vue planning global. |
| ADM-005 | Gestion des utilisateurs et rôles | Must | CRUD utilisateurs. Attribution de rôles : étudiant, enseignant, admin, secrétariat. Permissions séparées par rôle. Un utilisateur = un seul rôle principal. |
| ADM-006 | Communication ciblée | Should | Envoi d'emails ciblés par promotion, parcours, ou session. Templates email administrables. Envoi via Celery (asynchrone). |
| ADM-007 | Reporting et tableaux de bord | Should | Dashboard admin : nombre d'étudiants actifs, candidatures en cours, sessions planifiées, taux de complétion, paiements reçus. |
| ADM-008 | Gestion éditoriale CMS | Must | Publication de pages, actualités, événements, témoignages via Wagtail. Interface pensée pour profils non techniques. Formation incluse dans les livrables. |
| ADM-009 | Génération de documents PDF | Should | Génération d'attestations, relevés de notes, certificats via WeasyPrint. Templates PDF administrables. |
| ADM-010 | Archives et exports | Could | Export CSV/Excel des étudiants, inscriptions, notes, paiements. Archivage des promotions terminées. |

----------------------------------------------------------------------
5.5 Bibliothèque numérique
----------------------------------------------------------------------

| ID | Fonctionnalité | Priorité | Critères d'acceptation |
|----|---------------|----------|----------------------|
| BIB-001 | Catalogue indexé consultable | Should | Les 2 635+ notices sont consultables avec : titre, auteur, date, mots-clés, cote. Recherche full-text PostgreSQL. Pagination. |
| BIB-002 | Filtres et recherche avancée | Should | Filtres par discipline, auteur, année, mot-clé. Recherche par titre ou auteur. Résultats triables. |
| BIB-003 | Accès conditionnel | Could | Certaines ressources numériques accessibles uniquement aux étudiants connectés. Le catalogue public reste consultable par tous. |
| BIB-004 | Administration du catalogue | Should | CRUD sur les notices via l'admin Django. Import CSV pour migration initiale des 2 635 notices. |

======================================================================
6. HORS PÉRIMÈTRE V1 (EXCLUSIONS EXPLICITES)
======================================================================

Les éléments suivants sont EXCLUS de la V1. Ils pourront être intégrés dans les phases ultérieures :

| Élément | Justification |
|---------|--------------|
| Paiement en ligne (Stripe, PayPal) | Complexité réglementaire et technique. V1 = suivi manuel des paiements. À arbitrer en V2. |
| Multi-langue | Le public cible est francophone. À évaluer si la demande anglophone se confirme. |
| Multi-sites / multi-antennes | L'ITEAG opère depuis un seul site physique. Le distanciel est géré par la même instance. |
| Forum / espace communautaire | Usage réel non confirmé. Les échanges de classe se font via annonces enseignant en V1. |
| PWA / mode offline | Le profil utilisateur ne justifie pas l'investissement en V1. Mobile-first responsive suffit. |
| Visioconférence intégrée | Les sessions sont en présentiel. Le distanciel utilise des outils externes (Zoom, etc.). |
| Elasticsearch | PostgreSQL full-text suffit pour le volume de données (~2 635 notices + contenus). |
| Portail partenaire | À développer si le partenariat FLTE nécessite un accès dédié. V1 = échanges manuels. |
| LMS avancé (quiz interactifs, gamification, SCORM) | Le modèle ITEAG est basé sur cours magistraux + travaux écrits. Un LMS léger suffit en V1. |
| Antivirus sur fichiers uploadés | Disproportionné pour le volume et le profil utilisateur. Validation de type MIME + taille max suffisent en V1. |

======================================================================
7. WORKFLOWS MÉTIER FORMALISÉS
======================================================================

7.1 Workflow d'admission (candidature)

```
[SOUMIS]
    │
    ▼
[EN EXAMEN] ──── le secrétariat examine le dossier
    │
    ├──► [INCOMPLET] ──── pièces manquantes ──── notification email ──── retour à [EN EXAMEN]
    │
    ├──► [ACCEPTÉ] ──── notification email + instructions inscription
    │
    └──► [REFUSÉ] ──── notification email motivée
```

États du dossier de candidature :
1. **SOUMIS** : le candidat a rempli et envoyé le formulaire. Email de confirmation automatique.
2. **EN EXAMEN** : le secrétariat a pris en charge le dossier. Pas d'email à cette étape.
3. **INCOMPLET** : pièces manquantes ou informations à compléter. Email automatique avec détail des éléments manquants. Le candidat peut re-soumettre.
4. **ACCEPTÉ** : le dossier est validé. Email automatique avec instructions pour l'inscription et le paiement.
5. **REFUSÉ** : le dossier est rejeté. Email automatique avec motif.

Règles :
- Seul le rôle « secrétariat » ou « admin » peut changer le statut.
- Chaque changement de statut est horodaté et journalisé.
- Le candidat peut consulter le statut de son dossier en ligne (accès par lien unique signé envoyé par email).

7.2 Workflow d'inscription

```
[ACCEPTÉ] (dossier candidature)
    │
    ▼
[PRÉ-INSCRIT] ──── le secrétariat crée l'inscription
    │
    ▼
[PAIEMENT EN ATTENTE] ──── l'étudiant doit régler la session
    │
    ▼
[INSCRIT] ──── paiement confirmé manuellement par le secrétariat
    │
    ▼
[ACTIF] ──── l'étudiant a accès à son portail et ses cours
```

États :
1. **PRÉ-INSCRIT** : le secrétariat a converti la candidature acceptée en inscription. Choix du parcours et de la promotion.
2. **PAIEMENT EN ATTENTE** : instruction de paiement envoyée. Le secrétariat enregistre le paiement manuellement.
3. **INSCRIT** : paiement confirmé. Compte étudiant créé (ou activé). Email de bienvenue avec identifiants.
4. **ACTIF** : l'étudiant accède à son portail, ses cours et ses ressources.

Cas particuliers :
- **Suspension** : un étudiant peut être suspendu (accès désactivé sans suppression de données).
- **Réinscription** : un étudiant inactif peut être réinscrit pour une nouvelle année sans recréer de dossier de candidature.

7.3 Workflow de validation d'un cours

```
[COURS PROGRAMMÉ] ──── session planifiée, cours assigné à un enseignant
    │
    ▼
[EN COURS] ──── la semaine de session est en cours
    │
    ▼
[ÉVALUATION] ──── l'enseignant reçoit les travaux / évalue
    │
    ▼
[NOTÉ] ──── notes saisies par l'enseignant
    │
    ▼
[PUBLIÉ] ──── notes visibles par les étudiants
    │
    ├──► [VALIDÉ] ──── 2,5 ECTS crédités
    └──► [NON VALIDÉ] ──── 0 ECTS, possibilité de rattrapage selon règlement
```

7.4 Workflow de publication éditoriale

```
[BROUILLON] ──── contenu créé dans Wagtail
    │
    ▼
[EN RÉVISION] ──── optionnel, pour relecture
    │
    ▼
[PUBLIÉ] ──── visible sur le portail public
    │
    ▼
[ARCHIVÉ] ──── retiré du public mais conservé
```

======================================================================
8. ARCHITECTURE FONCTIONNELLE
======================================================================

8.1 Bloc public (non authentifié)

- Accueil
- Présentation institutionnelle
- Catalogue des formations
- Fiches parcours / programmes
- Équipe professorale
- Actualités
- Événements
- Bibliothèque publique (catalogue)
- FAQ
- Formulaires (contact, candidature)
- Newsletter

8.2 Bloc privé authentifié

- Espace étudiant (tableau de bord, cours, progression, devoirs, documents)
- Espace enseignant (cours, contenus, étudiants, notes)
- Suivi de candidature (accès limité pour le candidat)

8.3 Bloc de pilotage (administration)

- Gestion éditoriale via Wagtail
- Gestion des admissions via admin Django custom
- Gestion des inscriptions
- Gestion académique (sessions, cours, affectations)
- Gestion des utilisateurs et rôles
- Suivi des paiements
- Reporting
- Génération de documents PDF
- Exports

======================================================================
9. MODÈLE DE DONNÉES MÉTIER
======================================================================

9.1 Entités principales et attributs clés

```
┌─────────────────────────────────────────────┐
│                 UTILISATEUR                  │
│ id, email, nom, prénom, téléphone, rôle,    │
│ statut (actif/suspendu/inactif),            │
│ date_création, date_dernière_connexion       │
└─────────────────────────────────────────────┘
         │
         │ 1:1
         ▼
┌─────────────────────────────────────────────┐
│              PROFIL ÉTUDIANT                 │
│ id, utilisateur_fk, parcours_fk,            │
│ promotion_fk, numéro_étudiant,              │
│ statut_inscription, formule_tarif,           │
│ église_fondatrice (bool), total_ects_acquis  │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│              PROFIL ENSEIGNANT               │
│ id, utilisateur_fk, disciplines,             │
│ biographie, photo, spécialité                │
└─────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────┐
│                PARCOURS                      │
│ id, nom, type (diplômant_iteag /             │
│ bachelor_flte / libre / pro),                │
│ ects_requis, conditions_entrée,              │
│ description                                  │
└─────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────────────────────────────────┐
│                DISCIPLINE                    │
│ id, nom (AT, NT, Théo. Syst.,               │
│ Hist. Église, Théo. Pratique)               │
└─────────────────────────────────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────────────────────────────────┐
│                  COURS                       │
│ id, titre, discipline_fk, description,       │
│ ects (défaut: 2.5), enseignant_fk            │
└─────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────┐
│                PROMOTION                     │
│ id, nom (ex: "Promotion 2020-2026"),         │
│ année_début, année_fin, parcours_fk          │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│            SESSION ACADÉMIQUE                │
│ id, nom (ex: "Carnaval 2026"),               │
│ période (carnaval/pâques/juillet/toussaint), │
│ date_début, date_fin, année_académique,      │
│ statut (planifiée/en_cours/terminée)         │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│          COURS DE SESSION                    │
│ id, session_fk, cours_fk, enseignant_fk,    │
│ salle, horaires, statut                      │
└─────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────┐
│        INSCRIPTION SESSION                   │
│ id, étudiant_fk, session_fk,                │
│ cours_session_fk, statut                     │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│             ÉVALUATION                       │
│ id, étudiant_fk, cours_session_fk,          │
│ type (devoir/examen/stage/dissertation/VAE), │
│ note, appréciation, ects_validés (0 ou 2.5),│
│ statut (en_attente/soumis/en_correction/     │
│         noté/publié), date_soumission,       │
│ date_notation                                │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│          CRÉDIT ECTS                         │
│ id, étudiant_fk, cours_fk, ects_obtenus,    │
│ source (iteag/flte), session_fk,             │
│ date_validation                              │
│ >>> Permet le suivi croisé ITEAG + FLTE     │
└─────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────┐
│        DOSSIER DE CANDIDATURE                │
│ id, candidat_nom, candidat_email,            │
│ candidat_téléphone, parcours_souhaité,       │
│ motivations, pièces_jointes,                 │
│ statut (soumis/en_examen/incomplet/          │
│         accepté/refusé),                     │
│ date_soumission, date_dernière_maj,          │
│ motif_refus, notes_internes, token_suivi     │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│              PAIEMENT                        │
│ id, étudiant_fk, session_fk, montant,        │
│ date_paiement, mode (virement/espèces/       │
│ chèque/autre), statut (en_attente/confirmé), │
│ référence, reçu_pdf                          │
└─────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────┐
│           STAGE                              │
│ id, étudiant_fk, type_stage, lieu,           │
│ tuteur_fk, date_début, date_fin,             │
│ ects (défaut: 30 ou partiel),                │
│ statut (en_cours/validé/non_validé),         │
│ rapport_fk                                   │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│              VAE                              │
│ id, étudiant_fk, description_expérience,     │
│ ects_demandés, ects_accordés,                │
│ statut (soumis/en_examen/accordé/refusé),    │
│ date_soumission, décision_date               │
└─────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────┐
│         RESSOURCE PÉDAGOGIQUE                │
│ id, cours_fk, titre, type_fichier,           │
│ fichier, taille, uploadé_par,                │
│ date_upload, visible_étudiants (bool)        │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│        NOTICE BIBLIOTHÈQUE                   │
│ id, titre, auteur, date_publication,         │
│ mots_clés, cote, éditeur, discipline_fk,    │
│ disponible (bool)                            │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│         DOCUMENT ADMINISTRATIF               │
│ id, étudiant_fk, type (attestation/          │
│ relevé_notes/certificat), fichier_pdf,       │
│ date_génération                              │
└─────────────────────────────────────────────┘
```

9.2 Relations clés

- Un PARCOURS contient plusieurs COURS via des DISCIPLINES.
- Un COURS est dispensé lors de SESSIONS ACADÉMIQUES via COURS DE SESSION.
- Un ÉTUDIANT est inscrit à un PARCOURS via une PROMOTION.
- Un ÉTUDIANT s'inscrit à des SESSIONS via INSCRIPTION SESSION.
- Un ÉTUDIANT accumule des CRÉDITS ECTS (source ITEAG ou FLTE).
- Un DOSSIER DE CANDIDATURE suit un workflow à états (section 7.1).
- Un PAIEMENT est rattaché à un ÉTUDIANT et une SESSION.
- Un STAGE ou une VAE génère des ECTS spéciaux (30 ECTS stage, variable VAE).

9.3 Cardinalités principales

```
Parcours       1 ──── N  Discipline
Discipline     1 ──── N  Cours
Cours          1 ──── N  CoursDeSession
Session        1 ──── N  CoursDeSession
Enseignant     1 ──── N  CoursDeSession
Étudiant       1 ──── N  InscriptionSession
Étudiant       1 ──── N  CréditECTS
Étudiant       1 ──── N  Évaluation
Étudiant       1 ──── N  Paiement
Étudiant       0..1 ──── N  Stage
Étudiant       0..1 ──── N  VAE
Promotion      1 ──── N  ProfilÉtudiant
```

======================================================================
10. SPÉCIFICATIONS TECHNIQUES
======================================================================

10.1 Stack technique

| Couche | Technologie | Justification |
|--------|-------------|---------------|
| Backend | Python 3.12+ | Maturité, sécurité, écosystème robuste |
| Framework | Django 5.x | Socle applicatif solide, ORM puissant, sécurité native, admin maîtrisée |
| CMS éditorial | Wagtail 6.x | Gestion de contenu structurée pour profils non techniques |
| Templates | Django Templates + HTMX | Rendu serveur, interactivité ciblée, pas de SPA |
| Styling | Tailwind CSS 4.x | Design system propriétaire, léger, cohérent |
| Interactions UI | Alpine.js + HTMX | Réactivité fine sans lourdeur front-end |
| Base de données | PostgreSQL 16+ | Robustesse, full-text search, JSONB, extensibilité |
| Cache / sessions | Redis | Cache applicatif, sessions, broker Celery |
| Tâches asynchrones | Celery + Redis | Emails, notifications, génération PDF, traitements différés |
| PDF | WeasyPrint | Génération de documents administratifs (attestations, relevés) |
| Fichiers / stockage | S3 natif (AWS) ou compatible | Stockage pérenne des médias et ressources. S3 natif en production cloud pour simplicité. MinIO uniquement en dev local. |
| Recherche | PostgreSQL full-text (pg_trgm + ts_vector) | Suffisant pour le volume. Elasticsearch reporté si besoin confirmé. |
| Email transactionnel | Django + backend SMTP (ou API type Brevo/Mailgun) | Emails transactionnels (confirmation, notification). Service API recommandé pour la délivrabilité. Templates HTML administrables. |

10.2 Philosophie d'architecture

- Modular Monolith : un seul déploiement Django, des apps découplées.
- Pas de React. Pas de SPA.
- Interactivité ciblée via HTMX (navigation partielle, formulaires dynamiques) et Alpine.js (accordéons, dropdowns, toggles).
- Code maintenable, documenté, auditable.
- Autonomie de gestion côté ITEAG : tout contenu éditorial modifiable sans développeur.
- Aucune dépendance critique à un plugin payant ou propriétaire.
- Architecture propriétaire conforme au standard TUS.

10.3 Organisation applicative V1 (9 apps maximum)

| App Django | Responsabilité |
|-----------|---------------|
| `core` | Modèles partagés, utils, mixins, base templates, communication (email service) |
| `accounts` | Utilisateurs, profils, authentification, rôles, permissions |
| `website` | Pages Wagtail, actualités, événements, témoignages, FAQ, newsletter |
| `formations` | Parcours, disciplines, cours, catalogue de formations |
| `admissions` | Dossiers de candidature, workflow d'admission, formulaires publics |
| `academics` | Sessions, promotions, inscriptions, affectations, suivi ECTS, stages, VAE |
| `lms` | Ressources pédagogiques, devoirs, évaluations, notes, espace cours |
| `library` | Catalogue bibliothèque, notices, recherche |
| `documents` | Génération PDF (attestations, relevés, reçus), stockage documents admin |

Apps reportées en phases ultérieures :
- `billing` (paiement en ligne) → V2
- `partners` (portail partenaire FLTE) → V2+
- `analytics` (reporting avancé) → V2+

10.4 Architecture système

```
Client web/mobile (navigateur)
    │
    ▼
CDN (optionnel — assets statiques, images)
    │
    ▼
Reverse proxy (Nginx)
    │
    ├──► Application Django (Gunicorn)
    │       ├── Wagtail (éditorial)
    │       ├── HTMX endpoints
    │       └── API internes
    │
    ├──► PostgreSQL 16+
    │
    ├──► Redis (cache + sessions + broker)
    │
    ├──► Celery workers (emails, PDF, tâches différées)
    │
    └──► S3 (stockage fichiers, médias)
```

10.5 Dimensionnement proportionné

Réalité de l'ITEAG :
- < 200 étudiants actifs simultanés.
- Pic de concurrence : 50–100 utilisateurs max en semaine de session.
- Volume de données : ~2 635 notices biblio, ~50 cours, ~200 étudiants, ~7 enseignants.

Recommandation d'infrastructure :
- 1 serveur applicatif (VPS ou instance cloud) : 2 vCPU, 4 Go RAM.
- 1 instance PostgreSQL managée (ou sur le même serveur en V1).
- Redis sur le même serveur.
- S3 pour le stockage fichiers.
- Montée en charge possible par ajout d'instances Gunicorn / Celery workers si nécessaire.

Pas de Kubernetes, pas de microservices, pas de cluster multi-nœuds en V1. L'architecture reste simple et proportionnée au besoin réel.

======================================================================
11. CI/CD, ENVIRONNEMENTS ET DÉPLOIEMENT
======================================================================

11.1 Environnements

| Environnement | Usage | Accès |
|--------------|-------|-------|
| Local (dev) | Développement. Docker Compose (Django + PostgreSQL + Redis + MinIO). | Développeurs TUS |
| Staging | Pré-production. Données de test. Validation fonctionnelle par le secrétariat ITEAG. | TUS + ITEAG (secrétariat) |
| Production | Site en ligne (iteag.org). Données réelles. | Public + utilisateurs authentifiés |

11.2 Pipeline CI/CD

Dépôt Git : GitHub (github.com/beaudelaire1/iteag).

```
Push / PR → GitHub Actions
    │
    ├── Lint (Ruff)
    ├── Format check (Ruff format)
    ├── Tests unitaires (pytest)
    ├── Tests d'intégration
    ├── Vérification sécurité (pip-audit, bandit)
    ├── Vérification migrations Django
    ├── Build statique (collectstatic, Tailwind)
    │
    └── Déploiement staging (auto sur branche develop)
        └── Déploiement production (manuel après validation sur branche main)
```

11.3 Stratégie de branchement

- `main` : branche de production. Déploiement déclenché manuellement après validation staging.
- `develop` : branche d'intégration. Déploiement automatique vers staging.
- `feature/*` : branches de fonctionnalité. PR vers develop.
- `hotfix/*` : corrections critiques. PR vers main + rétro-merge vers develop.

11.4 Stratégie de déploiement

- Conteneurisation Docker pour la reproductibilité (Dockerfile + docker-compose).
- Déploiement VPS / instance cloud (recommandé : Scaleway, OVH, ou AWS Lightsail pour proximité géographique Antilles/Guyane).
- Nginx en reverse proxy.
- Gunicorn comme serveur WSGI.
- Supervisord ou systemd pour la gestion des processus (Gunicorn, Celery).
- TLS via Let's Encrypt (Certbot).

11.5 Sauvegarde et reprise

| Paramètre | Valeur cible |
|-----------|-------------|
| RPO (Recovery Point Objective) | 24 heures — perte de données maximale tolérée |
| RTO (Recovery Time Objective) | 4 heures — temps maximal de remise en service |
| Fréquence sauvegardes BDD | Quotidienne (pg_dump automatisé + rotation) |
| Rétention sauvegardes | 30 jours glissants |
| Stockage sauvegardes | Bucket S3 séparé, chiffré (AES-256) |
| Sauvegardes fichiers/médias | Réplication S3 cross-region ou backup quotidien |
| Test de restauration | Trimestriel (procédure documentée) |

11.6 Monitoring et alerting

- Monitoring applicatif : Sentry (erreurs Python/Django).
- Monitoring infrastructure : healthcheck endpoint Django + cron externe (UptimeRobot ou équivalent).
- Log management : logs structurés Django (JSON), rotation logrotate.
- Alerting : notification email/Slack sur erreur 5xx, indisponibilité, ou échec de tâche Celery.

======================================================================
12. EXIGENCES DE PERFORMANCE
======================================================================

12.1 Cibles techniques

| Métrique | Cible | Mesure |
|----------|-------|--------|
| LCP (Largest Contentful Paint) | < 2.5 secondes | PageSpeed Insights / Lighthouse |
| FID (First Input Delay) | < 100 ms | Lighthouse |
| CLS (Cumulative Layout Shift) | < 0.1 | Lighthouse |
| Score Lighthouse global | > 90 (performance, accessibilité, bonnes pratiques, SEO) | Pages publiques principales |
| Temps de réponse serveur (TTFB) | < 400 ms | Monitoring |
| Concurrence supportée | 100 utilisateurs simultanés sans dégradation | Test de charge |

12.2 Budget de performance par page

| Page | Poids max HTML+CSS+JS | Images max |
|------|----------------------|------------|
| Accueil | 200 Ko (gzippé) | 500 Ko (total, WebP, lazy-loaded) |
| Fiche formation | 150 Ko | 200 Ko |
| Tableau de bord étudiant | 200 Ko | 100 Ko |
| Catalogue bibliothèque | 150 Ko | 50 Ko |

12.3 Stratégie de cache

| Type de contenu | Durée de cache | Mécanisme |
|----------------|---------------|-----------|
| Assets statiques (CSS, JS, images) | 1 an (cache-busting via hash) | Nginx + headers HTTP |
| Pages publiques | 5 minutes | Redis cache middleware |
| Pages dynamiques authentifiées | Pas de cache HTTP, cache applicatif sélectif | Redis (fragments) |
| Requêtes BDD lourdes (catalogue biblio) | 15 minutes | Cache Django (low-level) |

12.4 Optimisation requêtes SQL

- N+1 : `select_related` / `prefetch_related` systématique sur les listes.
- Pagination obligatoire sur les listes longues (bibliothèque, étudiants, candidatures).
- Index sur les champs de recherche et de filtrage.

======================================================================
13. EXIGENCES DE SÉCURITÉ
======================================================================

13.1 Authentification

| Élément | Exigence |
|---------|----------|
| Mot de passe | 12 caractères minimum, complexité (majuscule, minuscule, chiffre, caractère spécial) |
| Brute-force | django-axes : verrouillage après 5 tentatives échouées, déblocage après 30 min |
| Sessions | Expiration après 30 min d'inactivité. Invalidation à la déconnexion. Cookie HttpOnly + Secure + SameSite=Lax. |
| 2FA | Obligatoire pour les comptes admin et secrétariat dès la V1 (via django-otp ou django-two-factor-auth) |
| Réinitialisation | Lien de réinitialisation par email, expirant après 1h, usage unique |

13.2 Autorisation et rôles

| Rôle | Accès |
|------|-------|
| Visiteur | Portail public uniquement |
| Candidat | Suivi de candidature (lien signé) |
| Étudiant | Portail étudiant + cours + ressources selon inscription |
| Enseignant | Portail enseignant + cours assignés uniquement |
| Secrétariat | Wagtail éditorial + admin métier (admissions, inscriptions, paiements) |
| Administrateur | Accès complet (technique + métier) |

Règles :
- Séparation stricte des rôles. Un étudiant ne peut pas accéder aux données d'un autre étudiant.
- Les permissions sont vérifiées côté serveur, jamais uniquement côté client.
- Les vues sensibles utilisent des mixins de permission Django (`LoginRequiredMixin`, `PermissionRequiredMixin`, ou décorateurs custom).

13.3 Protections applicatives

| Protection | Implémentation |
|-----------|---------------|
| XSS | Auto-escaping Django Templates (activé par défaut) |
| CSRF | Middleware CSRF Django (activé par défaut) |
| Injection SQL | ORM Django (requêtes paramétrées par défaut) |
| Clickjacking | X-Frame-Options: DENY |
| Sniffing de type | X-Content-Type-Options: nosniff |
| HSTS | Strict-Transport-Security: max-age=31536000; includeSubDomains |
| CSP | Content-Security-Policy restrictive (django-csp) |
| Rate limiting | django-ratelimit sur les formulaires publics (contact, candidature, login) |
| Upload de fichiers | Validation de type MIME, taille max (20 Mo devoirs, 50 Mo contenus enseignant), nom de fichier assaini |

13.4 Journalisation

- Journalisation de toutes les actions sensibles : connexion, déconnexion, changement de statut de candidature, création/modification d'utilisateur, modification de note, paiement enregistré.
- Logs structurés (JSON) avec : timestamp, utilisateur, action, objet, IP.
- Rétention des logs : 12 mois minimum.

13.5 Conformité RGPD

- Consentement cookies (bandeau conforme).
- Politique de confidentialité publiée.
- Droit d'accès, de rectification et de suppression des données personnelles.
- Durée de conservation des données définie (étudiants actifs : durée du cursus + 5 ans ; candidats refusés : 2 ans).
- Registre des traitements maintenu par l'ITEAG.

======================================================================
14. EXPÉRIENCE UTILISATEUR ET DESIGN
======================================================================

14.1 Principes directeurs

- Élégance épurée, conforme à l'identité visuelle de l'ITEAG.
- Clarté de navigation : 3 clics maximum pour atteindre l'information recherchée.
- Mobile-first : conception responsive prioritaire pour smartphone (persona étudiante sur mobile 90% du temps).
- Accessibilité : WCAG 2.2 niveau AA sur le portail public.
- Sobriété des animations : transitions CSS légères, pas d'animations gadget.
- Administration intuitive : l'interface Wagtail est le point d'entrée principal pour le secrétariat.

14.2 Design system

- Design system propriétaire basé sur Tailwind CSS 4.x.
- Composants réutilisables implémentés en Django Templates (partials/includes).
- Palette de couleurs : à définir en phase de cadrage (cohérence avec le logo ITEAG existant).
- Typographie : système à 2 fontes maximum (titraille + corps de texte).
- Grille responsive : 4/8/12 colonnes.
- Espacement cohérent : échelle basée sur la grille Tailwind (4px, 8px, 16px, 24px, 32px, 48px, 64px).
- Composants clés à livrer : boutons, formulaires, cartes, tableaux, badges, modales, alertes, navigation, breadcrumbs, pagination.

14.3 Accessibilité

- Navigation clavier complète.
- Contrastes des couleurs conformes (ratio 4.5:1 texte normal, 3:1 texte grand).
- Textes alternatifs sur toutes les images.
- Focus visible sur tous les éléments interactifs.
- Formulaires avec labels associés et messages d'erreur accessibles.
- Structure HTML sémantique (landmarks, headings hiérarchisés).
- Test d'accessibilité avec axe-core intégré aux tests automatisés.

======================================================================
15. SEO ET VISIBILITÉ
======================================================================

| Élément | Implémentation |
|---------|---------------|
| Balises meta | Administrables par page via Wagtail (title, description, og:image) |
| URLs | Propres, lisibles, slug administrable |
| Structure sémantique | HTML5 sémantique (article, section, nav, header, footer, main) |
| Sitemap XML | Généré automatiquement (django.contrib.sitemaps) |
| Robots.txt | Fichier statique configuré |
| Données structurées | JSON-LD : Organization, Course, Event, FAQPage, BreadcrumbList |
| Images | Format WebP, attribut alt, lazy loading, srcset responsive |
| Maillage interne | Liens contextuels entre pages de formation, professeurs, actualités |
| Redirections 301 | Mapping complet des anciennes URLs WordPress → nouvelles URLs |
| Fil d'Ariane | Breadcrumbs sur toutes les pages (balisé en JSON-LD) |
| Canonical | Balise canonical sur toutes les pages |
| Performance | LCP < 2.5s, CLS < 0.1 (facteurs SEO Google) |

======================================================================
16. STRATÉGIE DE MIGRATION DE CONTENU
======================================================================

16.1 Inventaire des contenus à migrer

| Type de contenu | Volume estimé | Source | Responsable migration | Méthode |
|----------------|--------------|--------|----------------------|---------|
| Pages institutionnelles | ~12 pages | iteag.org (HTML) | TUS | Saisie manuelle dans Wagtail (contenu restructuré) |
| Notices bibliothèque | 2 635+ fiches | Base existante (format à déterminer) | TUS | Script d'import CSV → modèle Notice |
| Images / visuels | ~50–100 images | S3 (s3.amazonaws.com/news.iteag.org/) | TUS | Migration vers nouveau bucket S3 |
| Actualités | ~20–30 articles | iteag.org | TUS + ITEAG | Saisie manuelle des plus récents dans Wagtail |
| Photos professeurs | 7 photos | iteag.org/static/img/professors/ | TUS | Copie dans le nouveau stockage |
| Témoignages | ~5 témoignages | iteag.org | TUS | Saisie dans Wagtail |

16.2 Données hors périmètre de migration automatique

- Vidéos de cours : actuellement distribuées sur demande. Pas de migration de masse. L'enseignant déposera les vidéos manuellement quand le module LMS sera prêt.
- Données étudiants existants : à saisir manuellement par le secrétariat ou via import CSV si un fichier structuré existe.

16.3 Validation

- Chaque page migrée doit être relue et validée par le secrétariat ITEAG avant mise en production.
- Le mapping de redirections 301 doit être testé exhaustivement en staging.

======================================================================
17. KPIs MÉTIER ET TECHNIQUES
======================================================================

17.1 KPIs métier

| KPI | Description | Cible V1 | Mesure |
|-----|------------|----------|--------|
| Taux de conversion visiteur → candidature | % de visiteurs uniques qui soumettent un dossier | > 3% | Analytics + compteur de dossiers soumis |
| Taux de complétion des dossiers | % de dossiers soumis vs abandonnés | > 70% | Tracking formulaire multi-étapes |
| Délai moyen de traitement des candidatures | Temps entre soumission et décision | < 10 jours ouvrés | Horodatage des changements de statut |
| Taux de remise des devoirs | % de devoirs remis vs attendus | > 80% | Module LMS |
| Satisfaction étudiante digitale | Perception de l'outil par les étudiants | Recueil qualitatif | Enquête post-session (phase ultérieure) |

17.2 KPIs techniques

| KPI | Cible | Mesure |
|-----|-------|--------|
| Score Lighthouse | > 90 sur les 4 axes | PageSpeed Insights |
| Disponibilité | 99,5% (proportionné à l'usage réel) | Monitoring uptime |
| Temps de réponse P95 | < 500 ms | Monitoring applicatif |
| Taux d'erreur 5xx | < 0,1% | Sentry + logs |
| Couverture de tests | > 80% sur le code métier critique | pytest-cov |

======================================================================
18. LIVRABLES ATTENDUS
======================================================================

18.1 Livrables techniques

| # | Livrable | Format |
|---|---------|--------|
| L01 | Code source complet | Dépôt Git privé (GitHub) |
| L02 | Documentation technique (architecture, modèle de données, API internes) | Markdown dans le dépôt |
| L03 | Documentation de déploiement (procédure complète, variables d'environnement, checklist) | Markdown dans le dépôt |
| L04 | Configuration Docker (Dockerfile, docker-compose dev + prod) | Dans le dépôt |
| L05 | Pipeline CI/CD (GitHub Actions) | Dans le dépôt |
| L06 | Scripts de sauvegarde et restauration | Dans le dépôt |
| L07 | Tests automatisés (unitaires + intégration, couverture > 80%) | Dans le dépôt |
| L08 | Mapping redirections 301 | Fichier CSV/Nginx conf |

18.2 Livrables utilisateur

| # | Livrable | Format |
|---|---------|--------|
| L09 | Guide d'administration Wagtail (publication de contenu) | PDF + vidéo courte |
| L10 | Guide d'utilisation étudiant | PDF |
| L11 | Guide d'utilisation enseignant | PDF |
| L12 | Session de formation secrétariat ITEAG (2h, en visio) | Visioconférence + enregistrement |

18.3 Engagements TUS

- Propriété intégrale du code source selon cadre contractuel.
- Aucune dépendance critique obligatoire à un plugin payant.
- Transparence sur l'architecture et les choix techniques.
- Solution évolutive et maintenable.
- Interlocuteur projet dédié : Beaudelaire VILME.
- Garantie corrective 30 jours post-mise en production.

======================================================================
19. PLANIFICATION ET PHASAGE
======================================================================

19.1 Phase 1 — Fondations et portail public

Objectif : mettre en ligne le nouveau site public institutionnel.

Livrables :
- Infrastructure déployée (staging + production).
- Design system défini et implémenté.
- Portail public complet (PUB-001 à PUB-015).
- CMS Wagtail opérationnel.
- Migration des contenus existants.
- SEO activé + redirections 301.
- CI/CD fonctionnelle.

Critère de passage à la Phase 2 :
- [ ] Portail public en production, validé par l'ITEAG.
- [ ] Score Lighthouse > 90 sur les pages principales.
- [ ] Redirections 301 testées et fonctionnelles.
- [ ] Secrétariat formé à Wagtail.

----------------------------------------------------------------------

19.2 Phase 2 — Admissions et espace étudiant

Objectif : digitaliser le parcours candidat → étudiant.

Livrables :
- Formulaire de candidature en ligne (PUB-011).
- Workflow d'admission complet (ADM-001).
- Gestion des inscriptions (ADM-002).
- Authentification sécurisée + 2FA admin (ETU-001).
- Tableau de bord étudiant (ETU-002).
- Suivi de progression ECTS (ETU-004).
- Suivi des paiements côté admin (ADM-003).
- Génération de documents PDF (ADM-009).

Critère de passage à la Phase 3 :
- [ ] Un candidat peut soumettre un dossier et suivre son statut en ligne.
- [ ] Le secrétariat gère les admissions et inscriptions depuis l'admin.
- [ ] Un étudiant inscrit accède à son tableau de bord et voit ses ECTS.
- [ ] Tests automatisés passent sur les workflows critiques.

----------------------------------------------------------------------

19.3 Phase 3 — Portail enseignant et LMS léger

Objectif : outiller les enseignants et enrichir l'expérience étudiante.

Livrables :
- Espace enseignant (ENS-001 à ENS-006).
- Accès cours et ressources pour étudiants (ETU-003).
- Remise de devoirs (ETU-005).
- Consultation des notes (ETU-006).
- Planning et notifications (ETU-007, ETU-008, ETU-009).
- Gestion académique (ADM-004).
- Catalogue bibliothèque (BIB-001 à BIB-004).

Critère de passage à la Phase 4 :
- [ ] Un enseignant peut déposer des supports, voir ses étudiants, et saisir des notes.
- [ ] Un étudiant peut accéder à ses cours, remettre un devoir, voir ses notes.
- [ ] La bibliothèque est consultable en ligne.

----------------------------------------------------------------------

19.4 Phase 4 — Consolidation et extensions

Objectif : enrichir et stabiliser l'écosystème.

Livrables possibles (à arbitrer) :
- Paiement en ligne (Stripe ou équivalent).
- Reporting avancé (ADM-007, ADM-010).
- Communication ciblée (ADM-006).
- Portail partenaire FLTE.
- Multi-langue (si demande confirmée).
- PWA.
- Optimisations de performance avancées.

======================================================================
20. CONTRAINTES ET PRÉREQUIS
======================================================================

20.1 Contraintes techniques

- Hébergement en France ou zone garantissant une latence acceptable depuis les Antilles et la Guyane (< 150 ms TTFB).
- Sauvegardes chiffrées avec procédure de restauration documentée et testée.
- Compatibilité navigateurs : Chrome, Firefox, Safari, Edge (2 dernières versions majeures).
- Responsive : smartphones (360px+), tablettes (768px+), desktop (1024px+).
- Gestion des médias : taille max upload, formats acceptés, nommage sécurisé.

20.2 Contraintes métier

- Maintien de la continuité de service : l'ancien site reste en ligne jusqu'à la bascule définitive.
- Conservation du référencement existant : redirections 301 obligatoires.
- Formation du secrétariat ITEAG avant la mise en production de chaque portail.
- Validation des workflows métier (admission, inscription) avec le secrétariat avant développement.
- Le modèle pédagogique ITEAG (section 2) est la contrainte structurante.

20.3 Prérequis ITEAG (à fournir par le maître d'ouvrage)

| # | Élément | Nécessaire pour | Priorité |
|---|---------|----------------|----------|
| P1 | Charte graphique / logo HD | Phase 1 | Must |
| P2 | Contenus textuels validés (pages institutionnelles) | Phase 1 | Must |
| P3 | Export du catalogue bibliothèque (CSV ou Excel) | Phase 3 | Should |
| P4 | Liste des étudiants actuels (si import souhaité) | Phase 2 | Could |
| P5 | Validation du workflow d'admission | Phase 2 | Must |
| P6 | Accès S3 actuel (images existantes) | Phase 1 | Must |
| P7 | Choix du prestataire d'hébergement | Phase 1 | Must |

======================================================================
21. POINTS DE VIGILANCE RÉSIDUELS
======================================================================

Les éléments suivants restent à confirmer ou arbitrer en cours de projet :

| # | Point | Impact | Décision attendue |
|---|-------|--------|-------------------|
| V1 | Stratégie vidéo (hébergement, CDN, transcodage) | Coût + infra | À arbitrer quand le volume vidéo sera connu. V1 = upload direct enseignant, stockage S3, lecture native HTML5. Pas de transcodage. |
| V2 | Solution de paiement en ligne | Phase 4 | Stripe recommandé (maturité, coût raisonnable). À confirmer par l'ITEAG. |
| V3 | Demande multi-langue réelle | Phase 4 | Non confirmée. À évaluer si un public anglophone significatif est identifié. |
| V4 | Format d'export du catalogue bibliothèque | Phase 3 | L'ITEAG doit fournir un export structuré (CSV minimum) pour le script d'import. |
| V5 | Validation des exigences FLTE pour le bachelor | Phase 2 | Le suivi des 30 ECTS FLTE externes repose sur une saisie manuelle ou un import CSV. Pas d'interconnexion système en V1. |
| V6 | Stratégie email (SMTP ou API) | Phase 1 | Recommandation : service API transactionnel (Brevo, Mailgun) pour la délivrabilité. Fallback SMTP si budget contraint. |

======================================================================
22. GLOSSAIRE MÉTIER ET TECHNIQUE
======================================================================

22.1 Termes métier ITEAG

| Terme | Définition |
|-------|-----------|
| Session | Semaine intensive de cours (4 par an : Carnaval, Pâques, Juillet, Toussaint) |
| Promotion | Groupe d'étudiants inscrits la même année, suivant le même cursus sur 6 ans |
| Parcours | Filière suivie par l'étudiant (diplômant ITEAG, bachelor FLTE, libre, Pro) |
| ECTS | European Credit Transfer System — unité de mesure des acquis (1 ECTS ≈ 25-30h de travail) |
| Cote | Code de classification d'un ouvrage dans la bibliothèque ITEAG |
| VAE | Validation des Acquis de l'Expérience — reconnaissance d'ECTS via expérience professionnelle/ministérielle |
| FLTE | Faculté Libre de Théologie Évangélique de Vaux-sur-Seine — partenaire pour le bachelor |
| ITEAG Pro | Formation continue destinée aux cadres d'église |
| Église fondatrice | Église membre fondatrice de l'ITEAG (tarif préférentiel) |
| Parcours libre | Parcours sans visée diplômante, sans obligation de validation |
| Discipline | Grande famille de matières (AT, NT, Théologie systématique, Histoire de l'Église, Théologie pratique) |

22.2 Termes techniques

| Terme | Définition |
|-------|-----------|
| LMS | Learning Management System — système de gestion de l'apprentissage |
| CMS | Content Management System — système de gestion de contenu (ici : Wagtail) |
| PWA | Progressive Web App — application web installable avec fonctions enrichies (notifications, offline) |
| 2FA | Authentification à deux facteurs |
| SEO | Search Engine Optimization — optimisation pour les moteurs de recherche |
| StreamField | Système de blocs de contenu flexible propre à Wagtail |
| HTMX | Librairie JS légère permettant des échanges serveur partiels sans framework SPA |
| Alpine.js | Micro-framework JS pour les interactions UI légères (toggles, dropdowns) |
| RPO | Recovery Point Objective — perte de données maximale tolérée |
| RTO | Recovery Time Objective — temps maximal de remise en service |
| TTFB | Time To First Byte — temps de réponse initial du serveur |
| LCP | Largest Contentful Paint — métrique de performance web |
| CLS | Cumulative Layout Shift — stabilité visuelle de la page |
| CI/CD | Continuous Integration / Continuous Deployment — intégration et déploiement continus |
| RGPD | Règlement Général sur la Protection des Données |
| WCAG | Web Content Accessibility Guidelines — normes d'accessibilité web |

======================================================================
23. SIGNATURES
======================================================================

Version approuvée : 2.0

Directeur ITEAG :
Nom : Alain Nisus
Signature :
Date :

Responsable Trait d'Union Studio :
Nom : Beaudelaire VILME
Signature :
Date :

======================================================================
FIN DU DOCUMENT
======================================================================
