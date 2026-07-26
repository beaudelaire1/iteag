"""
Les animations d'apparition ne doivent jamais rendre le contenu inaccessible.

Le défaut, découvert en regardant les pages rendues plutôt qu'en lisant la
feuille de style : « .reveal » part d'une opacité nulle et n'est révélé que par
un observateur d'intersection. Sans JavaScript — ou si le script échoue — la
moitié de chaque page reste invisible. Le contenu est bien dans le HTML : il
est simplement transparent.

Le même réglage ignorait « prefers-reduced-motion », qui est une demande de
l'utilisateur et non une préférence esthétique.
"""

import pathlib

import pytest
from django.urls import reverse

RACINE = pathlib.Path(__file__).resolve().parents[2]
CSS_SOURCE = RACINE / "assets" / "css" / "input.css"

# Toutes les familles d'animation qui partent d'une opacité nulle.
CLASSES_MASQUANTES = [
    ".reveal",
    ".reveal-left",
    ".reveal-right",
    ".reveal-scale",
    ".reveal-fade",
    ".reveal-blur",
    ".text-reveal-line",
    ".border-draw",
]


def bloc_mouvement_reduit() -> str:
    """Contenu de la règle « prefers-reduced-motion » de la feuille source."""
    texte = CSS_SOURCE.read_text(encoding="utf-8")
    marqueur = "@media (prefers-reduced-motion: reduce)"
    assert marqueur in texte, "Aucune règle « prefers-reduced-motion » dans la feuille de style"
    depart = texte.index(marqueur)
    # La règle se termine à la première accolade fermante en colonne zéro.
    fin = texte.index("\n}", depart) + 2
    return texte[depart:fin]


@pytest.mark.parametrize("classe", CLASSES_MASQUANTES)
def test_le_mouvement_reduit_revele_tout(classe):
    assert classe in bloc_mouvement_reduit(), f"« {classe} » resterait invisible en mouvement réduit"


def test_le_repli_sans_javascript_est_dans_le_gabarit_de_base():
    """
    Posé dans « base.html » et non dans chaque page : c'est le seul endroit où
    il ne peut pas être oublié.
    """
    base = (RACINE / "templates" / "base.html").read_text(encoding="utf-8")
    assert "<noscript>" in base
    debut = base.index("<noscript>")
    bloc = base[debut : base.index("</noscript>", debut)]
    for classe in CLASSES_MASQUANTES:
        assert classe in bloc, f"« {classe} » resterait invisible sans JavaScript"
    assert "opacity: 1 !important" in bloc


@pytest.mark.django_db
def test_les_pages_publiques_portent_le_repli(client):
    """Vérifié sur le rendu : une déclaration qui n'arrive pas au navigateur ne sert à rien."""
    for nom_route in ("elearning:catalogue", "formations:parcours_list", "accounts:login"):
        contenu = client.get(reverse(nom_route)).content.decode()
        assert "<noscript>" in contenu, nom_route
