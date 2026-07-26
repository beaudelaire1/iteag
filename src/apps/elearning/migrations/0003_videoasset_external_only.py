from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("elearning", "0002_fournisseur_diffusion"),
    ]

    operations = [
        migrations.AlterField(
            model_name="videoasset",
            name="fournisseur",
            field=models.CharField(
                choices=[
                    ("bunny", "Bunny Stream (adresse signée)"),
                    ("vimeo", "Vimeo (contenu public)"),
                    ("youtube", "YouTube (contenu public)"),
                ],
                default="bunny",
                max_length=20,
                verbose_name="Fournisseur de diffusion",
            ),
        ),
    ]
