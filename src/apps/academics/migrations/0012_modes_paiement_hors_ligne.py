from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("academics", "0011_presenceetudiant")]

    operations = [
        migrations.AlterField(
            model_name="paiement",
            name="mode",
            field=models.CharField(
                choices=[
                    ("virement", "Virement"),
                    ("especes", "Espèces sur place"),
                ],
                max_length=20,
            ),
        ),
    ]
