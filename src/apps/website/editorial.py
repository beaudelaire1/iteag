"""Vocabulaire éditorial léger pour les actualités publiques.

Le but n'est pas de transformer l'éditeur en tableur ou en outil de dataviz.
Une actualité doit simplement pouvoir porter les formes d'information que
l'ancien site utilisait déjà : texte, tableau, procédure, chiffres, graphique
simple, image, citation, encadré et document.
"""

from decimal import Decimal

from wagtail import blocks
from wagtail.contrib.typed_table_block.blocks import TypedTableBlock

from apps.website.models import (
    CitationEditorialeBlock,
    DocumentEditorialBlock,
    EncadreEditorialBlock,
    ImageEditorialeBlock,
    TexteEditorialBlock,
)


class TableauEditorialBlock(TypedTableBlock):
    """Petit tableau sémantique, sans embarquer un tableur complet."""

    def __init__(self, **kwargs):
        super().__init__(
            [
                ("texte", blocks.CharBlock(label="Texte")),
                ("nombre", blocks.DecimalBlock(label="Nombre", required=False)),
                ("date", blocks.DateBlock(label="Date", required=False)),
            ],
            **kwargs,
        )

    class Meta:
        icon = "table"
        label = "Tableau"
        template = "website/blocks/tableau_editorial.html"


class EtapeEditorialeBlock(blocks.StructBlock):
    titre = blocks.CharBlock(max_length=160, label="Étape")
    description = TexteEditorialBlock(
        features=["bold", "italic", "underline", "ol", "ul", "link"],
        label="Explication",
    )

    class Meta:
        icon = "list-ol"
        label = "Étape"


class ProcedureEditorialBlock(blocks.StructBlock):
    titre = blocks.CharBlock(required=False, max_length=180, label="Titre")
    etapes = blocks.ListBlock(EtapeEditorialeBlock(), min_num=1, max_num=12, label="Étapes")

    class Meta:
        icon = "list-ol"
        label = "Procédure / étapes"
        template = "website/blocks/procedure_editoriale.html"


class ChiffreCleBlock(blocks.StructBlock):
    valeur = blocks.CharBlock(max_length=40, label="Valeur")
    libelle = blocks.CharBlock(max_length=140, label="Libellé")
    precision = blocks.CharBlock(required=False, max_length=180, label="Précision")

    class Meta:
        icon = "plus-inverse"
        label = "Chiffre clé"


class ChiffresClesEditorialBlock(blocks.StructBlock):
    titre = blocks.CharBlock(required=False, max_length=180, label="Titre")
    elements = blocks.ListBlock(ChiffreCleBlock(), min_num=1, max_num=6, label="Chiffres")

    class Meta:
        icon = "plus-inverse"
        label = "Chiffres clés"
        template = "website/blocks/chiffres_cles_editorial.html"


class DonneeGraphiqueBlock(blocks.StructBlock):
    libelle = blocks.CharBlock(max_length=120, label="Libellé")
    valeur = blocks.DecimalBlock(min_value=Decimal("0"), decimal_places=2, label="Valeur")

    class Meta:
        icon = "chart"
        label = "Donnée"


class GraphiqueSimpleEditorialBlock(blocks.StructBlock):
    """Barres horizontales pour une petite série de valeurs positives.

    Ce bloc couvre le besoin courant d'une actualité sans introduire Chart.js
    dans l'éditeur ni stocker une configuration graphique opaque. Les valeurs
    restent lisibles comme données textuelles même sans CSS ou JavaScript.
    """

    titre = blocks.CharBlock(max_length=180, label="Titre")
    unite = blocks.CharBlock(required=False, max_length=40, label="Unité", help_text="Ex. %, étudiants, €")
    source = blocks.CharBlock(required=False, max_length=200, label="Source")
    donnees = blocks.ListBlock(DonneeGraphiqueBlock(), min_num=2, max_num=12, label="Données")

    def get_context(self, value, parent_context=None):
        contexte = super().get_context(value, parent_context=parent_context)
        maximum = max((item["valeur"] for item in value["donnees"]), default=Decimal("0"))
        barres = []
        for item in value["donnees"]:
            valeur = item["valeur"]
            pourcentage = float((valeur / maximum) * 100) if maximum else 0
            barres.append({"libelle": item["libelle"], "valeur": valeur, "pourcentage": round(pourcentage, 2)})
        contexte["barres"] = barres
        return contexte

    class Meta:
        icon = "chart"
        label = "Graphique simple"
        template = "website/blocks/graphique_simple_editorial.html"


class CorpsActualiteBlock(blocks.StreamBlock):
    """Les seules formes nécessaires à une actualité ITEAG."""

    texte = TexteEditorialBlock()
    image = ImageEditorialeBlock()
    tableau = TableauEditorialBlock(required=False)
    procedure = ProcedureEditorialBlock()
    chiffres_cles = ChiffresClesEditorialBlock()
    graphique = GraphiqueSimpleEditorialBlock()
    citation = CitationEditorialeBlock()
    encadre = EncadreEditorialBlock()
    document = DocumentEditorialBlock()

    class Meta:
        block_counts = {
            "graphique": {"max_num": 4},
            "tableau": {"max_num": 6},
        }
