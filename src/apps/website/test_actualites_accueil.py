"""
L'image à la une des actualités doit se voir depuis l'accueil.

La section « Actualités » de la page d'accueil rendait la date, le titre et le
résumé, mais jamais le champ « image » du modèle. Le visuel existait pourtant
en base sur la plupart des actualités, et la page d'index l'affichait déjà :
seul l'accueil montrait des cartes sans illustration, sans qu'aucune erreur ne
le signale.

Le gabarit passe par une rendition « fill-600x340 ». Servir le fichier
d'origine ferait télécharger plusieurs mégaoctets dès l'accueil pour des
vignettes de 600 pixels de large.
"""

import datetime

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from wagtail.images import get_image_model
from wagtail.models import Page, Site

from apps.website.models import HomePage, NewsIndexPage, NewsPage

# Le plus petit PNG valide : la vignette n'a pas à être réaliste pour ce test.
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00"
    b"\x00IEND\xaeB`\x82"
)


@pytest.fixture
def accueil(db):
    """Accueil rattaché au site, avec l'index dont les actualités descendent."""
    racine = Page.objects.get(depth=1)
    page = HomePage(title="Accueil test actualités", slug="accueil-actualites", sous_titre="")
    racine.add_child(instance=page)
    site = Site.objects.get(is_default_site=True)
    site.root_page = page
    site.save(update_fields=["root_page"])
    index = NewsIndexPage(title="Actualités", slug="actualites-accueil")
    page.add_child(instance=index)
    return page, index


def visuel(nom="actualite.png"):
    return get_image_model().objects.create(
        title="Visuel d'actualité",
        file=SimpleUploadedFile(nom, PNG, content_type="image/png"),
    )


def publier(index, titre, slug, image=None):
    actualite = NewsPage(
        title=titre,
        slug=slug,
        date=datetime.date(2026, 8, 7),
        excerpt="Résumé de l'actualité.",
        body="<p>Corps de l'actualité.</p>",
        image=image,
    )
    index.add_child(instance=actualite)
    return actualite


def section_actualites(client, page):
    """Isole la section : l'accueil rend d'autres images, professeurs compris."""
    contenu = client.get(page.url).content.decode()
    return contenu.split("Nos dernières nouvelles", 1)[1].split("</section>", 1)[0]


@pytest.mark.django_db
class TestActualitesVisiblesDepuisLAccueil:
    def test_l_image_a_la_une_est_rendue(self, client, accueil):
        page, index = accueil
        publier(index, "L'Iteag se modernise", "iteag-se-modernise", image=visuel())
        assert "<img" in section_actualites(client, page)

    def test_l_image_passe_par_une_rendition_calibree(self, client, accueil):
        """Servir le fichier d'origine chargerait plusieurs Mo dès l'accueil."""
        page, index = accueil
        publier(index, "L'Iteag se modernise", "iteag-se-modernise", image=visuel())
        assert "fill-600x340" in section_actualites(client, page)

    def test_sans_image_la_carte_reste_affichee(self, client, accueil):
        """Un repli garde les cartes alignées quand l'image manque."""
        page, index = accueil
        publier(index, "Rentrée 2026-2027", "rentree-2026-2027")
        section = section_actualites(client, page)
        assert "Rentrée 2026-2027" in section
        assert "<svg" in section
