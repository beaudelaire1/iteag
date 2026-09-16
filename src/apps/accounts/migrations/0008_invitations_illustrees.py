"""Renvoie l'invitation, désormais illustrée, au secrétariat et à l'administration.

Les premières invitations expliquaient l'enrôlement d'Authenticator en quatre
lignes de texte. Elles portent maintenant les captures des écrans à franchir.
Seuls les comptes à second facteur qui ne se sont encore jamais connectés les
reçoivent de nouveau : les autres ont déjà passé l'étape.

Même garde que 0006 : rien sur une base sans arborescence Wagtail.
"""

from django.db import migrations


def renvoyer(apps, schema_editor):
    if not apps.get_model("website", "HomePage").objects.exists():
        return

    from apps.administration.services.personnel import renvoyer_invitations_illustrees

    renvoyer_invitations_illustrees()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_invitation_patricia_alphonse"),
    ]

    operations = [
        migrations.RunPython(renvoyer, migrations.RunPython.noop),
    ]
