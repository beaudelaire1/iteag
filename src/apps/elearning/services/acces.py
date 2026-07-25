"""
Autorité unique du système sur l'accès à un contenu pédagogique — ADR-002.

Aucune vue, aucun gabarit, aucune tâche ne réimplémente cette logique. La
décision se calcule dans un ordre fixe, premier refus gagnant, et cette table
d'ordre **est** la spécification de test : une ligne, un cas.
"""

from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.elearning.models import InscriptionModule, JournalAccesVideo, Lecon, ModuleFormation

# Messages destinés à l'étudiant : un refus utile explique quoi faire.
MESSAGES = {
    JournalAccesVideo.Resultat.REFUSE_DROIT: (
        "Ce contenu n'est pas accessible avec votre compte. "
        "Contactez le secrétariat si vous pensez qu'il s'agit d'une erreur."
    ),
    JournalAccesVideo.Resultat.REFUSE_EXPIRE: (
        "Votre accès à ce module est arrivé à échéance ou a été suspendu. Le secrétariat peut le prolonger."
    ),
    JournalAccesVideo.Resultat.REFUSE_PREREQUIS: (
        "Ce module demande d'avoir terminé un ou plusieurs modules préalables."
    ),
    JournalAccesVideo.Resultat.REFUSE_QUOTA: (
        "Une lecture est déjà en cours sur un autre appareil. Fermez-la avant d'en démarrer une nouvelle."
    ),
}


@dataclass(frozen=True)
class DecisionAcces:
    autorise: bool
    motif: str = ""
    inscription: InscriptionModule | None = None

    @property
    def message(self) -> str:
        return MESSAGES.get(self.motif, "")


_AUTORISE = DecisionAcces(autorise=True)


def _refus(motif) -> DecisionAcces:
    return DecisionAcces(autorise=False, motif=motif)


def verifier_acces(
    utilisateur,
    lecon: Lecon,
    *,
    verifier_quota: bool = False,
    identifiant_flux: str = "",
) -> DecisionAcces:
    """Décide si `utilisateur` peut consulter `lecon`.

    `verifier_quota` n'est activé qu'au moment de délivrer une adresse de
    lecture : afficher une page ne consomme pas de flux.
    """
    R = JournalAccesVideo.Resultat
    module = lecon.chapitre.module

    # 1 — La leçon appartient à un module publié.
    if not module.est_publie:
        if not _est_gestionnaire(utilisateur, module):
            return _refus(R.REFUSE_DROIT)

    # 2 — Une leçon d'aperçu est ouverte à tous : c'est sa raison d'être.
    if lecon.apercu_gratuit:
        return _AUTORISE

    # 3 — Politique publique.
    if module.politique_acces == ModuleFormation.PolitiqueAcces.PUBLIC:
        return _AUTORISE

    # 4 — Au-delà, il faut être connecté.
    if utilisateur is None or not getattr(utilisateur, "is_authenticated", False):
        return _refus(R.REFUSE_DROIT)

    # 5 — Personnel, administration et enseignant responsable du module.
    if _est_gestionnaire(utilisateur, module):
        return _AUTORISE

    # 6 — Politique « tout compte connecté ».
    if module.politique_acces == ModuleFormation.PolitiqueAcces.AUTHENTIFIE:
        return _AUTORISE

    # 7 — Un profil étudiant est nécessaire pour porter un droit.
    profil = getattr(utilisateur, "profil_etudiant", None)
    if profil is None:
        return _refus(R.REFUSE_DROIT)

    # 8 — Un droit doit exister sur ce module.
    inscription = InscriptionModule.objects.filter(etudiant=profil, module=module).first()
    if inscription is None:
        return _refus(R.REFUSE_DROIT)

    # 9 — Le droit doit être exerçable : statut et fenêtre de validité.
    if not inscription.est_active():
        return _refus(R.REFUSE_EXPIRE)

    # 10 — Les modules prérequis doivent être terminés.
    if not prerequis_satisfaits(profil, module):
        return _refus(R.REFUSE_PREREQUIS)

    # 11 — Quota de lectures simultanées, au moment de délivrer l'adresse.
    if verifier_quota and not _quota_disponible(utilisateur, identifiant_flux):
        return _refus(R.REFUSE_QUOTA)

    return DecisionAcces(autorise=True, inscription=inscription)


