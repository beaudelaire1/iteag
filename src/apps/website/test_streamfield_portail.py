"""Contrat de chargement du StreamField utilisé hors de l'administration Wagtail."""

from pathlib import Path

from django.conf import settings

from apps.core.editeur_riche import StreamFieldPortail
from apps.website.formulaires_actualites import ActualiteForm


def _lire(chemin: str) -> str:
    return (Path(settings.BASE_DIR) / chemin).read_text(encoding="utf-8")


def _position(ressources: list[str], fragment: str) -> int:
    return next(i for i, url in enumerate(ressources) if fragment in url)


def test_actualite_utilise_le_widget_streamfield_autonome():
    assert isinstance(ActualiteForm().fields["contenu"].widget, StreamFieldPortail)


def test_runtime_wagtail_est_charge_avant_les_adaptateurs_streamfield():
    """Hors admin, core.js doit créer Telepath avant tout adaptateur de bloc."""
    ressources = [str(url) for url in ActualiteForm().fields["contenu"].widget.media._js]

    core = _position(ressources, "/core.js")
    widgets = _position(ressources, "/telepath/widgets.js")
    blocs = _position(ressources, "/telepath/blocks.js")

    assert core < widgets
    assert core < blocs


def test_vendor_est_charge_avant_draftail_dans_le_bloc_texte():
    ressources = [str(url) for url in ActualiteForm().fields["contenu"].widget.media._js]

    assert _position(ressources, "/vendor.js") < _position(ressources, "/draftail.js")


def test_medias_du_widget_precedent_l_amorcage_du_portail():
    gabarit = _lire("templates/website/actualites/formulaire.html")

    medias = gabarit.index("{{ form.media.js }}")
    amorcage = gabarit.index("streamfield-portail.js")

    assert medias < amorcage


def test_l_amorcage_exige_explicitement_telepath():
    script = _lire("static/js/streamfield-portail.js")

    assert "window.telepath" in script
    assert "window.telepath.unpack" in script
