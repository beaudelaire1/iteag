"""Retire les tirets des numéros étudiants : « ETU-2026-001 » → « ETU2026001 ».

Un numéro se dicte au téléphone, se recopie sur un formulaire papier et se
cherche dans une barre de recherche. Chaque séparateur y ajoute une question
sans réponse évidente — un tiret ou deux, avant l'année ou après — et une
recherche qui échoue sans dire pourquoi.

La reprise inverse est fournie : elle reconstitue la forme séparée pour les
seuls numéros qui suivent le gabarit « ETU » + 4 chiffres + 3 chiffres.
"""

import re

from django.db import migrations

FORME_JOINTE = re.compile(r"^ETU(\d{4})(\d{3})$")
FORME_SEPAREE = re.compile(r"^ETU-(\d{4})-(\d{3})$")


def _reecrire(profils, motif, remplacement):
    a_ecrire = []
    for profil in profils:
        correspondance = motif.match(profil.numero_etudiant or "")
        if correspondance:
            profil.numero_etudiant = remplacement.format(*correspondance.groups())
            a_ecrire.append(profil)
    return a_ecrire


def joindre(apps, schema_editor):
    ProfilEtudiant = apps.get_model("academics", "ProfilEtudiant")
    modifies = _reecrire(ProfilEtudiant.objects.all(), FORME_SEPAREE, "ETU{0}{1}")
    ProfilEtudiant.objects.bulk_update(modifies, ["numero_etudiant"])


def separer(apps, schema_editor):
    ProfilEtudiant = apps.get_model("academics", "ProfilEtudiant")
    modifies = _reecrire(ProfilEtudiant.objects.all(), FORME_JOINTE, "ETU-{0}-{1}")
    ProfilEtudiant.objects.bulk_update(modifies, ["numero_etudiant"])


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0007_merge_20260729_1650"),
    ]

    operations = [
        migrations.RunPython(joindre, separer),
    ]
