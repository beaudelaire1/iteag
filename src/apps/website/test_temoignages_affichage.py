"""Régressions d'affichage des témoignages publics."""

from pathlib import Path

from django.conf import settings


def _gabarit() -> str:
    chemin = Path(settings.BASE_DIR) / "templates/website/partials/temoignages_etudiants.html"
    return chemin.read_text(encoding="utf-8")


def test_un_temoignage_long_quitte_la_grille_pour_une_page_dediee():
    gabarit = _gabarit()

    assert 'id="temoignages"' in gabarit
    assert "truncatechars:220" in gabarit
    assert "website:temoignage_public" in gabarit
    assert "Lire le témoignage" in gabarit
    assert "Voir plus" not in gabarit
    assert "Voir moins" not in gabarit
    assert 'type="checkbox"' not in gabarit
    assert "testimonial-toggle" not in gabarit
