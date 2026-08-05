"""Crée le groupe qui ouvre la médiathèque, et y rattache les comptes existants.

Sans ce passage, la fonction n'existerait que pour les comptes créés après la
mise en service : les quatre personnes déjà en poste auraient vu apparaître un
bouton d'insertion d'image ouvrant une fenêtre vide.

Elle dépend des migrations de Wagtail parce qu'elle lit leurs permissions : les
créer avant qu'elles existent produirait un groupe sans droits, donc un accès
refusé sans rien pour l'expliquer.
"""

from django.db import migrations

from apps.accounts.services.droits_editoriaux import NOM_GROUPE, ROLES_CONCERNES, assurer_le_groupe


def poser_le_groupe(apps, schema_editor):
    Groupe = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    Utilisateur = apps.get_model("accounts", "User")

    groupe = assurer_le_groupe(Groupe, Permission)
    for compte in Utilisateur.objects.filter(role__in=ROLES_CONCERNES, is_active=True):
        compte.groups.add(groupe)


def retirer_le_groupe(apps, schema_editor):
    """Le groupe s'en va ; les comptes restent, seulement détachés."""
    apps.get_model("auth", "Group").objects.filter(name=NOM_GROUPE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_user_adresse_user_code_postal_and_more"),
        ("wagtailimages", "0001_initial"),
        ("wagtailadmin", "0001_create_admin_access_permissions"),
    ]

    operations = [migrations.RunPython(poser_le_groupe, retirer_le_groupe)]
