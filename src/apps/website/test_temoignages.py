import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import Context, Template
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import ProfilEtudiant, Promotion
from apps.accounts.models import User
from apps.core.models import Notification
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


def _petite_photo():
    # GIF 1×1 valide : aucune dépendance à un fichier du dépôt.
    contenu = (
        b"GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
        b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
        b"\x00\x02\x02D\x01\x00;"
    )
    return SimpleUploadedFile("portrait.gif", contenu, content_type="image/gif")


def _rendu_public():
    return Template("{% load website_public %}{% temoignages_publics %}").render(Context())


class TestSoumissionEtudiant:
    def test_l_etudiant_dispose_d_un_chemin_dans_son_espace(self, client, etudiant):
        client.force_login(etudiant)
        html = client.get(reverse("etudiant:dashboard")).content.decode()
        assert reverse("website:temoignage_etudiant") in html

    def test_l_etudiant_soumet_un_temoignage_en_attente_et_notifie_la_direction(
        self, client, etudiant, promotion, admin
    ):
        client.force_login(etudiant)
        reponse = client.post(reverse("website:temoignage_etudiant"), _soumission())
        assert reponse.status_code == 302

        temoignage = TemoignageEtudiant.objects.get(etudiant=etudiant)
        assert temoignage.statut == TemoignageEtudiant.Statut.EN_ATTENTE
        assert temoignage.nom_affiche == "Maya Jean"
        assert temoignage.promotion == str(promotion)
        assert temoignage.consentement_publication
        assert Notification.objects.filter(destinataire=admin, titre__contains="Témoignage à valider").exists()

    def test_le_consentement_est_obligatoire(self, client, etudiant):
        client.force_login(etudiant)
        reponse = client.post(
            reverse("website:temoignage_etudiant"),
            {"texte": "Un témoignage suffisamment long pour être recevable sans consentement."},
        )
        assert reponse.status_code == 200
        assert not TemoignageEtudiant.objects.filter(etudiant=etudiant).exists()

    def test_gras_et_italique_sont_conserves_mais_le_script_est_supprime(self, client, etudiant, admin):
        client.force_login(etudiant)
        client.post(
            reverse("website:temoignage_etudiant"),
            _soumission(
                "<p>Une expérience <strong>très structurante</strong> et <em>humaine</em> "
                "qui m'aide à progresser durablement.</p><script>alert('x')</script>"
            ),
        )
        texte = TemoignageEtudiant.objects.get(etudiant=etudiant).texte
        assert "<strong>très structurante</strong>" in texte
        assert "<em>humaine</em>" in texte
        assert "<script" not in texte

    def test_l_etudiant_peut_choisir_une_photo_specifique(self, client, etudiant, admin):
        client.force_login(etudiant)
        donnees = _soumission()
        donnees["photo"] = _petite_photo()
        reponse = client.post(reverse("website:temoignage_etudiant"), donnees)
        assert reponse.status_code == 302

        temoignage = TemoignageEtudiant.objects.get(etudiant=etudiant)
        assert temoignage.photo.name.startswith("temoignages/")

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

    def test_la_direction_publie_et_l_etudiant_est_notifie(self, client, admin, etudiant):
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
        assert Notification.objects.filter(destinataire=etudiant, titre__contains="est publié").exists()

    def test_un_refus_exige_un_motif_et_notifie_l_etudiant(self, client, admin, etudiant):
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
        assert Notification.objects.filter(destinataire=etudiant, titre__contains="à reprendre").exists()

    def test_la_direction_peut_retirer_un_temoignage_publie(self, client, admin, etudiant):
        temoignage = TemoignageEtudiant.objects.create(
            etudiant=etudiant,
            nom_affiche="Maya Jean",
            texte="Un témoignage publié qui pourra ensuite être retiré sans être supprimé.",
            consentement_publication=True,
            statut=TemoignageEtudiant.Statut.PUBLIE,
            valide_le=timezone.now(),
            valide_par=admin,
        )
        client.force_login(admin)
        reponse = client.post(
            reverse("website:temoignage_decision"),
            {"temoignage_id": temoignage.pk, "action": "retirer"},
        )
        assert reponse.status_code == 302

        temoignage.refresh_from_db()
        assert temoignage.statut == TemoignageEtudiant.Statut.RETIRE
        assert TemoignageEtudiant.objects.filter(pk=temoignage.pk).exists()
        assert Notification.objects.filter(destinataire=etudiant, titre__contains="retiré du site").exists()
        assert "publié qui pourra ensuite être retiré" not in _rendu_public()


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

    def test_l_extrait_public_reste_du_texte_simple(self, etudiant, admin):
        TemoignageEtudiant.objects.create(
            etudiant=etudiant,
            nom_affiche="Maya Jean",
            texte="<p>Une expérience <strong>solide</strong> et <em>exigeante</em>.</p>",
            consentement_publication=True,
            statut=TemoignageEtudiant.Statut.PUBLIE,
            valide_le=timezone.now(),
            valide_par=admin,
        )
        html = _rendu_public()
        assert "solide" in html
        assert "exigeante" in html
        assert "<strong>solide</strong>" not in html
        assert "<em>exigeante</em>" not in html

    def test_aucune_section_vide_n_est_affichee(self):
        assert "Paroles d'étudiants" not in _rendu_public()
