"""Contrat de chargement du StreamField utilisé hors de l'administration Wagtail."""

from pathlib import Path

from django.conf import settings


def _lire(chemin: str) -> str:
    return (Path(settings.BASE_DIR) / chemin).read_text(encoding="utf-8")


def test_telepath_est_charge_avant_les_medias_du_streamfield():
    """Le BlockWidget Wagtail suppose Telepath déjà présent dans l'admin.

    Le formulaire d'actualité vit dans le portail privé : il doit donc charger
    le noyau Telepath lui-même, avant les adaptateurs fournis par ``form.media``
    puis avant notre amorçage hors administration.
    """
    gabarit = _lire("templates/website/actualites/formulaire.html")

    noyau = gabarit.index("telepath/js/telepath.js")
    medias = gabarit.index("{{ form.media.js }}")
    amorcage = gabarit.index("streamfield-portail.js")

    assert noyau < medias < amorcage


def test_l_amorcage_exige_explicitement_telepath():
    script = _lire("static/js/streamfield-portail.js")

    assert "window.telepath" in script
    assert "window.telepath.unpack" in script
