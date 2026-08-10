from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("paiements", "0002_reglementinscription"),
    ]

    operations = [
        migrations.AddField(
            model_name="reglement",
            name="derniere_erreur_livraison",
            field=models.TextField(blank=True, verbose_name="Dernier échec de livraison"),
        ),
        migrations.AddField(
            model_name="reglement",
            name="livraison_signalee",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name="reglement",
            name="tentatives_livraison",
            field=models.PositiveSmallIntegerField(
                default=0,
                editable=False,
                verbose_name="Tentatives de rattrapage",
            ),
        ),
    ]
