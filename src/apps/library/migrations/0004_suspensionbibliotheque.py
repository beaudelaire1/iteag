import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0003_emprunt_bibliotheque"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SuspensionBibliotheque",
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
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("jours_retard", models.PositiveIntegerField(verbose_name="Jours de retard")),
                ("jours_suspension", models.PositiveIntegerField(verbose_name="Jours de suspension")),
                ("date_debut", models.DateField(verbose_name="Début de suspension")),
                ("date_fin", models.DateField(verbose_name="Fin de suspension")),
                ("levee_le", models.DateTimeField(blank=True, null=True, verbose_name="Levée le")),
                ("motif_levee", models.TextField(blank=True, verbose_name="Motif de la levée")),
                (
                    "emprunt",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sanction",
                        to="library.emprunt",
                        verbose_name="Emprunt à l'origine",
                    ),
                ),
                (
                    "emprunteur",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="suspensions_bibliotheque",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Emprunteur",
                    ),
                ),
                (
                    "levee_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="suspensions_bibliotheque_levees",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Levée par",
                    ),
                ),
            ],
            options={
                "verbose_name": "Suspension de bibliothèque",
                "verbose_name_plural": "Suspensions de bibliothèque",
                "ordering": ["-date_debut", "-created_at"],
                "indexes": [
                    models.Index(fields=["emprunteur", "date_fin"], name="library_sus_emprunt_78ad3c_idx"),
                    models.Index(fields=["levee_le", "date_fin"], name="library_sus_levee_l_346ed8_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(jours_retard__gt=0),
                        name="library_suspension_retard_positif",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(jours_suspension__gt=0),
                        name="library_suspension_duree_positive",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(date_fin__gte=models.F("date_debut")),
                        name="library_suspension_dates_valides",
                    ),
                ],
            },
        ),
    ]
