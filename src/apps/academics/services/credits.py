"""
Inscription des crédits ECTS au dossier de l'étudiant.

Le domaine académique possède le dossier ECTS ; il ne doit pas connaître le
modèle d'évaluation du LMS. La frontière est donc explicite : le domaine qui
publie un résultat lui transmet des ``ResultatECTSPublie`` et ce service ne
fait qu'appliquer la décision au dossier académique.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from django.db import transaction
from django.utils import timezone

from apps.academics.models import CreditECTS, ProfilEtudiant


@dataclass(frozen=True)
class ResultatECTSPublie:
    """Décision académique minimale nécessaire pour porter un crédit au dossier."""

    etudiant: ProfilEtudiant
    ects_valides: Decimal


@transaction.atomic
def crediter_resultats_publication(cours_session, resultats: Iterable[ResultatECTSPublie]) -> int:
    """Inscrit au dossier les ECTS d'un résultat déjà publié par son domaine.

    Cette fonction ne décide jamais qu'une évaluation est publiée : elle reçoit
    cette décision. L'opération reste idempotente grâce au ``get_or_create`` et
    à la contrainte d'unicité ``etudiant + cours + session + source`` portée par
    le schéma.
    """

    # La date de validation est celle de fin de session : c'est la date
    # académique du résultat, pas celle où le secrétariat a cliqué.
    date_validation = getattr(cours_session.session, "date_fin", None) or timezone.now().date()

    inscrits = 0
    for resultat in resultats:
        if resultat.ects_valides <= 0:
            continue
        _, cree = CreditECTS.objects.get_or_create(
            etudiant=resultat.etudiant,
            cours=cours_session.cours,
            session=cours_session.session,
            source=CreditECTS.SourceCredit.ITEAG,
            defaults={
                "ects_obtenus": resultat.ects_valides,
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
