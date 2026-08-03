"""Chaque type de page doit être créable, et dire à quoi il sert.

Wagtail exige l'accord des **deux côtés** : un type absent du
« subpage_types » de son parent ne peut être créé nulle part, quoi qu'en dise
son propre « parent_page_types ». Rien ne le signale — ni erreur au démarrage,
ni avertissement de « check » : le type disparaît simplement de l'écran
« Ajouter une page », et le rédacteur conclut que la fonction n'existe pas.

C'était le cas de la page de contact et de celle du catalogue : elles
existaient sur le site parce qu'une commande de peuplement les avait écrites
directement en base, et le secrétariat ne pouvait ni en créer ni en recréer.

Le second défaut est d'un autre ordre : neuf types portant des noms de modèles,
sans un mot d'explication, ne composent pas une interface compréhensible.
« page_description » est le texte que Wagtail affiche sous chaque nom.
"""

import pytest
from wagtail.models import Page

from apps.website import models as pages

TYPES_DE_PAGE = [
    pages.HomePage,
    pages.ContentPage,
    pages.NewsIndexPage,
    pages.NewsPage,
    pages.EventIndexPage,
    pages.EventPage,
    pages.FAQPage,
    pages.ModuleCataloguePage,
    pages.ContactPage,
]

# La page d'accueil se crée à l'installation, sous la racine de Wagtail.
CREES_A_L_INSTALLATION = {pages.HomePage}


@pytest.mark.parametrize("modele", TYPES_DE_PAGE, ids=[m.__name__ for m in TYPES_DE_PAGE])
def test_chaque_type_de_page_est_creable_quelque_part(modele):
    """Un type qu'aucun parent n'accepte est un type que personne ne peut créer."""
    if modele in CREES_A_L_INSTALLATION:
        pytest.skip("Créée à l'installation, sous la racine.")

    parents = [m.__name__ for m in modele.allowed_parent_page_models() if m is not Page]
    assert parents, (
        f"« {modele._meta.verbose_name} » n'est créable sous aucune page. "
        f"Wagtail veut l'accord des deux côtés : ajoutez « website.{modele.__name__} » "
        f"au « subpage_types » du parent voulu."
    )


@pytest.mark.parametrize("modele", TYPES_DE_PAGE, ids=[m.__name__ for m in TYPES_DE_PAGE])
def test_chaque_type_de_page_dit_a_quoi_il_sert(modele):
    """Neuf noms de modèles sans explication ne font pas une interface."""
    description = getattr(modele, "page_description", "")
    assert description, (
        f"« {modele._meta.verbose_name} » n'a pas de « page_description » : "
        "le rédacteur le voit dans la liste sans savoir ce qu'il fait."
    )
    assert len(description) > 25, "Une description d'un mot n'apprend rien."


def test_les_pages_du_site_se_creent_depuis_l_accueil():
    """Le rédacteur part de l'accueil : tout ce qui est de premier niveau doit y être."""
    depuis_accueil = {m.__name__ for m in pages.HomePage.allowed_subpage_models()}
    for attendu in ("ContentPage", "NewsIndexPage", "EventIndexPage", "FAQPage", "ContactPage", "ModuleCataloguePage"):
        assert attendu in depuis_accueil, f"{attendu} devrait être créable depuis la page d'accueil."


def test_une_page_de_contenu_peut_en_porter_d_autres():
    """Douze pages institutionnelles à plat, sous l'accueil, ne se rangent pas.

    Une rubrique éditoriale se compose de sous-pages ; sans cela, l'arborescence
    reste à deux niveaux et le menu ne peut refléter aucune hiérarchie.
    """
    assert "ContentPage" in {m.__name__ for m in pages.ContentPage.allowed_subpage_models()}


@pytest.mark.parametrize(
    ("index", "enfant"),
    [(pages.NewsIndexPage, "NewsPage"), (pages.EventIndexPage, "EventPage")],
    ids=["actualites", "evenements"],
)
def test_les_index_n_acceptent_que_leur_propre_contenu(index, enfant):
    """Un index d'actualités qui accepterait n'importe quoi cesse d'être un index."""
    autorises = {m.__name__ for m in index.allowed_subpage_models() if m is not Page}
    assert autorises == {enfant}, f"{index.__name__} devrait n'accepter que {enfant}, pas {autorises}."
