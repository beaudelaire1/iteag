import uuid

import django.db.models.deletion
import wagtail.fields
from django.conf import settings
from django.db import migrations, models

import apps.website.editorial


def migrer_corps_actualites(apps, schema_editor):
    NewsPage = apps.get_model("website", "NewsPage")
    ContenuActualite = apps.get_model("website", "ContenuActualite")

    for actualite in NewsPage.objects.all().iterator():
        corps = actualite.body or ""
        contenu = []
        if corps.strip():
            contenu = [{"type": "texte", "value": corps, "id": str(uuid.uuid4())}]
        ContenuActualite.objects.create(actualite_id=actualite.pk, contenu=contenu)


def annuler_migration_corps(apps, schema_editor):
    apps.get_model("website", "ContenuActualite").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("website", "0008_alter_contentpage_body_alter_faqpage_questions_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContenuActualite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "contenu",
                    wagtail.fields.StreamField(
                        apps.website.editorial.CorpsActualiteBlock(),
                        blank=True,
                        use_json_field=True,
                        verbose_name="Contenu structuré",
                    ),
                ),
                (
                    "actualite",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contenu_structure",
                        to="website.newspage",
                    ),
                ),
            ],
            options={
                "verbose_name": "Contenu structuré d'actualité",
                "verbose_name_plural": "Contenus structurés d'actualités",
            },
        ),
        migrations.CreateModel(
            name="TemoignageEtudiant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nom_affiche", models.CharField(max_length=160, verbose_name="Nom affiché")),
                ("promotion", models.CharField(blank=True, max_length=160, verbose_name="Promotion / parcours")),
                ("texte", models.TextField(max_length=2000, verbose_name="Témoignage")),
                (
                    "consentement_publication",
                    models.BooleanField(default=False, verbose_name="Consentement à la publication"),
                ),
                (
                    "statut",
                    models.CharField(
                        choices=[("en_attente", "En attente"), ("publie", "Publié"), ("refuse", "Refusé")],
                        db_index=True,
                        default="en_attente",
                        max_length=20,
                    ),
                ),
                ("motif_refus", models.CharField(blank=True, max_length=500, verbose_name="Motif du refus")),
                ("soumis_le", models.DateTimeField(auto_now_add=True)),
                ("modifie_le", models.DateTimeField(auto_now=True)),
                ("valide_le", models.DateTimeField(blank=True, null=True)),
                (
                    "etudiant",
                    models.OneToOneField(
                        blank=True,
                        limit_choices_to={"role": "etudiant"},
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="temoignage_iteag",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Étudiant",
                    ),
                ),
                (
                    "valide_par",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="temoignages_valides",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Validé par",
                    ),
                ),
            ],
            options={
                "verbose_name": "Témoignage étudiant",
                "verbose_name_plural": "Témoignages étudiants",
                "ordering": ["-soumis_le"],
            },
        ),
        migrations.RunPython(migrer_corps_actualites, annuler_migration_corps),
    ]
