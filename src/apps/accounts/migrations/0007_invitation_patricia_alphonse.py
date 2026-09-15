"""Renseigne l'adresse de Patricia Alphonse et lui envoie son invitation.

La migration 0006 a ouvert son compte d'administration sans adresse, faute de
la connaître : aucun lien n'avait pu partir, et le secrétariat ne peut pas
modifier un compte d'administration depuis l'interface. L'adresse figure
désormais dans PERSONNEL_ITEAG ; la reprise suit la même règle que 0006 — un
compte dont l'adresse a déjà été corrigée à la main n'est pas réécrit.

Même garde que 0006 : rien sur une base sans arborescence Wagtail.
"""

from django.db import migrations

IDENTIFIANT = "patricia.alphonse"


def inviter_patricia_alphonse(apps, schema_editor):
    if not apps.get_model("website", "HomePage").objects.exists():
        return

    from apps.administration.services.personnel import PERSONNEL_ITEAG, ouvrir_compte

    ouvrir_compte(next(membre for membre in PERSONNEL_ITEAG if membre.identifiant == IDENTIFIANT))


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_personnel_iteag"),
    ]

    operations = [
        migrations.RunPython(inviter_patricia_alphonse, migrations.RunPython.noop),
    ]
