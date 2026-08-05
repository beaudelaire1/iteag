"""Contrat de l'éditeur Wagtail étendu."""

import json

from django.conf import settings
from wagtail.admin.rich_text.converters.contentstate import ContentstateConverter
from wagtail.rich_text import features


def test_le_profil_draftail_est_complet_et_sans_embed_non_controle():
    actifs = settings.WAGTAILADMIN_RICH_TEXT_EDITORS["default"]["OPTIONS"]["features"]

    assert {"underline", "blockquote", "align-left", "align-center", "align-right", "align-justify"} <= set(actifs)
    assert "image" in actifs
    assert "document-link" in actifs
    assert "embed" not in actifs
    assert "h1" not in actifs


def test_l_alignement_survit_a_la_conversion_html_contentstate():
    convertisseur = ContentstateConverter(features=["align-center", "underline"])

    contentstate = convertisseur.from_database_format('<p class="iteag-align-center">Une <u>pensée</u> structurée.</p>')
    blocs = json.loads(contentstate)["blocks"]

    assert blocs[0]["type"] == "ITEAG_ALIGN_CENTER"
    assert blocs[0]["inlineStyleRanges"][0]["style"] == "UNDERLINE"

    html = convertisseur.to_database_format(contentstate)
    assert 'class="iteag-align-center"' in html
    assert "<u>pensée</u>" in html


def test_les_plugins_draftail_sont_enregistres():
    assert features.get_editor_plugin("draftail", "underline") is not None
    assert features.get_editor_plugin("draftail", "align-justify") is not None
