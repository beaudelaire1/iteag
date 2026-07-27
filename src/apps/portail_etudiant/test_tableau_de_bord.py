"""
Tests du tableau de bord étudiant.

Ce que ces tests protègent : que l'étudiant voie, depuis son accueil, **tout ce
à quoi il a droit**. La formation vidéo en était absente — non par oubli, mais
parce que ces vues vivaient dans « academics », qui n'a pas le droit de dépendre
d'« elearning ». L'étudiant devait deviner qu'un second écran existait.

C'est ce que l'extraction du portail débloque, et ce qu'il ne faut pas
reperdre : d'où des tests qui vérifient la présence du contenu, pas seulement
l'absence d'erreur.
"""

import pytest
from django.urls import reverse

from apps.academics.models import ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.elearning.models import AttestationModule, InscriptionModule, ModuleFormation
from apps.formations.models import Discipline, Parcours, Professeur


@pytest.fixture
def etudiant(db):
    parcours = Parcours.objects.create(
        nom="Diplômant", slug="diplomant-tdb", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG, ects_requis=180
    )
    promotion = Promotion.objects.create(nom="Promo TDB", parcours=parcours, annee_debut=2026, annee_fin=2032)
    utilisateur = User.objects.create_user(
        username="etu_tdb",
        email="etu_tdb@iteag.org",
        password="motdepasse-long-12",
        first_name="Judith",
        last_name="Alexis",
        role=User.Role.ETUDIANT,
    )
    return ProfilEtudiant.objects.create(
        utilisateur=utilisateur,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-TDB-001",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )


@pytest.fixture
def module(db):
    discipline = Discipline.objects.create(nom="Missiologie", slug="missiologie-tdb")
    utilisateur = User.objects.create_user(
        username="prof_tdb", email="prof_tdb@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
    )
    professeur = Professeur.objects.create(user=utilisateur, nom="Robert", prenom="Léa", slug="lea-robert")
    return ModuleFormation.objects.create(
        titre="Mission et cultures créoles",
        slug="mission-cultures-creoles",
        discipline=discipline,
        responsable=professeur,
        statut=ModuleFormation.StatutPublication.PUBLIE,
    )


def tableau_de_bord(client, etudiant) -> str:
    client.force_login(etudiant.utilisateur)
    reponse = client.get(reverse("etudiant:dashboard"))
    assert reponse.status_code == 200
    return reponse.content.decode()


@pytest.mark.django_db
class TestFormationVideoAuTableauDeBord:
    def test_un_module_en_cours_apparait(self, client, etudiant, module):
        InscriptionModule.objects.create(etudiant=etudiant, module=module, statut=InscriptionModule.StatutAcces.ACTIF)
        contenu = tableau_de_bord(client, etudiant)
        assert "Mission et cultures créoles" in contenu
        assert "Mon E-Learning" in contenu

    def test_la_progression_est_affichee(self, client, etudiant, module):
        InscriptionModule.objects.create(
            etudiant=etudiant,
            module=module,
            statut=InscriptionModule.StatutAcces.ACTIF,
            progression_percent=42,
        )
        assert "42 %" in tableau_de_bord(client, etudiant)

    def test_les_attestations_obtenues_sont_listees(self, client, etudiant, module):
        acces = InscriptionModule.objects.create(
            etudiant=etudiant, module=module, statut=InscriptionModule.StatutAcces.TERMINE
        )
        AttestationModule.objects.create(inscription=acces, numero="ITEAG-MOD-2027-00007")
        contenu = tableau_de_bord(client, etudiant)
        assert "ITEAG-MOD-2027-00007" in contenu

    def test_les_compteurs_distinguent_en_cours_et_termines(self, client, etudiant, module):
        InscriptionModule.objects.create(etudiant=etudiant, module=module, statut=InscriptionModule.StatutAcces.TERMINE)
        contexte = client.force_login(etudiant.utilisateur) or client.get(reverse("etudiant:dashboard")).context
        assert contexte["modules_total"] == 1
        assert contexte["modules_termines"] == 1
        assert list(contexte["modules_en_cours"]) == []

    def test_sans_aucun_module_la_section_disparait(self, client, etudiant):
        """
        Mieux vaut ne rien montrer qu'une section vide : un étudiant du
        présentiel n'a pas à voir un bloc « formation vidéo » sans contenu.
        """
        assert "Mon E-Learning" not in tableau_de_bord(client, etudiant)

    def test_un_acces_revoque_ne_compte_pas_comme_en_cours(self, client, etudiant, module):
        InscriptionModule.objects.create(etudiant=etudiant, module=module, statut=InscriptionModule.StatutAcces.REVOQUE)
        client.force_login(etudiant.utilisateur)
        contexte = client.get(reverse("etudiant:dashboard")).context
        assert list(contexte["modules_en_cours"]) == []


@pytest.mark.django_db
class TestCoutDuTableauDeBord:
    """Ajouter une section ne doit pas rendre l'accueil coûteux."""

    def test_le_cout_ne_croit_pas_avec_le_nombre_de_modules(self, client, etudiant, module):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        InscriptionModule.objects.create(etudiant=etudiant, module=module, statut=InscriptionModule.StatutAcces.ACTIF)
        client.force_login(etudiant.utilisateur)
        with CaptureQueriesContext(connection) as capture:
            client.get(reverse("etudiant:dashboard"))
        avec_un = len(capture)

        for i in range(8):
            autre = ModuleFormation.objects.create(
                titre=f"Module {i}",
                slug=f"module-tdb-{i}",
                discipline=module.discipline,
                responsable=module.responsable,
                statut=ModuleFormation.StatutPublication.PUBLIE,
            )
            InscriptionModule.objects.create(
                etudiant=etudiant, module=autre, statut=InscriptionModule.StatutAcces.ACTIF
            )

        with CaptureQueriesContext(connection) as capture:
            client.get(reverse("etudiant:dashboard"))
        avec_neuf = len(capture)

        assert avec_neuf - avec_un <= 2, f"{avec_un} requêtes pour 1 module, {avec_neuf} pour 9"
