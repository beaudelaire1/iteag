"""
Les deux annonces de la rentrée 2026 doivent survivre au déploiement.

Ces actualités sont écrites une fois pour toutes dans la migration
``0017_actualites_rentree_2026``, et non saisies dans le portail : sur une base
de test il n'existe pas d'index d'actualités, la migration n'a donc rien à
faire au moment où elle passe, et personne ne verrait qu'un bloc éditorial a
changé de forme entre-temps.

Ce test rejoue la fonction de la migration sur une arborescence réelle. Il
tient donc deux promesses : le contenu est bien accepté par les blocs tels
qu'ils existent aujourd'hui — un « chiffres clés », un tableau typé, un encadré
ou une citation dont la structure évoluerait ferait échouer ici plutôt qu'en
production — et rejouer la migration ne duplique pas les pages.
"""

import importlib

import pytest
from wagtail.models import Page, Site

from apps.website.models import HomePage, NewsIndexPage, NewsPage

migration = importlib.import_module("apps.website.migrations.0017_actualites_rentree_2026")


@pytest.fixture
def index_des_actualites(db):
    racine = Page.objects.get(depth=1)
    accueil = HomePage(title="Accueil annonces", slug="accueil-annonces", sous_titre="")
    racine.add_child(instance=accueil)
    site = Site.objects.get(is_default_site=True)
    site.root_page = accueil
    site.save(update_fields=["root_page"])
    index = NewsIndexPage(title="Actualités", slug="actualites")
    accueil.add_child(instance=index)
    return index


@pytest.mark.django_db
def test_sans_arborescence_la_migration_ne_fait_rien():
    """Base neuve ou base de test : aucun index, donc aucune page inventée."""
    migration.publier_les_annonces(None, None)

    assert not NewsPage.objects.exists()


@pytest.mark.django_db
def test_les_deux_annonces_sont_publiees_et_lisibles(client, index_des_actualites):
    migration.publier_les_annonces(None, None)

    formation = NewsPage.objects.get(slug=migration.FORMATION_SLUG)
    ateliers = NewsPage.objects.get(slug=migration.ATELIERS_SLUG)

    assert formation.live and ateliers.live
    # Le corps structuré est ce que le gabarit public préfère au RichText.
    assert len(formation.contenu_structure.contenu) == len(migration.FORMATION_CONTENU)
    assert len(ateliers.contenu_structure.contenu) == len(migration.ATELIERS_CONTENU)

    page = client.get(ateliers.url).content.decode()
    assert page.count("</sup> samedi du mois") == len(migration.ATELIERS_SEANCES)
    assert "Samedi 26 septembre 2026" in page
    assert "200,00" in page


@pytest.mark.django_db
def test_rejouer_la_migration_ne_duplique_rien(index_des_actualites):
    migration.publier_les_annonces(None, None)
    migration.publier_les_annonces(None, None)

    assert NewsPage.objects.count() == 2


@pytest.mark.django_db
def test_une_annonce_reecrite_a_la_main_nest_pas_ecrasee(index_des_actualites):
    """Une correction du secrétariat prime sur le texte figé dans la migration."""
    migration.publier_les_annonces(None, None)
    formation = NewsPage.objects.get(slug=migration.FORMATION_SLUG)
    formation.title = "Formation biblique — horaires modifiés"
    formation.save()

    migration.publier_les_annonces(None, None)

    formation.refresh_from_db()
    assert formation.title == "Formation biblique — horaires modifiés"
