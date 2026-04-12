# RAPPORT D'AUDIT — Cahier des Charges v1.1 — Refonte ITEAG
# Réalisé par : Trait d'Union Studio — Direction Technique
# Date : 12 avril 2026
# Méthode : atlas-prime / audit-report

---

## 1. Lecture stratégique

- **Objet** : audit complet du CDC v1.1 fusionné avant lancement du développement Django.
- **Périmètre** : 17 sections, ~560 lignes, 40 fonctionnalités codifiées (PUB/ETU/ENS/ADM), modèle de données, stack technique, phasage.
- **Niveau de risque global** : ÉLEVÉ — le document est riche en intention mais insuffisamment exécutable en l'état pour lancer un développement conforme au standard TUS.
- **Point de vigilance dominant** : le CDC traite l'ITEAG comme une institution académique générique alors que son modèle pédagogique est très spécifique (4 sessions intensives d'une semaine par an, sur 6 ans, avec ECTS, double filière diplôme/bachelor FLTE, VAE, stages). Cette spécificité doit structurer toute l'architecture.

---

## 2. Contexte observé (site ITEAG actuel audité)

### Données terrain extraites de iteag.org

| Élément | Réalité observée |
|---------|-----------------|
| Type d'institution | Association loi 1905 — théologie évangélique |
| Localisation | Guadeloupe (201 lot Pointe d'Or, 97139 Les Abymes) |
| Rayonnement | Guadeloupe, Martinique, Guyane (distanciel) |
| Modèle pédagogique | 4 sessions intensives d'une semaine / an × 6 ans |
| Calendrier sessions | Carnaval, Pâques, Juillet, Toussaint |
| Diplômes | Diplôme ITEAG (180 ECTS, sans prérequis d'entrée) + Bachelor FLTE (180 ECTS, bac requis) |
| ECTS par cours | 2,5 ECTS / cours validé |
| Stages | 30 ECTS obligatoires (ou dissertation 15 ECTS en remplacement) |
| VAE | Mentionnée sur le site, absente du CDC |
| Parcours libre | Sans validation, sans visée diplômante |
| Parcours ITEAG Pro | Formation continue pour cadres d'église |
| Tarification | 200–300 €/session selon statut (église fondatrice ou non) et formule (toutes sessions ou à la carte) |
| Professeurs identifiés | 7 (Labeth, Nisus, Reivax, Eugène, Guillet, Girondin, Kaulanjan) |
| Bibliothèque | > 2 635 ouvrages catalogués (titre, auteur, publication, mots-clés, cote) |
| Contenus vidéo | Existants, distribués sur demande au secrétariat |
| Stockage actuel | Images/news sur S3 (s3.amazonaws.com/news.iteag.org/) |
| Pages identifiées | accueil, présentation, professeurs, formations, diplôme, ITEAG Pro, inscription, contact, actualités, bibliothèque |
| Réseaux | Facebook, YouTube |
| Partenariat externe | FLTE Vaux-sur-Seine (30 ECTS complémentaires pour bachelor) |

### Échelle réelle estimée
- Étudiants actifs simultanés : probablement < 200
- Utilisateurs concurrents en pic (semaine de session) : 50–100 max
- Volume de contenu à migrer : ~12 pages + 2 635 notices bibliothèque + images S3 + actualités

---

## 3. Points forts réels du CDC v1

1. **Vision multi-portails cohérente** — la distinction public/étudiant/enseignant/admin est saine et alignée aux besoins réels.
2. **Stack technique solide** — Django 5 / Wagtail / HTMX / Alpine.js / Tailwind / PostgreSQL / Redis / Celery est une combinaison éprouvée, conforme au standard TUS, sans lourdeur inutile.
3. **Philosophie anti-gadget** — le refus explicite de React, des plugins payants et du SPA inutile protège la maintenabilité à long terme.
4. **Codification fonctionnelle** — les 40 identifiants (PUB-001 à ADM-010) permettent une traçabilité, même si les critères d'acceptation manquent.
5. **Points de vigilance documentés** — la section 14 identifie les bonnes questions (LMS, forum, multi-site, Elasticsearch, paiement, vidéo, langues, PWA).
6. **Modèle de données esquissé** — les 16 entités principales et leurs relations donnent un socle exploitable.
7. **Livrables contractuels détaillés** — les livrables techniques et utilisateur sont correctement listés (section 11).
8. **Accessibilité WCAG 2.2 AA** mentionnée comme cible.

---

## 4. Problèmes identifiés

### 4.1 CRITIQUES (bloquent le lancement d'un développement de qualité)

**C1 — Aucune persona utilisateur définie**
- Impact : impossible de prioriser les fonctionnalités ni de concevoir l'UX correctement.
- Cause : le CDC liste des portails sans définir qui les utilise, dans quel contexte, avec quelle compétence numérique, sur quel appareil.
- Correction : définir au minimum 5 personas (visiteur, candidat, étudiant actif, enseignant, secrétariat/admin) avec leur contexte réel.

**C2 — Aucun critère d'acceptation sur les 40 fonctionnalités**
- Impact : chaque fonctionnalité est interprétable différemment par le développeur, le client et le testeur. Risque de rejet à la réception.
- Cause : les identifiants PUB-001 à ADM-010 sont des libellés, pas des spécifications.
- Correction : chaque fonctionnalité doit avoir au minimum un scénario « Given/When/Then » ou un critère mesurable.

**C3 — Modèle pédagogique spécifique ITEAG non pris en compte**
- Impact : le LMS sera générique au lieu d'être adapté (sessions intensives hebdomadaires, système ECTS 2,5/cours, stages 30 ECTS, VAE, double filière, parcours libre sans validation).
- Cause : le CDC mentionne « LMS » de manière abstraite sans intégrer le fonctionnement réel.
- Correction : documenter le modèle pédagogique réel comme contrainte structurante de la section LMS et du modèle de données.

**C4 — Aucun workflow d'admission/inscription formalisé**
- Impact : ADM-001 et ADM-002 sont impossibles à développer sans états, transitions, et règles de validation.
- Cause : le CDC mentionne « un dossier de candidature suit un workflow précis » mais ne définit jamais ce workflow.
- Correction : modéliser les machines à états (candidature : soumis → en examen → accepté/refusé/en attente → inscrit ; inscription : pré-inscrit → paiement validé → inscrit → actif).

**C5 — Aucune priorisation intra-portail**
- Impact : l'équipe ne sait pas ce qui est MVP et ce qui est extension.
- Cause : les 40 fonctionnalités sont listées sans priorité (MoSCoW ou équivalent).
- Correction : classer chaque fonctionnalité en Must/Should/Could/Won't pour la V1.

**C6 — Pas de périmètre « hors scope » explicite**
- Impact : scope creep garanti. Le client et l'équipe liront des choses différentes dans les mêmes mots.
- Cause : le CDC mentionne des éléments « optionnels » ou « phase ultérieure » mais ne dit jamais clairement ce qui est EXCLU.
- Correction : ajouter une section « Hors périmètre V1 » avec liste explicite.

### 4.2 IMPORTANTS (dégradent la qualité de livraison s'ils ne sont pas traités)

**I1 — Modèle de données trop simplifié**
- Pas de cardinalités, pas de contraintes, pas d'états, pas de système ECTS modélisé.
- Les entités « Promotion », « Session », « Semestre / période » ne sont pas distinguées alors que le fonctionnement ITEAG est session-based.
- ECTS (crédits par cours, cumul par étudiant, seuils de validation) absents.
- VAE non modélisée.

**I2 — Double interface admin non traitée**
- Wagtail a sa propre interface d'administration. Django a la sienne. Le CDC demande les deux sans aborder leur coexistence.
- Risque : confusion UX pour l'équipe ITEAG qui devra naviguer entre deux back-offices.

**I3 — Partenariat FLTE non modélisé**
- Le bachelor FLTE nécessite 30 ECTS de la FLTE en plus des 150 de l'ITEAG.
- Comment la plateforme suit-elle des crédits obtenus dans une autre institution ?

**I4 — Aucune stratégie vidéo concrète**
- Video.js est listé mais : où sont stockées les vidéos ? Quel CDN ? Quel format ? Quel transcodage ? Quel coût ? L'ITEAG distribue déjà des vidéos sur demande.

**I5 — Pas de sizing infrastructure proportionné**
- Le CDC mentionne « centaines d'utilisateurs concurrents » et « 99,9% de disponibilité ».
- Réalité : < 200 étudiants actifs, pic à 50-100 concurrents en semaine de session.
- Le sizing doit être proportionné pour éviter un surcoût d'infrastructure inutile.

**I6 — Aucun KPI métier défini**
- Seuls des KPIs techniques (Lighthouse, LCP, disponibilité). Aucun indicateur business : taux de conversion visiteur→candidature, taux de complétion des dossiers, taux de remise des devoirs, etc.

**I7 — Stratégie de migration de contenu non inventoriée**
- ~12 pages, 2 635 notices bibliothèque, images S3, actualités.
- Le CDC dit « migration contenus prioritaires » sans inventaire ni responsable.

**I8 — Aucun RPO/RTO défini**
- « Sauvegardes régulières » ne veut rien dire sans : fréquence, rétention, objectif de point de reprise (RPO), objectif de temps de reprise (RTO).
- Pour une institution de cette taille : RPO 24h, RTO 4h serait raisonnable. Le dire.

**I9 — CI/CD absente du CDC**
- Aucune mention de pipeline, de stratégie de branchement, de déploiement automatisé, d'environnements (dev/staging/prod).

**I10 — Phases sans dépendances ni livrables intermédiaires**
- Les 4 phases listent des sujets mais ne disent pas ce qui doit être livré et validé à la fin de chaque phase comme critère de passage à la suivante.

### 4.3 MINEURS (améliorations recommandées)

**M1** — Le glossaire ne couvre pas les termes métier ITEAG (parcours, session, promotion, ECTS, cote bibliothécaire, VAE).
**M2** — ProseMirror via Wagtail est un détail d'implémentation, pas un choix stratégique ; il n'a pas sa place au même niveau que Django/PostgreSQL.
**M3** — La section « Signatures » est pertinente mais devrait inclure un champ « version approuvée ».
**M4** — Aucune mention de la stratégie email (transactionnel vs marketing, SMTP vs API, délivrabilité, templates).
**M5** — « MinIO ou stockage objet compatible S3 » — en production réelle, si l'hébergement est cloud, S3 natif sera plus simple que MinIO auto-hébergé. La décision doit être liée au choix d'hébergement.

---

## 5. Analyse transversale

### Sécurité
- Bonne couverture des fondamentaux (RBAC, TLS, CSRF/XSS, journalisation).
- Manque : politique de mots de passe explicite, gestion des sessions (durée, invalidation), rate limiting sur les formulaires publics (candidature, contact), headers de sécurité (CSP, HSTS, X-Frame-Options).
- La 2FA est en « optionnel » mais devrait être obligatoire pour les admins dès la V1 (standard TUS : sécurité renforcée pour administration).

### Performance
- Cibles correctes (Lighthouse > 90, LCP < 2.5s).
- Manque : budget de performance par page (poids max JS, CSS, images), stratégie de cache précise (durée par type de contenu), optimisation des requêtes N+1 sur les listes (formations, bibliothèque 2 635 entrées).

### Maintenabilité
- L'approche Modular Monolith est saine pour cette taille.
- Mais 13 apps Django en V1 est ambitieux. Recommandation : fusionner `news_events` dans `website`, `communication` dans `core`, et reporter `partners` + `analytics` en phase ultérieure. Cible V1 : 9 apps max.

### Accessibilité / UX
- WCAG 2.2 AA mentionné mais aucun plan de test d'accessibilité.
- Le design system est mentionné sans scope concret (combien de composants ? quel outil de documentation ? Storybook ? Figma ?).
- L'administration Wagtail impose ses propres patterns UX — le CDC ne dit pas si l'admin ITEAG travaillera principalement dans Wagtail ou dans un dashboard Django custom.

### Delivery / Ops
- Absence totale de CI/CD, environnements, monitoring, log management, alerting.
- Pas de stratégie de déploiement (Docker ? PaaS ? VPS ? managed services ?).

---

## 6. Priorisation recommandée pour le CDC v2

### Avant toute ligne de code (phase de cadrage)
1. Définir les personas et parcours critiques.
2. Formaliser les workflows métier (admission, inscription, validation, évaluation).
3. Prioriser toutes les fonctionnalités (MoSCoW V1).
4. Modéliser le schéma de données avec ECTS, sessions, statuts.
5. Définir le périmètre hors scope V1 de manière explicite.

### Au lancement technique
6. Réduire le nombre d'apps V1 à 9 maximum.
7. Choisir la stratégie d'hébergement et dimensionner proportionnellement.
8. Définir la pipeline CI/CD et la stratégie d'environnements.
9. Spécifier le RPO/RTO.
10. Inventorier les contenus à migrer avec responsable et calendrier.

### En continu pendant le développement
11. Ajouter des critères d'acceptation à chaque fonctionnalité avant développement.
12. Valider chaque phase avec des livrables intermédiaires et des critères de passage.

---

## 7. Livraison de cet audit

- **Résumé exécutable** : le CDC v1 est un bon document d'intention stratégique mais n'est PAS un document exécutable en l'état. Il doit être enrichi sur 11 points critiques/importants avant de servir de référence de développement.
- **Risques résiduels** :
  - Si le développement démarre sur la base v1 sans corrections : débordements de périmètre, rejet à la réception, dette technique précoce.
  - Les workflows métier non formalisés sont le risque n°1 de décalage client/livrable.
- **Étape suivante** : produire le CDC v2 corrigé intégrant toutes les corrections identifiées, puis valider avec le client avant lancement.

---

## NOTATION PAR DOMAINE — CDC v1 (avant correction)

| Domaine | Note /100 | Verdict |
|---------|-----------|---------|
| Vision et positionnement | 85 | Solide, bien articulé |
| Périmètre fonctionnel | 55 | Riche mais non priorisé, pas de critères d'acceptation |
| Architecture technique | 80 | Saine, bien justifiée, quelques lacunes ops |
| Modèle de données | 40 | Trop simplifié, ne reflète pas le métier réel |
| Sécurité | 70 | Fondamentaux couverts, détails manquants |
| Performance | 65 | Cibles correctes, moyens non spécifiés |
| UX/UI | 45 | Principes sans substance opérationnelle |
| SEO | 75 | Bien couvert |
| Exploitation / Ops | 30 | Quasi absente |
| Tests / Qualité | 35 | Mention sans stratégie réelle |
| Migration | 50 | Principe correct, exécution non planifiée |
| Documentation | 70 | Liste de livrables complète |
| **Moyenne pondérée** | **58** | **Non prêt pour lancement** |

Seuil TUS pour lancement : **85/100 minimum**.
Écart à combler : **27 points**.
