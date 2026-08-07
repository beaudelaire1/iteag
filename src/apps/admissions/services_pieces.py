from django.utils import timezone

from apps.admissions.models import DemandePieces, PieceDemandee


def synchroniser_statut_demande(demande: DemandePieces) -> DemandePieces:
    """Recalcule le lot depuis ses pièces, sans dépendre de la dernière action.

    Une pièce déposée attend toujours une décision. Une pièce refusée demande
    une correction. Une pièce obligatoire encore absente empêche la clôture ;
    une pièce facultative jamais déposée ne la bloque pas.
    """

    pieces = list(demande.pieces.only("statut", "obligatoire"))
    statuts = {piece.statut for piece in pieces}

    if PieceDemandee.Statut.DEPOSEE in statuts:
        nouveau_statut = DemandePieces.Statut.A_VERIFIER
    elif PieceDemandee.Statut.REFUSEE in statuts:
        nouveau_statut = DemandePieces.Statut.A_CORRIGER
    elif any(
        piece.obligatoire and piece.statut == PieceDemandee.Statut.DEMANDEE
        for piece in pieces
    ):
        nouveau_statut = DemandePieces.Statut.A_FOURNIR
    else:
        nouveau_statut = DemandePieces.Statut.VALIDEE

    champs = []
    if demande.statut != nouveau_statut:
        demande.statut = nouveau_statut
        champs.append("statut")

    if nouveau_statut == DemandePieces.Statut.A_VERIFIER:
        demande.date_soumission = demande.date_soumission or timezone.now()
        demande.date_decision = None
        champs.extend(["date_soumission", "date_decision"])
    elif nouveau_statut in (DemandePieces.Statut.A_CORRIGER, DemandePieces.Statut.VALIDEE):
        demande.date_decision = timezone.now()
        champs.append("date_decision")
    else:
        demande.date_decision = None
        champs.append("date_decision")

    if champs:
        demande.save(update_fields=[*dict.fromkeys(champs), "updated_at"])
    return demande
