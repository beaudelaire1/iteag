"""
Le secrétariat gère l'ensemble du service scolarité.

Ces cas couvrent les gestes qui lui manquaient ou dont on doutait :
traiter une demande d'inscription et ouvrir la fiche d'un étudiant.
Ils sont joués avec un vrai compte de rôle
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
from apps.core.models import Notification
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


def _compteur(reponse):
    valeur = reponse.context["demandes_inscription_a_traiter"]
    # Le processeur de contexte fournit un appelable, la vue un entier : la
    # pastille doit dire la même chose dans les deux cas.
    return valeur() if callable(valeur) else valeur


def test_la_pastille_des_demandes_decroit_une_fois_l_inscription_confirmee(client, secretaire, demande):
    """Une pastille qui ne retombe jamais cesse d'être lue."""
    client.force_login(secretaire)
    avant = _compteur(client.get(reverse("secretariat:dashboard")))

    client.post(
        reverse("administration:enrollment_request_action", args=[demande.pk]),
        {"action": "confirmer", "exonere_paiement": "on", "commentaire": "Boursière : exonérée."},
    )

    assert _compteur(client.get(reverse("secretariat:dashboard"))) == avant - 1


def test_la_pastille_retient_une_demande_mise_en_attente_de_paiement(client, secretaire, demande):
    """« Valider et demander le paiement » n'est pas la fin du traitement.

    La demande reste due : la retirer de la pastille ferait disparaître de la
    file un dossier sur lequel il reste à encaisser.
    """
    client.force_login(secretaire)
    avant = _compteur(client.get(reverse("secretariat:dashboard")))

    client.post(
        reverse("administration:enrollment_request_action", args=[demande.pk]),
        {"action": "demander_paiement", "commentaire": ""},
    )

    demande.refresh_from_db()
    assert demande.statut == DemandeInscriptionCours.Statut.PAIEMENT_ATTENTE
    assert _compteur(client.get(reverse("secretariat:dashboard"))) == avant


# ──────────────────────────────────────────────
# Fiche étudiant
# ──────────────────────────────────────────────


def test_le_secretariat_ouvre_la_fiche_d_un_etudiant(client, secretaire, demande):
    client.force_login(secretaire)
    reponse = client.get(reverse("administration:etudiant_detail", args=[demande.etudiant.pk]))
    assert reponse.status_code == 200
    assert "ETU-SEC-001" in reponse.content.decode()


def test_la_creation_d_une_formation_avertit_tous_les_etudiants_actifs(client, secretaire, demande):
    autre_etudiant = User.objects.create_user(
        username="autre_etudiant_formation",
        email="autre-formation@iteag.org",
        password=MOT_DE_PASSE,
        role=User.Role.ETUDIANT,
    )
    etudiant_inactif = User.objects.create_user(
        username="etudiant_inactif_formation",
        email="inactif-formation@iteag.org",
        password=MOT_DE_PASSE,
        role=User.Role.ETUDIANT,
        is_active=False,
    )
    discipline = Discipline.objects.create(nom="Formation nouvelle", slug="formation-nouvelle")
    client.force_login(secretaire)

    reponse = client.post(
        reverse("administration:course_create"),
        {
            "titre": "Histoire de l'Église",
            "slug": "histoire-eglise-notification",
            "code": "HIS101",
            "discipline": discipline.pk,
            "description": "",
            "objectifs": "",
            "ects": "2.5",
            "actif": "on",
        },
    )

    assert reponse.status_code == 302
    titre = "Nouvelle formation créée — Histoire de l'Église"
    assert Notification.objects.filter(destinataire=demande.etudiant.utilisateur, titre=titre).exists()
    assert Notification.objects.filter(destinataire=autre_etudiant, titre=titre).exists()
    assert not Notification.objects.filter(destinataire=etudiant_inactif, titre=titre).exists()


def test_le_secretariat_genere_une_feuille_d_emargement_pdf(client, secretaire, db):
    discipline = Discipline.objects.create(nom="AT Test", slug="at-test")
    cours = Cours.objects.create(titre="Cours Emargement", slug="cours-emargement", discipline=discipline, code="AT101")
    session = SessionAcademique.objects.create(nom="Session Auto 2026", date_debut="2026-09-01", date_fin="2027-06-30")
    prof = Professeur.objects.create(nom="Prof", prenom="Test", slug="prof-test")
    cours_session = CoursDeSession.objects.create(
        session=session,
        cours=cours,
        enseignant=prof,
        modalite=CoursDeSession.Modalite.PRESENTIEL,
    )

    client.force_login(secretaire)
    reponse = client.get(reverse("administration:emargement_pdf", args=[cours_session.pk]))
    assert reponse.status_code == 200
    assert reponse["Content-Type"] == "application/pdf"
    assert "emargement-" in reponse["Content-Disposition"]
