"""
Le coût d'une page de liste ne doit pas croître avec le nombre de lignes.

C'est la propriété qui distingue une page qui tient en production d'une page
qui s'effondre. Elle est invisible en développement, où les tables comptent
trois enregistrements, et se paie en secondes d'attente une fois l'institut en
service.

L'assertion porte sur la **stabilité**, pas sur un nombre figé : un seuil
absolu se périmerait au premier ajout de fonctionnalité et serait relevé sans
réfléchir. Une page qui passe de 7 à 7 requêtes quand on décuple les lignes est
correcte ; une page qui passe de 8 à 27 ne l'est pas, quel que soit le seuil.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.academics.models import CoursDeSession, CreditECTS, ProfilEtudiant, Promotion, SessionAcademique
from apps.accounts.models import User
from apps.elearning.models import ModuleFormation
from apps.formations.models import Cours, Discipline, Parcours, Professeur

# Marge tolérée entre un petit et un grand volume. Quelques requêtes de plus
# restent acceptables — un préchargement supplémentaire, un compteur — mais pas
# une par ligne.
ECART_TOLERE = 3


@pytest.fixture
def referentiel(db):
    parcours = Parcours.objects.create(
        nom="Diplômant", slug="diplomant-cout", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )
    discipline = Discipline.objects.create(nom="Théologie", slug="theologie-cout")
    promotion = Promotion.objects.create(nom="Promo coût", parcours=parcours, annee_debut=2026, annee_fin=2032)
    session = SessionAcademique.objects.create(
        nom="Session coût",
        periode=SessionAcademique.Periode.JUILLET,
        annee_academique="2026-2027",
        date_debut="2027-07-05",
        date_fin="2027-07-10",
    )
    utilisateur = User.objects.create_user(
        username="prof_cout", email="prof_cout@iteag.org", password="motdepasse-long-12", role=User.Role.ENSEIGNANT
    )
    professeur = Professeur.objects.create(user=utilisateur, nom="Coût", prenom="Prof", slug="prof-cout")
    return {
        "parcours": parcours,
        "discipline": discipline,
        "promotion": promotion,
        "session": session,
        "professeur": professeur,
    }


@pytest.fixture
def admin(db):
    return User.objects.create_user(
        username="admin_cout", email="admin_cout@iteag.org", password="motdepasse-long-12", role=User.Role.ADMIN
    )


def creer_etudiants(referentiel, nombre: int, prefixe: str):
    """Des étudiants dotés de crédits : c'est leur agrégation qui coûte cher."""
    for i in range(nombre):
        utilisateur = User.objects.create_user(
            username=f"{prefixe}{i}",
            email=f"{prefixe}{i}@iteag.org",
            password="motdepasse-long-12",
            first_name="Prénom",
            last_name=f"Nom{i}",
            role=User.Role.ETUDIANT,
        )
        profil = ProfilEtudiant.objects.create(
            utilisateur=utilisateur,
            parcours=referentiel["parcours"],
            promotion=referentiel["promotion"],
            numero_etudiant=f"{prefixe.upper()}-{i:04d}",
            statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
        )
        CreditECTS.objects.create(
            etudiant=profil,
            ects_obtenus="2.5",
            source=CreditECTS.SourceCredit.ITEAG,
            date_validation="2027-07-10",
        )


def creer_cours(referentiel, nombre: int, prefixe: str):
    for i in range(nombre):
        cours = Cours.objects.create(
            titre=f"Cours {prefixe} {i}", slug=f"cours-{prefixe}-{i}", discipline=referentiel["discipline"]
        )
        CoursDeSession.objects.create(session=referentiel["session"], cours=cours, enseignant=referentiel["professeur"])


def creer_modules(referentiel, nombre: int, prefixe: str):
    for i in range(nombre):
        ModuleFormation.objects.create(
            titre=f"Module {prefixe} {i}",
            slug=f"module-{prefixe}-{i}",
            discipline=referentiel["discipline"],
            responsable=referentiel["professeur"],
            statut=ModuleFormation.StatutPublication.PUBLIE,
        )


def compter_requetes(client, nom_route: str) -> int:
    with CaptureQueriesContext(connection) as capture:
        reponse = client.get(reverse(nom_route))
    assert reponse.status_code == 200, f"{nom_route} → {reponse.status_code}"
    return len(capture)


