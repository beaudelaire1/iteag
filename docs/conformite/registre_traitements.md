# ITEAG — Registre opérationnel des traitements de données personnelles

Version : 7 août 2026

Ce document sert de registre interne de référence pour la plateforme. Il ne remplace pas l'analyse juridique de cas particuliers. Il doit rester aligné avec le code, les contrats des prestataires et la politique publique `/protection-des-donnees/`.

## 1. Responsable du traitement et point de contact

Responsable : Institut de Théologie Évangélique des Antilles et de la Guyane (ITEAG)

Adresse : 201 lot Pointe d'Or, 97139 Les Abymes, Guadeloupe

Point de contact protection des données : secretariat@iteag.org — +590 690 37 64 17

Si un DPO est désigné ultérieurement, ses coordonnées remplacent ce point de contact dans la politique publique et dans les formulaires.

## 2. Principes retenus

- minimisation : ne collecter que ce qui sert à un usage identifié ;
- accès par rôle et besoin d'en connaître ;
- séparation des données métier, des données techniques et des sauvegardes ;
- durée de conservation définie pour chaque traitement ;
- effacement, anonymisation ou archivage intermédiaire à l'issue de la durée active ;
- traçabilité des opérations sensibles ;
- pas de réutilisation d'une donnée pour une finalité incompatible ;
- pas de vente de données personnelles ;
- révision du registre lors de l'ajout d'un nouveau prestataire ou d'une nouvelle fonctionnalité collectant des données.

## 3. Registre synthétique

| Traitement | Personnes concernées | Données principales | Finalité | Base principale | Destinataires internes | Conservation retenue | Source dans le projet |
|---|---|---|---|---|---|---|---|
| Navigation, authentification et sécurité | visiteurs et utilisateurs | IP, user-agent, session, événements de connexion, traces d'audit | sécuriser la plateforme, prévenir les abus, diagnostiquer les incidents | intérêt légitime | administration technique, personnes habilitées | journal d'audit : 12 mois ; prolongation ciblée uniquement si incident/contentieux | `apps/core/models.py`, `config/settings/*` |
| Contact | visiteurs | données saisies dans le formulaire, message, date | répondre et assurer le suivi | intérêt légitime ; mesures précontractuelles selon la demande | secrétariat | 12 mois après le dernier échange utile, sauf rattachement à un autre dossier | `apps/website/models.py` |
| Lettre d'information | abonnés | email, confirmation, désinscription | envoyer les informations demandées et prouver le consentement | consentement | secrétariat / communication | pendant l'abonnement ; après désinscription, conservation limitée aux éléments strictement nécessaires pour prouver le consentement ou respecter durablement la désinscription, pendant une durée proportionnée | `apps/core/models.py` |
| Candidature | candidats | identité, contact, date de naissance, parcours, motivation, église, pièces justificatives, décision, notes internes | instruire la candidature et préparer l'admission | mesures précontractuelles ; obligations applicables | direction, secrétariat | refus : 2 ans après décision ; acceptation : transfert des seules données encore nécessaires vers le dossier étudiant | `apps/admissions/models.py` |
| Compte utilisateur | étudiants, enseignants, personnel | identité, email, téléphone, adresse, photo, signature, rôle | fournir l'accès et gérer les habilitations | contrat / intérêt légitime | administration, secrétariat selon rôle | durée de la relation puis selon le dossier auquel le compte se rattache | `apps/accounts/models.py` |
| Scolarité | étudiants | numéro étudiant, parcours, promotion, statut, église, inscriptions, ECTS, stages, VAE | gérer la formation et le dossier académique | exécution de la relation de formation | direction, secrétariat, enseignants selon besoin | durée du cursus + 5 ans, sous réserve d'une obligation particulière | `apps/academics/models.py` |
| Assiduité, devoirs et évaluations | étudiants, enseignants | présences, copies, fichiers corrigés, notes, appréciations, révisions, échéances | enseignement, évaluation et suivi pédagogique | exécution de la relation de formation / intérêt légitime pédagogique | enseignant du cours, direction, secrétariat selon besoin | alignée sur le dossier académique : cursus + 5 ans | `apps/academics/*`, `apps/lms/models.py` |
| Bibliothèque | emprunteurs | identité via compte, ouvrage, dates, statut, remarques | gérer prêts, retours et réservations | exécution du service demandé / intérêt légitime | secrétariat / bibliothèque | durée du prêt puis historique utile au plus 2 ans, sauf litige ou dette non soldée | `apps/library/models.py` |
| Boutique et livraison | clients | identité, contact, adresse, commande, suivi, commentaire | exécuter la commande et la livraison | contrat | secrétariat, préparation, transporteur pour les données nécessaires | relation active puis pièces comptables 10 ans | `apps/commerce/models.py` |
| Paiement | payeurs | email, montant, référence, identifiants Stripe, statut, événements techniques | encaisser, rapprocher, rembourser, traiter un litige | contrat et obligations comptables | secrétariat, direction habilitée | référence comptable 10 ans ; charge utile technique Stripe à minimiser dès qu'elle n'est plus utile | `apps/paiements/models.py` |
| Témoignages étudiants | étudiants volontaires | nom, promotion, texte, photo éventuelle, consentement, statut | publier un témoignage choisi par l'étudiant | consentement | direction pour validation ; public après publication | publication jusqu'au retrait ; preuve du consentement et du retrait limitée à la durée nécessaire pour démontrer le respect de la demande | `apps/website/models_publications.py` / témoignages |
| Notifications internes | utilisateurs | destinataire, type, message, lien, lecture | informer l'utilisateur d'un événement métier | exécution du service / intérêt légitime | destinataire et personnels habilités | à purger avec le compte ou au plus tard selon le dossier métier lié | `apps/core/models.py` |
| Sauvegardes | toutes catégories présentes dans la base | copie chiffrée/logique de la base et fichiers concernés | continuité d'activité et reprise après incident | intérêt légitime / mêmes bases que les données originales | personnel technique strictement habilité | quotidiennes ~35 jours ; archives mensuelles ~400 jours | `.env.prod.example`, `docker-compose.prod.yml`, `scripts/postgres_backup_*` |

