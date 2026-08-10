"""Pont LMS → dossier académique lors de la publication des résultats.

Le LMS est le seul domaine qui sait ce qu'est une ``Evaluation`` et son statut
de publication. Il sélectionne donc ses propres données puis transmet au domaine
académique une décision minimale et typée. La dépendance reste unidirectionnelle
``lms → academics``.
"""

from apps.academics.services.credits import ResultatECTSPublie, crediter_resultats_publication

from .models import Evaluation


def crediter_publication(cours_session) -> int:
    """Porte au dossier les ECTS des évaluations publiées du cours."""

    evaluations = (
        Evaluation.objects.filter(
            cours_session=cours_session,
            statut=Evaluation.StatutEvaluation.PUBLIE,
            ects_valides__gt=0,
        )
        .select_related("etudiant")
        .only("id", "etudiant", "ects_valides")
    )
    resultats = [
        ResultatECTSPublie(etudiant=evaluation.etudiant, ects_valides=evaluation.ects_valides)
        for evaluation in evaluations
    ]
    return crediter_resultats_publication(cours_session, resultats)
