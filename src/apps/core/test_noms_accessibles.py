"""Tout champ de formulaire doit porter un nom accessible.

Un `<input>` sans étiquette ne provoque aucune erreur : la page s'affiche, le
formulaire fonctionne à la souris, et rien ne signale que le champ s'annonce
« zone d'édition, vide » à un lecteur d'écran. C'est exactement ce qui est
arrivé à la recherche du catalogue public, pendant que la page voisine de la
boutique, elle, étiquetait correctement son champ.

Ce test balaie les gabarits plutôt que les pages rendues : il n'exige aucune
donnée en base et couvre les écrans du back-office, que peu de tests visitent.
Les champs rendus par Django (`{{ form.x }}`) ne passent pas ici — ils héritent
de « partials/champ.html », qui pose déjà le libellé.
"""

import re
from pathlib import Path

import pytest

GABARITS = Path(__file__).resolve().parent.parent.parent / "templates"

# Un champ est considéré nommé s'il porte l'un de ces attributs.
NOMME_PAR_ATTRIBUT = re.compile(r"aria-label|aria-labelledby|\btitle\s*=", re.I)
# Un champ retiré de l'arbre d'accessibilité n'a pas à être nommé : c'est le cas
# des pièges à robots, volontairement invisibles et non focalisables.
HORS_ARBRE = re.compile(r"aria-hidden|sr-only|\bhidden\b", re.I)
# Les types ci-dessous portent leur nom dans leur valeur ou leur contenu.
TYPES_EXCLUS = re.compile(r'type\s*=\s*["\']?(hidden|submit|button|image)', re.I)


def champs_sans_nom_accessible(html: str) -> list[str]:
    etiquettes = set(re.findall(r'<label\b[^>]*\bfor\s*=\s*["\']([^"\']+)', html, re.I))
    anonymes = []

    for correspondance in re.finditer(r"<(input|select|textarea)\b[^>]*>", html, re.I):
        balise = correspondance.group(0)
        if TYPES_EXCLUS.search(balise) or NOMME_PAR_ATTRIBUT.search(balise) or HORS_ARBRE.search(balise):
            continue

        identifiant = re.search(r'\bid\s*=\s*["\']([^"\']+)', balise)
        if identifiant and identifiant.group(1) in etiquettes:
            continue

        # Étiquetage implicite : <label> … <input> … </label>. On regarde si une
        # balise <label> est ouverte et non refermée juste avant le champ.
        avant = html[max(0, correspondance.start() - 400) : correspondance.start()]
        apres = html[correspondance.end() : correspondance.end() + 400]
        if avant.rfind("<label") > avant.rfind("</label>") and "</label>" in apres:
            continue

        ligne = html[: correspondance.start()].count("\n") + 1
        anonymes.append(f"ligne {ligne} : {' '.join(balise.split())[:120]}")

    return anonymes


@pytest.mark.parametrize(
    "gabarit",
    sorted(chemin.relative_to(GABARITS).as_posix() for chemin in GABARITS.rglob("*.html")),
)
def test_chaque_champ_de_formulaire_a_un_nom_accessible(gabarit):
    html = (GABARITS / gabarit).read_text(encoding="utf-8")

    anonymes = champs_sans_nom_accessible(html)

    assert not anonymes, "Champ(s) sans étiquette, sans aria-label et hors <label> englobant :\n" + "\n".join(anonymes)


class TestLHeuristiqueNeSeTrompePas:
    """Un test de couverture qui accepte tout ne protège de rien."""

    def test_un_champ_nu_est_bien_signale(self):
        assert champs_sans_nom_accessible('<form><input type="text" name="q"></form>')

    def test_une_etiquette_liee_par_for_suffit(self):
        html = '<label for="q">Rechercher</label><input type="text" id="q" name="q">'
        assert champs_sans_nom_accessible(html) == []

    def test_une_etiquette_englobante_suffit(self):
        html = '<label>Rechercher <input type="text" name="q"></label>'
        assert champs_sans_nom_accessible(html) == []

    def test_un_aria_label_suffit(self):
        assert champs_sans_nom_accessible('<input type="text" name="q" aria-label="Rechercher">') == []

    def test_un_piege_a_robots_est_ignore(self):
        html = '<input type="text" name="site_web" aria-hidden="true" class="sr-only">'
        assert champs_sans_nom_accessible(html) == []

    def test_un_champ_cache_est_ignore(self):
        assert champs_sans_nom_accessible('<input type="hidden" name="suivant" value="/">') == []
