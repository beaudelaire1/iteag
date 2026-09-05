"""Rédaction et publication des actualités structurées depuis le back-office."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from wagtail.models import Site

from apps.accounts.models import User
from apps.website.editorial import CorpsActualiteBlock
from apps.website.models import NewsIndexPage, NewsPage
from apps.website.models_publications import ContenuActualite

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"


def _png_minimal() -> bytes:
    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(tampon, format="PNG")
    return tampon.getvalue()


@pytest.fixture
def index(db):
    accueil = Site.objects.get(is_default_site=True).root_page
    page = NewsIndexPage(title="Actualités", slug="actualites-test")
    accueil.add_child(instance=page)
    return page


@pytest.fixture
def secretaire(db):
    return User.objects.create_user(
        username="sec_actu", email="sa@iteag.org", password=MOT_DE_PASSE, role=User.Role.SECRETARIAT
    )


@pytest.fixture
def directrice(db):
    return User.objects.create_user(
        username="dir_actu", email="da@iteag.org", password=MOT_DE_PASSE, role=User.Role.ADMIN
    )


@pytest.fixture
def actualite(index):
    page = NewsPage(
        title="Rentrée académique 2026",
        slug="rentree-2026",
        date=timezone.localdate(),
        body="<p>La rentrée est fixée au 14 septembre.</p>",
        live=False,
        has_unpublished_changes=True,
    )
    index.add_child(instance=page)
    return page


def _saisie(**surcharges):
    """Ancien format volontairement accepté : il devient un bloc texte."""
    donnees = {
        "titre": "Journée portes ouvertes",
        "date": "2026-09-14",
        "chapeau": "L'institut ouvre ses portes.",
        "corps": "<p>Venez nous rencontrer.</p>",
    }
    donnees.update(surcharges)
    return donnees


PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"0" * 64


def _brochure(nom="brochure.pdf", contenu=PDF, type_mime="application/pdf"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(nom, contenu, content_type=type_mime)


class TestBrochure:
    """
    La secrétaire doit pouvoir joindre une brochure à une annonce.

    Jusqu'ici, publier un document supposait de le déposer quelque part puis d'en
    coller l'adresse dans le corps du texte — quand quelqu'un savait le faire.
    Le fichier rejoint la médiathèque Wagtail, comme les images : il reste donc
    consultable et remplaçable depuis l'administration.
    """

    def test_la_brochure_est_jointe_et_rejoint_la_mediatheque(self, client, secretaire, index):
        from wagtail.documents import get_document_model

        client.force_login(secretaire)
        client.post(
            reverse("website:actualite_creation"),
            _saisie(brochure=_brochure(), brochure_libelle="Brochure Licence 2026-2027"),
        )

        page = NewsPage.objects.get(title="Journée portes ouvertes")
        assert page.brochure_id is not None
        assert page.brochure_libelle == "Brochure Licence 2026-2027"
        assert get_document_model().objects.count() == 1

    def test_le_bouton_de_telechargement_apparait_sur_la_page(self, client, secretaire, index):
        client.force_login(secretaire)
        client.post(
            reverse("website:actualite_creation"),
            _saisie(brochure=_brochure(), brochure_libelle="Brochure Licence 2026-2027"),
        )
        # Une actualité créée reste un brouillon : sa page publique n'existe
        # qu'une fois la publication décidée.
        page = NewsPage.objects.get(title="Journée portes ouvertes")
        page.save_revision().publish()

        contenu = client.get(page.url).content.decode()

        assert "Brochure Licence 2026-2027" in contenu
        assert "Document à télécharger" in contenu

    def test_sans_brochure_aucun_bouton(self, client, secretaire, index):
        client.force_login(secretaire)
        client.post(reverse("website:actualite_creation"), _saisie())
        page = NewsPage.objects.get(title="Journée portes ouvertes")
        page.save_revision().publish()

        assert "Document à télécharger" not in client.get(page.url).content.decode()

    def test_un_fichier_renomme_en_pdf_est_refuse(self, client, secretaire, index):
        """L'extension ne prouve rien : c'est la signature qui tranche."""
        client.force_login(secretaire)
        reponse = client.post(
            reverse("website:actualite_creation"),
            _saisie(brochure=_brochure(contenu=b"MZ\x90\x00 programme" * 8)),
        )

        assert reponse.status_code == 200
        assert not NewsPage.objects.filter(title="Journée portes ouvertes").exists()

    def test_l_intitule_se_corrige_sans_redeposer_le_fichier(self, client, secretaire, index):
        """C'est le libellé d'un bouton qu'on ajuste le plus souvent après coup."""
        client.force_login(secretaire)
        client.post(
            reverse("website:actualite_creation"),
            _saisie(brochure=_brochure(), brochure_libelle="Brochre Licence"),
        )
        page = NewsPage.objects.get(title="Journée portes ouvertes")
        document_initial = page.brochure_id

        client.post(
            reverse("website:actualite_edition", args=[page.pk]),
            _saisie(brochure_libelle="Brochure Licence 2026-2027"),
        )

        page.refresh_from_db()
        assert page.brochure_libelle == "Brochure Licence 2026-2027"
        assert page.brochure_id == document_initial


