from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.services.audit import journaliser

from .emails import send_statut_change_email
from .models import DossierCandidature, HistoriqueStatut

ALLOWED_STATUS_TRANSITIONS = {
    DossierCandidature.Statut.SOUMIS: {DossierCandidature.Statut.EN_EXAMEN},
    DossierCandidature.Statut.EN_EXAMEN: {
        DossierCandidature.Statut.INCOMPLET,
        DossierCandidature.Statut.ACCEPTE,
        DossierCandidature.Statut.REFUSE,
    },
    DossierCandidature.Statut.INCOMPLET: {DossierCandidature.Statut.EN_EXAMEN},
    DossierCandidature.Statut.ACCEPTE: set(),
    DossierCandidature.Statut.REFUSE: set(),
}


def available_status_choices(dossier):
    allowed = ALLOWED_STATUS_TRANSITIONS.get(dossier.statut, set())
    return [(value, label) for value, label in DossierCandidature.Statut.choices if value in allowed]


@transaction.atomic
def transition_dossier(*, dossier, new_status, changed_by, comment=""):
    """Applique une transition atomique, journalisée, puis notifie après commit."""
    locked = DossierCandidature.objects.select_for_update().get(pk=dossier.pk)
    allowed = ALLOWED_STATUS_TRANSITIONS.get(locked.statut, set())
    if new_status not in allowed:
        raise ValidationError(
            f"Transition impossible de « {locked.get_statut_display()} » vers "
            f"« {dict(DossierCandidature.Statut.choices).get(new_status, new_status)} »."
        )

    HistoriqueStatut.objects.create(
        dossier=locked,
        ancien_statut=locked.statut,
        nouveau_statut=new_status,
        modifie_par=changed_by,
        commentaire=comment,
    )
    locked.statut = new_status
    locked.save(update_fields=["statut", "date_derniere_maj"])
    transaction.on_commit(lambda: send_statut_change_email(locked))
    return locked


# ──────────────────────────────────────────────
# Pièces complémentaires
# ──────────────────────────────────────────────


def demander_piece(dossier, *, libelle: str, description: str = "", obligatoire: bool = True, par=None):
    """Réclame une pièce au candidat, et le lui fait savoir.

    Le dossier passe en « incomplet » : c'est ce que signifie attendre une
    pièce, et cela évite qu'il reste à tort dans la file des dossiers à
    instruire.
    """

    from apps.admissions.models import DossierCandidature, PieceComplementaire

    libelle = (libelle or "").strip()
    if not libelle:
        raise ValidationError("Indiquez la pièce demandée.")

    piece = PieceComplementaire.objects.create(
        dossier=dossier,
        libelle=libelle,
        description=(description or "").strip(),
        obligatoire=obligatoire,
        demandee_par=par,
    )

    if dossier.statut in (DossierCandidature.Statut.SOUMIS, DossierCandidature.Statut.EN_EXAMEN):
        dossier.statut = DossierCandidature.Statut.INCOMPLET
        dossier.save(update_fields=["statut", "date_derniere_maj"])

    journaliser(
        "modification",
        utilisateur=par,
        objet=dossier,
        objet_libelle=f"Pièce demandée : {libelle}",
    )
    _prevenir_le_candidat(
        dossier,
        sujet="Une pièce complémentaire est attendue",
        message=(
            f"Le secrétariat vous demande de fournir : {libelle}." + (f"\n\n{description}" if description else "")
        ),
    )
    return piece


def deposer_piece(piece, fichier):
    """Enregistre le dépôt du candidat. Le contrôle reste au secrétariat."""
    from django.utils import timezone

    from apps.admissions.models import PieceComplementaire

    if not piece.est_en_attente:
        raise ValidationError("Cette pièce a déjà été déposée et vérifiée.")

    piece.fichier = fichier
    piece.statut = PieceComplementaire.Statut.DEPOSEE
    piece.date_depot = timezone.now()
    piece.motif_refus = ""
    piece.save(update_fields=["fichier", "statut", "date_depot", "motif_refus", "updated_at"])
    return piece


def verifier_piece(piece, *, acceptee: bool, motif: str = "", par=None):
    """Le secrétariat accepte la pièce, ou la refuse avec un motif.

    Un refus sans motif obligerait le candidat à deviner ce qui n'allait pas —
    et à redéposer la même chose.
    """
    from django.utils import timezone

    from apps.admissions.models import PieceComplementaire

    if piece.statut != PieceComplementaire.Statut.DEPOSEE:
        raise ValidationError("Seule une pièce déposée peut être vérifiée.")
    if not acceptee and not motif.strip():
        raise ValidationError("Précisez ce qui ne convient pas : le candidat doit savoir quoi corriger.")

    piece.statut = PieceComplementaire.Statut.VALIDEE if acceptee else PieceComplementaire.Statut.REFUSEE
    piece.motif_refus = "" if acceptee else motif.strip()
    piece.date_verification = timezone.now()
    piece.save(update_fields=["statut", "motif_refus", "date_verification", "updated_at"])

    journaliser(
        "changement_statut",
        utilisateur=par,
        objet=piece.dossier,
        objet_libelle=f"Pièce {'validée' if acceptee else 'refusée'} : {piece.libelle}",
        motif=piece.motif_refus,
    )
    _prevenir_le_candidat(
        piece.dossier,
        sujet="Pièce validée" if acceptee else "Pièce à redéposer",
        message=(
            f"Votre pièce « {piece.libelle} » a été validée."
            if acceptee
            else f"Votre pièce « {piece.libelle} » n'a pas été retenue.\n\nMotif : {piece.motif_refus}"
        ),
    )
    return piece


def _prevenir_le_candidat(dossier, *, sujet: str, message: str) -> None:
    """Le candidat n'a pas de compte : le lien de suivi est sa seule porte."""
    from django.conf import settings
    from django.urls import reverse

    from apps.core.services.emails import envoyer_email

    lien = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}" + reverse(
        "admissions:candidature_suivi", kwargs={"token": dossier.token_suivi}
    )
    envoyer_email(
        sujet=sujet,
        gabarit="admissions/emails/piece_complementaire.html",
        contexte={
            "titre": sujet,
            "message": message,
            "lien": lien,
            "libelle_lien": "Suivre ma candidature",
        },
        destinataires=[dossier.email],
    )
