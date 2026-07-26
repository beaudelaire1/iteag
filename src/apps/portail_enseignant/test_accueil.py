"""
Tests de l'accueil unifié de l'enseignant.

L'enjeu est le même que pour l'espace étudiant : un enseignant doit voir depuis
une seule page **tout ce qu'il enseigne**. Il avait deux tableaux de bord, l'un
pour le présentiel et l'autre pour la vidéo, aucun ne montrant l'autre.

Les tests vérifient la présence du contenu et non seulement l'absence d'erreur :
c'est la richesse de l'écran qui est protégée ici.
"""

import pytest
from django.urls import reverse

from apps.academics.models import CoursDeSession, InscriptionSession, ProfilEtudiant, Promotion, SessionAcademique
from apps.accounts.models import User
from apps.elearning.models import InscriptionModule, ModuleFormation, VideoAsset
from apps.formations.models import Cours, Discipline, Parcours, Professeur
from apps.lms.models import Evaluation


@pytest.fixture
def enseignant(db):
    utilisateur = User.objects.create_user(
        username="prof_accueil",
        email="prof_accueil@iteag.org",
        password="motdepasse-long-12",
        first_name="Emmanuel",
        last_name="Dorival",
        role=User.Role.ENSEIGNANT,
    )
    return Professeur.objects.create(user=utilisateur, nom="Dorival", prenom="Emmanuel", slug="emmanuel-dorival")


@pytest.fixture
def referentiel(db):
    return {
        "discipline": Discipline.objects.create(nom="Homilétique", slug="homiletique-acc"),
        "parcours": Parcours.objects.create(
            nom="Diplômant", slug="diplomant-acc", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
        ),
    }


@pytest.fixture
def cours_session(db, enseignant, referentiel):
    cours = Cours.objects.create(
        titre="Prêcher les Évangiles", slug="precher-evangiles", discipline=referentiel["discipline"]
    )
    session = SessionAcademique.objects.create(
        nom="Session de Toussaint",
        periode=SessionAcademique.Periode.TOUSSAINT,
        annee_academique="2027-2028",
        date_debut="2027-11-02",
        date_fin="2027-11-07",
    )
    return CoursDeSession.objects.create(session=session, cours=cours, enseignant=enseignant)


def accueil(client, enseignant) -> str:
    client.force_login(enseignant.user)
    reponse = client.get(reverse("enseignant:accueil"))
    assert reponse.status_code == 200
    return reponse.content.decode()