class TestPerimetre:
    def test_le_secretariat_ecrit_les_actualites(self, client, secretaire, index):
        client.force_login(secretaire)
        assert client.get(reverse("website:actualites_gestion")).status_code == 200

    def test_la_direction_aussi(self, client, directrice, index):
        client.force_login(directrice)
        assert client.get(reverse("website:actualites_gestion")).status_code == 200

    def test_un_enseignant_n_y_accede_pas(self, client, db, index):
        prof = User.objects.create_user(
            username="prof_actu", email="pa@iteag.org", password=MOT_DE_PASSE, role=User.Role.ENSEIGNANT
        )
        client.force_login(prof)
        assert client.get(reverse("website:actualites_gestion")).status_code in (302, 403)

    def test_la_barre_du_secretariat_y_mene(self, client, secretaire, index):
        client.force_login(secretaire)
        contenu = client.get(reverse("secretariat:dashboard")).content.decode()
        assert f'href="{reverse("website:actualites_gestion")}"' in contenu


class TestStructure:
    def test_le_vocabulaire_reste_volontairement_court(self):
        noms = set(CorpsActualiteBlock().child_blocks)
        assert noms == {
            "texte",
            "important",
            "tableau",
            "procedure",
            "chiffres_cles",
            "graphique",
            "citation",
            "encadre",
        }

    def test_l_editeur_du_portail_sert_le_runtime_wagtail_complet(self, client, secretaire, index):
        client.force_login(secretaire)
        html = client.get(reverse("website:actualite_creation")).content.decode()

        assert 'id="wagtail-config"' in html
        assert "wagtailadmin/js/core.js" in html
        assert "wagtailadmin/js/vendor.js" in html
        assert "telepath/blocks.js" in html
        assert 'data-controller="w-block"' in html
        assert "Contenu de l'actualité" in html
        assert "streamfield-portail.js" not in html

        assert html.index("wagtail-config") < html.index("wagtailadmin/js/core.js")
        assert html.index("wagtailadmin/js/core.js") < html.index("telepath/blocks.js")

    def test_un_ancien_corps_devient_un_bloc_texte(self, client, secretaire, index):
        client.force_login(secretaire)
        client.post(reverse("website:actualite_creation"), _saisie())

        page = NewsPage.objects.get(title="Journée portes ouvertes")
        structure = page.contenu_structure.contenu
        assert len(structure) == 1
        assert structure[0].block_type == "texte"
        assert "Venez nous rencontrer" in str(structure[0].value)

    def test_le_script_glisse_dans_l_ancien_corps_ne_survit_pas(self, client, secretaire, index):
        client.force_login(secretaire)
        client.post(
            reverse("website:actualite_creation"),
            _saisie(corps='<p>Bonjour</p><script>fetch("/vol")</script>'),
        )
        structure = NewsPage.objects.get(title="Journée portes ouvertes").contenu_structure.contenu
        texte = str(structure[0].value)
        assert "<script" not in texte
        assert "Bonjour" in texte

    def test_une_actualite_sans_contenu_est_refusee(self, client, secretaire, index):
        client.force_login(secretaire)
        reponse = client.post(reverse("website:actualite_creation"), _saisie(corps=""))
        assert reponse.status_code == 200
        assert not NewsPage.objects.filter(title="Journée portes ouvertes").exists()


