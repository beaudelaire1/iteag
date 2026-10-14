"""L'actualité du calendrier 2027 doit survivre au déploiement.

Comme pour les annonces de la rentrée 2026, la page est écrite dans une
migration : sur une base de test il n'y a pas d'index d'actualités, et rien ne
verrait qu'un bloc a changé de forme. Ce test rejoue la migration sur une
arborescence réelle et lit la page publiée.
"""

import importlib

import pytest
from wagtail.models import Page, Site

from apps.website.models import HomePage, NewsIndexPage, NewsPage

migration = importlib.import_module("apps.website.migrations.0021_actualite_calendrier_2027")


@pytest.fixture
def index_des_actualites(db):
    racine = Page.objects.get(depth=1)
    accueil = HomePage(title="Accueil calendrier", slug="accueil-calendrier", sous_titre="")
    racine.add_child(instance=accueil)
    site = Site.objects.get(is_default_site=True)
    site.root_page = accueil
    site.save(update_fields=["root_page"])
    index = NewsIndexPage(title="Actualités", slug="actualites")
    accueil.add_child(instance=index)
    return index


@pytest.mark.django_db
def test_sans_arborescence_la_migration_ne_fait_rien():
    migration.publier_le_calendrier_2027(None, None)

    assert not NewsPage.objects.exists()


@pytest.mark.django_db
def test_l_actualite_est_publiee_avec_la_grille_de_paques(client, index_des_actualites):
    migration.publier_le_calendrier_2027(None, None)

    actualite = NewsPage.objects.get(slug=migration.SLUG)
    assert actualite.live
    assert len(actualite.contenu_structure.contenu) == len(migration.CONTENU)

    page = client.get(actualite.url).content.decode()
    # La grille de Pâques est un vrai tableau : une ligne par soirée.
    assert page.count("<table") == 2
    for soiree in migration.SOIREES_PAQUES:
        assert f"{soiree} 2027" in page
    assert page.count(migration.SOIR_GUYANE) >= len(migration.SOIREES_PAQUES)
    for enseignant in ("Henri Blocher", "Ruth Labeth", "Wilhem Talbot", "Alain Nisus"):
        assert enseignant in page
    for enseignant in ("Madely Goram", "Jean Claude Girondin", "Karim Arezki", "Daniel Reivax"):
        assert enseignant in page
    assert "Pas de cours le mardi 9 février" in page


@pytest.mark.django_db
def test_rejouer_la_migration_ne_duplique_rien(index_des_actualites):
    migration.publier_le_calendrier_2027(None, None)
    migration.publier_le_calendrier_2027(None, None)

    assert NewsPage.objects.filter(slug=migration.SLUG).count() == 1


@pytest.mark.django_db
def test_une_actualite_corrigee_a_la_main_n_est_pas_ecrasee(index_des_actualites):
    migration.publier_le_calendrier_2027(None, None)
    actualite = NewsPage.objects.get(slug=migration.SLUG)
    actualite.title = "Calendrier 2027 — mis à jour"
    actualite.save()

    migration.publier_le_calendrier_2027(None, None)

    actualite.refresh_from_db()
    assert actualite.title == "Calendrier 2027 — mis à jour"