def _est_gestionnaire(utilisateur, module: ModuleFormation) -> bool:
    """Personnel, administration, ou enseignant responsable de ce module."""
    if utilisateur is None or not getattr(utilisateur, "is_authenticated", False):
        return False
    if utilisateur.is_superuser or utilisateur.is_staff:
        return True
    if getattr(utilisateur, "is_admin", False) or getattr(utilisateur, "is_secretariat", False):
        return True
    profil_professeur = getattr(utilisateur, "profil_professeur", None)
    return profil_professeur is not None and module.responsable_id == profil_professeur.pk


def prerequis_satisfaits(profil, module: ModuleFormation) -> bool:
    """Tous les modules prérequis sont-ils terminés par cet étudiant ?"""
    identifiants = list(module.prerequis.values_list("pk", flat=True))
    if not identifiants:
        return True
    termines = InscriptionModule.objects.filter(
        etudiant=profil,
        module_id__in=identifiants,
        statut=InscriptionModule.StatutAcces.TERMINE,
    ).count()
    return termines == len(identifiants)


# ──────────────────────────────────────────────
# Quota de lectures simultanées
# ──────────────────────────────────────────────


def _cle_quota(utilisateur) -> str:
    return f"elearning:flux:{utilisateur.pk}"


def _quota_disponible(utilisateur, identifiant_flux: str) -> bool:
    """Un même compte ne lit pas depuis plusieurs appareils à la fois.

    Le verrou porte l'identifiant du flux en cours : réactualiser sa propre
    lecture reste possible, en ouvrir une seconde ailleurs non.
    """
    maximum = getattr(settings, "ELEARNING_FLUX_SIMULTANES_MAX", 1)
    if maximum <= 0:
        return True

    duree = getattr(settings, "ELEARNING_FLUX_TTL", 900)
    cle = _cle_quota(utilisateur)
    actuel = cache.get(cle)

    if actuel is None or actuel == identifiant_flux or maximum > 1:
        cache.set(cle, identifiant_flux, duree)
        return True
    return False


def liberer_flux(utilisateur) -> None:
    """Libère le verrou de lecture — à l'arrêt de la lecture ou à la déconnexion."""
    cache.delete(_cle_quota(utilisateur))


# ──────────────────────────────────────────────
# Traçabilité
# ──────────────────────────────────────────────


def journaliser_acces(decision: DecisionAcces, *, utilisateur, lecon, request=None, ttl: int = 0) -> JournalAccesVideo:
    """Consigne la demande de lecture, qu'elle ait abouti ou non."""
    import hashlib

    from apps.core.services.audit import _adresse_ip

    empreinte = ""
    if request is not None:
        agent = request.META.get("HTTP_USER_AGENT", "")
        empreinte = hashlib.sha256(agent.encode()).hexdigest() if agent else ""

    return JournalAccesVideo.objects.create(
        utilisateur=utilisateur if getattr(utilisateur, "is_authenticated", False) else None,
        lecon=lecon,
        video=lecon.video if lecon else None,
        resultat=JournalAccesVideo.Resultat.AUTORISE if decision.autorise else decision.motif,
        adresse_ip=_adresse_ip(request),
        user_agent_hash=empreinte,
        ttl_accorde=ttl,
    )


def adresses_distinctes_recentes(utilisateur, heures: int = 24) -> int:
    """Nombre d'adresses IP distinctes utilisées récemment — indice de partage."""
    from datetime import timedelta

    depuis = timezone.now() - timedelta(hours=heures)
    return (
        JournalAccesVideo.objects.filter(utilisateur=utilisateur, created_at__gte=depuis)
        .exclude(adresse_ip__isnull=True)
        .values("adresse_ip")
        .distinct()
        .count()
    )
