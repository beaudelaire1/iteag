"""Fonctionnalités éditoriales communes aux contenus Wagtail de l'ITEAG.

Wagtail stocke un HTML volontairement structuré et convertit ce contenu vers
le format ContentState de Draftail. Une option ajoutée uniquement côté
JavaScript serait donc perdue à l'enregistrement. Chaque fonctionnalité
ci-dessous déclare les deux côtés du contrat : contrôle dans Draftail et
conversion HTML aller-retour.
"""

from wagtail import hooks
from wagtail.admin.rich_text.converters.html_to_contentstate import (
    BlockElementHandler,
    InlineStyleElementHandler,
)
from wagtail.admin.rich_text.editors.draftail import features as draftail_features

ALIGNEMENTS = (
    ("align-left", "ITEAG_ALIGN_LEFT", "iteag-align-left", "align-left", "Aligner le paragraphe à gauche"),
    ("align-center", "ITEAG_ALIGN_CENTER", "iteag-align-center", "align-center", "Centrer le paragraphe"),
    ("align-right", "ITEAG_ALIGN_RIGHT", "iteag-align-right", "align-right", "Aligner le paragraphe à droite"),
    ("align-justify", "ITEAG_ALIGN_JUSTIFY", "iteag-align-justify", "align-justify", "Justifier le paragraphe"),
)

FONCTIONNALITES_ETENDUES = (
    "h5",
    "h6",
    "blockquote",
    "underline",
    "strikethrough",
    "superscript",
    "subscript",
    "code",
    *(nom for nom, *_ in ALIGNEMENTS),
)


@hooks.register("register_rich_text_features")
def enregistrer_fonctionnalites_iteag(features):
    """Complète Draftail sans éditeur tiers ni ressource distante."""

    features.register_editor_plugin(
        "draftail",
        "underline",
        draftail_features.InlineStyleFeature(
            {
                "type": "UNDERLINE",
                "label": "U",
                "description": "Souligné",
            }
        ),
    )
    features.register_converter_rule(
        "contentstate",
        "underline",
        {
            "from_database_format": {
                "u": InlineStyleElementHandler("UNDERLINE"),
            },
            "to_database_format": {"style_map": {"UNDERLINE": "u"}},
        },
    )

    for nom, type_bloc, classe_css, icone, description in ALIGNEMENTS:
        features.register_editor_plugin(
            "draftail",
            nom,
            draftail_features.BlockFeature(
                {
                    "type": type_bloc,
                    "icon": icone,
                    "description": description,
                    "element": "div",
                },
                css={"all": ["css/wagtail-editeur-riche.css"]},
            ),
        )
        features.register_converter_rule(
            "contentstate",
            nom,
            {
                "from_database_format": {
                    f'p[class="{classe_css}"]': BlockElementHandler(type_bloc),
                },
                "to_database_format": {
                    "block_map": {
                        type_bloc: {
                            "element": "p",
                            "props": {"class": classe_css},
                        }
                    }
                },
            },
        )

    for nom in FONCTIONNALITES_ETENDUES:
        if nom not in features.default_features:
            features.default_features.append(nom)


@hooks.register("register_icons")
def enregistrer_icones_alignement(icons):
    """Ajoute au sprite Wagtail les quatre pictogrammes de mise en page."""
    icons.extend(
        [
            "website/icons/align-left.svg",
            "website/icons/align-center.svg",
            "website/icons/align-right.svg",
            "website/icons/align-justify.svg",
        ]
    )
    return icons
