"""
Octroi et retrait des droits d'accès aux modules.

Le droit est une donnée administrable ; ce module en est le seul point
d'écriture, afin que l'octroi automatique à l'admission et l'octroi manuel du
secrétariat produisent exactement le même objet.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
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
        InscriptionModule.StatutAcces.DEMANDE,
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


# ──────────────────────────────────────────────
# Demande d'accès à l'initiative de l'étudiant
# ──────────────────────────────────────────────


def motif_refus_demande(profil, module: ModuleFormation) -> str:
    """Pourquoi cet étudiant ne peut pas demander ce module — vide s'il le peut.

    L'ordre compte : le premier motif rencontré est celui qu'on affiche, et
    c'est celui qui explique le mieux la situation à l'étudiant.
    """
    from apps.academics.models import ProfilEtudiant

    if profil is None:
        return "Un dossier étudiant est nécessaire pour demander l'accès à un module."
    if profil.statut_inscription in {
        ProfilEtudiant.StatutInscription.SUSPENDU,
        ProfilEtudiant.StatutInscription.INACTIF,
    }:
        return "Votre statut administratif ne permet pas d'ouvrir un nouveau module."
    if not module.est_publie:
        return "Ce module n'est pas encore ouvert aux inscriptions."
    if module.politique_acces in {
        ModuleFormation.PolitiqueAcces.PUBLIC,
        ModuleFormation.PolitiqueAcces.AUTHENTIFIE,
    }:
        return "Ce module est déjà accessible : aucune demande n'est nécessaire."

    existante = InscriptionModule.objects.filter(etudiant=profil, module=module).first()
    if existante is None:
        return ""
    if existante.statut == InscriptionModule.StatutAcces.DEMANDE:
        return "Votre demande est déjà enregistrée ; le secrétariat la traite."
    if existante.statut == InscriptionModule.StatutAcces.REVOQUE:
        return ""  # une demande peut être renouvelée après un refus
    return "Vous avez déjà accès à ce module."


@transaction.atomic
def demander(profil, module: ModuleFormation, *, request=None) -> InscriptionModule:
    """Enregistre la demande d'accès d'un étudiant déjà inscrit à l'institut.

    L'institut détient déjà l'identité de cet étudiant : la demande ne
    redemande donc aucune coordonnée, elle ne porte que le fait d'avoir été
    formulée. Le droit est créé sans être exerçable — `est_active()` est faux
    tant que le secrétariat n'a pas tranché.
    """
    motif = motif_refus_demande(profil, module)
    if motif:
        raise ValidationError(motif)

    inscription, creee = InscriptionModule.objects.get_or_create(
        etudiant=profil,
        module=module,
        defaults={
            "source": InscriptionModule.SourceAcces.OCTROI_MANUEL,
            "statut": InscriptionModule.StatutAcces.DEMANDE,
        },
    )
    if not creee:
        # Renouvellement après refus : on repart d'une demande propre.
        inscription.statut = InscriptionModule.StatutAcces.DEMANDE
        inscription.motif_revocation = ""
        inscription.date_debut_acces = timezone.localdate()
        inscription.date_fin_acces = None
        inscription.save(
            update_fields=["statut", "motif_revocation", "date_debut_acces", "date_fin_acces", "updated_at"]
        )

    journaliser(
        "demande_acces",
        utilisateur=profil.utilisateur,
        request=request,
        objet=inscription,
        objet_libelle=f"{profil} → {module.titre}",
    )
    _prevenir_le_secretariat(profil, module)
    return inscription


def _prevenir_le_secretariat(profil, module: ModuleFormation) -> None:
    """Une demande sans destinataire resterait sans réponse."""
    from apps.accounts.models import User

    destinataires = User.objects.filter(
        is_active=True,
        role__in=[User.Role.SECRETARIAT, User.Role.ADMIN],
    )
    for destinataire in destinataires:
        notifier(
            destinataire,
            "Demande d'accès à un module",
            type_notification=Notification.Type.ACCES_OCTROYE,
            message=f"{profil} demande l'accès à « {module.titre} ».",
            url_cible=f"{reverse('administration:acces')}?statut={InscriptionModule.StatutAcces.DEMANDE}",
        )


def refuser_demande(inscription: InscriptionModule, *, motif: str, par=None) -> InscriptionModule:
    """Refuse une demande. Le motif est obligatoire : un refus muet est inexploitable."""
    if inscription.statut != InscriptionModule.StatutAcces.DEMANDE:
        raise ValidationError("Cette demande a déjà été traitée.")
    if not motif.strip():
        raise ValidationError("Précisez le motif du refus.")

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
    notifier(
        inscription.etudiant.utilisateur,
        f"Demande d'accès non retenue — {inscription.module.titre}",
        type_notification=Notification.Type.ACCES_OCTROYE,
        message=motif,
        url_cible=inscription.module.get_absolute_url(),
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
    notifier(
        inscription.etudiant.utilisateur,
        f"Accès retiré — {inscription.module.titre}",
        type_notification=Notification.Type.ACCES_OCTROYE,
        message=motif or "Votre accès à ce module a été retiré.",
        url_cible=inscription.module.get_absolute_url(),
    )
    return inscription


def suspendre(inscription: InscriptionModule, *, par=None) -> InscriptionModule:
    inscription.statut = InscriptionModule.StatutAcces.SUSPENDU
    inscription.save(update_fields=["statut", "updated_at"])
    journaliser("revocation_acces", utilisateur=par, objet=inscription, suspension=True)
    notifier(
        inscription.etudiant.utilisateur,
        f"Accès suspendu — {inscription.module.titre}",
        type_notification=Notification.Type.ACCES_OCTROYE,
        message="Votre accès à ce module est temporairement suspendu.",
        url_cible=inscription.module.get_absolute_url(),
    )
    return inscription


def reactiver(inscription: InscriptionModule, *, par=None) -> InscriptionModule:
    inscription.statut = InscriptionModule.StatutAcces.ACTIF
    inscription.suspendu_par_propagation = False
    inscription.save(update_fields=["statut", "suspendu_par_propagation", "updated_at"])
    journaliser("octroi_acces", utilisateur=par, objet=inscription, reactivation=True)
    notifier(
        inscription.etudiant.utilisateur,
        f"Accès réactivé — {inscription.module.titre}",
        type_notification=Notification.Type.ACCES_OCTROYE,
        message="Votre accès au module est de nouveau actif.",
        url_cible=inscription.module.get_absolute_url(),
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
    notifier(
        inscription.etudiant.utilisateur,
        f"Accès prolongé — {inscription.module.titre}",
        type_notification=Notification.Type.ACCES_OCTROYE,
        message=f"Votre accès est prolongé jusqu'au {inscription.date_fin_acces:%d/%m/%Y}.",
        url_cible=inscription.module.get_absolute_url(),
    )
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
