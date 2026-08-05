import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("documents", "0003_documentredige_donnees")]

    operations = [
        migrations.AddField(
            model_name="documentadministratif",
            name="statut_generation",
            field=models.CharField(
                choices=[
                    ("aucun", "Non demandé"),
                    ("en_attente", "En attente"),
                    ("en_cours", "En cours"),
                    ("pret", "Prêt"),
                    ("echec", "Échec"),
                ],
                default="aucun",
                max_length=16,
                verbose_name="État de la génération PDF",
            ),
        ),
        migrations.AddField(
            model_name="documentadministratif",
            name="erreur_generation",
            field=models.CharField(blank=True, max_length=300, verbose_name="Erreur de génération"),
        ),
        migrations.AddField(
            model_name="documentadministratif",
            name="jeton_generation",
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
        migrations.AddField(
            model_name="documentredige",
            name="statut_generation",
            field=models.CharField(
                choices=[
                    ("aucun", "Non demandé"),
                    ("en_attente", "En attente"),
                    ("en_cours", "En cours"),
                    ("pret", "Prêt"),
                    ("echec", "Échec"),
                ],
                default="aucun",
                max_length=16,
                verbose_name="État de la génération PDF",
            ),
        ),
        migrations.AddField(
            model_name="documentredige",
            name="erreur_generation",
            field=models.CharField(blank=True, max_length=300, verbose_name="Erreur de génération"),
        ),
        migrations.AddField(
            model_name="documentredige",
            name="jeton_generation",
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
    ]