@pytest.mark.django_db
class TestStabiliteDuCoutDesListes:
    def _verifier(self, client, nom_route, peupler, referentiel):
        peupler(referentiel, 2, "petit")
        petit = compter_requetes(client, nom_route)

        peupler(referentiel, 18, "grand")
        grand = compter_requetes(client, nom_route)

        assert grand - petit <= ECART_TOLERE, (
            f"{nom_route} : {petit} requêtes pour 2 lignes, {grand} pour 20. "
            "Le coût croît avec le volume — il manque un select_related, "
            "un prefetch_related ou une annotation."
        )

    def test_liste_des_etudiants(self, client, admin, referentiel):
        """
        Le cas qui a motivé ce fichier.

        La liste affiche le total d'ECTS de chaque étudiant. Calculé par une
        propriété, il déclenchait une agrégation par ligne ; il est désormais
        annoté sur le jeu de requêtes.
        """
        client.force_login(admin)
        self._verifier(client, "administration:etudiants", creer_etudiants, referentiel)

    def test_programmation_des_cours(self, client, admin, referentiel):
        client.force_login(admin)
        self._verifier(client, "administration:course_offerings", creer_cours, referentiel)

    def test_catalogue_public_des_modules(self, client, referentiel):
        """Page publique : c'est celle qui prend le plus de trafic."""
        self._verifier(client, "elearning:catalogue", creer_modules, referentiel)

    def test_liste_des_cours(self, client, admin, referentiel):
        client.force_login(admin)
        self._verifier(client, "administration:courses", creer_cours, referentiel)

    def test_export_csv_des_etudiants(self, client, admin, referentiel):
        """
        L'export est le pire cas : rien ne le pagine.

        La liste affiche vingt lignes ; l'export les prend toutes. Une
        agrégation par étudiant y coûte donc autant de requêtes que
        l'établissement compte d'inscrits, sur une page que le secrétariat
        ouvre en fin de session — le moment où la base est la plus sollicitée.
        """
        client.force_login(admin)
        self._verifier(client, "administration:export_etudiants", creer_etudiants, referentiel)


@pytest.mark.django_db
class TestAnnotationDesEcts:
    """L'annotation doit donner le même résultat que le calcul direct."""

    def test_l_annotation_et_le_calcul_concordent(self, client, admin, referentiel):
        creer_etudiants(referentiel, 1, "concord")
        profil = ProfilEtudiant.objects.get(numero_etudiant="CONCORD-0000")
        CreditECTS.objects.create(
            etudiant=profil, ects_obtenus="5", source=CreditECTS.SourceCredit.FLTE, date_validation="2027-01-10"
        )

        direct = float(profil.total_ects_acquis)

        client.force_login(admin)
        reponse = client.get(reverse("administration:etudiants"))
        annote = float(reponse.context["etudiants"][0].total_ects_acquis)

        assert annote == direct == 7.5

    def test_l_export_reprend_la_meme_valeur_que_le_calcul(self, client, admin, referentiel):
        """Une colonne annotée ne vaut que si elle dit la même chose que la propriété."""
        creer_etudiants(referentiel, 1, "exportconcord")
        profil = ProfilEtudiant.objects.get(numero_etudiant="EXPORTCONCORD-0000")
        CreditECTS.objects.create(
            etudiant=profil, ects_obtenus="5", source=CreditECTS.SourceCredit.FLTE, date_validation="2027-01-10"
        )

        client.force_login(admin)
        contenu = client.get(reverse("administration:export_etudiants")).content.decode("utf-8-sig")
        ligne = next(l for l in contenu.splitlines() if "EXPORTCONCORD-0000" in l)  # noqa: E741

        assert float(profil.total_ects_acquis) == 7.5
        assert ligne.split(";")[7] == "7.5"

    def test_un_etudiant_sans_credit_affiche_zero(self, client, admin, referentiel):
        """Sans crédit, la somme est nulle et non « None » — la page l'affiche."""
        utilisateur = User.objects.create_user(
            username="sans_credit", email="sc@iteag.org", password="motdepasse-long-12", role=User.Role.ETUDIANT
        )
        ProfilEtudiant.objects.create(
            utilisateur=utilisateur,
            parcours=referentiel["parcours"],
            promotion=referentiel["promotion"],
            numero_etudiant="SANS-CREDIT",
        )
        client.force_login(admin)
        profil = client.get(reverse("administration:etudiants")).context["etudiants"][0]
        assert float(profil.total_ects_acquis) == 0
