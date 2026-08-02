"""Publier une copie sans attendre que tout le cours soit corrigé.

La publication n'existait qu'en lot, par cours. Sur une session de trente
inscrits, le premier rendu restait invisible de son auteur jusqu'à la
correction de la dernière copie — des semaines, sans raison.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import CoursDeSession, ProfilEtudiant, Promotion, SessionAcademique
from apps.accounts.models import User
from apps.core.models import Notification
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.lms.models import Evaluation

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"


@pytest.fixture
def enseignant(db):
    compte = User.objects.create_user(
        username="prof_notes", email="prof@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    return Professeur.objects.create(nom="Nisus", prenom="Alain", slug="alain-nisus-notes", user=compte)


@pytest.fixture
def offre(db, enseignant):
    discipline = Discipline.objects.create(nom="Théologie", slug="theologie-notes")
    cours = Cours.objects.create(titre="Herméneutique", slug="hermeneutique-notes", discipline=discipline, ects=5)
    aujourd_hui = timezone.localdate()
    session = SessionAcademique.objects.create(
        nom="Session en cours",
        date_debut=aujourd_hui - timedelta(days=10),
        date_fin=aujourd_hui + timedelta(days=20),
    )
    return CoursDeSession.objects.create(session=session, cours=cours, enseignant=enseignant)


@pytest.fixture
def etudiant(db):
    parcours = Parcours.objects.create(nom="Bachelor", slug="bachelor-notes", type_parcours=Parcours.TypeParcours.LIBRE)
    promotion = Promotion.objects.create(nom="Promo notes", parcours=parcours, annee_debut=2026, annee_fin=2029)
    compte = User.objects.create_user(
        username="etu_notes", email="etu@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
    )
    return ProfilEtudiant.objects.create(
        utilisateur=compte,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU2026777",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )


@pytest.fixture
def copie_notee(offre, etudiant):
    return Evaluation.objects.create(
        cours_session=offre,
        etudiant=etudiant,
        note=Decimal("15.0"),
        ects_valides=Decimal("5.0"),
        statut=Evaluation.StatutEvaluation.NOTE,
    )


def _publier(client, evaluation):
    return client.post(reverse("lms:publish_grade", args=[evaluation.pk]))


class TestPublicationUnitaire:
    def test_l_enseignant_publie_une_copie_seule(self, client, enseignant, copie_notee):
        client.force_login(enseignant.user)

        _publier(client, copie_notee)

        copie_notee.refresh_from_db()
        assert copie_notee.statut == Evaluation.StatutEvaluation.PUBLIE

    def test_l_etudiant_est_averti(self, client, enseignant, copie_notee, etudiant):
        client.force_login(enseignant.user)
        _publier(client, copie_notee)

        avis = Notification.objects.filter(destinataire=etudiant.utilisateur)
        assert avis.count() == 1
        assert avis.get().type_notification == Notification.Type.NOTE_PUBLIEE

    def test_le_credit_ects_est_porte_au_dossier(self, client, enseignant, copie_notee, etudiant):
        """Publier, c'est arrêter un résultat : sans le crédit, le relevé reste vierge."""
        client.force_login(enseignant.user)
        _publier(client, copie_notee)

        assert etudiant.credits_ects.filter(ects_obtenus=Decimal("5.0")).exists()

    def test_les_autres_copies_du_cours_ne_bougent_pas(self, client, enseignant, offre, copie_notee, etudiant, db):
        """C'est tout l'objet : publier l'une n'oblige pas à publier les autres."""
        autre_compte = User.objects.create_user(
            username="etu2", email="etu2@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
        )
        autre = ProfilEtudiant.objects.create(
            utilisateur=autre_compte,
            parcours=etudiant.parcours,
            promotion=etudiant.promotion,
            numero_etudiant="ETU2026778",
        )
        en_attente = Evaluation.objects.create(
            cours_session=offre, etudiant=autre, statut=Evaluation.StatutEvaluation.SOUMIS
        )

        client.force_login(enseignant.user)
        _publier(client, copie_notee)

        en_attente.refresh_from_db()
        assert en_attente.statut == Evaluation.StatutEvaluation.SOUMIS

    def test_une_copie_non_notee_ne_se_publie_pas(self, client, enseignant, offre, etudiant):
        """Publier une copie sans note afficherait un résultat vide à l'étudiant."""
        copie = Evaluation.objects.create(
            cours_session=offre, etudiant=etudiant, statut=Evaluation.StatutEvaluation.SOUMIS
        )
        client.force_login(enseignant.user)

        _publier(client, copie)

        copie.refresh_from_db()
        assert copie.statut == Evaluation.StatutEvaluation.SOUMIS
        assert not Notification.objects.filter(destinataire=etudiant.utilisateur).exists()

    def test_on_ne_publie_pas_la_copie_d_un_autre_enseignant(self, client, db, copie_notee, etudiant):
        """Le cours fait autorité : un identifiant deviné ne suffit pas."""
        intrus_compte = User.objects.create_user(
            username="intrus_prof", email="ip@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
        )
        Professeur.objects.create(nom="Intrus", prenom="Prof", slug="intrus-prof", user=intrus_compte)

        client.force_login(intrus_compte)
        reponse = _publier(client, copie_notee)

        assert reponse.status_code == 404
        copie_notee.refresh_from_db()
        assert copie_notee.statut == Evaluation.StatutEvaluation.NOTE

    def test_un_etudiant_ne_publie_pas_sa_propre_note(self, client, copie_notee, etudiant):
        client.force_login(etudiant.utilisateur)
        reponse = _publier(client, copie_notee)

        assert reponse.status_code in (302, 403, 404)
        copie_notee.refresh_from_db()
        assert copie_notee.statut == Evaluation.StatutEvaluation.NOTE

    def test_la_publication_exige_un_post(self, client, enseignant, copie_notee):
        client.force_login(enseignant.user)
        assert client.get(reverse("lms:publish_grade", args=[copie_notee.pk])).status_code == 405

    def test_l_ecran_du_cours_propose_de_publier_une_copie_notee(self, client, enseignant, offre, copie_notee):
        client.force_login(enseignant.user)
        contenu = client.get(reverse("lms:course_detail", args=[offre.pk])).content.decode()
        assert reverse("lms:publish_grade", args=[copie_notee.pk]) in contenu
