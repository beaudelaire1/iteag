from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0005_rename_suspension_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="noticebibliographique",
            name="nombre_exemplaires",
            field=models.PositiveIntegerField(default=1, verbose_name="Nombre d'exemplaires"),
        ),
    ]
