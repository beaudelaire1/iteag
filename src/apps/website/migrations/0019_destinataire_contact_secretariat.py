"""Adresse par défaut du formulaire de contact : la boîte réelle du secrétariat.

Le domaine iteag.org n'ayant aucun enregistrement MX, l'ancienne adresse par
défaut ne recevait rien. La correction des données déjà enregistrées — la page
en service et ses révisions — est faite par la migration 0020, qui efface
l'ancienne adresse de toute la base.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0018_temoignages_ancien_site"),
        ("wagtailcore", "0094_alter_page_locale"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contactpage",
            name="destinataire",
            field=models.EmailField(
                default="secretariat.iteag@gmail.com",
                help_text="Adresse qui recevra les messages du formulaire.",
                max_length=254,
                verbose_name="Email destinataire",
            ),
        ),
    ]
