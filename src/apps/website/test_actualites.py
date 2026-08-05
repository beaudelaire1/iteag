"""Publier une actualité depuis le back-office, sans passer par Wagtail.

Le défaut corrigé n'est pas une erreur de code : c'est une fonction que
personne ne pouvait exercer. Les actualités sont des pages Wagtail, et
l'administration Wagtail n'a de lien depuis aucun des deux espaces de gestion.
Annoncer une rentrée supposait donc de connaître une seconde interface, ses
notions d'arbre, de révision et de brouillon.

Ce que les tests surveillent en priorité tient à ce que Wagtail impose et
qu'une vue ordinaire oublie :

- la page doit **entrer dans l'arbre**, faute de quoi elle n'a pas d'URL ;
- « enregistré » et « en ligne » sont deux états distincts — une annonce
  écrite ne doit pas paraître avant qu'on le demande ;
- l'adresse ne bouge plus après la création, sinon les liens partagés cassent ;
- ce qui vient de l'éditeur repasse par la liste blanche, comme partout
  ailleurs : la page est publique et servie sous le nom de l'institut.
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from wagtail.models import Site

from apps.accounts.models import User
from apps.website.models import NewsIndexPage, NewsPage

pytestmark = pytest.mark.django_db

MOT_DE_PASSE = "motdepasse-long-12"


def _png_minimal() -> bytes:
    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(tampon, format="PNG")
    return tampon.getvalue()


@pytest.fixture
def index(db):
    """L'index des actualités, créé par « setup_initial_pages » en exploitation.

    Accroché sous la page racine **du site**, et non sous la racine de l'arbre :
    une page hors du site n'a pas d'URL, et « page.url » vaudrait « None » sans
    que rien ne le signale. « add_child » ne vérifie pas « parent_page_types »,
    cette contrainte n'existant qu'à l'écran de création de Wagtail.
    """
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
    donnees = {
        "titre": "Journée portes ouvertes",
        "date": "2026-09-14",
        "chapeau": "L'institut ouvre ses portes.",
        "corps": "<p>Venez nous rencontrer.</p>",
    }
    donnees.update(surcharges)
    return donnees


# ══════════════════════════════════════════════
# Qui a le droit d'écrire
# ══════════════════════════════════════════════


class TestPerimetre:
    def test_le_secretariat_ecrit_les_actualites(self, client, secretaire, index):
        """C'est une annonce courante de l'institut, donc un acte de secrétariat."""
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

    def test_un_anonyme_n_y_accede_pas(self, client, index):
        assert client.get(reverse("website:actualites_gestion")).status_code != 200

    @pytest.mark.parametrize("barre", ["secretariat:dashboard"])
    def test_la_barre_du_secretariat_y_mene(self, client, secretaire, index, barre):
        """Un droit sans chemin pour l'exercer n'existe pas dans les faits."""
        client.force_login(secretaire)
        contenu = client.get(reverse(barre)).content.decode()
        assert f'href="{reverse("website:actualites_gestion")}"' in contenu


# ══════════════════════════════════════════════
# L'écriture
# ══════════════════════════════════════════════


class TestRedaction:
    def test_l_actualite_entre_dans_l_arbre_du_site(self, client, secretaire, index):
        """Une page hors de l'arbre n'a ni URL ni existence publique."""
        client.force_login(secretaire)
        client.post(reverse("website:actualite_creation"), _saisie())

        page = NewsPage.objects.get(title="Journée portes ouvertes")
        assert page.get_parent().specific == index
        assert page.url

    def test_elle_naît_hors_ligne(self, client, secretaire, index):
        """Une annonce s'écrit, se relit, et ne paraît qu'à la publication."""
        client.force_login(secretaire)
        client.post(reverse("website:actualite_creation"), _saisie())

        page = NewsPage.objects.get(title="Journée portes ouvertes")
        assert not page.live
        assert page not in NewsPage.objects.live()

    def test_une_actualite_sans_contenu_est_refusee(self, client, secretaire, index):
        client.force_login(secretaire)
        reponse = client.post(reverse("website:actualite_creation"), _saisie(corps=""))

        assert reponse.status_code == 200
        assert not NewsPage.objects.filter(title="Journée portes ouvertes").exists()

    def test_le_corps_vide_de_l_editeur_ne_compte_pas_pour_du_contenu(self, client, secretaire, index):
        """Un éditeur visuel peut laisser un paragraphe vide après effacement."""
        client.force_login(secretaire)
        client.post(reverse("website:actualite_creation"), _saisie(corps="<p><br></p>"))

        assert not NewsPage.objects.filter(title="Journée portes ouvertes").exists()

    def test_deux_actualites_de_meme_titre_ont_deux_adresses(self, client, secretaire, index):
        """Sans cela, la seconde écrase la première ou refuse de s'enregistrer."""
        client.force_login(secretaire)
        client.post(reverse("website:actualite_creation"), _saisie())
        client.post(reverse("website:actualite_creation"), _saisie())

        adresses = list(NewsPage.objects.filter(title="Journée portes ouvertes").values_list("slug", flat=True))
        assert len(adresses) == 2
        assert len(set(adresses)) == 2

    def test_le_script_glisse_dans_le_corps_ne_survit_pas(self, client, secretaire, index):
        """La page est publique et servie sous le nom de l'institut."""
        client.force_login(secretaire)
        client.post(
            reverse("website:actualite_creation"),
            _saisie(corps='<p>Bonjour</p><script>fetch("/vol")</script>'),
        )

        page = NewsPage.objects.get(title="Journée portes ouvertes")
        assert "<script" not in page.body
        assert "Bonjour" in page.body

    def test_l_image_deposee_rejoint_la_mediatheque(self, client, secretaire, index):
        client.force_login(secretaire)
        image = SimpleUploadedFile("photo.png", _png_minimal(), content_type="image/png")
        client.post(reverse("website:actualite_creation"), _saisie(image=image))

        page = NewsPage.objects.get(title="Journée portes ouvertes")
        assert page.image is not None
        assert page.image.width == 4

    def test_la_correction_ne_change_pas_l_adresse(self, client, secretaire, actualite):
        """Le titre se corrige ; les liens déjà partagés continuent d'aboutir."""
        client.force_login(secretaire)
        client.post(
            reverse("website:actualite_edition", args=[actualite.pk]),
            _saisie(titre="Rentrée académique 2026 — précisions"),
        )

        actualite.refresh_from_db()
        assert actualite.title == "Rentrée académique 2026 — précisions"
        assert actualite.slug == "rentree-2026"


