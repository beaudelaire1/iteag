"""
Passage du stockage à la diffusion — ADR-005.

Le champ est **renommé**, pas supprimé puis recréé comme le proposait
l'autodétection : un remove/add perdrait le fournisseur de chaque vidéo déjà
enregistrée, en silence et sans retour possible.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("elearning", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="videoasset",
            old_name="backend_stockage",
            new_name="fournisseur",
        ),
        migrations.AlterField(
            model_name="videoasset",
            name="fournisseur",
            field=models.CharField(
                choices=[
                    ("local", "Fichier local (développement)"),
                    ("s3", "S3 privé (adresse présignée)"),
                    ("bunny", "Bunny Stream (adresse signée)"),
                    ("vimeo", "Vimeo (contenu public)"),
                    ("youtube", "YouTube (contenu public)"),
                ],
                default="local",
                max_length=20,
                verbose_name="Fournisseur de diffusion",
            ),
        ),
        migrations.AlterField(
            model_name="videoasset",
            name="cle_stockage",
            field=models.CharField(
                help_text="Clé de stockage interne, ou identifiant de la vidéo chez le fournisseur externe",
                max_length=500,
                unique=True,
                verbose_name="Clé ou identifiant",
            ),
        ),
    ]
