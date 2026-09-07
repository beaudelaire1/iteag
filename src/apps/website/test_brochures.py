"""Dépôt, publication et consultation des brochures.

Ce que ces essais protègent : le secrétariat doit pouvoir publier une brochure
sans passer par l'administration Wagtail, et un brouillon ne doit être lisible
de personne — pas même par l'adresse de son fichier.
"""

import io
from zipfile import ZipFile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils.html import escape

from apps.accounts.models import User
from apps.website.models_publications import Brochure

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"


def _pdf_minimal(taille: int = 400) -> bytes:
    """Un PDF que la validation binaire accepte : la signature suffit."""
    corps = b"%PDF-1.4\n" + b"%iteag\n" * 20
    return corps.ljust(taille, b" ")


def _fichier_pdf(nom="brochure.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(nom, _pdf_minimal(), content_type="application/pdf")


def _fichier_docx(nom="brochure.docx") -> SimpleUploadedFile:
    """Un DOCX que la validation structurelle accepte.

    La signature ZIP ne suffit pas : « valider_fichier » ouvre l'archive et
    exige le manifeste et le dossier « word/ », faute de quoi n'importe quel
    ZIP renommé passerait.
    """
    tampon = io.BytesIO()
    with ZipFile(tampon, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    return SimpleUploadedFile(
        nom,
        tampon.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _png_minimal() -> bytes:
    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(tampon, format="PNG")
    return tampon.getvalue()


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="sec_brochure", email="sb@iteag.org", password=MOT_DE_PASSE, role=User.Role.SECRETARIAT
    )


@pytest.fixture
def etudiant(db):
    return User.objects.create_user(
        username="etu_brochure", email="eb@iteag.org", password=MOT_DE_PASSE, role=User.Role.ETUDIANT
    )


@pytest.fixture
def brochure(db, secretaire):
    return Brochure.objects.create(
        titre="Présentation de l'ITEAG",
        description="Le parcours, l'équipe et les modalités d'admission.",
        categorie=Brochure.Categorie.INSTITUTION,
        fichier=_fichier_pdf(),
        deposee_par=secretaire,
    )


# ══════════════════════════════════════════════
# Dépôt et cycle de publication
# ══════════════════════════════════════════════


class TestDepot:
    def test_la_secretaire_atteint_la_rubrique(self, client, secretaire):
        client.force_login(secretaire)
        reponse = client.get(reverse("website:brochures_gestion"))
        assert reponse.status_code == 200

    def test_un_etudiant_n_atteint_pas_la_gestion(self, client, etudiant):
        client.force_login(etudiant)
        reponse = client.get(reverse("website:brochures_gestion"))
        assert reponse.status_code in (302, 403)

    def test_le_lien_figure_dans_la_barre_du_secretariat(self, client, secretaire):
        client.force_login(secretaire)
        reponse = client.get(reverse("website:brochures_gestion"))
        assert reverse("website:brochures_gestion").encode() in reponse.content
        assert b"Brochures" in reponse.content

    def test_depot_d_une_brochure(self, client, secretaire):
        client.force_login(secretaire)
        reponse = client.post(
            reverse("website:brochure_creation"),
            {
                "titre": "Brochure Bachelor FLTE",
                "categorie": Brochure.Categorie.FORMATION,
                "description": "Le cursus en trois ans.",
                "fichier": _fichier_pdf(),
                "ordre": 0,
            },
        )
        assert reponse.status_code == 302
        deposee = Brochure.objects.get(titre="Brochure Bachelor FLTE")
        # Rien n'est publié par surprise : le dépôt est un brouillon.
        assert deposee.statut == Brochure.Statut.BROUILLON
        assert deposee.deposee_par == secretaire
        assert deposee.slug == "brochure-bachelor-flte"

    def test_un_fichier_qui_n_est_pas_un_pdf_est_refuse(self, client, secretaire):
        client.force_login(secretaire)
        reponse = client.post(
            reverse("website:brochure_creation"),
            {
                "titre": "Fausse brochure",
                "categorie": Brochure.Categorie.AUTRE,
                "fichier": SimpleUploadedFile("piege.pdf", b"<html>rien</html>", content_type="application/pdf"),
                "ordre": 0,
            },
        )
        assert reponse.status_code == 200
        assert not Brochure.objects.filter(titre="Fausse brochure").exists()

    def test_un_document_bureautique_est_accepte(self, client, secretaire):
        """Le catalogue accepte ce que l'actualité accepte, et rien d'autre.

        Une plaquette arrive parfois en DOCX. La refuser ici alors que le même
        fichier passe en pièce jointe d'une actualité serait incompréhensible
        pour qui dépose.
        """
        client.force_login(secretaire)
        reponse = client.post(
            reverse("website:brochure_creation"),
            {
                "titre": "Programme des portes ouvertes",
                "categorie": Brochure.Categorie.EVENEMENT,
                "fichier": _fichier_docx(),
                "ordre": 0,
            },
        )
        assert reponse.status_code == 302
        deposee = Brochure.objects.get(titre="Programme des portes ouvertes")
        assert deposee.format_lisible == "DOCX"

    def test_le_document_est_servi_sous_son_vrai_type(self, client, secretaire):
        """Annoncer « application/pdf » pour un DOCX le rendrait illisible."""
        brochure = Brochure.objects.create(
            titre="Programme en bureautique",
            fichier=_fichier_docx("programme.docx"),
            deposee_par=secretaire,
        )
        brochure.publier()
        reponse = client.get(brochure.get_absolute_url())
        assert reponse.status_code == 200
        assert reponse["Content-Type"] == ("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        assert reponse.filename == "programme-en-bureautique.docx"

    def test_la_regle_de_depot_est_celle_de_l_actualite(self):
        """Une seule règle : deux copies dériveraient au premier format ajouté."""
        from apps.website.formulaires_actualites import REGLE_BROCHURE as regle_actualite
        from apps.website.formulaires_brochures import REGLE_BROCHURE as regle_catalogue

        assert regle_catalogue is regle_actualite

    def test_modifier_le_titre_sans_redeposer_le_fichier(self, client, secretaire, brochure):
        client.force_login(secretaire)
        chemin_initial = brochure.fichier.name
        reponse = client.post(
            reverse("website:brochure_edition", kwargs={"pk": brochure.pk}),
            {
                "titre": "Présentation de l'ITEAG — édition 2026",
                "categorie": Brochure.Categorie.INSTITUTION,
                "description": brochure.description,
                "ordre": 0,
            },
        )
        assert reponse.status_code == 302
        brochure.refresh_from_db()
        assert brochure.titre == "Présentation de l'ITEAG — édition 2026"
        assert brochure.fichier.name == chemin_initial

    def test_publier_montre_ou_la_brochure_a_paru(self, client, secretaire, brochure):
        """Publier ne disait que « c'est en ligne ». Ni la page, ni l'endroit.

        Le secrétariat repartait de là sans savoir où regarder : la page publique
        n'était atteignable que par le pied de page, et le titre de la brochure
        menait au fichier, pas à l'endroit où il apparaît. On lui rend donc
        l'adresse, et un lien qui y mène.
        """
        client.force_login(secretaire)
        reponse = client.post(
            reverse("website:brochure_decision", kwargs={"pk": brochure.pk}),
            {"action": "publier"},
            follow=True,
        )

        assert reponse.status_code == 200
        brochure.refresh_from_db()
        assert reponse.context["vient_de_paraitre"] == brochure
        contenu = reponse.content.decode()
        assert brochure.url_sur_le_site in contenu
        assert "Voir la brochure sur le site" in contenu

    def test_l_adresse_publique_mene_a_la_place_de_la_brochure(self, client, brochure):
        """L'ancre doit exister sur la page, sinon le lien ne mène qu'à la liste."""
        brochure.publier()

        contenu = client.get(reverse("website:brochures")).content.decode()

        assert f'id="brochure-{brochure.slug}"' in contenu
        assert brochure.url_sur_le_site.endswith(f"#brochure-{brochure.slug}")

    def test_le_catalogue_figure_dans_la_navigation_publique(self, client):
        """Le pied de page ne suffit pas : personne n'y cherche une rubrique."""
        from apps.core.navigation import rubriques

        adresses = [entree.url for rubrique in rubriques() for entree in rubrique.entrees]

        assert reverse("website:brochures") in adresses

    def test_publier_puis_retirer(self, client, secretaire, brochure):
        client.force_login(secretaire)
        adresse = reverse("website:brochure_decision", kwargs={"pk": brochure.pk})

        client.post(adresse, {"action": "publier"})
        brochure.refresh_from_db()
        assert brochure.est_publiee
        assert brochure.date_publication is not None

        client.post(adresse, {"action": "depublier"})
        brochure.refresh_from_db()
        assert not brochure.est_publiee
        # Retirer ne détruit rien : le fichier et la date restent en place.
        assert brochure.fichier
        assert brochure.date_publication is not None

    def test_supprimer_efface_la_fiche(self, client, secretaire, brochure):
        client.force_login(secretaire)
        client.post(reverse("website:brochure_decision", kwargs={"pk": brochure.pk}), {"action": "supprimer"})
        assert not Brochure.objects.filter(pk=brochure.pk).exists()


# ══════════════════════════════════════════════
# Lecture publique
# ══════════════════════════════════════════════


class TestPagePublique:
    def test_seules_les_brochures_publiees_paraissent(self, client, brochure):
        # Le gabarit échappe l'apostrophe du titre : on compare donc sur la
        # forme échappée, sans quoi l'essai échouerait pour la mauvaise raison.
        attendu = escape(brochure.titre).encode()
        reponse = client.get(reverse("website:brochures"))
        assert reponse.status_code == 200
        assert attendu not in reponse.content

        brochure.publier()
        reponse = client.get(reverse("website:brochures"))
        assert attendu in reponse.content

    def test_filtrage_par_categorie(self, client, brochure, secretaire):
        brochure.publier()
        autre = Brochure.objects.create(
            titre="Guide des admissions",
            categorie=Brochure.Categorie.ADMISSION,
            fichier=_fichier_pdf("admissions.pdf"),
            deposee_par=secretaire,
        )
        autre.publier()

        reponse = client.get(reverse("website:brochures"), {"categorie": Brochure.Categorie.ADMISSION})
        assert autre.titre.encode() in reponse.content
        assert escape(brochure.titre).encode() not in reponse.content

    def test_telechargement_d_une_brochure_publiee(self, client, brochure):
        brochure.publier()
        reponse = client.get(brochure.get_absolute_url())
        assert reponse.status_code == 200
        assert reponse["Content-Type"] == "application/pdf"
        assert b"".join(reponse.streaming_content).startswith(b"%PDF-")

        brochure.refresh_from_db()
        assert brochure.nombre_telechargements == 1

    def test_un_brouillon_ne_se_telecharge_pas(self, client, brochure):
        reponse = client.get(brochure.get_absolute_url())
        assert reponse.status_code == 404


# ══════════════════════════════════════════════
# Modèle
# ══════════════════════════════════════════════


class TestModele:
    def test_deux_brochures_de_meme_titre_gardent_des_adresses_distinctes(self, secretaire):
        premiere = Brochure.objects.create(titre="Plaquette", fichier=_fichier_pdf(), deposee_par=secretaire)
        seconde = Brochure.objects.create(titre="Plaquette", fichier=_fichier_pdf("p2.pdf"), deposee_par=secretaire)
        assert premiere.slug != seconde.slug

    def test_taille_lisible_ne_casse_pas_sans_fichier(self):
        assert Brochure(titre="Sans fichier").taille_lisible == ""
