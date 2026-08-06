import importlib
from unittest.mock import MagicMock


def test_migration_0007_convertit_un_stream_value_en_html():
    migration_blocs = importlib.import_module("apps.documents.migrations.0006_bloc_image")
    migration_texte = importlib.import_module("apps.documents.migrations.0007_corps_en_texte_riche")
    champ_stream = migration_blocs.Migration.operations[0].field
    corps = champ_stream.to_python(
        [
            {
                "type": "paragraphe",
                "value": "<p>Texte conserve</p>",
                "id": "11111111-1111-1111-1111-111111111111",
            },
            {
                "type": "saut_de_page",
                "value": None,
                "id": "22222222-2222-2222-2222-222222222222",
            },
        ]
    )
    document = MagicMock()
    document.objects.values_list.return_value = [(7, corps)]
    apps = MagicMock()
    apps.get_model.return_value = document

    migration_texte.blocs_vers_html(apps, None)

    document.objects.filter.assert_called_once_with(pk=7)
    document.objects.filter.return_value.update.assert_called_once_with(corps="<p>Texte conserve</p>")
