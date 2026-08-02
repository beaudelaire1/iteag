"""L'espace documents doit laisser consulter ses notes, pas seulement les éditer.

Il fallait générer un relevé PDF pour savoir ce qu'il contiendrait, ou changer
d'écran. Les notes publiées se lisent désormais sur place, avec le total d'ECTS
acquis — et seulement les publiées : une note posée sans être publiée n'est pas
un résultat arrêté, l'afficher reviendrait à la divulguer avant l'heure.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import CoursDeSession, ProfilEtudiant, Promotion, SessionAcademique
from apps.accounts.models import User
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.lms.models import Evaluation

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"


@pytest.fixture
def etudiant(db):
    parcours = Parcours.objects.create(nom="Bachelor", slug="bach-doc", type_parcours=Parcours.TypeParcours.LIBRE)
    promotion = Promotion.objects.create(nom="Promo doc", parcours=parcours, annee_debut=2026, annee_fin=2029)
    compte = User.objects.create_user(
        username="etu_doc", email="ed@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
    )
    return ProfilEtudiant.objects.create(
        utilisateur=compte,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU2026950",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )


@pytest.fixture
def offre(db):
    compte = User.objects.create_user(
        username="prof_doc", email="pdoc@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    professeur = Professeur.objects.create(nom="Nisus", prenom="Alain", slug="nisus-doc", user=compte)
    discipline = Discipline.objects.create(nom="Théologie", slug="theo-doc")
    cours = Cours.objects.create(titre="Herméneutique", slug="herm-doc", discipline=discipline)
    aujourd_hui = timezone.localdate()
    session = SessionAcademique.objects.create(
        nom="Session 2026", date_debut=aujourd_hui - timedelta(days=5), date_fin=aujourd_hui + timedelta(days=25)
    )
    return CoursDeSession.objects.create(session=session, cours=cours, enseignant=professeur)


def test_les_notes_publiees_se_lisent_dans_l_espace_documents(client, etudiant, offre):
    evaluation = Evaluation.objects.create(
        cours_session=offre,
        etudiant=etudiant,
        note=Decimal("15.0"),
        ects_valides=Decimal("5.0"),
        statut=Evaluation.StatutEvaluation.PUBLIE,
        date_notation=timezone.now(),
    )

    client.force_login(etudiant.utilisateur)
    reponse = client.get(reverse("documents:list"))
    contenu = reponse.content.decode()

    # Le rendu du nombre dépend de la locale : c'est la présence de la note
    # dans l'écran qui compte, pas sa virgule décimale.
    assert list(reponse.context["notes_publiees"]) == [evaluation]
    assert "Mes notes" in contenu
    assert "Herméneutique" in contenu
    assert "/20" in contenu


def test_une_note_non_publiee_ne_parait_pas(client, etudiant, offre):
    """L'afficher reviendrait à divulguer un résultat que l'enseignant n'a pas arrêté."""
    Evaluation.objects.create(
        cours_session=offre,
        etudiant=etudiant,
        note=Decimal("8.0"),
        statut=Evaluation.StatutEvaluation.NOTE,
    )

    client.force_login(etudiant.utilisateur)
    contenu = client.get(reverse("documents:list")).content.decode()

    assert "Aucune note publiée" in contenu
    assert "8.0/20" not in contenu


def test_l_ecran_reste_lisible_sans_aucune_note(client, etudiant):
    client.force_login(etudiant.utilisateur)
    contenu = client.get(reverse("documents:list")).content.decode()
    assert "Aucune note publiée pour le moment." in contenu


def test_les_notes_d_un_autre_etudiant_ne_paraissent_pas(client, etudiant, offre, db):
    autre_compte = User.objects.create_user(
        username="autre_etu", email="ae@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
    )
    autre = ProfilEtudiant.objects.create(
        utilisateur=autre_compte,
        parcours=etudiant.parcours,
        promotion=etudiant.promotion,
        numero_etudiant="ETU2026951",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )
    Evaluation.objects.create(
        cours_session=offre,
        etudiant=autre,
        note=Decimal("19.0"),
        statut=Evaluation.StatutEvaluation.PUBLIE,
        date_notation=timezone.now(),
    )

    client.force_login(etudiant.utilisateur)
    contenu = client.get(reverse("documents:list")).content.decode()

    assert "19.0/20" not in contenu
    assert "Aucune note publiée" in contenu