## 4. Données susceptibles de révéler des convictions religieuses

Le champ « église d'appartenance » et certaines informations librement fournies dans un dossier de candidature ou de formation peuvent révéler indirectement des convictions religieuses. Elles doivent être traitées comme des données sensibles :

- accès limité à la direction et au secrétariat lorsque l'information est utile ;
- pas d'affichage public par défaut ;
- pas de prospection ou de profilage à partir de cette information ;
- dans le cadre couvert par l'article 9(2)(d) du RGPD, traitement limité aux activités légitimes de l'ITEAG en tant qu'organisme sans but lucratif à finalité religieuse et aux relations visées par cette disposition ;
- pas de communication à l'extérieur de ce cadre sans consentement ou autre exception prévue par l'article 9 ;
- si une nouvelle finalité sort de ce cadre, définir avant traitement l'exception de l'article 9 applicable et la documenter.

## 5. Prestataires techniques à suivre

| Prestataire / service | Usage | Données possibles | Action de conformité avant production |
|---|---|---|---|
| OVHcloud | hébergement de l'infrastructure | données hébergées par l'application | conserver le contrat/DPA et la localisation choisie |
| Cloudflare R2 | médias et sauvegardes | fichiers, sauvegardes de base | conserver DPA, vérifier région/configuration et accès aux buckets |
| Cloudflare Turnstile | anti-abus sur formulaires | IP, navigateur, signaux techniques | documenter le service dans l'information des formulaires |
| Stripe | paiement carte | données de paiement et de transaction | conserver DPA ; ITEAG ne doit pas stocker les numéros complets de carte |
| Sentry | erreurs applicatives | traces techniques, URL, identifiants si mauvaise configuration | `send_default_pii=False` doit rester le défaut ; vérifier le projet/région et le DPA |
| Bunny.net | diffusion vidéo protégée | IP, requêtes de lecture, jetons | conserver DPA et vérifier la configuration de journalisation |
| Fournisseur de messagerie | emails transactionnels | adresses et contenu des emails | identifier le compte réellement utilisé et conserver le DPA/contrat pertinent |
| YouTube / Vimeo | vidéos publiques | données du visiteur lors d'une consultation/lecture | traiter ce point avec la politique cookies/traceurs et le mode d'intégration retenu |

Aucun nouveau prestataire manipulant des données personnelles ne doit être ajouté sans mise à jour de ce tableau et vérification de ses conditions de sous-traitance et de transfert.

## 6. Cycle de vie et effacement

La politique distingue trois états :

1. **Base active** : données nécessaires au service courant.
2. **Archivage intermédiaire** : données conservées uniquement pour une obligation légale, un litige ou une preuve, avec accès réduit.
3. **Suppression/anonymisation** : disparition de la base active ; les sauvegardes expirent selon leur rotation normale et ne servent pas à réintroduire une donnée supprimée pour un usage courant.

L'effacement d'un enregistrement contenant des fichiers doit également supprimer ou rendre inaccessibles les fichiers correspondants dans le stockage objet. Une simple suppression de la ligne PostgreSQL ne suffit pas si le fichier reste dans R2.

## 7. Contrôles à terminer avant mise en production

Priorité haute :

- mettre en place une purge périodique du `JournalAudit` au-delà de 12 mois, avec exception documentée en cas d'incident ;
- définir puis automatiser la purge des candidatures refusées au-delà de 2 ans, y compris leurs fichiers dans R2 ;
- supprimer ou réduire la `charge_utile` des événements Stripe une fois la période technique utile écoulée, tout en conservant les références comptables nécessaires ;
- définir la purge des soumissions du formulaire de contact au-delà de 12 mois ;
- définir le traitement des comptes étudiants arrivés à `promotion.annee_fin + 5 ans` sans supprimer les pièces comptables encore soumises à une obligation de 10 ans ;
- vérifier les DPA, régions de traitement et mécanismes de transfert de chaque prestataire réellement activé en production ;
- ajouter la politique distincte relative aux cookies et autres traceurs avant activation d'outils non strictement nécessaires soumis au consentement.

Priorité moyenne :

- documenter une procédure de réponse aux demandes d'accès, rectification, effacement, limitation et opposition ;
- tenir un historique des versions de la politique publique ;
- vérifier chaque année que les champs des formulaires correspondent encore à une finalité documentée.

## 8. Références de cadrage

Le cahier des charges du projet impose déjà : politique de confidentialité publiée, droits d'accès/rectification/suppression, registre des traitements, candidats refusés conservés 2 ans, dossiers étudiants pendant le cursus + 5 ans et journaux de sécurité pendant 12 mois.

Références externes à contrôler lors des révisions :

- RGPD, articles 5, 6, 9, 12 à 22, 28, 32 et chapitre V ;
- CNIL — informer les personnes ;
- CNIL — durées de conservation ;
- CNIL — paiement à distance par carte bancaire ;
- Code de commerce, obligations de conservation des pièces comptables.
