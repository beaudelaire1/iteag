import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0010_assiduite"),
        ("paiements", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReglementInscription",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        editable=False,
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "demande",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reglement_en_ligne",
                        to="academics.demandeinscriptioncours",
                        verbose_name="Demande d'inscription",
                    ),
                ),
                (
                    "reglement",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inscription_associee",
                        to="paiements.reglement",
                        verbose_name="Règlement",
                    ),
                ),
            ],
            options={
                "verbose_name": "Règlement d'inscription",
                "verbose_name_plural": "Règlements d'inscription",
                "ordering": ["-created_at"],
            },
        ),
    ]
