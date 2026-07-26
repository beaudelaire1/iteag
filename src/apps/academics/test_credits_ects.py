"""
Tests de la chaîne des crédits ECTS.

Le relevé de notes, la progression et les ECTS restants lisent tous
`CreditECTS`. Or l'enseignant, lui, saisit `Evaluation.ects_valides`. Si les
deux ne sont pas reliés, un étudiant peut valider tous ses cours et garder un
relevé vierge — c'est ce que ces tests verrouillent.
"""

import pytest
from django.urls import reverse

from apps.academics.models import (
    CoursDeSession,
    CreditECTS,
    InscriptionSession,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
)
from apps.accounts.models import User
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.lms.models import Evaluation


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Diplômant", slug="diplomant-ects", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG, ects_requis=180
    )


@pytest.fixture
def enseignant(db):
    utilisateur = User.objects.create_user(
        username="prof_ects", email="prof_ects@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
    )
    return Professeur.objects.create(user=utilisateur, nom="Nathan", prenom="Ruth", slug="ruth-nathan")


@pytest.fixture
def cours_session(db, enseignant):
    discipline = Discipline.objects.create(nom="Dogmatique", slug="dogmatique-ects")
    cours = Cours.objects.create(titre="Doctrine de la grâce", slug="doctrine-grace", discipline=discipline)
    session = SessionAcademique.objects.create(
        nom="Session de Toussaint",
        periode=SessionAcademique.Periode.TOUSSAINT,
        annee_academique="2026-2027",
        date_debut="2026-11-02",
        date_fin="2026-11-07",
    )
    return CoursDeSession.objects.create(session=session, cours=cours, enseignant=enseignant)


@pytest.fixture
def etudiant(db, parcours, cours_session):
    utilisateur = User.objects.create_user(
        username="etu_ects",
        email="etu_ects@iteag.org",
        password="motdepasse-long-12",
        first_name="Sarah",
        last_name="Lubin",
        role=User.Role.ETUDIANT,
    )
    promotion = Promotion.objects.create(nom="Promo ECTS", parcours=parcours, annee_debut=2026, annee_fin=2032)
    profil = ProfilEtudiant.objects.create(
        utilisateur=utilisateur,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-ECTS-001",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )
    InscriptionSession.objects.create(etudiant=profil, cours_session=cours_session)
    return profil


def noter(client, enseignant, evaluation, ects):
    client.force_login(enseignant.user)
    client.post(
        reverse("lms:grade_evaluation", kwargs={"pk": evaluation.pk}),
        {"note": "16", "appreciation": "Travail solide.", "ects_valides": str(ects)},
    )


@pytest.fixture
def evaluation(db, cours_session, etudiant):
    return Evaluation.objects.create(
        etudiant=etudiant,
        cours_session=cours_session,
        statut=Evaluation.StatutEvaluation.SOUMIS,
    )


@pytest.mark.django_db
class TestPublicationCrediteLeReleve:
    """
    Publier une note doit inscrire le crédit au dossier de l'étudiant.

    C'est le moment choisi plutôt que la notation : tant que la note n'est pas
    publiée, elle peut encore être reprise par l'enseignant. Créditer plus tôt
    reviendrait à inscrire au dossier une décision non arrêtée.
    """

    def test_le_credit_est_enregistre_a_la_publication(self, client, enseignant, evaluation, etudiant):
        noter(client, enseignant, evaluation, "2.5")
        client.post(reverse("lms:publish_grades", kwargs={"pk": evaluation.cours_session.pk}))

        credit = CreditECTS.objects.get(etudiant=etudiant)
        assert float(credit.ects_obtenus) == 2.5
        assert credit.source == CreditECTS.SourceCredit.ITEAG
        assert credit.cours == evaluation.cours_session.cours
        assert credit.session == evaluation.cours_session.session

    def test_le_total_de_l_etudiant_suit(self, client, enseignant, evaluation, etudiant):
        """Le compteur affiché à l'étudiant doit refléter ce qui a été validé."""
        noter(client, enseignant, evaluation, "2.5")
        client.post(reverse("lms:publish_grades", kwargs={"pk": evaluation.cours_session.pk}))

        etudiant.refresh_from_db()
        assert float(etudiant.total_ects_acquis) == 2.5
        assert float(etudiant.ects_restants) == 177.5

    def test_une_note_non_publiee_ne_credite_rien(self, client, enseignant, evaluation, etudiant):
        noter(client, enseignant, evaluation, "2.5")
        assert CreditECTS.objects.filter(etudiant=etudiant).count() == 0

    def test_republier_ne_duplique_pas_le_credit(self, client, enseignant, evaluation, etudiant):
        """Une double publication ne doit pas doubler le dossier académique."""
        noter(client, enseignant, evaluation, "2.5")
        url = reverse("lms:publish_grades", kwargs={"pk": evaluation.cours_session.pk})
        client.post(url)
        client.post(url)
        assert CreditECTS.objects.filter(etudiant=etudiant).count() == 1

    def test_zero_ects_ne_cree_pas_de_credit(self, client, enseignant, evaluation, etudiant):
        """Un cours validé sans crédit ne doit pas polluer le relevé d'une ligne vide."""
        noter(client, enseignant, evaluation, "0")
        client.post(reverse("lms:publish_grades", kwargs={"pk": evaluation.cours_session.pk}))
        assert CreditECTS.objects.filter(etudiant=etudiant).count() == 0

    def test_le_credit_apparait_sur_la_page_de_progression(self, client, enseignant, evaluation, etudiant):
        noter(client, enseignant, evaluation, "2.5")
        client.post(reverse("lms:publish_grades", kwargs={"pk": evaluation.cours_session.pk}))

        client.force_login(etudiant.utilisateur)
        reponse = client.get(reverse("etudiant:progress"))
        assert reponse.status_code == 200
        assert "Doctrine de la grâce" in reponse.content.decode()
