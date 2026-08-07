"""Contrat de chargement du StreamField utilisé hors de l'administration Wagtail."""

from pathlib import Path

from django.conf import settings
from wagtail.blocks import BlockWidget

from apps.core.templatetags.socle_wagtail import SOCLE
from apps.website.formulaires_actualites import ActualiteForm


def _lire(chemin: str) -> str:
    return (Path(settings.BASE_DIR) / chemin).read_text(encoding="utf-8")


def _position(ressources: list[str], fragment: str) -> int:
    return next(i for i, url in enumerate(ressources) if fragment in url)


def test_actualite_utilise_le_blockwidget_officiel_wagtail():
    assert isinstance(ActualiteForm().fields["contenu"].widget, BlockWidget)


def test_blockwidget_rend_le_contrat_w_block_attendu_par_wagtail():
    html = str(ActualiteForm()["contenu"])

    assert 'data-block' in html
    assert 'data-controller="w-block"' in html
    assert 'data-w-block-data-value=' in html
    assert 'data-w-block-arguments-value=' in html
    assert 'id="contenu"' in html


def test_socle_reproduit_l_ordre_necessaire_du_runtime_wagtail():
    ressources = list(SOCLE)

    core = _position(ressources, "/core.js")
    vendor = _position(ressources, "/vendor.js")

    assert core < vendor


def test_le_gabarit_emet_configuration_et_socle_avant_les_medias_du_widget():
    gabarit = _lire("templates/website/actualites/formulaire.html")

    socle = gabarit.index("{% wagtail_socle_portail %}")
    medias = gabarit.index("{{ form.media.js }}")
    amorcage = gabarit.index("streamfield-portail.js")

    assert socle < medias < amorcage


def test_les_medias_du_blockwidget_contiennent_les_adaptateurs_streamfield():
    ressources = [str(url) for url in ActualiteForm().fields["contenu"].widget.media._js]

    assert any("/telepath/widgets.js" in url for url in ressources)
    assert any("/telepath/blocks.js" in url for url in ressources)
    assert any("/draftail.js" in url for url in ressources)


def test_l_amorcage_manuel_suit_la_signature_du_blockcontroller_officiel():
    script = _lire("static/js/streamfield-portail.js")

    # BlockController appelle rootBlock.render(element, id, ...argumentsValue).
    # Notre portail ne réimplémente rien d'autre : il fournit exactement ces
    # arguments après que le runtime officiel a enregistré les adaptateurs.
    assert "window.telepath.unpack" in script
    assert "definition.render(emplacement, emplacement.id, ...arguments_)" in script
