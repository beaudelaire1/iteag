"""Les sessions 2027 programmées par migration, sans écraser l'existant."""

import datetime
import importlib

import pytest
from django.apps import apps as registre
from django.utils.text import slugify

from apps.academics.models import CoursDeSession, SessionAcademique
from apps.formations.models import Cours, Discipline, Professeur

migration = importlib.import_module("apps.academics.migrations.0017_sessions_2027")

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def referentiel():
    """Les cinq disciplines de l'ITEAG, présentes en production."""
    for ordre, nom in enumerate(migration.DISCIPLINES, start=1):
        Discipline.objects.create(nom=nom, slug=slugify(nom), ordre=ordre)


def programmer():
    migration.programmer_les_sessions_2027(registre, None)


def test_sans_referentiel_la_migration_ne_fait_rien():
    Discipline.objects.all().delete()

    programmer()

    assert not SessionAcademique.objects.exists()
    assert not Professeur.objects.exists()


def test_les_quatre_sessions_et_leurs_huit_cours_sont_programmes():
    programmer()

    sessions = {s.periode: s for s in SessionAcademique.objects.all()}
    assert set(sessions) == {"carnaval", "paques", "juillet", "toussaint"}
    assert sessions["carnaval"].date_debut == datetime.date(2027, 2, 8)
    assert sessions["paques"].date_fin == datetime.date(2027, 5, 7)
    assert sessions["juillet"].annee_academique == "2026-2027"
    # Rentrée en août : la Toussaint 2027 ouvre l'année suivante.
    assert sessions["toussaint"].annee_academique == "2027-2028"
    assert CoursDeSession.objects.count() == 8

    paques = CoursDeSession.objects.filter(session=sessions["paques"])
    assert {c.modalite for c in paques} == {CoursDeSession.Modalite.DISTANCIEL}
    assert all("vendredi 7 mai" in c.informations_pratiques for c in paques)
    assert all(c.est_inscriptible for c in CoursDeSession.objects.all())


def test_un_enseignant_deja_present_est_repris_tel_quel():
    nisus = Professeur.objects.create(prenom="Alain", nom="Nisus", slug="alain-nisus", biographie="Théologien")

    programmer()

    assert Professeur.objects.filter(nom="Nisus").count() == 1
    assert CoursDeSession.objects.get(cours__titre="Les grands axes de l'éthique biblique").enseignant == nisus


def test_un_nouvel_enseignant_est_cree_sans_fiche_publique():
    programmer()

    blocher = Professeur.objects.get(prenom="Henri", nom="Blocher")
    assert blocher.actif is False


def test_une_session_deja_saisie_n_est_pas_reecrite():
    """Le secrétariat a pu créer la session à la main, avec d'autres dates."""
    saisie = SessionAcademique.objects.create(
        nom="Carnaval 2027 (salle Bethel)",
        periode="carnaval",
        annee_academique="2026-2027",
        date_debut=datetime.date(2027, 2, 9),
        date_fin=datetime.date(2027, 2, 13),
    )

    programmer()

    saisie.refresh_from_db()
    assert saisie.nom == "Carnaval 2027 (salle Bethel)"
    assert saisie.date_debut == datetime.date(2027, 2, 9)
    assert SessionAcademique.objects.filter(periode="carnaval").count() == 1
    assert saisie.cours_de_session.count() == 2


def test_un_cours_existant_est_reutilise():
    discipline = Discipline.objects.get(nom="Nouveau Testament")
    hebreux = Cours.objects.create(
        titre="Étude de l'épître aux Hébreux", slug="etude-de-lepitre-aux-hebreux", discipline=discipline
    )

    programmer()

    assert Cours.objects.filter(titre="Étude de l'épître aux Hébreux").count() == 1
    assert CoursDeSession.objects.filter(cours=hebreux).exists()


def test_rejouer_la_migration_ne_duplique_rien():
    programmer()
    programmer()

    assert SessionAcademique.objects.count() == 4
    assert CoursDeSession.objects.count() == 8
    assert Professeur.objects.filter(prenom="Karim", nom="Arezki").count() == 1
