"""Renvoie son invitation à Alain Nisus, et à lui seul.

Le 21 septembre 2026, il a demandé un lien par « Mot de passe oublié » sans
rien recevoir. Ce formulaire se tait quand l'adresse saisie ne correspond à
aucun compte ; l'invitation part, elle, vers l'adresse que porte son compte.
Le nouveau lien remplace le précédent.

Même garde que 0006 : rien sur une base sans arborescence Wagtail.
"""

from django.db import migrations

IDENTIFIANT = "alain.nisus"


def renvoyer_a_alain_nisus(apps, schema_editor):
    if not apps.get_model("website", "HomePage").objects.exists():
        return

    from apps.administration.services.personnel import renvoyer_invitation

    renvoyer_invitation(IDENTIFIANT)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_nettoyer_adresses_iteag"),
    ]

    operations = [
        migrations.RunPython(renvoyer_a_alain_nisus, migrations.RunPython.noop),
    ]
