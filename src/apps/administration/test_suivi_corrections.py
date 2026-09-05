"""
Une copie remise et jamais notée n'alertait personne.

L'enseignant la voyait dans son propre tableau, l'étudiant attendait sans rien
savoir, et le secrétariat — celui à qui l'on vient se plaindre — n'avait ni
moyen de constater le retard ni moyen de relancer.

Deux principes tiennent ce suivi, et ces tests les gardent :

- **le retard reste interne.** L'étudiant est prévenu que sa copie est arrivée,
  jamais qu'elle traîne : le lui dire l'inquiéterait sans rien lui permettre de
  faire ;
- **la relance part d'un geste.** Aucune horloge n'écrit à l'enseignant.
"""

from datetime import timedelta

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
        username="prof_corr", email="pc@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
    )
    return Professeur.objects.create(nom="Nisus", prenom="Alain", slug="nisus-corr", user=compte)


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="sec_corr", email="sc@iteag.org", password=MOT_DE_PASSE, role=User.Role.SECRETARIAT
    )


@pytest.fixture
def cours_session(db, enseignant):
    parcours = Parcours.objects.create(
        nom="Licence", slug="lic-corr", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )
    discipline = Discipline.objects.create(nom="Homilétique", slug="homiletique-corr")
    cours = Cours.objects.create(titre="Prédication", slug="predication-corr", discipline=discipline)
    session = SessionAcademique.objects.create(
        nom="Session 2026",
        date_debut=timezone.now().date() - timedelta(days=60),
        date_fin=timezone.now().date() + timedelta(days=60),
    )
    Promotion.objects.create(nom="Promo corr", parcours=parcours, annee_debut=2026, annee_fin=2029)
    return CoursDeSession.objects.create(session=session, cours=cours, enseignant=enseignant, delai_correction_jours=15)


@pytest.fixture
def etudiant(db, cours_session):
    compte = User.objects.create_user(
        username="etu_corr", email="ec@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
    )
    return ProfilEtudiant.objects.create(utilisateur=compte, numero_etudiant="ETU-CORR-1")


def copie(cours_session, etudiant, *, jours, statut=Evaluation.StatutEvaluation.SOUMIS):
    return Evaluation.objects.create(
        etudiant=etudiant,
        cours_session=cours_session,
        type_evaluation=Evaluation.TypeEvaluation.DEVOIR,
        statut=statut,
        date_soumission=timezone.now() - timedelta(days=jours),
    )


class TestRetardDeCorrection:
    def test_une_copie_au_dela_du_delai_du_cours_est_en_retard(self, cours_session, etudiant):
        assert copie(cours_session, etudiant, jours=20).correction_en_retard()

    def test_une_copie_dans_les_temps_ne_l_est_pas(self, cours_session, etudiant):
        assert not copie(cours_session, etudiant, jours=3).correction_en_retard()

    def test_un_delai_a_zero_desactive_le_suivi(self, cours_session, etudiant):
        """Certains cours n'ont pas à être suivis ; zéro le dit explicitement."""
        cours_session.delai_correction_jours = 0
        cours_session.save(update_fields=["delai_correction_jours"])

        assert not copie(cours_session, etudiant, jours=90).correction_en_retard()

    def test_une_copie_deja_notee_n_est_jamais_en_retard(self, cours_session, etudiant):
        notee = copie(cours_session, etudiant, jours=90, statut=Evaluation.StatutEvaluation.NOTE)
        assert not notee.correction_en_retard()


class TestEcranDuSecretariat:
    def test_le_secretariat_voit_les_copies_en_attente(self, client, secretaire, cours_session, etudiant):
        copie(cours_session, etudiant, jours=20)
        client.force_login(secretaire)

        reponse = client.get(reverse("administration:corrections"))

        assert reponse.status_code == 200
        assert "ETU-CORR-1" in reponse.content.decode() or "Prédication" in reponse.content.decode()

    def test_un_enseignant_n_y_accede_pas(self, client, cours_session, etudiant, enseignant):
        client.force_login(enseignant.user)
        assert client.get(reverse("administration:corrections")).status_code in (302, 403)

    def test_le_filtre_retard_ecarte_les_copies_recentes(self, client, secretaire, cours_session, etudiant):
        copie(cours_session, etudiant, jours=2)
        client.force_login(secretaire)

        reponse = client.get(reverse("administration:corrections"), {"etat": "retard"})

        assert "Aucune copie en retard" in reponse.content.decode()


class TestRelance:
    def test_la_relance_previent_l_enseignant(self, client, secretaire, cours_session, etudiant, enseignant):
        attendue = copie(cours_session, etudiant, jours=20)
        client.force_login(secretaire)

        reponse = client.post(reverse("administration:correction_relance", args=[attendue.pk]))

        assert reponse.status_code == 302
        assert Notification.objects.filter(
            destinataire=enseignant.user, titre__contains="attente de correction"
        ).exists()

    def test_la_relance_ne_dit_rien_a_l_etudiant(self, client, secretaire, cours_session, etudiant):
        """Le retard est une affaire entre le secrétariat et l'enseignant."""
        attendue = copie(cours_session, etudiant, jours=20)
        client.force_login(secretaire)
        client.post(reverse("administration:correction_relance", args=[attendue.pk]))

        assert not Notification.objects.filter(
            destinataire=etudiant.utilisateur, titre__contains="attente de correction"
        ).exists()

    def test_relancer_une_copie_deja_notee_est_refuse(self, client, secretaire, cours_session, etudiant, enseignant):
        notee = copie(cours_session, etudiant, jours=20, statut=Evaluation.StatutEvaluation.NOTE)
        client.force_login(secretaire)

        client.post(reverse("administration:correction_relance", args=[notee.pk]))

        assert not Notification.objects.filter(destinataire=enseignant.user).exists()