class TestRedaction:
    def test_l_actualite_entre_dans_l_arbre_et_nait_hors_ligne(self, client, secretaire, index):
        client.force_login(secretaire)
        client.post(reverse("website:actualite_creation"), _saisie())
        page = NewsPage.objects.get(title="Journée portes ouvertes")
        assert page.get_parent().specific == index
        assert page.url
        assert not page.live

    def test_deux_actualites_de_meme_titre_ont_deux_adresses(self, client, secretaire, index):
        client.force_login(secretaire)
        client.post(reverse("website:actualite_creation"), _saisie())
        client.post(reverse("website:actualite_creation"), _saisie())
        slugs = list(NewsPage.objects.filter(title="Journée portes ouvertes").values_list("slug", flat=True))
        assert len(slugs) == 2
        assert len(set(slugs)) == 2

    def test_l_image_deposee_rejoint_la_mediatheque(self, client, secretaire, index):
        client.force_login(secretaire)
        image = SimpleUploadedFile("photo.png", _png_minimal(), content_type="image/png")
        client.post(reverse("website:actualite_creation"), _saisie(image=image))
        page = NewsPage.objects.get(title="Journée portes ouvertes")
        assert page.image is not None
        assert page.image.width == 4

    def test_la_correction_ne_change_pas_l_adresse(self, client, secretaire, actualite):
        client.force_login(secretaire)
        client.post(
            reverse("website:actualite_edition", args=[actualite.pk]),
            _saisie(titre="Rentrée académique 2026 — précisions"),
        )
        actualite.refresh_from_db()
        assert actualite.title == "Rentrée académique 2026 — précisions"
        assert actualite.slug == "rentree-2026"
        assert ContenuActualite.objects.filter(actualite=actualite).exists()


class TestMiseEnLigne:
    def test_la_publication_rend_l_actualite_visible_du_public(self, client, secretaire, actualite, index):
        client.force_login(secretaire)
        client.post(reverse("website:actualite_decision", args=[actualite.pk]), {"action": "publier"})
        actualite.refresh_from_db()
        assert actualite.live
        client.logout()
        assert "Rentrée académique 2026" in client.get(index.url).content.decode()

    def test_la_depublication_conserve_le_contenu_historique(self, client, secretaire, actualite):
        client.force_login(secretaire)
        client.post(reverse("website:actualite_decision", args=[actualite.pk]), {"action": "publier"})
        client.post(reverse("website:actualite_decision", args=[actualite.pk]), {"action": "depublier"})
        actualite.refresh_from_db()
        assert not actualite.live
        assert "14 septembre" in actualite.body

    def test_la_correction_d_une_actualite_en_ligne_se_voit_aussitot(self, client, secretaire, actualite):
        client.force_login(secretaire)
        client.post(reverse("website:actualite_decision", args=[actualite.pk]), {"action": "publier"})
        client.post(
            reverse("website:actualite_edition", args=[actualite.pk]),
            _saisie(titre="Rentrée académique 2026", corps="<p>La rentrée est repoussée au 21.</p>"),
        )
        client.logout()
        assert "repoussée au 21" in client.get(actualite.url).content.decode()

    def test_la_suppression_retire_aussi_le_contenu_structure(self, client, secretaire, actualite):
        ContenuActualite.objects.create(actualite=actualite, contenu=[("texte", "<p>Texte</p>")])
        client.force_login(secretaire)
        client.post(reverse("website:actualite_decision", args=[actualite.pk]), {"action": "supprimer"})
        assert not NewsPage.objects.filter(pk=actualite.pk).exists()
        assert not ContenuActualite.objects.filter(actualite_id=actualite.pk).exists()

    def test_une_action_inconnue_ne_change_rien(self, client, secretaire, actualite):
        client.force_login(secretaire)
        client.post(reverse("website:actualite_decision", args=[actualite.pk]), {"action": "n_importe_quoi"})
        actualite.refresh_from_db()
        assert not actualite.live


class TestEcranDeGestion:
    def test_les_brouillons_figurent_a_l_ecran(self, client, secretaire, actualite):
        client.force_login(secretaire)
        contenu = client.get(reverse("website:actualites_gestion")).content.decode()
        assert "Rentrée académique 2026" in contenu
        assert "Brouillons (1)" in contenu

    def test_ecrire_sans_index_dans_l_arbre_le_dit_franchement(self, client, secretaire):
        client.force_login(secretaire)
        reponse = client.post(reverse("website:actualite_creation"), _saisie())
        assert reponse.status_code == 404
