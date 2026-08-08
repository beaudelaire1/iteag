import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0010_assiduite"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PresenceEtudiant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "statut",
                    models.CharField(
                        choices=[
                            ("present", "Présent"),
                            ("retard", "En retard"),
                            ("absent_justifie", "Absent (justifié)"),
                            ("absent_non_justifie", "Absent (non justifié)"),
                        ],
                        default="present",
                        max_length=20,
                    ),
                ),
                ("commentaire", models.TextField(blank=True, verbose_name="Remarque / justificatif")),
                (
                    "cours_session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="presences_etudiants",
                        to="academics.coursdesession",
                    ),
                ),
                (
                    "etudiant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="presences_etudiants",
                        to="academics.profiletudiant",
                    ),
                ),
                (
                    "saisi_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="presences_etudiants_saisies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Présence / Assiduité",
                "verbose_name_plural": "Présences / Assiduités",
                "ordering": ["etudiant__utilisateur__last_name", "etudiant__utilisateur__first_name"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("cours_session", "etudiant"), name="presence_unique_par_cours_session_etudiant"
                    )
                ],
            },
        ),
    ]
