"""Contrat du StreamField structuré rendu hors de l'administration Wagtail."""

from pathlib import Path

from django.conf import settings
from wagtail.blocks import BlockWidget

from apps.core.editeur_riche import StreamFieldPortail
from apps.website.formulaires_actualites import ActualiteForm


def _lire(chemin: str) -> str:
    return (Path(settings.BASE_DIR) / chemin).read_text(encoding="utf-8")


def _position(ressources: list[str], fragment: str) -> int:
    return next(i for i, url in enumerate(ressources) if fragment in url)


def test_actualite_conserve_le_blockwidget_wagtail():
    widget = ActualiteForm().fields["contenu"].widget

    assert isinstance(widget, StreamFieldPortail)
    assert isinstance(widget, BlockWidget)


def test_blockwidget_rend_le_controleur_officiel_w_block():
    html = str(ActualiteForm()["contenu"])

    assert 'data-block' in html
    assert 'data-controller="w-block"' in html
    assert 'data-w-block-data-value=' in html
    assert 'data-w-block-arguments-value=' in html
    assert 'id="contenu"' in html


def test_configuration_wagtail_precede_les_medias_du_widget():
    gabarit = _lire("templates/website/actualites/formulaire.html")

    configuration = gabarit.index("{% wagtail_configuration_portail %}")
    medias = gabarit.index("{{ form.media.js }}")

    assert configuration < medias


def test_runtime_officiel_precede_les_adaptateurs_streamfield():
    ressources = [str(url) for url in ActualiteForm().fields["contenu"].widget.media._js]

    core = _position(ressources, "/core.js")
    vendor = _position(ressources, "/vendor.js")
    widgets = _position(ressources, "/telepath/widgets.js")
    blocs = _position(ressources, "/telepath/blocks.js")
    draftail = _position(ressources, "/draftail.js")

    assert core < vendor < widgets
    assert core < vendor < blocs
    assert vendor < draftail


def test_le_portail_ne_reimplemente_plus_blockcontroller():
    gabarit = _lire("templates/website/actualites/formulaire.html")

    assert "streamfield-portail.js" not in gabarit


def test_le_vocabulaire_structure_reste_complet_dans_le_widget():
    widget = ActualiteForm().fields["contenu"].widget
    noms = set(widget.block_def.child_blocks)

    assert noms == {"texte", "tableau", "procedure", "chiffres_cles", "graphique", "citation", "encadre"}
