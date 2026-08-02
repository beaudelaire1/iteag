from django.core.exceptions import ValidationError
from django.db import transaction

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
# Pièces réclamées au candidat
# ──────────────────────────────────────────────
# Elles n'ont pas de service : « PieceDemandee » porte lui-même ses transitions
# (`deposer`, `valider`, `refuser`), et les vues de
# « administration/views_pieces.py » les enchaînent. Trois fonctions doublaient
# ici ce comportement sur un modèle jumeau, retiré depuis.
