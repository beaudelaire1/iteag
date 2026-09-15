"""Adresse le formulaire de contact à la boîte réelle du secrétariat.

« secretariat@iteag.org » était le défaut du champ, et donc la valeur de la page
en service. Le domaine iteag.org n'ayant aucun enregistrement MX, chaque message
de contact partait vers une boîte inexistante. La page et sa dernière révision
sont corrigées ensemble : corriger la seule page laisserait la prochaine
publication depuis l'éditeur rétablir l'ancienne adresse. Une adresse choisie
par un rédacteur, quelle qu'elle soit, est laissée telle quelle.
"""

from django.db import migrations, models

ANCIENNE = "secretariat@iteag.org"
NOUVELLE = "secretariat.iteag@gmail.com"


def corriger_le_destinataire(apps, schema_editor):
    ContactPage = apps.get_model("website", "ContactPage")
    Revision = apps.get_model("wagtailcore", "Revision")

    pages = list(ContactPage.objects.filter(destinataire__iexact=ANCIENNE).values_list("pk", flat=True))
    if not pages:
        return
    ContactPage.objects.filter(pk__in=pages).update(destinataire=NOUVELLE)

    for revision in Revision.objects.filter(object_id__in=[str(pk) for pk in pages]):
        contenu = revision.content or {}
        if str(contenu.get("destinataire", "")).casefold() == ANCIENNE:
            contenu["destinataire"] = NOUVELLE
            revision.content = contenu
            revision.save(update_fields=["content"])


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
                default=NOUVELLE,
                help_text="Adresse qui recevra les messages du formulaire.",
                max_length=254,
                verbose_name="Email destinataire",
            ),
        ),
        migrations.RunPython(corriger_le_destinataire, migrations.RunPython.noop),
    ]
