"""Le corps passe d'un bloc de HTML libre à une suite de blocs déclarés.

La conversion des contenus déjà écrits vient **avant** le changement de type.
Sans elle, la colonne contiendrait du HTML là où StreamField attend du JSON :
chaque document existant deviendrait illisible, et l'écran d'édition planterait
au premier chargement.

Le HTML existant devient un unique bloc « paragraphe » — c'est exactement ce
qu'il était. Rien n'est deviné, rien n'est découpé : un découpage automatique
en plusieurs blocs supposerait d'interpréter l'intention de l'auteur.
"""

import json
import uuid

import wagtail.fields
from django.db import migrations


def html_vers_blocs(apps, schema_editor):
    """Enveloppe chaque corps HTML dans un bloc « paragraphe »."""
    Document = apps.get_model("documents", "DocumentRedige")
    for identifiant, corps in Document.objects.values_list("pk", "corps"):
        texte = (corps or "").strip()
        if not texte or texte.startswith("["):
            # Déjà converti, ou vide : on n'y touche pas. Une migration doit
            # pouvoir être rejouée sans empiler les enveloppes.
            continue
        Document.objects.filter(pk=identifiant).update(
            corps=json.dumps(
                [{"type": "paragraphe", "value": texte, "id": str(uuid.uuid4())}],
                ensure_ascii=False,
            )
        )


def blocs_vers_html(apps, schema_editor):
    """Retour en arrière : on recolle les paragraphes, on perd le reste.

    Un tableau ou un encadré n'a pas d'équivalent en HTML libre assaini. La
    marche arrière est donc **dégradante**, et le dit plutôt que de faire
    croire à une réversibilité complète.
    """
    Document = apps.get_model("documents", "DocumentRedige")
    for identifiant, corps in Document.objects.values_list("pk", "corps"):
        try:
            blocs = json.loads(corps or "[]")
        except (TypeError, ValueError):
            continue
        html = "".join(b.get("value", "") for b in blocs if b.get("type") == "paragraphe")
        Document.objects.filter(pk=identifiant).update(corps=html)


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0004_suivi_generation_pdf"),
    ]

    operations = [
        migrations.RunPython(html_vers_blocs, blocs_vers_html),
        migrations.AlterField(
            model_name="documentredige",
            name="corps",
            field=wagtail.fields.StreamField(
                [("paragraphe", 0), ("tableau", 5), ("encadre", 9), ("icone", 12), ("saut_de_page", 13)],
                blank=True,
                block_lookup={
                    0: ("apps.documents.blocs.ParagrapheBlock", (), {}),
                    1: ("wagtail.blocks.CharBlock", (), {"label": "Texte"}),
                    2: ("wagtail.blocks.DecimalBlock", (), {"label": "Nombre", "required": False}),
                    3: ("wagtail.blocks.DateBlock", (), {"label": "Date", "required": False}),
                    4: (
                        "wagtail.blocks.RichTextBlock",
                        (),
                        {"features": ["bold", "italic", "link"], "required": False},
                    ),
                    5: (
                        "wagtail.contrib.typed_table_block.blocks.TypedTableBlock",
                        [[("texte", 1), ("nombre", 2), ("date", 3), ("paragraphe", 4)]],
                        {"required": False},
                    ),
                    6: ("wagtail.blocks.CharBlock", (), {"label": "Titre", "max_length": 140, "required": False}),
                    7: (
                        "wagtail.blocks.RichTextBlock",
                        (),
                        {"features": ["bold", "italic", "ol", "ul", "link"], "label": "Texte"},
                    ),
                    8: (
                        "wagtail.blocks.ChoiceBlock",
                        [],
                        {
                            "choices": [
                                ("information", "Information"),
                                ("avertissement", "Avertissement"),
                                ("mention_legale", "Mention légale"),
                            ],
                            "label": "Tonalité",
                        },
                    ),
                    9: ("wagtail.blocks.StructBlock", [[("titre", 6), ("texte", 7), ("tonalite", 8)]], {}),
                    10: (
                        "wagtail.blocks.ChoiceBlock",
                        [],
                        {
                            "choices": [
                                ("calendrier", "Calendrier"),
                                ("horloge", "Horloge"),
                                ("lieu", "Lieu"),
                                ("telephone", "Téléphone"),
                                ("courriel", "Courriel"),
                                ("piece_jointe", "Pièce jointe"),
                                ("attention", "Attention"),
                                ("valide", "Validé"),
                            ],
                            "label": "Pictogramme",
                        },
                    ),
                    11: ("wagtail.blocks.CharBlock", (), {"label": "Texte", "max_length": 250}),
                    12: ("wagtail.blocks.StructBlock", [[("icone", 10), ("texte", 11)]], {}),
                    13: ("apps.documents.blocs.SautDePageBlock", (), {}),
                },
                verbose_name="Corps du document",
            ),
        ),
    ]
