# ADR-002 — Modèle de contrôle d'accès aux modules

- **Statut** : Accepté
- **Contexte CDC** : ADM-005 (rôles), BIB-003 (accès conditionnel), §13 (sécurité)

## Contexte

La plateforme doit répondre à quatre questions différentes, souvent confondues :

1. *Qui es-tu ?* → authentification
2. *Quel est ton rôle ?* → RBAC
3. *As-tu le droit d'accéder à **ce** module ?* → droit métier (*entitlement*)
4. *Peux-tu lire **ce fichier** maintenant ?* → accès à la ressource

Le code existant ne traite que (1) et (2), via `RoleRequiredMixin`. Le rôle
« étudiant » ne dit rien du fait qu'un étudiant donné a payé, est à jour, ou a le droit
de suivre tel module. Confondre les deux mènerait à des contrôles dispersés et
incohérents dans les vues.

## Décision

### 1. Séparer le rôle du droit

Le **rôle** reste porté par `User.role` et vérifié par les mixins existants.
Le **droit** est porté par un objet dédié, `InscriptionModule`, qui matérialise :
bénéficiaire, module, source de l'octroi, fenêtre de validité, statut.

Un droit est une **donnée**, pas une règle codée en dur : le secrétariat peut donc
octroyer, suspendre, prolonger ou révoquer sans intervention de développeur.

### 2. Un point de contrôle unique

Toute la logique d'autorisation métier vit dans une fonction unique :

```python
# apps/elearning/services/acces.py

@dataclass(frozen=True)
class DecisionAcces:
    autorise: bool
    motif: ResultatAcces
    inscription: InscriptionModule | None = None

def verifier_acces(user, lecon) -> DecisionAcces: ...
```

Règle d'équipe : **aucune vue, aucun template, aucune tâche ne réimplémente cette
logique**. Un test d'architecture vérifie qu'aucun module hors `services/acces.py`
n'interroge directement `InscriptionModule.statut`.

### 3. Table de vérité explicite

La décision se calcule dans cet ordre, premier refus gagnant :

| # | Condition évaluée | Refus retourné si fausse |
|---|------------------|--------------------------|
| 1 | La leçon appartient à un module `PUBLIE` | `REFUSE_DROIT` |
| 2 | Si `apercu_gratuit` → **autorisé immédiatement** | — |
| 3 | Si politique `PUBLIC` → **autorisé** | — |
| 4 | L'utilisateur est authentifié | `REFUSE_DROIT` |
| 5 | Staff, admin, ou enseignant responsable → **autorisé** | — |
| 6 | Le profil étudiant existe | `REFUSE_DROIT` |
| 7 | Une `InscriptionModule` existe pour ce module | `REFUSE_DROIT` |
| 8 | Son statut est `ACTIF` (ou `TERMINE` si révision autorisée) | `REFUSE_EXPIRE` |
| 9 | La date du jour est dans la fenêtre d'accès | `REFUSE_EXPIRE` |
| 10 | Les modules prérequis sont complétés | `REFUSE_PREREQUIS` |
| 11 | Le quota de flux simultanés n'est pas dépassé | `REFUSE_QUOTA` |

Cette table **est** la spécification de test : un cas de test par ligne, plus les cas
combinés. C'est ce qui permet d'affirmer que le contrôle d'accès est couvert.

### 4. Propagation des états

Un changement de statut de l'étudiant se propage à ses droits :

- `ProfilEtudiant` → `SUSPENDU` ⇒ toutes ses `InscriptionModule` passent `SUSPENDU`
- `ProfilEtudiant` → `ACTIF` ⇒ les inscriptions suspendues *de ce fait* repassent `ACTIF`
- Candidature `ACCEPTE` ⇒ octroi automatique des modules obligatoires du parcours

La propagation est implémentée dans la couche service, jamais dans un signal implicite
difficile à tracer, **sauf** pour la journalisation d'audit qui reste un signal.

## Conséquences

**Positives**
- Le secrétariat devient autonome sur la gestion des accès.
- Le contrôle d'accès est testable de façon exhaustive et démontrable en recette.
- Les motifs de refus sont typés : l'interface peut afficher un message utile
  (« votre accès a expiré » ≠ « module non disponible »).

**Négatives**
- Une table supplémentaire à alimenter à chaque inscription : la génération automatique
  à l'admission est donc obligatoire, sans quoi le secrétariat croulera sous la saisie.
- Le calcul de `verifier_acces()` touche plusieurs tables : mise en cache Redis par
  couple (utilisateur, module) avec invalidation sur écriture de `InscriptionModule`.
