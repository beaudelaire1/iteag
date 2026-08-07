from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import CoursDeSession, SessionAcademique
from apps.accounts.models import User
from apps.formations.models import Cours, Discipline, Professeur
from apps.lms.models import Devoir, Question

pytestmark = pytest.mark.django_db


@pytest.fixture
def qcm_a_construire():
    discipline = Discipline.objects.create(nom="QCM création", slug="qcm-creation-intuitive")
    cours = Cours.objects.create(titre="Cours QCM création", slug="cours-qcm-creation", discipline=discipline)
    compte = User.objects.create_user(
        username="enseignant-qcm-creation",
        password="MotDePasse!2026",
        role=User.Role.ENSEIGNANT,
    )
    professeur = Professeur.objects.create(
        user=compte,
        nom="Création",
        prenom="QCM",
        slug="creation-qcm",
    )
    session = SessionAcademique.objects.create(
        nom="Session QCM création",
        periode=SessionAcademique.Periode.JUILLET,
        annee_academique="2026-2027",
        date_debut=date(2026, 7, 1),
        date_fin=date(2026, 7, 31),
    )
    cours_session = CoursDeSession.objects.create(session=session, cours=cours, enseignant=professeur)
    devoir = Devoir.objects.create(
        cours_session=cours_session,
        titre="Questionnaire intuitif",
        modalite=Devoir.Modalite.QCM,
        date_ouverture=timezone.now(),
        date_fermeture=timezone.now() + timedelta(days=1),
    )
    return compte, devoir


def test_creation_en_une_etape_enregistre_question_et_propositions(client, qcm_a_construire):
    enseignant, devoir = qcm_a_construire
    client.force_login(enseignant)

    reponse = client.post(
        reverse("lms:question_create", args=[devoir.pk]),
        {
            "enonce": "Quel livre ouvre le Nouveau Testament ?",
            "type_question": Question.TypeQuestion.CHOIX_UNIQUE,
            "points": "2",
            "explication": "L'Évangile selon Matthieu ouvre le Nouveau Testament.",
            "ordre": "0",
            "proposition": ["Matthieu", "Marc", "Luc", ""],
            "correcte": ["0"],
        },
    )

    assert reponse.status_code == 302
    assert reponse.url == reverse("lms:questionnaire", args=[devoir.pk])
    question = devoir.questions.get()
    assert question.enonce == "Quel livre ouvre le Nouveau Testament ?"
    assert list(question.choix.values_list("libelle", "correct")) == [
        ("Matthieu", True),
        ("Marc", False),
        ("Luc", False),
    ]


def test_creation_refuse_une_question_unique_avec_plusieurs_bonnes_reponses(client, qcm_a_construire):
    enseignant, devoir = qcm_a_construire
    client.force_login(enseignant)

    reponse = client.post(
        reverse("lms:question_create", args=[devoir.pk]),
        {
            "enonce": "Question invalide",
            "type_question": Question.TypeQuestion.CHOIX_UNIQUE,
            "points": "1",
            "explication": "",
            "ordre": "0",
            "proposition": ["Réponse A", "Réponse B"],
            "correcte": ["0", "1"],
        },
    )

    assert reponse.status_code == 400
    assert "ne peut avoir qu’une seule bonne réponse" in reponse.content.decode().replace("'", "’")
    assert not devoir.questions.exists()
