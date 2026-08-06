from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import (
    CoursDeSession,
    InscriptionSession,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
)
from apps.accounts.models import User
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.lms import services
from apps.lms.models import Devoir

pytestmark = pytest.mark.django_db


@pytest.fixture
def contexte_qcm():
    discipline = Discipline.objects.create(nom="QCM", slug="qcm-garde-fous")
    cours = Cours.objects.create(titre="Cours QCM", slug="cours-qcm-garde-fous", discipline=discipline)
    compte_enseignant = User.objects.create_user(
        username="enseignant_qcm_garde_fous",
        password="MotDePasse!2026",
        role=User.Role.ENSEIGNANT,
    )
    professeur = Professeur.objects.create(
        user=compte_enseignant,
        nom="Professeur",
        prenom="QCM",
        slug="professeur-qcm-garde-fous",
    )
    session = SessionAcademique.objects.create(
        nom="Session QCM garde-fous",
        periode=SessionAcademique.Periode.JUILLET,
        annee_academique="2026-2027",
        date_debut=date(2026, 7, 1),
        date_fin=date(2026, 7, 31),
    )
    cours_session = CoursDeSession.objects.create(session=session, cours=cours, enseignant=professeur)

    parcours = Parcours.objects.create(
        nom="Parcours QCM garde-fous",
        slug="parcours-qcm-garde-fous",
        type_parcours=Parcours.TypeParcours.LIBRE,
    )
    promotion = Promotion.objects.create(
        nom="Promotion QCM garde-fous",
        parcours=parcours,
        annee_debut=2026,
        annee_fin=2029,
    )
    compte_etudiant = User.objects.create_user(
        username="etudiant_qcm_garde_fous",
        password="MotDePasse!2026",
        role=User.Role.ETUDIANT,
    )
    etudiant = ProfilEtudiant.objects.create(
        utilisateur=compte_etudiant,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="QCM-GARDE-001",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )
    InscriptionSession.objects.create(etudiant=etudiant, cours_session=cours_session)
    return cours_session, compte_enseignant


def creer_qcm_incomplet(cours_session):
    return Devoir.objects.create(
        cours_session=cours_session,
        titre="Questionnaire sans question",
        modalite=Devoir.Modalite.QCM,
        date_ouverture=timezone.now(),
        date_fermeture=timezone.now() + timedelta(days=1),
    )


def test_service_refuse_un_questionnaire_incomplet(contexte_qcm):
    cours_session, _ = contexte_qcm
    devoir = creer_qcm_incomplet(cours_session)

    with pytest.raises(ValidationError, match="Questionnaire incomplet"):
        services.publier_devoir(devoir)

    devoir.refresh_from_db()
    assert devoir.statut == Devoir.Statut.BROUILLON
    assert not devoir.copies.exists()


def test_publication_refuse_un_questionnaire_incomplet(client, contexte_qcm):
    cours_session, enseignant = contexte_qcm
    devoir = creer_qcm_incomplet(cours_session)
    client.force_login(enseignant)

    reponse = client.post(reverse("lms:devoir_action", args=[devoir.pk]), {"action": "publier"})

    assert reponse.status_code == 302
    devoir.refresh_from_db()
    assert devoir.statut == Devoir.Statut.BROUILLON
    assert not devoir.copies.exists()


def test_atelier_qcm_refuse_un_devoir_classique(client, contexte_qcm):
    cours_session, enseignant = contexte_qcm
    devoir = Devoir.objects.create(
        cours_session=cours_session,
        titre="Dépôt de fichier",
        modalite=Devoir.Modalite.DEPOT_FICHIER,
        date_ouverture=timezone.now(),
        date_fermeture=timezone.now() + timedelta(days=1),
    )
    client.force_login(enseignant)

    reponse = client.get(reverse("lms:questionnaire", args=[devoir.pk]))

    assert reponse.status_code == 404
