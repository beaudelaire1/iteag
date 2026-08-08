"""Tests unitaires et d'intégration pour la saisie d'assiduité et le PV de délibération."""

from datetime import date

import pytest
from django.urls import reverse

from apps.academics.models import (
    CoursDeSession,
    InscriptionSession,
    PresenceEtudiant,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
)
from apps.accounts.models import User
from apps.formations.models import Cours, Discipline, Parcours, Professeur

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "Secret!123456"


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="secretaire_test",
        email="secretaire@iteag.org",
        password=MOT_DE_PASSE,
        first_name="Marie",
        last_name="DUPONT",
        role=User.Role.SECRETARIAT,
    )


@pytest.fixture
def session_et_cours(db):
    discipline = Discipline.objects.create(nom="Théologie", slug="theologie")
    parcours = Parcours.objects.create(
        nom="Diplômant ITEAG", slug="diplomant", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )
    cours = Cours.objects.create(
        titre="Théologie Systématique 1",
        slug="theologie-1",
        code="TH101",
        discipline=discipline,
    )
    cours.parcours.add(parcours)

    prof_user = User.objects.create_user(
        username="prof_test", email="prof@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    prof = Professeur.objects.create(user=prof_user, nom="MARTIN", prenom="Paul", slug="paul-martin")

    session = SessionAcademique.objects.create(
        nom="Carnaval 2026",
        periode=SessionAcademique.Periode.CARNAVAL,
        annee_academique="2025-2026",
        date_debut=date(2026, 2, 16),
        date_fin=date(2026, 2, 20),
    )

    cours_session = CoursDeSession.objects.create(
        session=session,
        cours=cours,
        enseignant=prof,
    )

    # Création d'un étudiant
    etudiant_user = User.objects.create_user(
        username="etudiant1",
        email="etudiant1@iteag.org",
        password=MOT_DE_PASSE,
        first_name="Jean",
        last_name="VALJEAN",
        role=User.Role.ETUDIANT,
    )
    promo = Promotion.objects.create(nom="Promo 2026", parcours=parcours, annee_debut=2024, annee_fin=2026)
    profil = ProfilEtudiant.objects.create(
        utilisateur=etudiant_user,
        parcours=parcours,
        promotion=promo,
        numero_etudiant="ETU2026001",
    )

    # Inscription au cours
    InscriptionSession.objects.create(etudiant=profil, cours_session=cours_session)

    return session, cours_session, profil


def test_saisie_presence_get_et_post(client, secretaire, session_et_cours):
    session, cours_session, profil = session_et_cours
    client.login(username=secretaire.username, password=MOT_DE_PASSE)

    url = reverse("administration:cours_session_presences", args=[cours_session.pk])

    # 1. Vérification affichage GET
    resp = client.get(url)
    assert resp.status_code == 200
    assert "VALJEAN" in resp.content.decode()

    # 2. Soumission POST pour marquer absent justifié avec motif
    data = {
        f"statut_{profil.pk}": PresenceEtudiant.Statut.ABSENT_JUSTIFIE,
        f"commentaire_{profil.pk}": "Certificat médical fourni",
    }
    resp_post = client.post(url, data, follow=True)
    assert resp_post.status_code == 200

    # Verification en base de données
    presence = PresenceEtudiant.objects.get(cours_session=cours_session, etudiant=profil)
    assert presence.statut == PresenceEtudiant.Statut.ABSENT_JUSTIFIE
    assert presence.commentaire == "Certificat médical fourni"
    assert presence.saisi_par == secretaire


def test_generation_pdf_pv_deliberation(client, secretaire, session_et_cours):
    session, cours_session, profil = session_et_cours
    client.login(username=secretaire.username, password=MOT_DE_PASSE)

    url = reverse("administration:session_pv_deliberation_pdf", args=[session.pk])
    resp = client.get(url)

    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert "pv-deliberation-" in resp["Content-Disposition"]
