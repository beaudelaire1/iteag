import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0013_completer_formulaire_contact"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="article",
            name="auteur",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="articles",
                to="formations.professeur",
            ),
        ),
        migrations.AddField(
            model_name="article",
            name="auteur_etudiant",
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={"role": "etudiant"},
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="articles_rediges",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Auteur étudiant",
            ),
        ),
        migrations.AddIndex(
            model_name="article",
            index=models.Index(fields=["auteur_etudiant", "statut"], name="website_ar_auteur__30c162_idx"),
        ),
        migrations.AddConstraint(
            model_name="article",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("auteur__isnull", False), ("auteur_etudiant__isnull", True))
                    | models.Q(("auteur__isnull", True), ("auteur_etudiant__isnull", False))
                ),
                name="article_exactement_un_auteur",
            ),
        ),
    ]
