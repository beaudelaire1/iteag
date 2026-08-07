from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("admissions", "0006_separer_lots_pieces_herites"),
    ]

    operations = [
        migrations.AlterField(
            model_name="piecedemandee",
            name="precisions",
            field=models.TextField(blank=True, verbose_name="Précisions propres à la pièce"),
        ),
    ]
