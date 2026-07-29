"""
Tests du portail enseignant présentiel.

Ces vues n'étaient couvertes qu'indirectement. L'enjeu est le même que pour la
formation vidéo : un enseignant n'agit que sur ses propres cours.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.academics.models import CoursDeSession, InscriptionSession, ProfilEtudiant, Promotion, SessionAcademique
from apps.accounts.models import User
from apps.core.models import Notification
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.lms.models import Annonce, Evaluation, RessourcePedagogique


@pytest.fixture
def discipline(db):
    return Discipline.objects.create(nom="Nouveau Testament", slug="nouveau-testament")


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Diplômant", slug="diplomant-lms", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )


@pytest.fixture
def enseignant(db):
    utilisateur = User.objects.create_user(
        username="prof_lms", email="prof_lms@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
    )
    return Professeur.objects.create(user=utilisateur, nom="Guillet", prenom="Stéphane", slug="stephane-guillet")


@pytest.fixture
def autre_enseignant(db):
    utilisateur = User.objects.create_user(
        username="prof_lms2", email="prof_lms2@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
    )
    return Professeur.objects.create(user=utilisateur, nom="Eugène", prenom="Cédric", slug="cedric-eugene")


@pytest.fixture
def cours_session(db, discipline, enseignant):
    cours = Cours.objects.create(titre="L'Évangile de Jean", slug="evangile-jean", discipline=discipline)
    session = SessionAcademique.objects.create(
        nom="Session de Pâques",
        periode=SessionAcademique.Periode.PAQUES,
        annee_academique="2026-2027",
        date_debut="2027-04-05",
        date_fin="2027-04-10",
    )
    return CoursDeSession.objects.create(session=session, cours=cours, enseignant=enseignant)


@pytest.fixture
def etudiant_inscrit(db, parcours, cours_session):
    utilisateur = User.objects.create_user(
        username="etu_lms",
        email="etu_lms@iteag.org",
        password="motdepasse-long-12",
        first_name="Jean",
        last_name="Petit",
        role=User.Role.ETUDIANT,
    )
    promotion = Promotion.objects.create(nom="Promo LMS", parcours=parcours, annee_debut=2026, annee_fin=2032)
    profil = ProfilEtudiant.objects.create(
        utilisateur=utilisateur, parcours=parcours, promotion=promotion, numero_etudiant="ETU-LMS-001"
    )
    InscriptionSession.objects.create(etudiant=profil, cours_session=cours_session)
    return profil


@pytest.mark.django_db
class TestPagesDuPortail:
    @pytest.mark.parametrize(
        "nom_url", ["lms:dashboard", "lms:courses_list", "lms:evaluations_list", "lms:annonces_list"]
    )
    def test_les_pages_repondent(self, client, enseignant, nom_url):
        client.force_login(enseignant.user)
        assert client.get(reverse(nom_url)).status_code == 200

    def test_le_detail_d_un_cours(self, client, enseignant, cours_session, etudiant_inscrit):
        client.force_login(enseignant.user)
        reponse = client.get(reverse("lms:course_detail", kwargs={"pk": cours_session.pk}))
        assert reponse.status_code == 200
        assert "Petit" in reponse.content.decode()

    def test_le_cours_d_un_autre_est_inaccessible(self, client, autre_enseignant, cours_session):
        client.force_login(autre_enseignant.user)
        assert client.get(reverse("lms:course_detail", kwargs={"pk": cours_session.pk})).status_code == 404

    def test_un_etudiant_est_refuse(self, client, etudiant_inscrit):
        client.force_login(etudiant_inscrit.utilisateur)
        assert client.get(reverse("lms:dashboard")).status_code in (302, 403)

    def test_un_enseignant_sans_fiche_ne_plante_pas(self, client, db):
        """Un compte enseignant sans fiche professeur doit voir une page vide, pas une erreur."""
        utilisateur = User.objects.create_user(
            username="prof_sans_fiche",
            email="psf@iteag.org",
            password="motdepasse-long-12",
            role=User.Role.ENSEIGNANT,
        )
        client.force_login(utilisateur)
        assert client.get(reverse("lms:dashboard")).status_code == 200


@pytest.mark.django_db
class TestRessourcesEtAnnonces:
    def test_depot_d_une_ressource(
        self,
        client,
        enseignant,
        cours_session,
        etudiant_inscrit,
        tmp_path,
        settings,
    ):
        settings.MEDIA_ROOT = tmp_path
        client.force_login(enseignant.user)
        client.post(
            reverse("lms:resource_upload", kwargs={"cours_pk": cours_session.pk}),
            {
                "titre": "Plan du cours",
                "description": "Le déroulé de la semaine.",
                "fichier": SimpleUploadedFile("plan.pdf", b"%PDF-1.7 contenu"),
                "visible_etudiants": "on",
            },
        )
        ressource = RessourcePedagogique.objects.get(cours_session=cours_session)
        assert ressource.titre == "Plan du cours"
        assert ressource.uploade_par == enseignant.user
        # Type et taille sont déduits du fichier, pas saisis.
        assert ressource.type_fichier == "PDF"
        assert ressource.taille > 0
        assert Notification.objects.filter(
            destinataire=etudiant_inscrit.utilisateur,
            type_notification=Notification.Type.NOUVELLE_RESSOURCE,
        ).exists()

    def test_on_ne_depose_pas_sur_le_cours_d_un_autre(
        self, client, autre_enseignant, cours_session, tmp_path, settings
    ):
        settings.MEDIA_ROOT = tmp_path
        client.force_login(autre_enseignant.user)
        reponse = client.post(
            reverse("lms:resource_upload", kwargs={"cours_pk": cours_session.pk}),
            {"titre": "Intrusion", "fichier": SimpleUploadedFile("x.pdf", b"%PDF")},
        )
        assert reponse.status_code == 404
        assert RessourcePedagogique.objects.count() == 0

    def test_modification_et_suppression_d_une_ressource(
        self, client, enseignant, autre_enseignant, cours_session, tmp_path, settings
    ):
        settings.MEDIA_ROOT = tmp_path
        ressource = RessourcePedagogique.objects.create(
            cours_session=cours_session,
            uploade_par=enseignant.user,
            titre="Document initial",
            fichier=SimpleUploadedFile("initial.pdf", b"%PDF-1.7"),
        )
        client.force_login(autre_enseignant.user)
        assert client.get(reverse("lms:resource_update", kwargs={"pk": ressource.pk})).status_code == 404

        client.force_login(enseignant.user)
        response = client.post(reverse("lms:resource_delete", kwargs={"pk": ressource.pk}))
        assert response.status_code == 302
        assert not RessourcePedagogique.objects.filter(pk=ressource.pk).exists()

    def test_publication_d_une_annonce(self, client, enseignant, cours_session, etudiant_inscrit):
        client.force_login(enseignant.user)
        client.post(
            reverse("lms:announcement_create", kwargs={"cours_pk": cours_session.pk}),
            {"titre": "Consignes de session", "contenu": "Apportez votre Bible."},
        )
        annonce = Annonce.objects.get(cours_session=cours_session)
        assert annonce.auteur == enseignant.user
        assert Notification.objects.filter(
            destinataire=etudiant_inscrit.utilisateur,
            type_notification=Notification.Type.ANNONCE,
        ).exists()

    def test_modification_d_une_annonce(self, client, enseignant, cours_session):
        annonce = Annonce.objects.create(
            cours_session=cours_session, auteur=enseignant.user, titre="Avant", contenu="…"
        )
        client.force_login(enseignant.user)
        client.post(
            reverse("lms:announcement_update", kwargs={"pk": annonce.pk}),
            {"titre": "Après", "contenu": "Texte révisé."},
        )
        annonce.refresh_from_db()
        assert annonce.titre == "Après"

    def test_on_ne_modifie_pas_l_annonce_d_un_autre(self, client, autre_enseignant, cours_session, enseignant):
        annonce = Annonce.objects.create(
            cours_session=cours_session, auteur=enseignant.user, titre="Privée", contenu="…"
        )
        client.force_login(autre_enseignant.user)
        assert (
            client.post(
                reverse("lms:announcement_update", kwargs={"pk": annonce.pk}),
                {"titre": "Détournée", "contenu": "…"},
            ).status_code
            == 404
        )

    def test_suppression_d_une_annonce(self, client, enseignant, cours_session):
        annonce = Annonce.objects.create(
            cours_session=cours_session,
            auteur=enseignant.user,
            titre="À supprimer",
            contenu="Information périmée.",
        )
        client.force_login(enseignant.user)
        response = client.post(reverse("lms:announcement_delete", kwargs={"pk": annonce.pk}))
        assert response.status_code == 302
        assert not Annonce.objects.filter(pk=annonce.pk).exists()


@pytest.mark.django_db
class TestNotation:
    @pytest.fixture
    def evaluation(self, db, cours_session, etudiant_inscrit):
        return Evaluation.objects.create(
            etudiant=etudiant_inscrit,
            cours_session=cours_session,
            statut=Evaluation.StatutEvaluation.SOUMIS,
        )

    def test_saisie_d_une_note(self, client, enseignant, evaluation):
        client.force_login(enseignant.user)
        client.post(
            reverse("lms:grade_evaluation", kwargs={"pk": evaluation.pk}),
            {"note": "15.5", "appreciation": "Travail sérieux.", "ects_valides": "2.5"},
        )
        evaluation.refresh_from_db()
        assert evaluation.statut == Evaluation.StatutEvaluation.NOTE
        assert evaluation.date_notation is not None

    def test_on_ne_note_pas_l_etudiant_d_un_autre(self, client, autre_enseignant, evaluation):
        client.force_login(autre_enseignant.user)
        assert (
            client.post(
                reverse("lms:grade_evaluation", kwargs={"pk": evaluation.pk}),
                {"note": "20", "ects_valides": "2.5"},
            ).status_code
            == 404
        )

    def test_publication_groupee_des_notes(self, client, enseignant, cours_session, evaluation):
        evaluation.statut = Evaluation.StatutEvaluation.NOTE
        evaluation.save(update_fields=["statut"])

        client.force_login(enseignant.user)
        client.post(reverse("lms:publish_grades", kwargs={"pk": cours_session.pk}))
        evaluation.refresh_from_db()
        assert evaluation.statut == Evaluation.StatutEvaluation.PUBLIE
        assert Notification.objects.filter(
            destinataire=evaluation.etudiant.utilisateur,
            type_notification=Notification.Type.NOTE_PUBLIEE,
        ).exists()

    def test_une_evaluation_non_notee_n_est_pas_publiee(self, client, enseignant, cours_session, evaluation):
        client.force_login(enseignant.user)
        client.post(reverse("lms:publish_grades", kwargs={"pk": cours_session.pk}))
        evaluation.refresh_from_db()
        assert evaluation.statut == Evaluation.StatutEvaluation.SOUMIS

    def test_preparation_des_evaluations(self, client, enseignant, cours_session, etudiant_inscrit):
        """Crée une évaluation à remettre pour chaque étudiant inscrit."""
        client.force_login(enseignant.user)
        client.post(
            reverse("lms:prepare_evaluations", kwargs={"pk": cours_session.pk}),
            {"type_evaluation": Evaluation.TypeEvaluation.DEVOIR},
        )
        assert Evaluation.objects.filter(cours_session=cours_session, etudiant=etudiant_inscrit).exists()
        assert Notification.objects.filter(
            destinataire=etudiant_inscrit.utilisateur,
            titre__startswith="Nouvelle évaluation",
        ).exists()

    def test_la_preparation_ne_duplique_pas(self, client, enseignant, cours_session, etudiant_inscrit):
        client.force_login(enseignant.user)
        for _ in range(2):
            client.post(
                reverse("lms:prepare_evaluations", kwargs={"pk": cours_session.pk}),
                {"type_evaluation": Evaluation.TypeEvaluation.DEVOIR},
            )
        assert Evaluation.objects.filter(cours_session=cours_session).count() == 1

    def test_un_type_d_evaluation_invalide_est_refuse(self, client, enseignant, cours_session, etudiant_inscrit):
        client.force_login(enseignant.user)
        client.post(
            reverse("lms:prepare_evaluations", kwargs={"pk": cours_session.pk}),
            {"type_evaluation": "type-invente"},
        )
        assert Evaluation.objects.count() == 0
