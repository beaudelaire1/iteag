"""
Octroi et retrait des droits d'accès aux modules.

Le droit est une donnée administrable ; ce module en est le seul point
d'écriture, afin que l'octroi automatique à l'admission et l'octroi manuel du
secrétariat produisent exactement le même objet.
"""

from datetime import timedelta

from django.utils import timezone

from apps.core.models import Notification
from apps.core.services.audit import journaliser
from apps.core.services.notifications import notifier
from apps.elearning.models import InscriptionModule, ModuleFormation, RegleAccesParcours


def octroyer(
    profil,
    module: ModuleFormation,
    *,
    source: str = InscriptionModule.SourceAcces.OCTROI_MANUEL,
    duree_jours: int | None = None,
    octroye_par=None,
    notifier_etudiant: bool = True,
) -> InscriptionModule:
    """Ouvre l'accès d'un étudiant à un module. Idempotent.

    Un accès révoqué ou expiré est réactivé plutôt que dupliqué : la contrainte
    d'unicité l'impose, et l'historique de progression est ainsi conservé.
    """
    debut = timezone.localdate()
    fin = debut + timedelta(days=duree_jours) if duree_jours else None

    inscription, creee = InscriptionModule.objects.get_or_create(
        etudiant=profil,
        module=module,
        defaults={
            "source": source,
            "date_debut_acces": debut,
            "date_fin_acces": fin,
            "octroye_par": octroye_par,
        },
    )

    if not creee and inscription.statut in (
        InscriptionModule.StatutAcces.REVOQUE,
        InscriptionModule.StatutAcces.EXPIRE,
        InscriptionModule.StatutAcces.SUSPENDU,
    ):
        inscription.statut = InscriptionModule.StatutAcces.ACTIF
        inscription.motif_revocation = ""
        inscription.suspendu_par_propagation = False
        inscription.date_fin_acces = fin
        inscription.octroye_par = octroye_par or inscription.octroye_par
        inscription.save(
            update_fields=[
                "statut",
                "motif_revocation",
                "suspendu_par_propagation",
                "date_fin_acces",
                "octroye_par",
                "updated_at",
            ]
        )
        creee = True  # rétabli : mérite la même notification qu'une ouverture

    if creee:
        journaliser(
            "octroi_acces",
            utilisateur=octroye_par,
            objet=inscription,
            objet_libelle=f"{profil} → {module.titre}",
            source=source,
        )
        if notifier_etudiant and module.est_publie:
            notifier(
                profil.utilisateur,
                f"Nouveau module accessible — {module.titre}",
                type_notification=Notification.Type.ACCES_OCTROYE,
                message="Ce module de formation est désormais disponible dans votre espace.",
                url_cible=module.get_absolute_url(),
            )

    return inscription


def revoquer(inscription: InscriptionModule, *, motif: str = "", par=None) -> InscriptionModule:
    """Retire l'accès. La révocation prend effet immédiatement."""
    inscription.statut = InscriptionModule.StatutAcces.REVOQUE
    inscription.motif_revocation = motif
    inscription.save(update_fields=["statut", "motif_revocation", "updated_at"])
    journaliser(
        "revocation_acces",
        utilisateur=par,
        objet=inscription,
        objet_libelle=f"{inscription.etudiant} → {inscription.module.titre}",
        motif=motif,
    )
    return inscription


def prolonger(inscription: InscriptionModule, *, jours: int, par=None) -> InscriptionModule:
    """Repousse l'échéance et réactive un accès arrivé à terme."""
    base = inscription.date_fin_acces or timezone.localdate()
    if base < timezone.localdate():
        base = timezone.localdate()
    inscription.date_fin_acces = base + timedelta(days=jours)
    if inscription.statut == InscriptionModule.StatutAcces.EXPIRE:
        inscription.statut = InscriptionModule.StatutAcces.ACTIF
    inscription.save(update_fields=["date_fin_acces", "statut", "updated_at"])
    journaliser("octroi_acces", utilisateur=par, objet=inscription, prolongation_jours=jours)
    return inscription


def octroyer_modules_du_parcours(profil, *, octroye_par=None) -> list[InscriptionModule]:
    """Ouvre les modules obligatoires du parcours de l'étudiant.

    Appelé à l'acceptation d'une candidature : sans cette automatisation, le
    secrétariat croulerait sous la saisie.
    """
    regles = (
        RegleAccesParcours.objects.filter(parcours=profil.parcours, obligatoire=True)
        .select_related("module")
        .order_by("ordre_recommande")
    )
    return [
        octroyer(
            profil,
            regle.module,
            source=InscriptionModule.SourceAcces.PARCOURS,
            duree_jours=regle.duree_acces_jours,
            octroye_par=octroye_par,
        )
        for regle in regles
    ]


def propager_statut_etudiant(profil) -> int:
    """Répercute le statut d'inscription de l'étudiant sur ses accès vidéo.

    Une suspension coupe l'accès dans la seconde. Le rétablissement ne relève
    que les accès suspendus *de ce fait* : une révocation individuelle demeure.
    """
    from apps.academics.models import ProfilEtudiant

    bloquants = {
        ProfilEtudiant.StatutInscription.SUSPENDU,
        ProfilEtudiant.StatutInscription.INACTIF,
    }

    if profil.statut_inscription in bloquants:
        return InscriptionModule.objects.filter(
            etudiant=profil,
            statut=InscriptionModule.StatutAcces.ACTIF,
        ).update(statut=InscriptionModule.StatutAcces.SUSPENDU, suspendu_par_propagation=True)

    return InscriptionModule.objects.filter(
        etudiant=profil,
        statut=InscriptionModule.StatutAcces.SUSPENDU,
        suspendu_par_propagation=True,
    ).update(statut=InscriptionModule.StatutAcces.ACTIF, suspendu_par_propagation=False)


def expirer_acces_echus() -> int:
    """Bascule en « expiré » les accès dont la date de fin est dépassée."""
    return InscriptionModule.objects.filter(
        statut=InscriptionModule.StatutAcces.ACTIF,
        date_fin_acces__lt=timezone.localdate(),
    ).update(statut=InscriptionModule.StatutAcces.EXPIRE)
