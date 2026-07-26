# ADR-001 — Stratégie de diffusion vidéo sécurisée

- **Statut** : **Remplacé par [ADR-005](ADR-005-fournisseurs-video-externes.md)** le 2026-07-26
- **Contexte CDC** : §2.1 (distanciel Martinique/Guyane), V1 « stratégie vidéo à arbitrer »
- **Décideur** : direction technique Trait d'Union Studio

> **Ce qui a changé.** La maîtrise d'ouvrage a demandé de ne pas héberger les
> fichiers. L'examen a par ailleurs montré une lacune de la présente décision :
> un MP4 servi depuis S3 se lit à débit constant, sans adaptation à la bande
> passante réelle — le risque R4 (débit en Guyane et en Martinique) restait
> donc entier. L'ADR-005 retient un fournisseur externe à adresse signée.
>
> **Ce qui reste valable** et n'est pas remis en cause : la revérification du
> droit à chaque demande de lecture, l'adresse à durée de vie courte, l'absence
> de toute adresse de fichier dans le HTML, et l'abstraction de diffusion — qui
> a précisément permis ce changement sans toucher aux vues ni aux gabarits. Le
> backend S3 décrit ici est conservé et testé comme chemin de retour.

## Contexte

L'ITEAG distribue aujourd'hui ses vidéos de cours *sur demande au secrétariat*. La
plateforme doit industrialiser cette distribution : l'étudiant à distance (Martinique,
Guyane) doit pouvoir suivre les modules en vidéo, et ce contenu constitue la valeur
commerciale de l'institut — il ne doit pas fuiter.

Le CDC v2 arbitre pour la V1 : « upload direct enseignant, stockage S3, lecture native
HTML5, pas de transcodage ». Cet arbitrage reste valable sur le plan du coût, mais il
est muet sur la **protection du contenu**, qui est désormais une exigence explicite.

## Options examinées

| Option | Coût | Protection | Complexité | Verdict |
|--------|------|-----------|-----------|---------|
| A — Fichiers publics sur S3/CDN | € | Nulle (URL partageable indéfiniment) | Faible | ❌ Rejetée |
| B — Fichiers servis par Django (`FileResponse`) | € | Bonne | Faible | ❌ Sature les workers Gunicorn |
| C — **S3 privé + URL présignée courte** | € | Bonne | Moyenne | ✅ **Retenue** |
| D — HLS chiffré (AES-128) + transcodage | €€€ | Très bonne | Élevée | ⏭ Reportée V2 |
| E — Prestataire tiers (Vimeo OTT, Mux) | €€€ | Très bonne | Faible | ❌ Contraire à l'objectif de souveraineté (O4) |

## Décision

**Option C** : les vidéos sont stockées dans un bucket S3 **strictement privé**
(aucune ACL publique, aucun accès anonyme). La lecture passe par une **URL présignée
d'une durée de vie de 300 secondes**, générée à la demande par un endpoint Django après
vérification du droit d'accès.

Points de conception non négociables :

1. **Aucune URL de fichier n'est présente dans le HTML servi.** Le lecteur la demande
   par un appel authentifié séparé (`POST /formations-video/lecon/<uuid>/playback/`).
2. **Le droit est revérifié à chaque demande de lecture**, jamais seulement au
   chargement de la page. Une révocation prend effet immédiatement.
3. **La clé de stockage est un UUID**, pas le nom de fichier d'origine : aucune
   information métier n'est déductible d'une URL interceptée.
4. **Chaque octroi est journalisé** (`JournalAccesVideo`) avec IP et empreinte du
   user-agent — ce journal est la base de la détection de partage de compte.
5. **Un quota de flux simultanés par utilisateur** est appliqué via Redis.

L'accès au stockage est encapsulé derrière une interface :

```python
class BackendStockageVideo(Protocol):
    def url_lecture(self, cle: str, ttl: int) -> str: ...
    def televerser(self, fichier, cle: str) -> None: ...
```

Deux implémentations : `S3StockageVideo` (production) et `LocalStockageVideo`
(développement et tests, avec URL signée par `django.core.signing`). Ce point est ce qui
rend le passage ultérieur à HLS ou à un CDN signé **non intrusif**.

## Conséquences

**Positives**
- Le contenu n'est pas aspirable par simple partage de lien.
- Le trafic vidéo ne traverse pas Django : les workers restent disponibles.
- Coût d'infrastructure inchangé par rapport à l'arbitrage V1 du CDC.
- La bascule vers HLS chiffré (V2) ne touche que le backend de stockage et le lecteur.

**Négatives / limites assumées**
- Un utilisateur légitime peut techniquement enregistrer son écran. Aucune solution
  sans DRM matériel ne l'empêche ; le DRM est hors de proportion pour cet institut.
- Une URL présignée reste valable 5 minutes si elle est interceptée. Fenêtre acceptée,
  mesurée contre le confort de lecture (reprise après pause).
- Pas d'adaptation automatique du débit en V1 : les vidéos doivent être téléversées
  dans une définition raisonnable (recommandation : 720p, H.264, ≤ 2 Go).

## Suivi

Rouvrir cette décision si l'un de ces seuils est franchi :
- volume de contenu vidéo > 200 heures ;
- constat de fuite de contenu attestée ;
- plaintes récurrentes de qualité de lecture depuis la Guyane.
