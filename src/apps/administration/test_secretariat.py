"""
Le secrétariat gère l'ensemble du service scolarité.

Ces cas couvrent les quatre gestes qui lui manquaient ou dont on doutait :
réclamer une pièce à un candidat, traiter une demande d'inscription, ouvrir la
fiche d'un étudiant, et administrer la boutique. Ils sont joués avec un vrai
compte de rôle « secrétariat », et non avec un compte d'administration.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.academics.models import (
    CoursDeSession,
    DemandeInscriptionCours,
    ProfilEtudiant,
    Promotion,
    SessionAcademique,
)
from apps.accounts.models import User
from apps.admissions.models import DossierCandidature, PieceComplementaire
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


@pytest.fixture
def dossier(parcours):
    return DossierCandidature.objects.create(
        nom="Abaul",
        prenom="Léonie",
        email="candidate@exemple.org",
        parcours_souhaite=parcours,
        motivations="Je souhaite me former.",
    )


# ──────────────────────────────────────────────
# Pièces complémentaires
# ──────────────────────────────────────────────


def test_le_secretariat_reclame_une_piece(client, secretaire, dossier):
    client.force_login(secretaire)

    reponse = client.post(
        reverse("administration:demander_piece", args=[dossier.pk]),
        {"libelle": "Relevé de notes du baccalauréat", "description": "Recto verso, lisible.", "obligatoire": "on"},
    )

    assert reponse.status_code == 302
    piece = dossier.pieces_complementaires.get()
    assert piece.libelle == "Relevé de notes du baccalauréat"
    assert piece.statut == PieceComplementaire.Statut.DEMANDEE
    assert piece.demandee_par == secretaire

    # Attendre une pièce, c'est avoir un dossier incomplet : l'état le dit.
    dossier.refresh_from_db()
    assert dossier.statut == DossierCandidature.Statut.INCOMPLET


def test_une_demande_sans_libelle_est_refusee(client, secretaire, dossier):
    client.force_login(secretaire)
    client.post(reverse("administration:demander_piece", args=[dossier.pk]), {"libelle": "   "})
    assert dossier.pieces_complementaires.count() == 0


def test_le_candidat_depose_depuis_son_lien_de_suivi(client, dossier, secretaire):
    """Le candidat n'a pas de compte : le jeton du lien est son seul titre."""
    from apps.admissions.services import demander_piece

    piece = demander_piece(dossier, libelle="Attestation d'église", par=secretaire)

    reponse = client.post(
        reverse("admissions:candidature_suivi", kwargs={"token": dossier.token_suivi}),
        {
            "piece": piece.pk,
            "fichier": SimpleUploadedFile("attestation.pdf", b"%PDF-1.4", content_type="application/pdf"),
        },
    )

    assert reponse.status_code == 302
    piece.refresh_from_db()
    assert piece.statut == PieceComplementaire.Statut.DEPOSEE
    assert piece.fichier
    assert piece.date_depot is not None


def test_le_jeton_d_un_dossier_ne_depose_pas_sur_un_autre(client, dossier, parcours, secretaire):
    from apps.admissions.services import demander_piece

    autre = DossierCandidature.objects.create(
        nom="Céleste",
        prenom="Patrick",
        email="autre@exemple.org",
        parcours_souhaite=parcours,
        motivations="…",
    )
    piece_de_l_autre = demander_piece(autre, libelle="Pièce d'identité", par=secretaire)

    reponse = client.post(
        reverse("admissions:candidature_suivi", kwargs={"token": dossier.token_suivi}),
        {"piece": piece_de_l_autre.pk, "fichier": SimpleUploadedFile("x.pdf", b"%PDF", content_type="application/pdf")},
    )

    assert reponse.status_code == 404
    piece_de_l_autre.refresh_from_db()
    assert piece_de_l_autre.statut == PieceComplementaire.Statut.DEMANDEE


def test_le_secretariat_valide_une_piece(client, secretaire, dossier):
    from apps.admissions.services import demander_piece, deposer_piece

    piece = demander_piece(dossier, libelle="Diplôme", par=secretaire)
    deposer_piece(piece, SimpleUploadedFile("d.pdf", b"%PDF", content_type="application/pdf"))

    client.force_login(secretaire)
    client.post(reverse("administration:verifier_piece", args=[piece.pk]), {"decision": "accepter"})

    piece.refresh_from_db()
    assert piece.statut == PieceComplementaire.Statut.VALIDEE
    assert piece.date_verification is not None


def test_un_refus_sans_motif_est_impossible(client, secretaire, dossier):
    """Refuser sans dire pourquoi obligerait le candidat à redéposer la même chose."""
    from apps.admissions.services import demander_piece, deposer_piece

    piece = demander_piece(dossier, libelle="Diplôme", par=secretaire)
    deposer_piece(piece, SimpleUploadedFile("d.pdf", b"%PDF", content_type="application/pdf"))

    client.force_login(secretaire)
    client.post(reverse("administration:verifier_piece", args=[piece.pk]), {"decision": "refuser", "motif": "  "})

    piece.refresh_from_db()
    assert piece.statut == PieceComplementaire.Statut.DEPOSEE


def test_un_refus_motive_rouvre_le_depot(client, secretaire, dossier):
    from apps.admissions.services import demander_piece, deposer_piece

    piece = demander_piece(dossier, libelle="Diplôme", par=secretaire)
    deposer_piece(piece, SimpleUploadedFile("d.pdf", b"%PDF", content_type="application/pdf"))

    client.force_login(secretaire)
    client.post(
        reverse("administration:verifier_piece", args=[piece.pk]),
        {"decision": "refuser", "motif": "Document illisible."},
    )

    piece.refresh_from_db()
    assert piece.statut == PieceComplementaire.Statut.REFUSEE
    assert piece.motif_refus == "Document illisible."
    assert piece.est_en_attente is True  # le candidat peut redéposer


def test_un_etudiant_ne_reclame_pas_de_piece(client, dossier, parcours):
    intrus = User.objects.create_user(
        username="intrus", email="intrus@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
    )
    client.force_login(intrus)
    reponse = client.post(reverse("administration:demander_piece", args=[dossier.pk]), {"libelle": "Rien"})
    assert reponse.status_code == 403
    assert dossier.pieces_complementaires.count() == 0


# ──────────────────────────────────────────────
# Demandes d'inscription
# ──────────────────────────────────────────────


@pytest.fixture
def demande(parcours):
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
        nom="Session de Juillet 2026", date_debut=date(2026, 7, 1), date_fin=date(2026, 7, 31)
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
