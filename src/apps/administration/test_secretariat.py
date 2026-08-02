"""
Le secrétariat gère l'ensemble du service scolarité.

Ces cas couvrent les trois gestes qui lui manquaient ou dont on doutait :
traiter une demande d'inscription, ouvrir la fiche d'un étudiant, et
administrer la boutique. Ils sont joués avec un vrai compte de rôle
« secrétariat », et non avec un compte d'administration.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import (
    CoursDeSession,
    DemandeInscriptionCours,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
)
from apps.accounts.models import User
from apps.commerce.models import ProduitLivre
from apps.formations.models import Cours, Discipline, Parcours, Professeur

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "MotDePasseSolide!2026"


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="secretariat",
        email="secretariat@iteag.org",
        password=MOT_DE_PASSE,
        first_name="Secrétariat",
        last_name="ITEAG",
        role=User.Role.SECRETARIAT,
    )


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(nom="Bachelor", slug="bachelor", type_parcours=Parcours.TypeParcours.LIBRE)


# Les pièces réclamées à un candidat sont couvertes par
# « apps/admissions/test_pieces.py », qui joue le même parcours — réclamation,
# dépôt au jeton, validation, refus motivé — sur le modèle « PieceDemandee ».
# Les cas qui vivaient ici visaient un second modèle, supprimé depuis.


# ──────────────────────────────────────────────
# Demandes d'inscription
# ──────────────────────────────────────────────


@pytest.fixture
def demande(parcours):
    # La session encadre le jour où la suite tourne. Des dates absolues
    # faisaient passer ce cas jusqu'au dernier jour de la session écrite en
    # dur, puis échouer tous les jours suivants sur « Cette session est
    # terminée » — un refus légitime du domaine, contre un dossier de test
    # devenu invraisemblable.
    aujourd_hui = timezone.localdate()
    promotion = Promotion.objects.create(nom="Promotion 2026", parcours=parcours, annee_debut=2026, annee_fin=2029)
    compte = User.objects.create_user(
        username="etudiante", email="etudiante@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
    )
    profil = ProfilEtudiant.objects.create(
        utilisateur=compte,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ETU-SEC-001",
        statut_inscription=ProfilEtudiant.StatutInscription.ACTIF,
    )
    discipline = Discipline.objects.create(nom="Théologie", slug="theologie")
    matiere = Cours.objects.create(titre="Herméneutique", slug="hermeneutique", discipline=discipline)
    professeur = Professeur.objects.create(nom="Nisus", prenom="Alain", slug="alain-nisus")
    session = SessionAcademique.objects.create(
        nom="Session en cours",
        date_debut=aujourd_hui - timedelta(days=7),
        date_fin=aujourd_hui + timedelta(days=23),
    )
    offre = CoursDeSession.objects.create(session=session, cours=matiere, enseignant=professeur)
    return DemandeInscriptionCours.objects.create(
        etudiant=profil,
        cours_session=offre,
        montant_du=Decimal("120.00"),
        statut=DemandeInscriptionCours.Statut.SOUMISE,
    )


def test_le_secretariat_traite_une_demande_d_inscription(client, secretaire, demande):
    """Le 302 observé dans les journaux est la redirection normale d'un POST."""
    client.force_login(secretaire)

    reponse = client.post(
        reverse("administration:enrollment_request_action", args=[demande.pk]),
        {"action": "confirmer", "exonere_paiement": "on", "commentaire": "Boursière : exonérée."},
    )

    assert reponse.status_code == 302
    demande.refresh_from_db()
    assert demande.statut == DemandeInscriptionCours.Statut.CONFIRMEE
    # Confirmer, c'est inscrire : sans cela le geste n'aurait aucun effet réel.
    assert demande.cours_session.inscriptions.filter(etudiant=demande.etudiant).exists()


def test_le_secretariat_ouvre_la_liste_des_demandes(client, secretaire, demande):
    client.force_login(secretaire)
    reponse = client.get(reverse("administration:enrollment_requests"))
    assert reponse.status_code == 200
    assert "Herméneutique" in reponse.content.decode()


# ──────────────────────────────────────────────
# Fiche étudiant et boutique
# ──────────────────────────────────────────────


def test_le_secretariat_ouvre_la_fiche_d_un_etudiant(client, secretaire, demande):
    client.force_login(secretaire)
    reponse = client.get(reverse("administration:etudiant_detail", args=[demande.etudiant.pk]))
    assert reponse.status_code == 200
    assert "ETU-SEC-001" in reponse.content.decode()


def test_le_secretariat_gere_les_commandes_et_le_stock(client, secretaire):
    ProduitLivre.objects.create(
        titre="Théologie systématique",
        slug="theologie-systematique",
        sku="LIV-001",
        prix_ttc=Decimal("35.00"),
        stock_physique=10,
    )
    client.force_login(secretaire)

    assert client.get(reverse("commerce:gestion_commandes")).status_code == 200
    reponse_stock = client.get(reverse("commerce:gestion_stock"))
    assert reponse_stock.status_code == 200
    assert "Théologie systématique" in reponse_stock.content.decode()


def test_la_boutique_est_atteignable_depuis_la_barre_du_secretariat(client, secretaire):
    """Le droit existait déjà ; c'est le chemin pour y arriver qui manquait."""
    client.force_login(secretaire)
    corps = client.get(reverse("secretariat:dashboard")).content.decode()
    assert reverse("commerce:gestion_commandes") in corps
    assert reverse("commerce:gestion_stock") in corps
