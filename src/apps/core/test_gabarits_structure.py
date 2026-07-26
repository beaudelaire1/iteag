"""
Contrôle structurel des gabarits.

Une balise `<details>` laissée ouverte dans une boucle imbrique les éléments
suivants les uns dans les autres : refermer le premier masque alors tous les
autres. Le défaut ne se voit ni au lint, ni à l'exécution des vues — seul un
comptage le révèle.
"""

import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parent.parent.parent / "templates"

BALISES_APPARIEES = ["details", "summary", "section", "article", "aside", "nav", "table"]


def gabarits():
    return sorted(TEMPLATES.rglob("*.html"))


@pytest.mark.parametrize("gabarit", gabarits(), ids=lambda p: str(p.relative_to(TEMPLATES)))
def test_balises_appariees(gabarit):
    """Chaque balise ouvrante a sa fermante, dans chaque gabarit."""
    contenu = gabarit.read_text(encoding="utf-8")
    for balise in BALISES_APPARIEES:
        ouvrantes = len(re.findall(rf"<{balise}[\s>]", contenu))
        fermantes = len(re.findall(rf"</{balise}>", contenu))
        assert ouvrantes == fermantes, (
            f"{gabarit.relative_to(TEMPLATES)} : {ouvrantes} <{balise}> "
            f"pour {fermantes} </{balise}>. Une balise non refermée dans une "
            "boucle imbrique les itérations suivantes."
        )


def test_aucun_commentaire_multiligne_en_syntaxe_courte():
    """
    « {# … #} » est mono-ligne en Django. Sur plusieurs lignes, la balise n'est
    pas interprétée et le commentaire s'affiche en clair au visiteur — une faute
    qui ne se voit qu'en regardant la page rendue. Les commentaires longs
    doivent utiliser « {% comment %} ».
    """
    fautifs = []
    for chemin in sorted(TEMPLATES.rglob("*.html")):
        contenu = chemin.read_text(encoding="utf-8")
        position = 0
        while (ouverture := contenu.find("{#", position)) != -1:
            fermeture = contenu.find("#}", ouverture)
            if fermeture == -1:
                break
            if "\n" in contenu[ouverture:fermeture]:
                ligne = contenu[:ouverture].count("\n") + 1
                fautifs.append(f"{chemin.relative_to(TEMPLATES)}:{ligne}")
            position = fermeture + 2

    assert not fautifs, "Commentaires multilignes rendus en clair :\n" + "\n".join(fautifs)
