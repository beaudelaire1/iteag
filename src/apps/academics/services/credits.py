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


def _synchroniser(objet, champ: str, eligible: bool, valeurs: dict) -> str:
    """
    Aligne le dossier sur la décision courante.

    Retourne « porte », « retire » ou « inchange ». Le tri-état est nécessaire :
    un booléen confondrait « déjà crédité » et « non éligible », et le second
    enregistrement d'une décision inchangée retirerait le crédit.
    """
    existant = CreditECTS.objects.filter(**{champ: objet}).first()
    if eligible:
        if existant:
            return "inchange"
        CreditECTS.objects.create(**{champ: objet}, **valeurs)
        return "porte"
    if existant:
        existant.delete()
        return "retire"
    return "inchange"


def synchroniser_stage(stage) -> str:
    """
    Porte ou retire les ECTS d'un stage selon qu'il est validé.

    Un stage vaut 30 ECTS au CDC : sans ce pont, un étudiant pourrait valider
    son stage sans en voir la trace sur son relevé. Le retour en arrière est
    traité aussi — une décision reprise doit rendre le dossier conforme.
    """
    from apps.academics.models import Stage

    return _synchroniser(
        stage,
        "stage",
        eligible=stage.statut == Stage.StatutStage.VALIDE and stage.ects > 0,
        valeurs={
            "etudiant": stage.etudiant,
            "ects_obtenus": stage.ects,
            "source": CreditECTS.SourceCredit.ITEAG,
            "date_validation": stage.date_fin,
        },
    )


def synchroniser_vae(vae) -> str:
    """
    Porte ou retire les ECTS d'une VAE selon la décision.

    Seuls les ECTS **accordés** comptent, jamais les ECTS demandés : la
    décision appartient au jury, pas au candidat.
    """
    from apps.academics.models import VAE

    return _synchroniser(
        vae,
        "vae",
        eligible=vae.statut == VAE.StatutVAE.ACCORDE and vae.ects_accordes > 0,
        valeurs={
            "etudiant": vae.etudiant,
            "ects_obtenus": vae.ects_accordes,
            "source": CreditECTS.SourceCredit.ITEAG,
            "date_validation": vae.date_decision or timezone.now().date(),
        },
    )
