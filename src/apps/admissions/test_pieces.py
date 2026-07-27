"""
Réclamation de pièces justificatives — du dossier accepté au dossier complet.

Le parcours couvert ici est celui qui n'existait pas : une fois la candidature
tranchée, le secrétariat réclame des justificatifs, le candidat les dépose
depuis son lien de suivi sans créer de compte, et le secrétariat valide ou
refuse en disant pourquoi.

Le point sensible est l'accès : la page de dépôt est publique par construction.
Ces tests vérifient qu'un jeton n'ouvre que son propre dossier.
"""

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import User
from apps.admissions.models import DossierCandidature, PieceDemandee
from apps.formations.models import Parcours


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Licence en théologie", slug="licence-pieces", type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG
    )


@pytest.fixture
def dossier(db, parcours):
    return DossierCandidature.objects.create(
        nom="Ranguin",
        prenom="Micheline",
        email="micheline.ranguin@example.org",
        parcours_souhaite=parcours,
        motivations="Servir mon Église avec de meilleurs outils.",
        statut=DossierCandidature.Statut.ACCEPTE,
    )


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="sec_pieces", email="s@iteag.org", password="motdepasse-long-12", role=User.Role.SECRETARIAT
    )


@pytest.fixture
def piece(db, dossier):
    return PieceDemandee.objects.create(
        dossier=dossier,
        libelle="Acte de naissance",
        precisions="Copie intégrale de moins de trois mois.",
    )


def fichier(nom="acte.pdf"):
    return SimpleUploadedFile(nom, b"%PDF-1.4 contenu", content_type="application/pdf")


# ══════════════════════════════════════════════
# Le secrétariat réclame
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestReclamation:
    def test_le_secretariat_reclame_plusieurs_pieces_en_une_fois(self, client, secretaire, dossier):
        client.force_login(secretaire)
        reponse = client.post(
            reverse("administration:demander_pieces", args=[dossier.pk]),
            {"pieces": ["Acte de naissance", "Photo d'identité"], "precisions": "", "piece_libre": ""},
        )
        assert reponse.status_code == 302
        assert dossier.pieces_demandees.count() == 2

    def test_un_seul_courriel_est_envoye_pour_l_ensemble(self, client, secretaire, dossier):
        """Un courriel par pièce noierait la demande et ferait robot."""
        mail.outbox.clear()
        client.force_login(secretaire)
        client.post(
            reverse("administration:demander_pieces", args=[dossier.pk]),
            {"pieces": ["Acte de naissance", "Photo d'identité", "Curriculum vitæ"], "piece_libre": ""},
        )
        assert len(mail.outbox) == 1
        assert dossier.email in mail.outbox[0].to
        assert "Acte de naissance" in mail.outbox[0].body
        assert "Curriculum vitæ" in mail.outbox[0].body

    def test_le_courriel_porte_le_lien_de_depot(self, client, secretaire, dossier):
        mail.outbox.clear()
        client.force_login(secretaire)
        client.post(
            reverse("administration:demander_pieces", args=[dossier.pk]),
            {"pieces": ["Acte de naissance"], "piece_libre": ""},
        )
        assert dossier.token_suivi in mail.outbox[0].body

    def test_une_piece_hors_liste_peut_etre_saisie(self, client, secretaire, dossier):
        client.force_login(secretaire)
        client.post(
            reverse("administration:demander_pieces", args=[dossier.pk]),
            {"pieces": [], "piece_libre": "Attestation de baptême"},
        )
        assert dossier.pieces_demandees.filter(libelle="Attestation de baptême").exists()

    def test_une_demande_vide_est_refusee(self, client, secretaire, dossier):
        client.force_login(secretaire)
        reponse = client.post(
            reverse("administration:demander_pieces", args=[dossier.pk]),
            {"pieces": [], "piece_libre": ""},
        )
        assert reponse.status_code == 200  # le formulaire est réaffiché
        assert dossier.pieces_demandees.count() == 0

    def test_un_etudiant_ne_peut_pas_reclamer(self, client, dossier, db):
        intrus = User.objects.create_user(
            username="intrus", email="i@x.org", password="motdepasse-long-12", role=User.Role.ETUDIANT
        )
        client.force_login(intrus)
        reponse = client.post(
            reverse("administration:demander_pieces", args=[dossier.pk]),
            {"pieces": ["Acte de naissance"], "piece_libre": ""},
        )
        assert reponse.status_code in (302, 403)
        assert dossier.pieces_demandees.count() == 0


