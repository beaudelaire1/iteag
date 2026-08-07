from decimal import Decimal
from types import SimpleNamespace

from apps.academics.models import DemandeInscriptionCours
from apps.academics.services.inscriptions import _details_demande, _message_notification


def test_motif_du_refus_figure_dans_le_message_et_les_details():
    motif = "La capacité maximale du cours est atteinte pour cette session."
    demande = SimpleNamespace(
        statut=DemandeInscriptionCours.Statut.REFUSEE,
        motif_decision=motif,
        montant_du=Decimal("0"),
        cours_session=SimpleNamespace(
            cours=SimpleNamespace(titre="Introduction à la théologie"),
            session="Session de juillet 2026",
        ),
        get_statut_display=lambda: "Refusée",
    )

    assert motif in _message_notification(demande)
    assert {"libelle": "Motif du refus", "valeur": motif} in _details_demande(demande)