# ══════════════════════════════════════════════
# La mise en ligne
# ══════════════════════════════════════════════


class TestMiseEnLigne:
    def test_la_publication_rend_l_actualite_visible_du_public(self, client, secretaire, actualite, index):
        client.force_login(secretaire)
        client.post(reverse("website:actualite_decision", args=[actualite.pk]), {"action": "publier"})

        actualite.refresh_from_db()
        assert actualite.live

        client.logout()
        assert "Rentrée académique 2026" in client.get(index.url).content.decode()

    def test_la_depublication_laisse_le_texte_intact(self, client, secretaire, actualite):
        """Une annonce périmée se remet en ligne l'année suivante à peu de frais."""
        client.force_login(secretaire)
        client.post(reverse("website:actualite_decision", args=[actualite.pk]), {"action": "publier"})
        client.post(reverse("website:actualite_decision", args=[actualite.pk]), {"action": "depublier"})

        actualite.refresh_from_db()
        assert not actualite.live
        assert "14 septembre" in actualite.body

    def test_la_correction_d_une_actualite_en_ligne_se_voit_aussitot(self, client, secretaire, actualite):
        """Sans publication de la révision, le visiteur lirait encore l'ancienne version."""
        client.force_login(secretaire)
        client.post(reverse("website:actualite_decision", args=[actualite.pk]), {"action": "publier"})
        client.post(
            reverse("website:actualite_edition", args=[actualite.pk]),
            _saisie(titre="Rentrée académique 2026", corps="<p>La rentrée est repoussée au 21.</p>"),
        )

        client.logout()
        assert "repoussée au 21" in client.get(actualite.url).content.decode()

    def test_la_suppression_retire_la_page(self, client, secretaire, actualite):
        client.force_login(secretaire)
        client.post(reverse("website:actualite_decision", args=[actualite.pk]), {"action": "supprimer"})

        assert not NewsPage.objects.filter(pk=actualite.pk).exists()

    def test_une_action_inconnue_ne_change_rien(self, client, secretaire, actualite):
        client.force_login(secretaire)
        client.post(reverse("website:actualite_decision", args=[actualite.pk]), {"action": "n_importe_quoi"})

        actualite.refresh_from_db()
        assert not actualite.live
        assert NewsPage.objects.filter(pk=actualite.pk).exists()


class TestEcranDeGestion:
    def test_les_brouillons_figurent_a_l_ecran(self, client, secretaire, actualite):
        """C'est tout l'intérêt : une annonce oubliée en brouillon n'existe pour personne."""
        client.force_login(secretaire)
        contenu = client.get(reverse("website:actualites_gestion")).content.decode()

        assert "Rentrée académique 2026" in contenu
        assert "Brouillons (1)" in contenu

    def test_l_ecran_reste_lisible_sans_aucune_actualite(self, client, secretaire, index):
        client.force_login(secretaire)
        assert client.get(reverse("website:actualites_gestion")).status_code == 200

    def test_ecrire_sans_index_dans_l_arbre_le_dit_franchement(self, client, secretaire):
        """Un site non initialisé n'est pas une faute de l'utilisateur."""
        client.force_login(secretaire)
        reponse = client.post(reverse("website:actualite_creation"), _saisie())
        assert reponse.status_code == 404
