from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0009_contenu_actualite_temoignage_etudiant"),
    ]

    operations = [
        migrations.AlterField(
            model_name="temoignageetudiant",
            name="statut",
            field=models.CharField(
                choices=[
                    ("en_attente", "En attente"),
                    ("publie", "Publié"),
                    ("refuse", "Refusé"),
                    ("retire", "Retiré"),
                ],
                db_index=True,
                default="en_attente",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="temoignageetudiant",
            name="texte",
            field=models.TextField(max_length=6000, verbose_name="Témoignage"),
        ),
        migrations.AddField(
            model_name="temoignageetudiant",
            name="photo",
            field=models.ImageField(
                blank=True,
                help_text="Photo facultative choisie spécifiquement pour l'affichage public du témoignage.",
                upload_to="temoignages/%Y/%m/",
                verbose_name="Photo du témoignage",
            ),
        ),
    ]
