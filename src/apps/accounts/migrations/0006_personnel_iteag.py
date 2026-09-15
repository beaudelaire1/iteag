"""Ouvre les comptes nominatifs du personnel et referme ceux de démonstration.

Viviane Foucan (secrétariat), Alain Nisus (enseignant) et Patricia Alphonse
(administration) reçoivent chacun un compte et, quand leur adresse est connue,
un lien pour choisir leur mot de passe. Tout compte du personnel portant encore
le mot de passe de démonstration publié dans le dépôt le perd.

La logique vit dans apps/administration/services/personnel.py, où elle est
testée ; la migration n'est que le moyen de l'exécuter sur la base en service.
Elle travaille donc avec les vrais modèles, et ne fait rien sur une base sans
arborescence Wagtail — les tests, une installation neuve — où ces comptes
fausseraient tout décompte de destinataires. Pour une installation neuve :
« python manage.py ouvrir_comptes_personnel ».
"""

from django.db import migrations


def ouvrir_les_comptes(apps, schema_editor):
    if not apps.get_model("website", "HomePage").objects.exists():
        return

    from apps.administration.services.personnel import installer_personnel_iteag

    installer_personnel_iteag()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_user_nom_autorite_signature_and_more"),
        ("formations", "0004_bibliographie_cours"),
        ("website", "0019_destinataire_contact_secretariat"),
    ]

    operations = [
        migrations.RunPython(ouvrir_les_comptes, migrations.RunPython.noop),
    ]
