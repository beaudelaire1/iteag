from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0015_reparer_profils_etudiants_manquants"),
    ]

    operations = [
        migrations.AlterField(
            model_name="paiement",
            name="mode",
            field=models.CharField(
                choices=[
                    ("virement", "Virement"),
                    ("especes", "Espèces sur place"),
                    ("cheque", "Chèque"),
                ],
                max_length=20,
            ),
        ),
    ]
