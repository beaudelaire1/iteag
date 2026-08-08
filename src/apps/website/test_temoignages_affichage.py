"""Régressions d'affichage des témoignages publics."""

from pathlib import Path

from django.conf import settings


def _gabarit() -> str:
    chemin = Path(settings.BASE_DIR) / "templates/website/partials/temoignages_etudiants.html"
    return chemin.read_text(encoding="utf-8")


def test_voir_plus_ne_depend_plus_de_javascript():
    gabarit = _gabarit()

    assert 'type="checkbox"' in gabarit
    assert 'class="testimonial-toggle"' in gabarit
    assert 'class="btn-toggle-read-more' in gabarit
    assert "testimonial-toggle:checked" in gabarit
    assert "Voir plus" in gabarit
    assert "Voir moins" in gabarit
    assert "addEventListener('click'" not in gabarit
    assert "DOMContentLoaded" not in gabarit
