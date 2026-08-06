# Generated manually for the assiduité vertical slice.

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0009_proposition_enseignement"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SeanceCours",
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
                ("date", models.DateField()),
                ("heure_debut", models.TimeField(verbose_name="Heure de début")),
                ("heure_fin", models.TimeField(verbose_name="Heure de fin")),
                (
                    "libelle",
                    models.CharField(
                        blank=True,
                        help_text="Facultatif : matin, examen, atelier…",
                        max_length=150,
                        verbose_name="Intitulé",
                    ),
                ),
                (
                    "cloturee",
                    models.BooleanField(
                        default=False,
                        help_text="Une feuille clôturée n'est plus modifiable avant sa réouverture.",
                        verbose_name="Feuille clôturée",
                    ),
                ),
                (
                    "cours_session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="seances_assiduite",
                        to="academics.coursdesession",
                        verbose_name="Cours de session",
                    ),
                ),
                (
                    "cree_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="seances_assiduite_creees",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Séance de cours",
                "verbose_name_plural": "Séances de cours",
                "ordering": ["-date", "-heure_debut"],
                "indexes": [
                    models.Index(
                        fields=["cours_session", "-date"],
                        name="academics_s_cours_s_8752db_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("cours_session", "date", "heure_debut"),
                        name="seance_assiduite_unique",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(heure_fin__gt=models.F("heure_debut")),
                        name="seance_assiduite_fin_apres_debut",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Presence",
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
                (
                    "statut",
                    models.CharField(
                        choices=[
                            ("present", "Présent"),
                            ("absent", "Absent"),
                            ("retard", "En retard"),
                            ("excuse", "Absence excusée"),
                        ],
                        default="present",
                        max_length=20,
                    ),
                ),
                (
                    "commentaire",
                    models.CharField(
                        blank=True,
                        help_text="Motif, durée du retard ou précision utile.",
                        max_length=300,
                        verbose_name="Commentaire",
                    ),
                ),
                (
                    "etudiant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="presences",
                        to="academics.profiletudiant",
                    ),
                ),
                (
                    "modifie_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="presences_modifiees",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "saisi_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="presences_saisies",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "seance",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="presences",
                        to="academics.seancecours",
                    ),
                ),
            ],
            options={
                "verbose_name": "Présence",
                "verbose_name_plural": "Présences",
                "ordering": ["seance__date", "etudiant__utilisateur__last_name"],
                "indexes": [
                    models.Index(
                        fields=["etudiant", "statut"],
                        name="academics_p_etudian_5abdb4_idx",
                    ),
                    models.Index(
                        fields=["seance", "statut"],
                        name="academics_p_seance__b0148b_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("seance", "etudiant"),
                        name="presence_unique_par_seance_et_etudiant",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="HistoriquePresence",
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
                (
                    "ancien_statut",
                    models.CharField(
                        choices=[
                            ("present", "Présent"),
                            ("absent", "Absent"),
                            ("retard", "En retard"),
                            ("excuse", "Absence excusée"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "nouveau_statut",
                    models.CharField(
                        choices=[
                            ("present", "Présent"),
                            ("absent", "Absent"),
                            ("retard", "En retard"),
                            ("excuse", "Absence excusée"),
                        ],
                        max_length=20,
                    ),
                ),
                ("ancien_commentaire", models.CharField(blank=True, max_length=300)),
                ("nouveau_commentaire", models.CharField(blank=True, max_length=300)),
                (
                    "modifie_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="corrections_assiduite",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "presence",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="historique",
                        to="academics.presence",
                    ),
                ),
            ],
            options={
                "verbose_name": "Correction de présence",
                "verbose_name_plural": "Corrections de présence",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["presence", "-created_at"],
                        name="academics_h_presenc_f6b852_idx",
                    )
                ],
            },
        ),
    ]