# ══════════════════════════════════════════════
# Le candidat dépose, sans compte
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestDepotParLeCandidat:
    def test_le_candidat_voit_ses_pieces_sur_la_page_de_suivi(self, client, dossier, piece):
        contenu = client.get(reverse("admissions:candidature_suivi", args=[dossier.token_suivi])).content.decode()
        assert "Acte de naissance" in contenu

    def test_le_depot_enregistre_le_fichier_et_l_horodate(self, client, dossier, piece):
        client.post(
            reverse("admissions:deposer_piece", args=[dossier.token_suivi, piece.pk]),
            {"fichier": fichier()},
        )
        piece.refresh_from_db()
        assert piece.statut == PieceDemandee.Statut.DEPOSEE
        assert piece.date_depot is not None
        assert piece.fichier

    def test_un_format_refuse_n_est_pas_enregistre(self, client, dossier, piece):
        client.post(
            reverse("admissions:deposer_piece", args=[dossier.token_suivi, piece.pk]),
            {"fichier": SimpleUploadedFile("script.exe", b"MZ", content_type="application/octet-stream")},
        )
        piece.refresh_from_db()
        assert piece.statut == PieceDemandee.Statut.DEMANDEE
        assert not piece.fichier

    def test_un_jeton_n_ouvre_que_son_propre_dossier(self, client, dossier, piece, parcours):
        """
        Le point sensible : la page est publique, seul le jeton fait autorité.
        Sans cette vérification, deviner un identifiant de pièce suffirait à
        déposer — ou à écraser — un document dans le dossier d'un autre.
        """
        autre = DossierCandidature.objects.create(
            nom="Placide",
            prenom="Serge",
            email="serge@example.org",
            parcours_souhaite=parcours,
            motivations="…",
        )
        reponse = client.post(
            reverse("admissions:deposer_piece", args=[autre.token_suivi, piece.pk]),
            {"fichier": fichier()},
        )
        assert reponse.status_code == 404
        piece.refresh_from_db()
        assert not piece.fichier

    def test_le_depot_exige_un_post(self, client, dossier, piece):
        reponse = client.get(reverse("admissions:deposer_piece", args=[dossier.token_suivi, piece.pk]))
        assert reponse.status_code == 405


# ══════════════════════════════════════════════
# Le secrétariat tranche
# ══════════════════════════════════════════════


@pytest.mark.django_db
class TestDecision:
    def test_la_validation_cloture_la_piece(self, client, secretaire, piece):
        piece.deposer(fichier())
        client.force_login(secretaire)
        client.post(reverse("administration:piece_decision", args=[piece.pk]), {"action": "valider"})
        piece.refresh_from_db()
        assert piece.statut == PieceDemandee.Statut.VALIDEE
        assert piece.est_fournie is True

    def test_un_refus_sans_motif_est_rejete(self, piece):
        """Un refus muet obligerait le candidat à deviner ce qui ne va pas."""
        piece.deposer(fichier())
        with pytest.raises(ValidationError):
            piece.refuser("   ")

    def test_le_refus_previent_le_candidat_avec_le_motif(self, client, secretaire, piece):
        piece.deposer(fichier())
        mail.outbox.clear()
        client.force_login(secretaire)
        client.post(
            reverse("administration:piece_decision", args=[piece.pk]),
            {"action": "refuser", "motif": "Le document est illisible."},
        )
        piece.refresh_from_db()
        assert piece.statut == PieceDemandee.Statut.REFUSEE
        assert piece.est_fournie is False
        assert len(mail.outbox) == 1
        assert "illisible" in mail.outbox[0].body

    def test_un_nouveau_depot_efface_le_refus(self, piece):
        piece.deposer(fichier())
        piece.refuser("Illisible.")
        piece.deposer(fichier("acte-net.pdf"))
        assert piece.statut == PieceDemandee.Statut.DEPOSEE
        assert piece.motif_refus == ""
        assert piece.date_decision is None

    def test_le_fichier_depose_n_est_pas_public(self, client, piece):
        """Une pièce d'identité ne se télécharge pas sans être identifié."""
        piece.deposer(fichier())
        reponse = client.get(reverse("administration:piece_fichier", args=[piece.pk]))
        assert reponse.status_code in (302, 403)

    def test_le_secretariat_telecharge_la_piece(self, client, secretaire, piece):
        piece.deposer(fichier())
        client.force_login(secretaire)
        reponse = client.get(reverse("administration:piece_fichier", args=[piece.pk]))
        assert reponse.status_code == 200
