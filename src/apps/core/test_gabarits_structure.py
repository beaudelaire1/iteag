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
