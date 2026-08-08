"""Contrat du StreamField structuré rendu hors de l'administration Wagtail."""

from pathlib import Path

from django.conf import settings
from wagtail.blocks import BlockWidget, RichTextBlock

from apps.core.editeur_riche import StreamFieldPortail
from apps.website.editorial import FONCTIONNALITES_CELLULE_TABLEAU, TableauEditorialBlock
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

    assert "data-block" in html
    assert 'data-controller="w-block"' in html
    assert "data-w-block-data-value=" in html
    assert "data-w-block-arguments-value=" in html
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
    barre_portail = _position(ressources, "/js/streamfield-draftail-portail.js")

    assert core < vendor < widgets
    assert core < vendor < blocs
    assert vendor < draftail < barre_portail


def test_styles_streamfield_restent_isoles_du_portail():
    widget = ActualiteForm().fields["contenu"].widget
    ressources = [str(url) for urls in widget.media._css.values() for url in urls]
    gabarit = _lire("templates/website/actualites/formulaire.html")

    assert any("/css/streamfield-portail.css" in url for url in ressources)
    assert any("/css/streamfield-draftail-portail.css" in url for url in ressources)
    assert any("/css/streamfield-picker-portail.css" in url for url in ressources)
    assert any("/css/typed-table-portail.css" in url for url in ressources)
    assert any("/css/streamfield-ux-portail.css" in url for url in ressources)
    assert not any("wagtailadmin/css/core.css" in url for url in ressources)
    assert 'class="streamfield-portail"' in gabarit


def test_draftail_streamfield_est_ancre_au_bloc():
    styles = _lire("static/css/streamfield-draftail-portail.css")
    script = _lire("static/js/streamfield-draftail-portail.js")

    assert "position: static !important" in styles
    assert ".Draftail-ToolbarButton--pin" in styles
    assert ".Draftail-BlockToolbar" in styles
    assert 'detail: { toolbar: "sticky" }' in script
    assert "localStorage" not in script


def test_picker_streamfield_est_une_liste_stable_hors_core_admin():
    styles = _lire("static/css/streamfield-picker-portail.css")
    ux = _lire("static/css/streamfield-ux-portail.css")

    assert '[data-tippy-root]' in styles
    assert '.tippy-box[data-theme="dropdown"]' in styles
    assert ".w-combobox__menu" in styles
    assert "grid-template-columns: minmax(0, 1fr)" in styles
    assert ".w-combobox__option-preview" in styles
    assert "max-height:" in styles
    assert '[data-tippy-root]:has(.w-combobox-container)' in ux
    assert "position: fixed !important" in ux
    assert "transform: none !important" in ux
    assert ".w-combobox__option-text" in ux


def test_tableau_propose_du_texte_riche_compact_dans_les_cellules():
    tableau = TableauEditorialBlock()
    texte = tableau.child_blocks["texte"]

    assert isinstance(texte, RichTextBlock)
    assert texte.required is False
    assert list(texte.features) == FONCTIONNALITES_CELLULE_TABLEAU
    assert "bold" in texte.features
    assert "underline" in texte.features
    assert "align-center" in texte.features
    assert "link" in texte.features
    assert texte.meta.template == "website/blocks/texte_cellule_tableau.html"


def test_tableau_portail_a_des_commandes_et_menus_explicites():
    styles = _lire("static/css/typed-table-portail.css")
    ux = _lire("static/css/streamfield-ux-portail.css")

    assert ".typed-table-block__wrapper" in styles
    assert "ul.add-column-menu" in styles
    assert 'content: "Ajouter une ligne"' in styles
    assert ".typed-table-block .Draftail-Editor--focus .Draftail-Toolbar" in styles
    assert "min-height: 5.25rem !important" in styles
    assert ".typed-table-block .Draftail-Toolbar" in ux
    assert "display: flex !important" in ux
    assert "position: sticky !important" in ux


def test_le_portail_ne_reimplemente_plus_blockcontroller():
    gabarit = _lire("templates/website/actualites/formulaire.html")

    assert "streamfield-portail.js" not in gabarit


def test_le_vocabulaire_structure_reste_complet_dans_le_widget():
    widget = ActualiteForm().fields["contenu"].widget
    noms = list(widget.block_def.child_blocks)

    assert noms == [
        "texte",
        "important",
        "tableau",
        "procedure",
        "chiffres_cles",
        "graphique",
        "citation",
        "encadre",
    ]
    assert widget.block_def.child_blocks["important"].meta.label == "Important"
