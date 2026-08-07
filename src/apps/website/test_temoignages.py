import pytest
from django.template import Context, Template
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.formations.models import Parcours
from apps.website.models_publications import TemoignageEtudiant

pytestmark = pytest.mark.django_db
MOT_DE_PASSE = "motdepasse-long-12"


@pytest.fixture
def parcours(db):
    return Parcours.objects.create(
        nom="Parcours diplômant",
        slug="parcours-temoignage",
        type_parcours=Parcours.TypeParcours.DIPLOMANT_ITEAG,
    )


@pytest.fixture
def promotion(parcours):
    return Promotion.objects.create(
        nom="Promotion 2026-2032",
        parcours=parcours,
        annee_debut=2026,
        annee_fin=2032,
    )


@pytest.fixture
def etudiant(parcours, promotion):
    utilisateur = User.objects.create_user(
        username="etu_tem",
        email="etu-tem@iteag.org",
        password=MOT_DE_PASSE,
        role=User.Role.ETUDIANT,
        first_name="Maya",
        last_name="Jean",
    )
    ProfilEtudiant.objects.create(
        utilisateur=utilisateur,
        parcours=parcours,
        promotion=promotion,
        numero_etudiant="ITEAGTEST01",
    )
    return utilisateur


@pytest.fixture
def admin(db):
    return User.objects.create_user(
        username="dir_tem",
        email="dir-tem@iteag.org",
        password=MOT_DE_PASSE,
        role=User.Role.ADMIN,
    )


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="sec_tem",
        email="sec-tem@iteag.org",
        password=MOT_DE_PASSE,
        role=User.Role.SECRETARIAT,
    )


def _soumission(texte="L'ITEAG m'a donné des repères solides pour approfondir ma formation théologique."):
    return {"texte": texte, "consentement_publication": "on"}


def _rendu_public():
    return Template("{% load website_public %}{% temoignages_publics %}").render(Context())


class TestSoumissionEtudiant:
    def test_l_etudiant_dispose_d_un_chemin_dans_son_espace(self, client, etudiant):
        client.force_login(etudiant)
        html = client.get(reverse("etudiant:dashboard")).content.decode()
        assert reverse("website:temoignage_etudiant") in html

    def test_l_etudiant_soumet_un_temoignage_en_attente(self, client, etudiant, promotion):
        client.force_login(etudiant)
        reponse = client.post(reverse("website:temoignage_etudiant"), _soumission())
        assert reponse.status_code == 302

        temoignage = TemoignageEtudiant.objects.get(etudiant=etudiant)
        assert temoignage.statut == TemoignageEtudiant.Statut.EN_ATTENTE
        assert temoignage.nom_affiche == "Maya Jean"
        assert temoignage.promotion == str(promotion)
        assert temoignage.consentement_publication

    def test_le_consentement_est_obligatoire(self, client, etudiant):
        client.force_login(etudiant)
        reponse = client.post(
            reverse("website:temoignage_etudiant"),
            {"texte": "Un témoignage suffisamment long pour être recevable sans consentement."},
        )
        assert reponse.status_code == 200
        assert not TemoignageEtudiant.objects.filter(etudiant=etudiant).exists()

    def test_modifier_un_temoignage_publie_le_remet_en_attente(self, client, etudiant, admin):
        temoignage = TemoignageEtudiant.objects.create(
            etudiant=etudiant,
            nom_affiche="Maya Jean",
            promotion="Promotion 2026-2032",
            texte="Un premier témoignage publié et approuvé par la direction.",
            consentement_publication=True,
            statut=TemoignageEtudiant.Statut.PUBLIE,
            valide_le=timezone.now(),
            valide_par=admin,
        )
        client.force_login(etudiant)
        client.post(
            reverse("website:temoignage_etudiant"),
            _soumission("Voici une nouvelle version de mon témoignage, qui doit être relue avant publication."),
        )
        temoignage.refresh_from_db()
        assert temoignage.statut == TemoignageEtudiant.Statut.EN_ATTENTE
        assert temoignage.valide_le is None
        assert temoignage.valide_par is None


class TestModeration:
    def test_le_secretariat_ne_peut_pas_valider(self, client, secretaire):
        client.force_login(secretaire)
        assert client.get(reverse("website:temoignages_gestion")).status_code in (302, 403)

    def test_la_direction_voit_l_ecran_de_validation(self, client, admin):
        client.force_login(admin)
        assert client.get(reverse("website:temoignages_gestion")).status_code == 200

    def test_la_direction_publie_un_temoignage_consenti(self, client, admin, etudiant):
        temoignage = TemoignageEtudiant.objects.create(
            etudiant=etudiant,
            nom_affiche="Maya Jean",
            promotion="Promotion 2026-2032",
            texte="Un témoignage prêt à être publié après relecture par la direction.",
            consentement_publication=True,
        )
        client.force_login(admin)
        client.post(
            reverse("website:temoignage_decision"),
            {"temoignage_id": temoignage.pk, "action": "publier"},
        )
        temoignage.refresh_from_db()
        assert temoignage.statut == TemoignageEtudiant.Statut.PUBLIE
        assert temoignage.valide_par == admin
        assert temoignage.valide_le is not None

    def test_un_refus_exige_un_motif(self, client, admin, etudiant):
        temoignage = TemoignageEtudiant.objects.create(
            etudiant=etudiant,
            nom_affiche="Maya Jean",
            texte="Un témoignage à revoir avant toute éventuelle publication publique.",
            consentement_publication=True,
        )
        client.force_login(admin)
        client.post(
            reverse("website:temoignage_decision"),
            {"temoignage_id": temoignage.pk, "action": "refuser", "motif": ""},
        )
        temoignage.refresh_from_db()
        assert temoignage.statut == TemoignageEtudiant.Statut.EN_ATTENTE

        client.post(
            reverse("website:temoignage_decision"),
            {
                "temoignage_id": temoignage.pk,
                "action": "refuser",
                "motif": "Précisez davantage ce que la formation vous a apporté.",
            },
        )
        temoignage.refresh_from_db()
        assert temoignage.statut == TemoignageEtudiant.Statut.REFUSE
        assert "Précisez" in temoignage.motif_refus


class TestPublicationPublique:
    def test_seul_un_temoignage_publie_et_consenti_apparait(self, etudiant, admin):
        TemoignageEtudiant.objects.create(
            etudiant=etudiant,
            nom_affiche="Maya Jean",
            texte="Ce témoignage a été explicitement validé et peut être montré au public.",
            consentement_publication=True,
            statut=TemoignageEtudiant.Statut.PUBLIE,
            valide_le=timezone.now(),
            valide_par=admin,
        )
        TemoignageEtudiant.objects.create(
            nom_affiche="Autre étudiant",
            texte="Ce texte attend encore une décision et ne doit pas apparaître publiquement.",
            consentement_publication=True,
            statut=TemoignageEtudiant.Statut.EN_ATTENTE,
        )

        html = _rendu_public()
        assert "explicitement validé" in html
        assert "attend encore une décision" not in html

    def test_aucune_section_vide_n_est_affichee(self):
        assert "Paroles d'étudiants" not in _rendu_public()
