"""Nettoie les anciennes adresses @iteag.org portées par les comptes.

Le domaine iteag.org n'héberge pas de messagerie. Les anciennes commandes de
peuplement ont pourtant créé des adresses comme direction@iteag.org et des
adresses synthétiques pour les enseignants. Elles peuvent rester en base même
après correction du code, car get_or_create ne réécrit pas les valeurs déjà
stockées.

Les comptes génériques de démonstration sont désactivés sans condition de mot
de passe : ils ont été remplacés par les comptes nominatifs du personnel.
Les autres comptes restent actifs mais perdent seulement l'adresse fictive.
"""

from django.db import migrations

DOMAINE_SANS_MX = "@iteag.org"
COMPTES_DEMONSTRATION = ("secretariat_iteag", "direction_iteag")


def nettoyer_adresses_historiques(apps, schema_editor):
    User = apps.get_model("accounts", "User")

    User.objects.filter(email__iendswith=DOMAINE_SANS_MX).update(email="")
    User.objects.filter(username__in=COMPTES_DEMONSTRATION).update(
        email="",
        is_active=False,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_invitations_illustrees"),
    ]

    operations = [
        migrations.RunPython(nettoyer_adresses_historiques, migrations.RunPython.noop),
    ]
