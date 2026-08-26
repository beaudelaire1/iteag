from django.db import migrations, models


def convertir_anciens_acces(apps, schema_editor):
    ModuleFormation = apps.get_model("elearning", "ModuleFormation")
    InscriptionModule = apps.get_model("elearning", "InscriptionModule")
    ModuleFormation.objects.filter(politique_acces="achat").update(politique_acces="sur_octroi")
    InscriptionModule.objects.filter(source="achat").update(source="octroi_manuel")


class Migration(migrations.Migration):
    dependencies = [("elearning", "0006_ressourcelecon")]

    operations = [
        migrations.RunPython(convertir_anciens_acces, migrations.RunPython.noop),
        migrations.RemoveField(model_name="moduleformation", name="prix_ttc"),
        migrations.RemoveField(model_name="moduleformation", name="taux_tva"),
        migrations.AlterField(
            model_name="moduleformation",
            name="politique_acces",
            field=models.CharField(
                choices=[
                    ("public", "Public — accessible à tous"),
                    ("authentifie", "Réservé aux comptes connectés"),
                    ("inscrit_parcours", "Réservé aux inscrits du parcours"),
                    ("sur_octroi", "Sur octroi individuel"),
                ],
                default="inscrit_parcours",
                max_length=20,
                verbose_name="Politique d'accès",
            ),
        ),
        migrations.AlterField(
            model_name="inscriptionmodule",
            name="source",
            field=models.CharField(
                choices=[
                    ("parcours", "Parcours"),
                    ("session", "Session académique"),
                    ("octroi_manuel", "Octroi manuel"),
                    ("libre", "Accès libre"),
                ],
                default="parcours",
                max_length=20,
            ),
        ),
    ]
