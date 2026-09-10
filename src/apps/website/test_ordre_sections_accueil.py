"""
L'ordre de lecture de la page d'accueil.

Les actualités se lisaient après l'équipe professorale. Or ce sont elles qui
portent les annonces datées — l'ouverture d'une formation, un atelier, une
rentrée : l'information la plus périssable du site arrivait donc en avant-
dernier, derrière une section qui, elle, ne change presque jamais. La suite
« ce que nous proposons → ce qui se passe maintenant → qui l'enseigne » répond
aux questions dans l'ordre où le visiteur se les pose.

Ce test fige la suite : elle se casse d'un simple déplacement de bloc dans le
gabarit, sans qu'aucune erreur ne le signale.
"""

import datetime

import pytest
from wagtail.models import Page, Site

from apps.formations.models import Professeur
from apps.website.models import HomePage, NewsIndexPage, NewsPage


@pytest.fixture
def accueil_garni(db):
    """Un accueil où chaque section a de quoi s'afficher."""
    racine = Page.objects.get(depth=1)
    page = HomePage(title="Accueil test ordre", slug="accueil-ordre", sous_titre="")
    racine.add_child(instance=page)
    site = Site.objects.get(is_default_site=True)
    site.root_page = page
    site.save(update_fields=["root_page"])

    index = NewsIndexPage(title="Actualités", slug="actualites-ordre")
    page.add_child(instance=index)
    index.add_child(
        instance=NewsPage(
            title="Formation biblique d'octobre",
            slug="formation-biblique-octobre",
            date=datetime.date(2026, 9, 1),
            excerpt="Les inscriptions sont ouvertes.",
            body="<p>Détail de l'annonce.</p>",
        )
    )
    Professeur.objects.create(nom="Bélizaire", prenom="Samuel", slug="samuel-belizaire-ordre")
    return page


@pytest.mark.django_db
def test_les_actualites_precedent_l_equipe_professorale(client, accueil_garni):
    contenu = client.get(accueil_garni.url).content.decode()
    # Deux repères propres aux sections : « Équipe professorale » figure aussi
    # dans la barre publique, et serait rencontré bien avant sa section.
    assert contenu.index("Nos dernières nouvelles") < contenu.index("Notre équipe")


@pytest.mark.django_db
def test_la_suite_des_sections_va_de_l_offre_a_l_inscription(client, accueil_garni):
    contenu = client.get(accueil_garni.url).content.decode()
    reperes = [
        "Qui sommes-nous",
        "Nos formations",
        "Nos dernières nouvelles",
        "Notre équipe",
        "Prêt à vous former ?",
    ]
    positions = [contenu.index(repere) for repere in reperes]
    assert positions == sorted(positions)