@pytest.mark.django_db
class TestAccueilUnifie:
    def test_le_presentiel_et_la_video_coexistent(self, client, enseignant, cours_session, referentiel):
        """Le cœur du sujet : une seule page pour les deux modes d'enseignement."""
        ModuleFormation.objects.create(
            titre="Prédication et culture antillaise",
            slug="predication-culture",
            discipline=referentiel["discipline"],
            responsable=enseignant,
            statut=ModuleFormation.StatutPublication.PUBLIE,
        )
        contenu = accueil(client, enseignant)
        assert "Prêcher les Évangiles" in contenu
        assert "Prédication et culture antillaise" in contenu

    def test_les_copies_a_corriger_sont_signalees(self, client, enseignant, cours_session, referentiel):
        """C'est l'action la plus urgente d'un enseignant : elle doit sauter aux yeux."""
        promotion = Promotion.objects.create(
            nom="Promo accueil", parcours=referentiel["parcours"], annee_debut=2027, annee_fin=2033
        )
        utilisateur = User.objects.create_user(
            username="etu_acc", email="etu_acc@iteag.org", password="motdepasse-long-12", role=User.Role.ETUDIANT
        )
        profil = ProfilEtudiant.objects.create(
            utilisateur=utilisateur,
            parcours=referentiel["parcours"],
            promotion=promotion,
            numero_etudiant="ETU-ACC-1",
        )
        InscriptionSession.objects.create(etudiant=profil, cours_session=cours_session)
        Evaluation.objects.create(
            etudiant=profil, cours_session=cours_session, statut=Evaluation.StatutEvaluation.SOUMIS
        )

        client.force_login(enseignant.user)
        contexte = client.get(reverse("enseignant:accueil")).context
        assert contexte["evaluations_a_corriger"] == 1
        assert contexte["etudiants_suivis"] == 1

    def test_les_apprenants_video_sont_comptes(self, client, enseignant, referentiel):
        module = ModuleFormation.objects.create(
            titre="Module accueil",
            slug="module-accueil",
            discipline=referentiel["discipline"],
            responsable=enseignant,
        )
        promotion = Promotion.objects.create(
            nom="Promo vidéo", parcours=referentiel["parcours"], annee_debut=2027, annee_fin=2033
        )
        utilisateur = User.objects.create_user(
            username="etu_vid", email="etu_vid@iteag.org", password="motdepasse-long-12", role=User.Role.ETUDIANT
        )
        profil = ProfilEtudiant.objects.create(
            utilisateur=utilisateur,
            parcours=referentiel["parcours"],
            promotion=promotion,
            numero_etudiant="ETU-VID-1",
        )
        InscriptionModule.objects.create(etudiant=profil, module=module, statut=InscriptionModule.StatutAcces.ACTIF)

        client.force_login(enseignant.user)
        assert client.get(reverse("enseignant:accueil")).context["apprenants_video"] == 1

    def test_une_video_en_preparation_est_signalee(self, client, enseignant):
        """
        Une vidéo bloquée empêche la publication d'un module — c'est le premier
        incident du manuel d'exploitation. L'enseignant doit le voir sans avoir
        à ouvrir sa bibliothèque.
        """
        VideoAsset.objects.create(
            titre="En cours",
            cle_stockage="acc-video-1",
            uploade_par=enseignant.user,
            statut_traitement=VideoAsset.StatutTraitement.EN_COURS,
        )
        contenu = accueil(client, enseignant)
        assert "préparation" in contenu

    def test_un_enseignant_sans_fiche_est_guide(self, client, db):
        """
        Un compte enseignant sans fiche professeur ne doit pas voir une page de
        compteurs à zéro, qui laisserait croire à une panne.
        """
        utilisateur = User.objects.create_user(
            username="prof_sans_fiche_acc",
            email="psfa@iteag.org",
            password="motdepasse-long-12",
            role=User.Role.ENSEIGNANT,
        )
        client.force_login(utilisateur)
        reponse = client.get(reverse("enseignant:accueil"))
        assert reponse.status_code == 200
        assert "fiche enseignant n'est pas encore créée" in reponse.content.decode()

    def test_un_etudiant_n_y_accede_pas(self, client, referentiel):
        promotion = Promotion.objects.create(
            nom="Promo refus", parcours=referentiel["parcours"], annee_debut=2027, annee_fin=2033
        )
        utilisateur = User.objects.create_user(
            username="etu_refus", email="er@iteag.org", password="motdepasse-long-12", role=User.Role.ETUDIANT
        )
        ProfilEtudiant.objects.create(
            utilisateur=utilisateur,
            parcours=referentiel["parcours"],
            promotion=promotion,
            numero_etudiant="ETU-REFUS",
        )
        client.force_login(utilisateur)
        assert client.get(reverse("enseignant:accueil")).status_code in (302, 403)

    def test_l_enseignant_ne_voit_pas_le_contenu_d_un_confrere(self, client, enseignant, referentiel):
        """La restriction de propriété vaut aussi pour les compteurs d'accueil."""
        autre_utilisateur = User.objects.create_user(
            username="autre_prof_acc", email="apa@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
        )
        autre = Professeur.objects.create(user=autre_utilisateur, nom="Autre", prenom="Prof", slug="autre-prof-acc")
        ModuleFormation.objects.create(
            titre="Module confidentiel",
            slug="module-confidentiel",
            discipline=referentiel["discipline"],
            responsable=autre,
        )
        assert "Module confidentiel" not in accueil(client, enseignant)


@pytest.mark.django_db
class TestConnexionMeneAlAccueilUnifie:
    def test_l_enseignant_atterrit_sur_l_accueil_unifie(self, enseignant):
        """
        Un seul endroit décide de la page d'arrivée par rôle. L'enseignant doit
        y trouver l'accueil unifié, pas l'un des deux tableaux partiels.
        """
        from apps.accounts.views import tableau_de_bord

        assert tableau_de_bord(enseignant.user) == reverse("enseignant:accueil")


@pytest.mark.django_db
class TestCoutDeLAccueil:
    def test_le_cout_ne_croit_pas_avec_le_nombre_de_modules(self, client, enseignant, referentiel):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(enseignant.user)
        ModuleFormation.objects.create(
            titre="Module 0", slug="module-cout-0", discipline=referentiel["discipline"], responsable=enseignant
        )
        with CaptureQueriesContext(connection) as capture:
            client.get(reverse("enseignant:accueil"))
        avec_un = len(capture)

        for i in range(1, 10):
            ModuleFormation.objects.create(
                titre=f"Module {i}",
                slug=f"module-cout-{i}",
                discipline=referentiel["discipline"],
                responsable=enseignant,
            )
        with CaptureQueriesContext(connection) as capture:
            client.get(reverse("enseignant:accueil"))
        avec_dix = len(capture)

        assert avec_dix - avec_un <= 2, f"{avec_un} requêtes pour 1 module, {avec_dix} pour 10"
