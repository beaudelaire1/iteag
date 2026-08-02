from django.db import migrations

COLONNES_DEVOIR = ("date_limite_reportee", "depot_tardif", "devoir")


def ajouter_colonnes_manquantes(apps, schema_editor):
    """Répare les bases passées par la branche supprimée sans doubler les colonnes."""

    Evaluation = apps.get_model("lms", "Evaluation")
    table = Evaluation._meta.db_table
    with schema_editor.connection.cursor() as curseur:
        presentes = {
            colonne.name for colonne in schema_editor.connection.introspection.get_table_description(curseur, table)
        }

    for nom in COLONNES_DEVOIR:
        champ = Evaluation._meta.get_field(nom)
        if champ.column in presentes:
            continue

        if schema_editor.connection.vendor == "sqlite":
            # SQLite reconstruit toute la table dans ``add_field``. Sur cette
            # base désynchronisée, la reconstruction essaierait de recopier
            # aussi les deux autres colonnes encore absentes. Un ajout SQL
            # nullable/avec valeur par défaut est sûr et conserve les lignes.
            table_sql = schema_editor.quote_name(table)
            colonne_sql = schema_editor.quote_name(champ.column)
            if nom == "date_limite_reportee":
                definition = "datetime NULL"
            elif nom == "depot_tardif":
                definition = "bool NOT NULL DEFAULT 0"
            else:
                table_devoir = schema_editor.quote_name(apps.get_model("lms", "Devoir")._meta.db_table)
                definition = (
                    f"bigint NULL REFERENCES {table_devoir} "
                    f"({schema_editor.quote_name('id')}) DEFERRABLE INITIALLY DEFERRED"
                )
            schema_editor.execute(f"ALTER TABLE {table_sql} ADD COLUMN {colonne_sql} {definition}")
        else:
            schema_editor.add_field(Evaluation, champ)
        presentes.add(champ.column)


class Migration(migrations.Migration):
    dependencies = [
        ("lms", "0005_merge_20260729_1650"),
    ]

    operations = [
        migrations.RunPython(ajouter_colonnes_manquantes, migrations.RunPython.noop),
    ]
