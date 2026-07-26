"""
Inscription des crédits ECTS au dossier de l'étudiant.

L'enseignant saisit `Evaluation.ects_valides` ; le relevé de notes, la
progression et le calcul des ECTS restants lisent `CreditECTS`. Ce service est
le seul pont entre les deux. Sans lui, un étudiant peut valider tous ses cours
et conserver un relevé vierge.

Le crédit est inscrit **à la publication** des notes, pas à leur saisie : tant
qu'une note n'est pas publiée, l'enseignant peut la reprendre. Créditer plus
tôt reviendrait à porter au dossier une décision non arrêtée.
"""

from django.db import transaction
from django.utils import timezone

from apps.academics.models import CreditECTS


def crediter_publication(cours_session) -> int:
    """
    Inscrit au dossier les crédits des évaluations publiées de ce cours.

    Retourne le nombre de crédits nouvellement inscrits. L'opération est
    idempotente : republier ne double pas le dossier académique.
    """
    from apps.lms.models import Evaluation

    evaluations = (
        Evaluation.objects.filter(
            cours_session=cours_session,
            statut=Evaluation.StatutEvaluation.PUBLIE,
            ects_valides__gt=0,
        )
        .select_related("etudiant")
        .only("id", "etudiant", "ects_valides")
    )

    # La date de validation est celle de fin de session : c'est la date
    # académique du résultat, pas celle où le secrétariat a cliqué.
    date_validation = getattr(cours_session.session, "date_fin", None) or timezone.now().date()

    inscrits = 0
    with transaction.atomic():
        for evaluation in evaluations:
            _, cree = CreditECTS.objects.get_or_create(
                etudiant=evaluation.etudiant,
                cours=cours_session.cours,
                session=cours_session.session,
                source=CreditECTS.SourceCredit.ITEAG,
                defaults={
                    "ects_obtenus": evaluation.ects_valides,
                    "date_validation": date_validation,
                },
            )
            inscrits += int(cree)
    return inscrits
