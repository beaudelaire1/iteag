"""
Fiche de scolarité — l'écran que le secrétariat reconstituait à la main.

Coordonnées, église, cours suivis, notes, crédits, paiements et accès vidéo
tenaient dans cinq écrans différents. Ces cas fixent ce que la fiche réunit, et
qui a le droit de l'ouvrir.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.academics.models import (
    CoursDeSession,
    InscriptionSession,
    Paiement,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
)
from apps.accounts.models import User
from apps.formations.models import Cours, Discipline, Parcours, Professeur

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "MotDePasseSolide!2026"


@pytest.fixture
def dossier():
    parcours = Parcours.objects.create(
        nom="Bachelor", slug="bachelor", type_parcours=Parcours.TypeParcours.BACHELOR_FLTE
    )
    promotion = Promotion.objects.create(nom="Promotion 2026", parcours=parcours, annee_debut=2026, annee_fin=2029)
    compte = User.objects.create_user(
        username="etudiante",
        email="etudiante@iteag.org",
        password=MOT_DE_PASSE,
        first_name="Rosemonde",
        last_name="Lauriette",
        role=User.Role.ETUDIANT,
        phone="0690112233",
        adresse="8 impasse des Manguiers",
        code_postal="97110",
        ville="Pointe-à-Pitre",
    )
    profil = ProfilEtudiant.objects.create(
        utilisateur=compte,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-FICHE-001",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
        eglise="Église Évangélique des Abymes",
    )

    discipline = Discipline.objects.create(nom="Théologie", slug="theologie")
    cours = Cours.objects.create(titre="Herméneutique", slug="hermeneutique", discipline=discipline)
    professeur = Professeur.objects.create(nom="Nisus", prenom="Alain", slug="alain-nisus")
    session = SessionAcademique.objects.create(
        nom="Session de Juillet 2026", date_debut=date(2026, 7, 1), date_fin=date(2026, 7, 31)
    )
    offre = CoursDeSession.objects.create(session=session, cours=cours, enseignant=professeur)
    InscriptionSession.objects.create(etudiant=profil, cours_session=offre)
    Paiement.objects.create(
        etudiant=profil,
        session=session,
        montant=Decimal("250.00"),
        date_paiement=date(2026, 7, 2),
        statut=Paiement.StatutPaiement.CONFIRME,
    )
    return profil


def _compte(role, username):
    return User.objects.create_user(username=username, email=f"{username}@iteag.org", password=MOT_DE_PASSE, role=role)


def test_le_secretariat_lit_la_fiche(client, dossier):
    client.force_login(_compte(User.Role.SECRETARIAT, "secretaire"))
    reponse = client.get(reverse("administration:etudiant_detail", args=[dossier.pk]))
    corps = reponse.content.decode()

    assert reponse.status_code == 200
    assert "Rosemonde Lauriette" in corps
    assert "ETU-FICHE-001" in corps
    assert "etudiante@iteag.org" in corps
    assert "0690112233" in corps
    assert "8 impasse des Manguiers, 97110 Pointe-à-Pitre" in corps
    assert "Église Évangélique des Abymes" in corps
    assert "Herméneutique" in corps  # historique des cours suivis
    assert "250,00" in corps or "250.00" in corps  # paiement confirmé


def test_la_direction_lit_la_fiche(client, dossier):
    client.force_login(_compte(User.Role.ADMIN, "directrice"))
    assert client.get(reverse("administration:etudiant_detail", args=[dossier.pk])).status_code == 200


@pytest.mark.parametrize("role", [User.Role.ETUDIANT, User.Role.ENSEIGNANT])
def test_ni_l_etudiant_ni_l_enseignant_n_y_accedent(client, dossier, role):
    """Le dossier d'un étudiant n'est pas une donnée pédagogique partagée."""
    client.force_login(_compte(role, f"intrus-{role}"))
    reponse = client.get(reverse("administration:etudiant_detail", args=[dossier.pk]))
    assert reponse.status_code == 403


def test_le_visiteur_est_renvoye_vers_la_connexion(client, dossier):
    reponse = client.get(reverse("administration:etudiant_detail", args=[dossier.pk]))
    assert reponse.status_code == 302
    assert "/connexion/" in reponse["Location"]


def test_la_liste_renvoie_vers_la_fiche(client, dossier):
    client.force_login(_compte(User.Role.SECRETARIAT, "secretaire2"))
    corps = client.get(reverse("administration:etudiants")).content.decode()
    assert reverse("administration:etudiant_detail", args=[dossier.pk]) in corps
