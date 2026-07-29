"""
Espace enseignant : calendrier d'évaluation, notation, copies.

Trois manques traités ici, et chacun a sa manière de coûter cher :

* une note posée n'était plus modifiable — corriger une faute de frappe
  demandait un passage par l'administration Django ;
* la remise n'avait pas de fenêtre — un devoir pouvait arriver après la
  publication des notes des autres ;
* la copie d'un étudiant était servie par une adresse média, donc lisible par
  qui en connaissait le chemin.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
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
from apps.core.models import Notification
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.lms.models import Evaluation


@pytest.fixture
def professeur(db):
    utilisateur = User.objects.create_user(
        username="prof_eval", email="pe@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
    )
    return Professeur.objects.create(user=utilisateur, nom="Nestor", prenom="Alix", slug="alix-nestor")


@pytest.fixture
def cours_session(db, professeur):
    parcours = Parcours.objects.create(
        nom="Licence", slug="licence-eval", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )
    session = SessionAcademique.objects.create(
        nom="Session d'essai",
        periode=SessionAcademique.Periode.PAQUES,
        annee_academique="2025-2026",
        date_debut=timezone.localdate(),
        date_fin=timezone.localdate() + timedelta(days=10),
    )
    cours = Cours.objects.create(
        titre="Exégèse",
        slug="exegese-eval",
        discipline=Discipline.objects.create(nom="Exégèse", slug="exegese-d"),
        ects=Decimal("5.0"),
    )
    cours.parcours.add(parcours)
    return CoursDeSession.objects.create(session=session, cours=cours, enseignant=professeur)


@pytest.fixture
def etudiant(db, cours_session):
    parcours = Parcours.objects.first()
    promotion = Promotion.objects.create(nom="Promo eval", parcours=parcours, annee_debut=2025, annee_fin=2028)
    utilisateur = User.objects.create_user(
        username="etu_eval", email="ee@iteag.org", password="motdepasse-long-12", role=User.Role.ETUDIANT
    )
    profil = ProfilEtudiant.objects.create(
        utilisateur=utilisateur,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-EVAL-1",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )
    InscriptionSession.objects.create(etudiant=profil, cours_session=cours_session)
    return profil


@pytest.fixture
def evaluation(db, etudiant, cours_session):
    return Evaluation.objects.create(
        etudiant=etudiant,
        cours_session=cours_session,
        type_evaluation=Evaluation.TypeEvaluation.DEVOIR,
        statut=Evaluation.StatutEvaluation.EN_ATTENTE,
    )


def copie(nom="devoir.pdf"):
    return SimpleUploadedFile(nom, b"%PDF-1.4 copie", content_type="application/pdf")


# ══════════════════════════════════════════════
# La fenêtre de remise
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestFenetreDeRemise:
    def test_sans_bornes_le_depot_reste_ouvert(self, cours_session):
        """Les cours existants ne doivent pas se fermer du jour au lendemain."""
        assert cours_session.depot_est_ouvert is True
        assert cours_session.motif_depot_ferme == ""

    def test_avant_l_ouverture_le_depot_est_refuse(self, cours_session):
        cours_session.depot_ouverture = timezone.now() + timedelta(days=2)
        cours_session.save()
        assert cours_session.depot_est_ouvert is False
        assert "ouvrira" in cours_session.motif_depot_ferme

    def test_apres_la_fermeture_le_depot_est_refuse(self, cours_session):
        cours_session.depot_fermeture = timezone.now() - timedelta(hours=1)
        cours_session.save()
        assert cours_session.depot_est_ouvert is False
        assert "close" in cours_session.motif_depot_ferme

    def test_l_etudiant_ne_peut_pas_deposer_hors_fenetre(self, client, cours_session, etudiant, evaluation):
        """
        Le contrôle porte sur la vue, pas sur le gabarit : masquer le bouton
        laisserait passer un envoi direct.
        """
        cours_session.depot_fermeture = timezone.now() - timedelta(hours=1)
        cours_session.save()

        client.force_login(etudiant.utilisateur)
        client.post(reverse("etudiant:submit_evaluation", args=[evaluation.pk]), {"fichier_soumis": copie()})

        evaluation.refresh_from_db()
        assert evaluation.statut == Evaluation.StatutEvaluation.EN_ATTENTE
        assert not evaluation.fichier_soumis

    def test_l_etudiant_depose_dans_la_fenetre(self, client, cours_session, etudiant, evaluation):
        cours_session.depot_ouverture = timezone.now() - timedelta(days=1)
        cours_session.depot_fermeture = timezone.now() + timedelta(days=1)
        cours_session.save()

        client.force_login(etudiant.utilisateur)
        client.post(reverse("etudiant:submit_evaluation", args=[evaluation.pk]), {"fichier_soumis": copie()})

        evaluation.refresh_from_db()
        assert evaluation.statut == Evaluation.StatutEvaluation.SOUMIS
        assert evaluation.fichier_soumis
        assert Notification.objects.filter(
            destinataire=etudiant.utilisateur,
            titre__startswith="Travail remis",
        ).exists()
        assert Notification.objects.filter(
            destinataire=cours_session.enseignant.user,
            titre__startswith="Nouveau travail remis",
        ).exists()

    def test_l_enseignant_ferme_la_remise_en_un_clic(self, client, professeur, cours_session):
        client.force_login(professeur.user)
        client.post(reverse("lms:basculer_depot", args=[cours_session.pk]))
        cours_session.refresh_from_db()
        assert cours_session.depot_est_ouvert is False

    def test_l_enseignant_rouvre_la_remise(self, client, professeur, cours_session):
        cours_session.depot_fermeture = timezone.now() - timedelta(hours=1)
        cours_session.save()

        client.force_login(professeur.user)
        client.post(reverse("lms:basculer_depot", args=[cours_session.pk]))
        cours_session.refresh_from_db()
        assert cours_session.depot_est_ouvert is True

    def test_une_fenetre_inversee_est_refusee(self, client, professeur, cours_session):
        """Fermer avant d'ouvrir n'accepterait jamais rien, sans dire pourquoi."""
        client.force_login(professeur.user)
        maintenant = timezone.now()
        reponse = client.post(
            reverse("lms:parametres_evaluation", args=[cours_session.pk]),
            {
                "date_examen": "",
                "depot_ouverture": (maintenant + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M"),
                "depot_fermeture": (maintenant + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            },
        )
        assert reponse.status_code == 200  # formulaire réaffiché
        cours_session.refresh_from_db()
        assert cours_session.depot_ouverture is None

    def test_l_enseignant_fixe_la_date_d_examen(self, client, professeur, cours_session):
        client.force_login(professeur.user)
        quand = (timezone.now() + timedelta(days=20)).replace(second=0, microsecond=0)
        client.post(
            reverse("lms:parametres_evaluation", args=[cours_session.pk]),
            {"date_examen": quand.strftime("%Y-%m-%dT%H:%M"), "depot_ouverture": "", "depot_fermeture": ""},
        )
        cours_session.refresh_from_db()
        assert cours_session.date_examen is not None


# ══════════════════════════════════════════════
# Notation et correction
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestNotation:
    def test_une_note_deja_posee_reste_modifiable(self, client, professeur, evaluation):
        """C'est le cas d'usage le plus banal : corriger une saisie."""
        evaluation.statut = Evaluation.StatutEvaluation.NOTE
        evaluation.note = Decimal("12.0")
        evaluation.save()

        client.force_login(professeur.user)
        client.post(
            reverse("lms:grade_evaluation", args=[evaluation.pk]),
            {"note": "15.5", "appreciation": "Corrigé après relecture.", "ects_valides": "5.0"},
        )
        evaluation.refresh_from_db()
        assert evaluation.note == Decimal("15.50")

    def test_une_note_publiee_reste_publiee_apres_correction(self, client, professeur, evaluation):
        """La repasser en « notée » la retirerait du relevé sans prévenir personne."""
        evaluation.statut = Evaluation.StatutEvaluation.PUBLIE
        evaluation.note = Decimal("9.0")
        evaluation.save()

        client.force_login(professeur.user)
        client.post(
            reverse("lms:grade_evaluation", args=[evaluation.pk]),
            {"note": "11.0", "appreciation": "Erreur de report.", "ects_valides": "5.0"},
        )
        evaluation.refresh_from_db()
        assert evaluation.note == Decimal("11.00")
        assert evaluation.statut == Evaluation.StatutEvaluation.PUBLIE

    def test_l_enseignant_joint_la_copie_corrigee(self, client, professeur, evaluation):
        evaluation.statut = Evaluation.StatutEvaluation.SOUMIS
        evaluation.save()

        client.force_login(professeur.user)
        client.post(
            reverse("lms:grade_evaluation", args=[evaluation.pk]),
            {
                "note": "14.0",
                "appreciation": "Voir les annotations.",
                "ects_valides": "5.0",
                "fichier_corrige": copie("corrige.pdf"),
            },
        )
        evaluation.refresh_from_db()
        assert evaluation.fichier_corrige
        assert evaluation.statut == Evaluation.StatutEvaluation.NOTE

    def test_un_enseignant_ne_note_pas_le_cours_d_un_autre(self, client, db, evaluation):
        intrus_utilisateur = User.objects.create_user(
            username="autre_prof", email="ap@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
        )
        Professeur.objects.create(user=intrus_utilisateur, nom="Autre", prenom="Prof", slug="autre-prof")

        client.force_login(intrus_utilisateur)
        reponse = client.get(reverse("lms:grade_evaluation", args=[evaluation.pk]))
        assert reponse.status_code == 404


# ══════════════════════════════════════════════
# Les copies ne sont pas des documents publics
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestConfidentialiteDesCopies:
    def test_l_espace_documents_liste_les_copies(self, client, professeur, evaluation):
        evaluation.fichier_soumis.save("devoir.pdf", copie(), save=True)
        client.force_login(professeur.user)
        contenu = client.get(reverse("lms:documents")).content.decode()
        assert evaluation.etudiant.numero_etudiant in contenu

    def test_un_visiteur_ne_telecharge_pas_une_copie(self, client, evaluation):
        evaluation.fichier_soumis.save("devoir.pdf", copie(), save=True)
        reponse = client.get(reverse("lms:evaluation_fichier", args=[evaluation.pk, "remise"]))
        assert reponse.status_code in (302, 403)

    def test_un_enseignant_etranger_ne_telecharge_pas_la_copie(self, client, db, evaluation):
        """Le contrôle porte sur la copie, pas seulement sur la page qui y mène."""
        intrus_utilisateur = User.objects.create_user(
            username="curieux", email="c@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
        )
        Professeur.objects.create(user=intrus_utilisateur, nom="Curieux", prenom="Jean", slug="jean-curieux")
        evaluation.fichier_soumis.save("devoir.pdf", copie(), save=True)

        client.force_login(intrus_utilisateur)
        reponse = client.get(reverse("lms:evaluation_fichier", args=[evaluation.pk, "remise"]))
        assert reponse.status_code == 404

    def test_l_enseignant_du_cours_telecharge_la_copie(self, client, professeur, evaluation):
        evaluation.fichier_soumis.save("devoir.pdf", copie(), save=True)
        client.force_login(professeur.user)
        assert client.get(reverse("lms:evaluation_fichier", args=[evaluation.pk, "remise"])).status_code == 200
